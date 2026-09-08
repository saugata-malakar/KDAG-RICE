# RimeTrack Architecture Deep-Dive

RimeTrack is an end-to-end full-duplex voice agent runtime designed to solve **interruption, recovery, and state consistency** during realtime tool-augmented voice conversations.

---

## 1. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Client ["Client Interface / Telephony / Browser"]
        Mic[User Microphone]
        Spk[Speaker Playback]
        HUD[Live Debug HUD & State Stream]
    end

    subgraph Transport ["LiveKit WebRTC Media Server"]
        RTC_In[Inbound Audio Stream]
        RTC_Out[Outbound Audio Stream]
        Data_Chan[Data Channel Events]
    end

    subgraph RimeTrack_Runtime ["RimeTrack Server Worker"]
        VAD[Silero VAD / Turn Detector]
        ASR[Deepgram Nova-3 STT]
        Fence["GenerationFence (Core Authority)"]
        Ledger["ConversationStateManager (Heard-Text Ledger)"]
        Executor["ToolExecutor (Cancellable / Uncancellable)"]
        LLM["OpenAI GPT-4o-mini"]
        Rime_TTS["Rime TTS Engine (WebSocket coda/astra)"]
        Log[Structured JSONL Event Log]
    end

    Mic -->|WebRTC Audio| RTC_In
    RTC_In --> VAD
    VAD -->|Voice Activity| ASR
    ASR -->|Final Transcript| Ledger
    ASR -->|User Speech Detected| Fence

    Fence -->|Advance / Invalidate G_id| Ledger
    Fence -->|Gate Output| Executor
    Fence -->|Gate LLM Token Stream| LLM

    LLM -->|Stream Text| Rime_TTS
    Rime_TTS -->|Stream Audio Chunks + Word Timestamps| RTC_Out
    RTC_Out -->|WebRTC Audio| Spk

    Executor -->|Fenced Tool Result| Ledger
    Fence -->|Emit Events| Log
    Log -->|Telemetry| Data_Chan
    Data_Chan --> HUD
```

---

## 2. The Core Problem: The Naive Baseline Failure

In standard voice agents (e.g., standard LangChain/LiveKit pipelines without fencing), interruptions trigger audio mute, but background execution continues unchecked:

```
[Agent Turn 1 (G1)]
User: "Book table for 7pm."
Agent: "Sure, reserving a table for 7pm at your usual place..."
LLM finishes generating: 10 words.
Tool called: reserve_table(time="7pm")  [Takes 500ms]

-- BARGE-IN --
User: "Wait, actually make it 8pm!"
Audio stops locally after word 3 ("Sure, reserving a").

-- NAIVE FAILURE --
1. Context Poisoning: The next LLM call receives the full un-spoken turn: "Sure, reserving a table for 7pm at your usual place...". The agent hallucinates that the 7pm booking was confirmed and understood by the user.
2. Tool Bleed: 300ms later, reserve_table(time="7pm") finishes and writes to DB, then speaks: "Your 7pm booking is confirmed!" over the user's 8pm request.
```

---

## 3. RimeTrack Solution: Generation Fence & Heard-Text Ledger

### 3.1 Monotonic Generation IDs
Every assistant turn is assigned a monotonically increasing ID (`G1`, `G2`, `G3`, ...).
At every step where data or audio attempts to cross into shared conversation state or playback, it must query `fence.is_current(generation_id)`.

### 3.2 Heard-Text Ledger (`ConversationStateManager`)
Rather than storing what the LLM generated, the ledger records what was **actually played aloud**:
- **WebSocket Native Path (Preferred):** Rime's WebSocket sends per-word `timestamps`. LiveKit's `ChatMessage.interrupted` contains the exact truncated text corresponding to the audio timestamp when the stop signal arrived.
- **Chunk-Flush Fallback Path:** If aligned timestamps are unavailable, RimeTrack's `record_chunk_played()` commits chunks at flush time. When interrupted, `truncate_on_interrupt()` freezes the history to the heard prefix.

### 3.3 Tool Execution Strategies (`ToolExecutor`)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant LiveKit as LiveKit WebRTC
    participant Fence as GenerationFence
    participant Tool as ToolExecutor
    participant ExtAPI as External API / DB

    Note over User, ExtAPI: Cancellable Tool Flow
    User->>LiveKit: "Check my order" (G1)
    LiveKit->>Fence: advance() -> G1
    Fence->>Tool: run_cancellable(order_lookup, gen=G1)
    Tool->>ExtAPI: HTTP GET /order/123
    User->>LiveKit: "Actually cancel that" (Barge-in)
    LiveKit->>Fence: interrupt_current() -> G1 marked Stale, G2 active
    Tool->>Tool: is_stale(G1) == True -> task.cancel()
    Tool-->>ExtAPI: Abort HTTP connection
    Tool->>Fence: Return ToolResult(cancelled=True)

    Note over User, ExtAPI: Uncancellable Tool Flow (Result Fencing)
    User->>LiveKit: "Reserve room 101" (G3)
    LiveKit->>Fence: advance() -> G3
    Fence->>Tool: run_uncancellable(db_insert, gen=G3)
    Tool->>ExtAPI: DB Write in progress...
    User->>LiveKit: "No wait, room 102!" (Barge-in)
    LiveKit->>Fence: interrupt_current() -> G3 marked Stale, G4 active
    ExtAPI-->>Tool: DB Write returns {room: 101, status: "booked"}
    Tool->>Fence: is_stale(G3)? -> TRUE
    Tool->>Tool: Result Quarantined (withheld from LLM context & speech)
    Tool->>LiveKit: Log fenced result, proceed with G4 turn
```

---

## 4. State Machine Lifecycle

```mermaid
state_diagram
    [*] --> Idle: Session Started
    Idle --> Generating: User Speech Finished (ASR Final)
    Generating --> Speaking: Rime WS Audio Stream Starts
    Speaking --> Completed: Normal Turn Completion
    Completed --> Idle: Ready for Next Turn

    Speaking --> Interrupted: User Barge-In Detected
    Generating --> Interrupted: User Barge-In Detected
    Interrupted --> Quarantined: In-flight Tools / LLM fenced
    Quarantined --> Generating: New Turn (G_{n+1}) Grounded in Heard Prefix
```

---

## 5. Rime Integration Specifications

- **Endpoint:** Rime WebSocket Streaming Engine (`wss://users.rime.ai/v1/rime-ws`)
- **Model:** `coda` (Optimized for conversational latency and prosodic nuance)
- **Speaker:** `astra`
- **Language:** `eng`
- **Transport:** WebSocket (`use_websocket=True`), enabling streaming token push, synchronized word alignment timestamps, and server-side buffer flushing on interrupt.
- **Speed Control:** `speed_alpha=1.0` (WebSocket native speed scaling).
