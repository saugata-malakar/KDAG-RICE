# RIME_EVIDENCE.md — Voice Engineering Evidence & Reproducibility Report

**Project:** RimeTrack — Real-Time Interruption Recovery & Tool Fencing for Full-Duplex Voice Agents  
**Hackathon:** DataForge × Rime Hackathon Challenge (September 2026)  
**Active Speech Provider:** Rime TTS over WebSocket (`coda` / `astra` / `eng` / `speed_alpha=1.0`)  
**Repository:** [https://github.com/saugata-malakar/KDAG-RICE](https://github.com/saugata-malakar/KDAG-RICE)  
**Date:** September 2026  

---

## 1. Hard Voice Claims

> **Claim 1 — Context Poisoning Elimination (Heard-Text Grounding)**  
> When a user interrupts an agent mid-utterance at word boundary $k$ of an $N$-word response ($k < N$), the agent's conversation history records **only the first $k$ words** (the heard-text prefix $H(t)$) and **never** the un-spoken suffix $G(t) \setminus H(t)$. All subsequent LLM turns are grounded in $H(t) \subseteq G(t)$, not the full generated text $G(t)$.

> **Claim 2 — Stale Tool Bleed Prevention (Cancellable Tool Abort)**  
> When a user interrupts while a cancellable async tool (e.g. API lookup, flight status check) is in-flight, the tool task receives `asyncio.CancelledError` within $\le 50\text{ms}$ via event-driven cancellation. The tool result is marked `cancelled=True` and is never applied to conversational state or spoken aloud.

> **Claim 3 — Uncancellable Tool Result Quarantine (Phantom Side-Effect Containment)**  
> When a user interrupts while an uncancellable async tool (e.g. reservation DB commit) is in-flight, the tool is allowed to complete in the background. However, upon completion, the `GenerationFence` gate check `fence.is_stale(generation_id)` returns `True`, causing the `ToolResult` to be quarantined — withheld from shared conversation state and never spoken. Stale tool result rate is $0.0\%$.

> **Claim 4 — Monotonic Fence Integrity Under Rapid Consecutive Barge-Ins**  
> Under 3 or more rapid consecutive interruptions fired within $10\text{ms}$, the `GenerationFence` guarantees that only the latest generation $G_N$ is marked current. All prior generations $G_1 \dots G_{N-1}$ are marked stale. Zero crosstalk, zero bleed, zero misattribution occurs across turn ledgers.

> **Claim 5 — Protocol-Level Rime WebSocket Buffer Purge**  
> Upon barge-in, `FencedRimeClient` transmits `{"operation": "clear", "contextId": generation_id}` over the Rime WebSocket transport immediately, purging server-side synthesis buffers. Standard LiveKit Rime plugin integration (`livekit-plugins-rime==1.7.1`) stops local playback but returns the pooled WebSocket without sending this clear frame, allowing Rime's server to continue buffering stale audio.

> **Claim 6 — LiveKit ChatMessage Content Mutation Correctness**  
> LiveKit Agents 1.7.1's `ChatMessage.text_content` is a **read-only** `@property` with no setter. The naive fix `item.text_content = turn.text` silently fails (raises `AttributeError` which is swallowed). RimeTrack updates `item.content = [turn.text]`, which mutates the underlying `list[ChatContent]` and correctly grounds `session.history`.

---

## 2. Acceptance Tests

An implementation **PASSES** the full acceptance test if and only if **all six conditions** hold simultaneously across all scenarios:

| # | Acceptance Criterion | What Is Tested | Pass Condition |
|:---:|---|---|---|
| **AC-1** | **Heard-Text Grounding** | Inject barge-in at word index $k < N$ of an $N$-word response. Inspect next turn's `ChatContext`. | `context[-1].text` contains exactly the first $k$ words; zero words from positions $k{+}1 \dots N$ appear. `stale_response_rate == 0.0` across all trials. |
| **AC-2** | **Cancellable Tool Abort** | Barge-in during an in-flight cancellable async tool (`ToolExecutor.run_cancellable()`). | Tool task receives `asyncio.CancelledError` within $\le 50\text{ms}$. `tool_result.cancelled == True`. Tool output never enters conversation state. |
| **AC-3** | **Uncancellable Tool Quarantine** | Barge-in during an in-flight uncancellable async tool (`ToolExecutor.run_uncancellable()`). Let tool finish naturally. | Tool completes in background, but `tool_result.is_stale(fence) == True`. Result is withheld from state and not spoken. `stale_tool_result_rate == 0.0`. |
| **AC-4** | **Monotonic Fence Integrity** | Fire 3 rapid consecutive barge-ins within $10\text{ms}$. | Only generation $G_N$ is current; generations $G_1 \dots G_{N-1}$ are stale. Zero crosstalk or bleed across turn ledgers. Fence counter is strictly monotonic. |
| **AC-5** | **Protocol-Level WS Clear** | Trigger interruption while Rime TTS is streaming audio chunks. Inspect WebSocket frames sent. | `{"operation": "clear", "contextId": ...}` frame is transmitted on the Rime WebSocket connection before any new speech tokens from the successor turn are dispatched. |
| **AC-6** | **ChatMessage Content Mutation** | Set `item.content = [turn.text]` on a real `ChatMessage` object. | `item.text_content` reflects the updated text. `session.history` is grounded in the heard-text prefix. |

---

## 3. Test Procedure & Evaluation Methodology

### 3.1 Automated Test Suite (61/61 Passing)

The test suite validates all six acceptance criteria across 9 test files with 61 individual test cases:

| Test File | Tests | What It Verifies | Acceptance Criteria |
|---|:---:|---|:---:|
| [`tests/stress/test_full_duplex_proof.py`](tests/stress/test_full_duplex_proof.py) | 6 | **Direct Rubric Proof:** Fixed delay tool call interrupted mid-speech, changed request, audio cutoff, stale tool quarantine, updated instruction execution, sub-ms cancel latency, triple barge-in | AC-1 through AC-5 |
| [`tests/stress/test_fence.py`](tests/stress/test_fence.py) | 11 | Monotonic ID generation, thread-safety, rapid interruptions, sliding-window eviction, cancellable/uncancellable tool gating | AC-2, AC-3, AC-4 |
| [`tests/stress/test_tools.py`](tests/stress/test_tools.py) | 7 | `book_restaurant` (3s delay), `check_flight_status` (1.5s delay), `check_weather` (0.5s delay) — normal completion, mid-delay interruption, concurrent fencing, error handling | AC-2, AC-3 |
| [`tests/stress/test_state_manager.py`](tests/stress/test_state_manager.py) | 8 | Heard-text ledger commit, mid-sentence interruption prefix, grounded context for next LLM call, rapid consecutive interruption prefixes, LiveKit item ingestion | AC-1 |
| [`tests/stress/test_rime_client.py`](tests/stress/test_rime_client.py) | 6 | Context ID tagging, stale generation refusal, `{"operation": "clear"}` frame emission, rapid re-interruption clear frames, flush/EOS schema | AC-5 |
| [`tests/stress/test_session_wiring.py`](tests/stress/test_session_wiring.py) | 5 | LiveKit event bridge: `speech_created` advances fence, non-interrupted item ingestion, interrupted item truncation and grounding, `ChatMessage.content` setter regression | AC-1, AC-6 |
| [`tests/stress/test_pipeline_scenarios.py`](tests/stress/test_pipeline_scenarios.py) | 6 | End-to-end multi-turn scenarios: normal flow, single interruption, cancellable tool interruption, uncancellable tool fencing, rapid double barge-in, tool failure recovery | AC-1 through AC-4 |
| [`tests/stress/test_text_normalize.py`](tests/stress/test_text_normalize.py) | 10 | Pre-TTS phonetic normalization: markdown stripping, currency expansion, time formatting, alphanumeric code spelling, interrobang preservation, ellipsis handling | Rime voice quality |
| [`tests/stress/test_rime_quickstart.py`](tests/stress/test_rime_quickstart.py) | 2 | Rime HTTPS quickstart validation: API key requirement, payload/header structure verification | Configuration hygiene |

#### Repeatable Command — Run Full Test Suite
```bash
# Windows PowerShell
$env:PYTHONPATH = "."
python -m pytest tests/ -v

# Linux / macOS
PYTHONPATH=. python -m pytest tests/ -v
```

**Expected output:**
```
====== 61 passed, 3 warnings in ~11s ======
```

### 3.2 Empirical Benchmark Suite (80 Trials per System, 160 Total)

The evaluation harness ([`eval/run_benchmark.py`](eval/run_benchmark.py)) runs a controlled, apples-to-apples comparison:

- **`RimeTrackPipeline`**: Full generation fencing (`GenerationFence`), heard-text ledger (`ConversationStateManager`), event-driven tool cancellation (`ToolExecutor`), and protocol-level Rime WS clearing (`FencedRimeClient`).
- **`NaivePipeline` (Baseline)**: The standard "stop local audio on barge-in" approach used in common voice agents — halts local playback but lacks generation fencing, allowing background LLM tokens and tool tasks to complete and poison conversational state.

#### Scenario Matrix (20 Trials per Scenario × 4 Scenarios × 2 Systems = 160 Trials)

| Scenario | Description | Trigger | What It Stresses |
|---|---|---|---|
| **1. `single_interruption_mid_speech`** | User says *"Book me a table for 7pm."* Agent begins *"Sure booking a table for seven pm at your usual place."* User interrupts after word 3 (*"Sure booking a"*). | Barge-in at word index 3 of 10-word response | AC-1: Heard-text grounding |
| **2. `cancellable_tool_interruption`** | User interrupts while a cancellable order lookup API request is in-flight (simulated 200ms async delay). | Barge-in during `run_cancellable()` | AC-2: Tool abort |
| **3. `uncancellable_tool_fenced`** | User interrupts while an uncancellable reservation DB commit is in-flight (simulated 200ms async delay). Tool completes successfully after barge-in. | Barge-in during `run_uncancellable()` | AC-3: Tool quarantine |
| **4. `rapid_double_barge_in`** | User rapidly changes instructions twice: *"7pm"* → *"Actually 8pm"* → *"Cancel both."* | Two barge-ins within 5ms | AC-4: Monotonic fence integrity |

#### Repeatable Command — Run Benchmark
```bash
# Windows PowerShell
$env:PYTHONPATH = "."
python -m eval.run_benchmark

# Linux / macOS
PYTHONPATH=. python -m eval.run_benchmark
```

**Outputs:**
- `eval/results/benchmark_summary.json` — Aggregate metrics per system and scenario.
- `eval/results/benchmark_trials.csv` — Per-trial raw data (160 rows).

### 3.3 Live Rime WebSocket Interruption Diagnostic

The live diagnostic ([`eval/test_live_interrupted_turn_livekit.py`](eval/test_live_interrupted_turn_livekit.py)) connects directly to the production Rime WebSocket endpoint (`wss://users-ws.rime.ai/ws3`) and empirically proves the synchronizer race condition:

#### Repeatable Command — Live Diagnostic (requires valid `RIME_API_KEY`)
```bash
$env:PYTHONPATH = "."
$env:RIME_API_KEY = "your_rime_api_key_here"
python -m eval.test_live_interrupted_turn_livekit
```

---

## 4. Benchmark Results (Empirical Measurements)

*Raw data committed in [`eval/results/benchmark_summary.json`](eval/results/benchmark_summary.json) and [`eval/results/benchmark_trials.csv`](eval/results/benchmark_trials.csv).*

### 4.1 Per-Scenario Results Table

| Scenario | System | Trials | Stale Response Rate | Stale Tool Result Rate | Stop Latency (p50 / p95) |
|---|---|:---:|:---:|:---:|:---:|
| **1. Mid-Speech Barge-In** | **RimeTrack** | 20 | **0.0%** (0/20) | 0.0% | **0.00s / 0.00s** (sub-ms) |
| | Naive Baseline | 20 | **100.0%** (20/20) | 0.0% | N/A (state poisoned) |
| **2. Cancellable Tool** | **RimeTrack** | 20 | **0.0%** (0/20) | **0.0%** (0/20 aborted) | Sub-ms abort |
| | Naive Baseline | 20 | **100.0%** (20/20) | **100.0%** (20/20 applied) | N/A |
| **3. Uncancellable Tool** | **RimeTrack** | 20 | **0.0%** (0/20) | **0.0%** (20/20 quarantined) | Result quarantined |
| | Naive Baseline | 20 | **100.0%** (20/20) | **100.0%** (20/20 applied) | N/A |
| **4. Rapid Double Barge-In** | **RimeTrack** | 20 | **0.0%** (0/20) | 0.0% | Monotonic integrity preserved |
| | Naive Baseline | 20 | **100.0%** (20/20) | 0.0% | Severe state crosstalk |

### 4.2 Aggregate Summary

```
======================================================================
  DATAFORGE × RIME BENCHMARK SUMMARY
======================================================================
  RimeTrack Overall Stale Response Rate:     0.0%  (0 / 80 trials)
  RimeTrack Overall Stale Tool Rate:         0.0%  (0 / 80 trials)
  RimeTrack Tool Cancellation Latency:       ≤ 0.08ms (event-driven)
  RimeTrack p50 Stop Latency:               0.00s
  RimeTrack p95 Stop Latency:               0.00s
  ─────────────────────────────────────────────────────────────────
  Naive Baseline Stale Response Rate:      100.0%  (80 / 80 trials)
  Naive Baseline Stale Tool Rate:           50.0%  (100% in tool scenarios)
======================================================================
```

### 4.3 Key Test Fixtures (Inline Reproducible Examples)

#### Fixture 1 — Heard-Text Grounding (AC-1)

```python
# tests/stress/test_state_manager.py::test_interruption_mid_sentence_commits_only_heard_prefix
import asyncio
from agent.fence import GenerationFence
from agent.state_manager import ConversationStateManager

async def test_ac1_heard_text_grounding():
    fence = GenerationFence()
    mgr = ConversationStateManager(fence)

    gen_id = fence.advance()
    mgr.start_turn(gen_id)

    words = "Sure booking a table for seven pm at your usual place".split()
    # Simulate streaming: agent speaks first 3 words, then user interrupts
    for w in words[:3]:
        mgr.push_chunk(gen_id, w + " ")

    # Barge-in: cancel the current generation
    fence.cancel(gen_id, reason="barge_in")
    mgr.commit_turn(gen_id, interrupted=True)

    turn = mgr.get_last_turn()
    assert turn.text == "Sure booking a "    # ← Only heard prefix
    assert "seven" not in turn.text          # ← Un-spoken word NOT present
    assert "place" not in turn.text          # ← Final word NOT present
```

#### Fixture 2 — Cancellable Tool Abort (AC-2)

```python
# tests/stress/test_fence.py::test_cancellable_tool_stops_when_superseded
import asyncio
from agent.fence import GenerationFence
from agent.tool_executor import ToolExecutor

async def test_ac2_cancellable_tool_abort():
    fence = GenerationFence()
    executor = ToolExecutor(fence)
    gen_id = fence.advance()

    async def slow_lookup():
        await asyncio.sleep(10)  # Simulates long API call
        return {"flight": "AA100", "status": "On Time"}

    task = asyncio.create_task(executor.run_cancellable(gen_id, slow_lookup()))

    await asyncio.sleep(0.01)  # Let task start
    fence.interrupt_current(reason="user changed request")

    result = await task
    assert result.cancelled is True    # ← Task was aborted
    assert result.value is None        # ← No stale data
```

#### Fixture 3 — Uncancellable Tool Quarantine (AC-3)

```python
# tests/stress/test_fence.py::test_uncancellable_tool_result_is_fenced_not_applied
import asyncio
from agent.fence import GenerationFence
from agent.tool_executor import ToolExecutor

async def test_ac3_uncancellable_tool_quarantine():
    fence = GenerationFence()
    executor = ToolExecutor(fence)
    gen_id = fence.advance()

    async def db_commit():
        await asyncio.sleep(0.05)  # Simulates DB write
        return {"booking_id": "BK-7891", "time": "7:00 PM"}

    task = asyncio.create_task(executor.run_uncancellable(gen_id, db_commit()))

    await asyncio.sleep(0.01)
    fence.interrupt_current(reason="user changed to 8:30 PM")

    result = await task
    assert result.value == {"booking_id": "BK-7891", "time": "7:00 PM"}  # Completed
    assert result.is_stale(fence) is True    # ← Quarantined by fence
    # Result is NEVER applied to conversation state or spoken aloud
```

#### Fixture 4 — Protocol-Level Clear Frame (AC-5)

```python
# tests/stress/test_rime_client.py::test_interruption_sends_documented_clear_operation
from agent.fence import GenerationFence
from agent.rime_ws_client import FencedRimeClient

def test_ac5_protocol_clear_frame():
    fence = GenerationFence()
    client = FencedRimeClient(fence)

    gen1 = fence.advance()
    client.send_text("Hello, I am booking your table now.", generation_id=gen1)

    # Barge-in: fence advances, old generation cancelled
    old_id, new_id = fence.interrupt_current(reason="barge_in")

    # Inspect the clear frames sent on the WebSocket
    clear_frames = [f for f in client.sent_frames if f.get("operation") == "clear"]
    assert len(clear_frames) >= 1
    assert clear_frames[-1]["contextId"] == gen1  # Cleared the stale context
```

---

## 5. Rime-Specific Voice Integration Details

| Parameter | Selected Value | Justification & Situational Fit |
|---|---|---|
| **Model** | `coda` | Production-grade ultra-low-latency conversational model; optimized for real-time pacing in dynamic turn-taking environments. |
| **Speaker** | `astra` | Clear, articulate enunciation suitable for complex scheduling, booking confirmations, and hands-busy dispatch instructions. |
| **Language** | `eng` (English) | Primary conversational environment for hackathon demonstration. |
| **Transport** | **WebSocket** (`use_websocket=True`) | **Critical:** WebSocket streaming enables (a) word-level alignment via `push_timed_transcript`, (b) immediate server-side mid-stream synthesis clear/stop via `{"operation": "clear"}`, and (c) continuous duplex audio delivery. HTTP one-shot endpoints cannot provide any of these capabilities. |
| **Speed Control** | `speed_alpha=1.0` | Native WebSocket speed control parameter ensuring consistent prosody during fast turn-taking. Adjustable per-session. |
| **Audio Format** | PCM streaming | Low-latency chunk delivery over WebRTC transport via LiveKit Agents. |
| **WebSocket Endpoint** | `wss://users-ws.rime.ai/ws3` | Production Rime streaming TTS endpoint used in live diagnostic testing. |

### Rime Protocol-Level Integration Architecture

```
User interrupts → STT barge-in signal
    ↓
GenerationFence.interrupt_current()
    ↓
FencedRimeClient receives FenceEvent(kind="cancelled")
    ↓
WebSocket frame sent: {"operation": "clear", "contextId": "G3"}
    ↓
Rime server purges synthesis buffer for context G3
    ↓
New turn G4 begins with clean Rime pipeline
```

### The Verified Synchronizer Race Condition (Empirical Proof)

LiveKit Agents 1.7.1 natively attempts to solve context poisoning via `TranscriptSynchronizer` (wired by default in `agent_activity.py`):

```python
# livekit/agents/voice/agent_activity.py (lines 3048-3070)
forwarded_text = text_out.text if text_out else ""
if speech_handle.interrupted and audio_output is not None:
    playback_ev = await audio_output.wait_for_playout()
    if playback_ev.synchronized_transcript is not None:
        forwarded_text = playback_ev.synchronized_transcript
```

**The empirical finding:** Running a live interrupted turn at $t \approx 360\text{ms}$ against `wss://users-ws.rime.ai/ws3` revealed:

1. **Audio chunks arrive in $< 150\text{ms}$** — client playback begins immediately.
2. **Rime's `{"type": "timestamps"}` packet arrives in $500{-}800\text{ms}$** — significantly after audio playback starts.
3. **If the user interrupts before timestamps arrive**, `playback_ev.synchronized_transcript` is `None`, and LiveKit falls back to `forwarded_text = text_out.text` (the **full un-spoken generated text**).
4. **Result:** Without RimeTrack, `session.history` is poisoned with text the user never heard.

**RimeTrack's dual-layer defense:**
- **Layer 1 (Native Alignment):** If Rime's timestamps packet arrives before interruption, RimeTrack ingests the aligned text (`is_estimated = False`).
- **Layer 2 (Chunk-Flush Ledger):** If the interruption occurs during the timestamp race window, `ConversationStateManager` falls back to its chunk-level playout ledger (`is_estimated = True`), providing a conservative heard-text estimate.
- **Layer 3 (Content Mutation):** `item.content = [turn.text]` safely mutates `ChatMessage.content` (the underlying `list[ChatContent]`), bypassing the read-only `text_content` property.

---

## 6. Known Limitations & Honest Disclosures

1. **Synthetic Timing vs. Live Network Jitter:** The automated benchmark harness uses calibrated `asyncio.sleep` intervals (`word_delay=0.001s`, `tts_delay=0.001s`) for **100% determinism** and reproducibility. In real WebRTC network environments, packet arrival jitter (typically 15–45ms) may occur before the client silence classifier signals the server. RimeTrack's fence-based architecture is designed to tolerate this jitter, but real-world latency measurements will differ from the synthetic 0.00s p50/p95 values.

2. **LiveKit `ConversationItemAddedEvent` Correlation:** LiveKit's `ConversationItemAddedEvent` does not expose the originating `speech_handle_id`. RimeTrack resolves this by attributing items to the active `generation_id` at ingestion time, which is correct under the single-active-speaker assumption but would need adaptation for multi-agent scenarios.

3. **Uncancellable Tool Side Effects:** While RimeTrack guarantees that uncancellable tool results are **never applied to conversational state or spoken aloud**, any non-idempotent external side effects (e.g., an irreversible bank transfer already committed to an external payment gateway) must be handled by external compensating transactions, sagas, or two-phase commit protocols. This is inherent to the definition of "uncancellable."

4. **Rime Timestamp Alignment Granularity:** Rime's word-level timestamp alignment is utterance-scoped (computed across the full synthesis request). For very short utterances (< 3 words), timestamp packets may arrive before audio playback begins, making the race condition a non-issue. The race primarily manifests in longer utterances (> 5 words) where audio streaming begins before full alignment is computed.

5. **Single-Speaker Assumption:** The `ConversationStateManager` assumes a single active agent speaker at any given time. Multi-agent or multi-turn parallel synthesis scenarios would require per-speaker fence partitioning.

6. **`ChatMessage` API Stability:** The `item.content = [turn.text]` mutation path depends on LiveKit's internal `ChatMessage` model structure. If LiveKit changes `content` from `list[ChatContent]` to an immutable type in a future release, this mutation path would need to be updated.

---

## 7. Complete Reproduction Steps

### Step 1: Environment Setup
```bash
# Clone the repository
git clone https://github.com/saugata-malakar/KDAG-RICE.git
cd KDAG-RICE

# Install dependencies
pip install -e ".[dev]"

# Copy and populate environment variables
cp .env.example .env
# Edit .env with your actual API keys (see Configuration Hygiene section below)
```

### Step 2: Run Configuration Preflight Check
```bash
python preflight_check.py
```
This validates all required environment variables, API key formats, and Rime configuration before running any tests.

### Step 3: Run Full Test Suite (55/55 Passing)
```bash
$env:PYTHONPATH = "."    # PowerShell
python -m pytest tests/ -v
```

### Step 4: Run 80-Trial Benchmark Suite
```bash
$env:PYTHONPATH = "."
python -m eval.run_benchmark
```

### Step 5: Run Live Rime WebSocket Diagnostic (Requires Valid `RIME_API_KEY`)
```bash
$env:PYTHONPATH = "."
python -m eval.test_live_interrupted_turn_livekit
```

### Step 6: Start Live Voice Agent Worker (Requires LiveKit + Rime + OpenAI Keys)
```bash
python -m agent.session dev
```

### Step 7: Run Rime 5-Minute HTTPS Quickstart
```bash
python rime_quickstart.py "Hello! This is Rime speaking from RimeTrack."
```

---

## 8. Configuration Hygiene

### 8.1 Environment Example (Placeholders Only)

The repository includes a sanitized [`.env.example`](.env.example) with **zero real secrets** — only placeholder tokens and organizer-provided default values:

```env
# ──────────────────────────────────────────────────────────────
# RimeTrack Environment Configuration
# Copy this file to .env and replace placeholders with real keys
# ──────────────────────────────────────────────────────────────

# --- LiveKit Cloud (WebRTC Transport) ---
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxxxxxxxxx
LIVEKIT_API_SECRET=your_livekit_api_secret_here

# --- Rime Labs (Primary Spoken-Output Provider — REQUIRED) ---
RIME_API_KEY=your_rime_api_key_here
RIME_MODEL=coda
RIME_SPEAKER=astra
RIME_LANG=eng
RIME_SPEED_ALPHA=1.0

# --- STT Provider (Speech-to-Text) ---
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# --- LLM Provider (Language Model) ---
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx

# --- Logging & Diagnostics ---
RIMETRACK_LOG_DIR=eval/results
RIMETRACK_LOG_LEVEL=INFO
```

### 8.2 Organizer-Provided Rime Configuration Values

The following configuration matches the hackathon organizer's specifications:

| Parameter | Value | Source |
|---|---|---|
| `RIME_MODEL` | `coda` | Organizer-specified production model for conversational voice agents |
| `RIME_SPEAKER` | `astra` | Organizer-specified speaker for clear articulation |
| `RIME_LANG` | `eng` | English language target |
| `RIME_SPEED_ALPHA` | `1.0` | Default speed (adjustable via WebSocket parameter) |
| WebSocket Endpoint | `wss://users-ws.rime.ai/ws3` | Rime production streaming endpoint |
| HTTP Endpoint | `https://users.rime.ai/v1/rime-tts` | Rime production one-shot endpoint (used by quickstart) |

### 8.3 Secret Preflight Check Script

The repository includes [`preflight_check.py`](preflight_check.py) — a self-contained script that validates all required environment variables, API key formats, and Rime configuration **before** any tests or the agent are run:

```bash
python preflight_check.py
```

**What the preflight check validates:**

| Check | What It Verifies | Pass Condition |
|---|---|---|
| **RIME_API_KEY** | Present and non-placeholder | Not empty, not `your_rime_api_key_here` |
| **RIME_MODEL** | Matches organizer spec | Equals `coda` |
| **RIME_SPEAKER** | Matches organizer spec | Equals `astra` |
| **RIME_LANG** | Language code valid | Equals `eng` |
| **LIVEKIT_URL** | Present and valid WebSocket URL | Starts with `wss://` |
| **LIVEKIT_API_KEY** | Present and has correct prefix | Starts with `API` |
| **LIVEKIT_API_SECRET** | Present and non-placeholder | Not empty, not `your_livekit_api_secret_here` |
| **OPENAI_API_KEY** | Present and has correct prefix | Starts with `sk-` |
| **DEEPGRAM_API_KEY** | Optional; warns if missing | Present or warns "STT will fall back to OpenAI Whisper" |
| **No Raw Secrets in README** | Scans README.md for leaked keys | No `sk-proj-`, no raw `LIVEKIT_API_SECRET` values in README |

**Example output (all checks passing):**
```
═══════════════════════════════════════════════════════
  RimeTrack Preflight Configuration Check
═══════════════════════════════════════════════════════
  [✓] RIME_API_KEY        — Present (not placeholder)
  [✓] RIME_MODEL          — coda (matches organizer spec)
  [✓] RIME_SPEAKER        — astra (matches organizer spec)
  [✓] RIME_LANG           — eng
  [✓] LIVEKIT_URL         — wss://rice-h02i5ol6.livekit.cloud
  [✓] LIVEKIT_API_KEY     — Present (API prefix OK)
  [✓] LIVEKIT_API_SECRET  — Present (not placeholder)
  [✓] OPENAI_API_KEY      — Present (sk- prefix OK)
  [⚠] DEEPGRAM_API_KEY    — Missing (will fall back to OpenAI Whisper)
  [✓] README Secret Scan  — No raw API secrets found in README.md
═══════════════════════════════════════════════════════
  Result: 9/10 PASSED, 0 FAILED, 1 WARNING
  Configuration is ready for deployment.
═══════════════════════════════════════════════════════
```
