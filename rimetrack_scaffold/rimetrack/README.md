# RimeTrack 🎙️
### Real-Time Interruption Recovery & Tool Fencing for Full-Duplex Voice Agents

> **DataForge × Rime Hackathon Challenge (September 2026)**  
> **Primary Voice Provider:** Rime Labs WebSocket Neural TTS (`coda` / `astra` / `eng`)  
> **Official Repository:** [https://github.com/saugata-malakar/KDAG-RICE](https://github.com/saugata-malakar/KDAG-RICE)  
> **Architecture & Research Paper:** [`docs/ARCHITECTURE_REPORT.md`](docs/ARCHITECTURE_REPORT.md) | [`docs/ARCHITECTURE_REPORT.tex`](docs/ARCHITECTURE_REPORT.tex)  
> **Empirical Evidence & Acceptance Criteria:** [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 61/61 Passing](https://img.shields.io/badge/Tests-61%2F61%20Passing-brightgreen.svg)](tests/)
[![Rime TTS: Coda / Astra (WS)](https://img.shields.io/badge/Rime%20TTS-Coda%20%2F%20Astra%20(WS)-orange.svg)](https://rime.ai)
[![LiveKit Agents: 1.7.1](https://img.shields.io/badge/LiveKit-Agents%201.7.1-blue.svg)](https://livekit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🚀 LIVE DEMO & JUDGE TESTING INSTRUCTIONS

Judges can test the live full-duplex agent immediately in the browser without deploying any local infrastructure:

### Option 1: LiveKit Agents Playground (Interactive WebRTC Audio)
1. **Open the Playground:** [https://agents-playground.livekit.io/](https://agents-playground.livekit.io/)
2. **Server URL:** `wss://rice-h02i5ol6.livekit.cloud`
3. **Pre-Generated Judge Access Token (Valid for 30 Days):**
```text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiSGFja2F0aG9uIEp1ZGdlIiwidmlkZW8iOnsicm9vbUpvaW4iOnRydWUsInJvb20iOiJyaW1ldHJhY2stZGVtbyIsImNhblB1Ymxpc2giOnRydWUsImNhblN1YnNjcmliZSI6dHJ1ZSwiY2FuUHVibGlzaERhdGEiOnRydWV9LCJzdWIiOiJoYWNrYXRob24tanVkZ2UiLCJpc3MiOiJBUElSSmNWazZobVJNYU4iLCJuYmYiOjE3ODg4NTU0MTUsImV4cCI6MTc5MTQ0NzQxNX0.4mOH2JEkHLIFyRbh3ouSR7D4Gb_-mF3Ffw1l-TDnJPc
```
4. **Connection Steps:**
   - Click the gear/settings icon in the top right of the Playground.
   - Enter the Server URL: `wss://rice-h02i5ol6.livekit.cloud`
   - Paste the **Judge Access Token** into the Token field.
   - Click **Connect** and allow microphone access.

### Option 2: Live Hackathon Acceptance Test Flow (Fixed Delay + Barge-In + Request Change)
Once connected, test the exact stress challenge defined in the hackathon brief:

1. **Trigger Normal Flow with Injected Tool Delay:**  
   Say aloud: *"Book a table for two at Olive Garden at 7:00 PM."*  
   *(The agent initiates `book_restaurant` with a deliberate 3.0-second delay — see [`agent/tools.py`](agent/tools.py)).*
2. **Interrupt Mid-Turn While Speaking or Waiting (Barge-In):**  
   While the agent speaks or waits for the tool, interrupt clearly:  
   *"Wait, change that to 8:30 PM for four people!"*
3. **Verify All 5 Hackathon Rubric Behaviors:**  
   - ✅ **(1) Queued Rime audio stops promptly:** Spoken audio cuts off instantly ($\le 1\text{ms}$) via Rime WebSocket `{"operation": "clear", "contextId": "G1"}` frame. Un-spoken words are purged from server-side synthesis buffers.
   - ✅ **(2) Updated instruction reaches the application:** The `GenerationFence` advances to `G2`, and the application immediately ingests the revised request without dropping audio or freezing.
   - ✅ **(3) Stale tool results are NOT spoken as current:** The 7:00 PM booking finishes in the background, but the `ToolExecutor` checks `fence.is_stale("G1")`, marks the result `cancelled=True`, and **quarantines** it. It is never spoken aloud.
   - ✅ **(4) Background work is cancelled or reconciled correctly:** Cancellable tools receive `asyncio.CancelledError` in $\le 0.08\text{ms}$. Uncancellable tools complete without state contamination.
   - ✅ **(5) Final spoken response reflects heard & requested:** The agent confirms: *"Done! I have booked a table for four at Olive Garden at 8:30 PM."* The heard-text ledger guarantees that conversation context contains only audible words and the updated booking.
4. **Full-Duplex Application Property:** Full duplex is treated as a property of the **complete application**, not the TTS model alone. The application continuously accepts user microphone audio while Rime speech is streaming and while background tools are executing.
5. **Automated Verification:** Run the dedicated end-to-end integration test:
   ```bash
   pytest tests/stress/test_full_duplex_proof.py -v
   ```

### Option 3: Interactive Visual Debug HUD (Standalone Client)
Open [`client/index.html`](client/index.html) in any browser to inspect the Web Audio spectrum analyzer, simulate word-by-word streaming, trigger barge-ins, and view real-time side-by-side context audit logs.

---

## 🎯 1. Problem & Necessity of Voice (Judging Weight: 25%)

In hands-busy, accessibility-focused, and operational workflows (emergency dispatch, field medicine, air logistics, table booking), voice interaction is **essential**—removing speech destroys product utility.

Standard conversational voice agents suffer from two catastrophic failure modes upon interruption:
1. **Context Poisoning (Hallucinated Grounding):** When an agent is interrupted mid-utterance, standard LLM histories append the *full generated text* instead of the *heard-text prefix*. The agent hallucinates that the user heard information that was never spoken.
2. **Stale Tool Bleed (Phantom Side Effects):** When a slow background tool (e.g., reservation write, order dispatch) completes *after* the user interrupted to change their request, standard frameworks unconditionally apply the stale tool output to conversational state and speak the obsolete confirmation aloud.

### RimeTrack's Core Solution:
* **`GenerationFence` (`agent/fence.py`):** Monotonically increasing generation IDs (`G1`, `G2`, ...) gate all in-flight LLM tokens and tool execution results at the exact boundary of re-entry into shared conversation state.
* **Heard-Text Ledger (`agent/state_manager.py`):** Grounded directly in Rime's real-time per-word timestamp alignment over WebSocket (`push_timed_transcript`), recording strictly what reached audible playback before the interruption cut.
* **Protocol-Level Clear Operation (`agent/rime_ws_client.py`):** Binds to Rime's WebSocket wire protocol, transmitting `{"operation": "clear", "contextId": ...}` to immediately flush server-side synthesis buffers upon barge-in.
* **Sub-Millisecond Tool Cancellation (`agent/tool_executor.py`):** Event-driven cancellation replaces CPU polling loops, aborting in-flight tasks in <= 0.08ms.
* **LiveKit ChatContext Mutation:** Safely updates `item.content = [turn.text]` on `ChatMessage` models, eliminating silent setter failures and guaranteeing grounding in `session.history`.

---

## 🏗️ 2. System Architecture

```mermaid
flowchart TD
    subgraph Client ["Client Interface (Microphone / Speaker)"]
        Mic[User Audio Input]
        Spk[Audio Playback Output]
    end

    subgraph Transport ["LiveKit Cloud WebRTC Server"]
        RTC_In[Inbound WebRTC Stream]
        RTC_Out[Outbound WebRTC Stream]
    end

    subgraph RimeTrack_Worker ["RimeTrack Agent Runtime"]
        STT[Deepgram Nova-3 <br> <i>Fallback: OpenAI Whisper</i>]
        LLM[OpenAI GPT-4o-mini]
        Norm[Pre-TTS Text Normalizer]
        Rime[Rime TTS WebSocket <br> <i>coda / astra / eng</i>]
        Fence["GenerationFence <br> (Monotonic Authority)"]
        Ledger["ConversationStateManager <br> (Heard-Text Ledger)"]
        Executor["ToolExecutor <br> (Event-Driven & Result Fencing)"]
        Tools["RimeTrack Tools <br> (book_restaurant, check_flight, weather)"]
    end

    Mic -->|Audio| RTC_In
    RTC_In --> STT
    STT -->|Barge-in Signal| Fence
    STT -->|Final Transcript| Ledger

    Fence -->|Advance / Invalidate G_id| Ledger
    Fence -->|Gate In-Flight Result| Executor
    Fence -->|Send Clear Frame| Rime

    Ledger -->|Grounded Context H_t| LLM
    LLM -->|Tool Calls| Executor
    Executor --> Tools
    LLM -->|Text Stream| Norm
    Norm -->|Normalized Text| Rime
    Rime -->|Audio Chunks + Timestamps| RTC_Out
    RTC_Out -->|WebRTC| Spk
```

---

## 📊 3. Empirical Evidence & Reproducibility (Judging Weight: 20%)

We evaluated RimeTrack against the standard **Naive Baseline** across 80 empirical benchmark trials per system ($N_{total} = 160$ trials) across 4 distinct failure scenarios using [`eval/run_benchmark.py`](eval/run_benchmark.py):

| Scenario Tested | Trials | RimeTrack Stale Response Rate | RimeTrack Stale Tool Bleed | Naive Baseline Stale Rate | Naive Baseline Tool Bleed | Stop Latency |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **1. Mid-Speech Barge-In (3 of 10 words)** | 20 | **0.0%** (0/20) | 0.0% | **100.0%** (20/20) | 0.0% | < 1.0ms |
| **2. Cancellable Tool Interruption** | 20 | **0.0%** (0/20) | **0.0%** (20/20 aborted) | **100.0%** (20/20) | **100.0%** (20/20 applied) | <= 0.08ms |
| **3. Uncancellable Tool (Result Fencing)** | 20 | **0.0%** (0/20) | **0.0%** (20/20 quarantined)| **100.0%** (20/20) | **100.0%** (20/20 applied) | Quarantined |
| **4. Rapid Double Barge-In** | 20 | **0.0%** (0/20) | 0.0% | **100.0%** (20/20) | 0.0% | Monotonic |
| **OVERALL AGGREGATE** | **80** | **0.0%** | **0.0%** | **100.0%** | **50.0% Stale Bleed** | **Sub-ms** |

*Raw data files committed to repo: [`eval/results/benchmark_summary.json`](eval/results/benchmark_summary.json) and [`eval/results/benchmark_trials.csv`](eval/results/benchmark_trials.csv).*

---

## ⚡ 4. Acceptance Criteria (Pre-Demo Contract)

| Criterion | What is Tested | Acceptance Condition | Verification File | Status |
|---|---|---|---|:---:|
| **AC-1: Heard-Text Grounding** | Barge-in mid-sentence during Rime speech playback | Next turn's prompt context contains **only the words the user actually heard** before the interrupt. | [`tests/stress/test_state_manager.py`](tests/stress/test_state_manager.py) | ✅ Verified |
| **AC-2: Cancellable Tool Abort** | Barge-in while an async API call is in-flight | In-flight background task receives cancellation within $\le 0.08\text{ms}$; no stale audio is synthesized. | [`tests/stress/test_fence.py`](tests/stress/test_fence.py) | ✅ Verified |
| **AC-3: Uncancellable Tool Fencing** | Fixed delay in an irreversible DB tool completes *after* interrupt | Tool finishes in background, but the result is **quarantined by the `GenerationFence`** and never spoken aloud. | [`tests/stress/test_tools.py`](tests/stress/test_tools.py) | ✅ Verified |
| **AC-4: Monotonic Fence Integrity** | Rapid back-to-back user barge-ins ($\le 10\text{ms}$) | Only latest generation $G_N$ is current; zero crosstalk or state bleed across turn ledgers. | [`tests/stress/test_fence.py`](tests/stress/test_fence.py) | ✅ Verified |
| **AC-5: Protocol-Level WS Clearing** | Interruption during active Rime WebSocket synthesis | Explicit `{"operation": "clear", "contextId": ...}` is sent over Rime WebSocket to clear server buffers. | [`tests/stress/test_rime_client.py`](tests/stress/test_rime_client.py) | ✅ Verified |
| **AC-6: ChatMessage Content Mutation** | `ChatMessage.content = [turn.text]` mutation target | Safely updates underlying `list[ChatContent]`, eliminating LiveKit setter failure and grounding `session.history`. | [`tests/stress/test_session_wiring.py`](tests/stress/test_session_wiring.py) | ✅ Verified |
| **Rubric Proof: Full-Duplex Interruption & Tool Delay** | Fixed 3.0s tool delay, barge-in mid-speech/wait, changed request | Audio cuts off, 7pm booking quarantined, 8:30pm booking executed, final response reflects heard & requested. | [`tests/stress/test_full_duplex_proof.py`](tests/stress/test_full_duplex_proof.py) | ✅ Verified |

---

## 🔊 5. Rime Integration & Voice Experience (Judging Weight: 20%)

* **Production Model & Speaker:** `coda` model with `astra` speaker, configured for natural, conversational prosody (`speed_alpha=1.0`).
* **Transport:** Full-duplex WebSocket streaming (`use_websocket=True`) to enable mid-stream cancellation and per-word timestamp alignment.
* **Writing for the Ear Compliance:** System prompt in [`agent/prompts.py`](agent/prompts.py) implements Brooke Larson's guidelines for punctuation-as-pitch, conversational fillers, and register pacing.
* **Pre-TTS Normalization:** [`agent/text_normalize.py`](agent/text_normalize.py) expands domain flight codes (`UA-402` -> `UA 402`), tracking IDs (`BK-5521` -> `BK 5521`), currency, and times into spoken form while preserving Rime's `?!` interrobang inflection convention.
* **Prosody Analysis Report:** Full comparative evaluation in [`docs/PROSODY_ANALYSIS.md`](docs/PROSODY_ANALYSIS.md).
* **Transparent Fallback Disclosure:** Speech recognition defaults to Deepgram (`nova-3`), transparently falling back to OpenAI Whisper STT when Deepgram is unavailable.

---

## 🔧 6. Exact Rime Configuration

The following table specifies every Rime parameter used in production. These values are locked in [`agent/session.py`](agent/session.py) and validated by [`preflight_check.py`](preflight_check.py):

| Parameter | Exact Value | Notes |
|---|---|---|
| **Model ID** | `coda` | Rime's production-grade ultra-low-latency conversational TTS model |
| **Speaker** | `astra` | Clear, articulate female voice optimized for scheduling and dispatch |
| **Language** | `eng` | English |
| **Endpoint (WebSocket)** | `wss://users-ws.rime.ai/ws3` | Production Rime streaming TTS endpoint — used for all live synthesis |
| **Endpoint (HTTP)** | `https://users.rime.ai/v1/rime-tts` | One-shot endpoint — used only by [`rime_quickstart.py`](rime_quickstart.py) |
| **Transport** | **WebSocket** (`use_websocket=True`) | Enables (a) mid-stream `{"operation":"clear"}` cancellation, (b) per-word `timestamps` alignment, (c) continuous duplex audio delivery |
| **Audio Format** | PCM 16-bit, 24kHz, mono | Raw PCM chunks streamed over WebSocket, delivered via LiveKit WebRTC |
| **Speed Control** | `speed_alpha=1.0` | Native speaking rate — adjustable per-session without re-synthesis |
| **Wire-Protocol Clear Frame** | `{"operation":"clear","contextId":"G<n>"}` | Sent on barge-in to purge server-side synthesis buffers for superseded context |
| **Wire-Protocol Flush Frame** | `{"flush":true}` | Signals end of text input for current context |
| **Wire-Protocol EOS Frame** | `{"is_eos":true}` | Signals end of synthesis stream |
| **LiveKit Plugin Version** | `livekit-plugins-rime==1.7.1` | Installed via `livekit-agents[rime]` metapackage |

Configuration is set in code at [`agent/session.py:31-39`](agent/session.py):
```python
def build_rime_tts() -> rime.TTS:
    return rime.TTS(
        model=os.environ.get("RIME_MODEL", "coda"),
        speaker=os.environ.get("RIME_SPEAKER", "astra"),
        lang=os.environ.get("RIME_LANG", "eng"),
        use_websocket=True,
        speed_alpha=1.0,
        api_key=os.environ.get("RIME_API_KEY"),
    )
```

---

## 🌐 7. Third-Party Services & Dependencies

| Service | Role | Version / Model | Required? | Fallback |
|---|---|---|:---:|---|
| **Rime Labs** | Primary TTS (spoken output) | `coda` model, `astra` speaker, WebSocket | **Yes** | None — Rime is the designated voice provider |
| **LiveKit Cloud** | WebRTC transport & room infrastructure | Agents SDK `1.7.1` | **Yes** | None |
| **OpenAI** | LLM (conversation intelligence) | `gpt-4o-mini` | **Yes** | None |
| **Deepgram** | Primary STT (speech recognition) | `nova-3` | No | OpenAI Whisper STT |
| **Silero VAD** | Voice Activity Detection | `silero-vad` via LiveKit plugin | **Yes** | Built into LiveKit Agents |

### Python Dependencies (from [`pyproject.toml`](pyproject.toml))
```
livekit-agents[rime,deepgram,openai,silero]   # Core agent framework with all plugins
python-dotenv                                  # Environment variable loading from .env
pytest + pytest-asyncio                        # Test framework (dev dependency)
```

### No Additional Infrastructure Required
- **No database** — tool demonstrations use in-memory mock responses with deliberate delays
- **No external queue** — all event routing is in-process via `asyncio`
- **No Docker** — runs directly with `python -m agent.session dev`

---

## 🖥️ 8. Working Code & Demo

### Source Repository
**All demonstrated behavior exists in this repository and can be reproduced by judges.**

| What | Link |
|---|---|
| **GitHub Repository** | [https://github.com/saugata-malakar/KDAG-RICE](https://github.com/saugata-malakar/KDAG-RICE) |
| **Branch** | `main` (all commits on default branch) |
| **Language** | Python 3.11+ |
| **Total Test Coverage** | 61/61 tests passing across 9 test files |
| **Benchmark Data** | 160 trials (80 per system), raw CSV committed |

### Working Demo Link
Judges can test the live voice agent immediately in the browser:

| Demo Method | Link / Instructions |
|---|---|
| **LiveKit Agents Playground** | [https://agents-playground.livekit.io/](https://agents-playground.livekit.io/) |
| **Server URL** | `wss://rice-h02i5ol6.livekit.cloud` |
| **Room Name** | `rimetrack-demo` |
| **30-Day Judge Token** | See [§ LIVE DEMO](#-live-demo--judge-testing-instructions) above |
| **Interactive Visual HUD** | Open [`client/index.html`](client/index.html) locally |
| **Demo Recording Script** | [`demo/DEMO_GUIDE.md`](demo/DEMO_GUIDE.md) — 4-minute video recording blueprint |

### Reproducing Demonstrated Behavior
Every behavior shown in the demo exists in the source code and can be reproduced:

| Demonstrated Behavior | Source File | Reproduction Command |
|---|---|---|
| **Full-Duplex Rubric Proof** (fixed tool delay, barge-in, request change, audio cutoff, stale tool quarantine, grounded output) | [`tests/stress/test_full_duplex_proof.py`](tests/stress/test_full_duplex_proof.py) | `pytest tests/stress/test_full_duplex_proof.py -v` |
| Barge-in halts audio instantly via WS clear | [`agent/rime_ws_client.py`](agent/rime_ws_client.py) | `pytest tests/stress/test_rime_client.py -v` |
| Stale tool result is quarantined | [`agent/tool_executor.py`](agent/tool_executor.py) | `pytest tests/stress/test_tools.py -v` |
| Heard-text grounding (no context poisoning) | [`agent/state_manager.py`](agent/state_manager.py) | `pytest tests/stress/test_state_manager.py -v` |
| 0.0% stale rate vs 100% baseline | [`eval/run_benchmark.py`](eval/run_benchmark.py) | `python -m eval.run_benchmark` |
| Monotonic fence under rapid interruptions | [`agent/fence.py`](agent/fence.py) | `pytest tests/stress/test_fence.py -v` |
| End-to-end multi-turn scenarios | [`agent/pipeline.py`](agent/pipeline.py) | `pytest tests/stress/test_pipeline_scenarios.py -v` |
| LiveKit session event wiring & content setter | [`agent/session.py`](agent/session.py) | `pytest tests/stress/test_session_wiring.py -v` |
| Pre-TTS text normalization | [`agent/text_normalize.py`](agent/text_normalize.py) | `pytest tests/stress/test_text_normalize.py -v` |

---

## 🛠️ 9. Setup Instructions & Local Reproduction

### Step 1: Clone & Install
```bash
git clone https://github.com/saugata-malakar/KDAG-RICE.git
cd KDAG-RICE

# Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### Step 2: Configure Credentials
```bash
cp .env.example .env
# Edit .env with your actual API keys
```

| Variable | Description | Required? |
|---|---|:---:|
| `LIVEKIT_URL` | LiveKit Cloud project URL (`wss://...`) | Yes |
| `LIVEKIT_API_KEY` | LiveKit API key (starts with `API`) | Yes |
| `LIVEKIT_API_SECRET` | LiveKit API secret | Yes |
| `RIME_API_KEY` | Rime Labs API key | Yes |
| `RIME_MODEL` | Rime TTS model (default: `coda`) | Yes |
| `RIME_SPEAKER` | Rime TTS speaker (default: `astra`) | Yes |
| `RIME_LANG` | Language code (default: `eng`) | Yes |
| `OPENAI_API_KEY` | OpenAI API key (starts with `sk-`) | Yes |
| `DEEPGRAM_API_KEY` | Deepgram API key | Optional |
| `RIMETRACK_LOG_DIR` | Log output directory (default: `eval/results`) | Optional |
| `RIMETRACK_LOG_LEVEL` | Log level: `DEBUG`/`INFO`/`WARNING` | Optional |

### Step 3: Run Preflight Configuration Check
```bash
python preflight_check.py
```
Validates all API keys, organizer-specified Rime configuration, and scans for accidentally committed secrets.

### Step 4: Run the Full Test Suite (61/61 Passing)
```bash
pytest tests/ -v
```

### Step 5: Run the 80-Trial Empirical Benchmark Suite
```bash
python -m eval.run_benchmark
```

### Step 6: Run the Live Interruption Synchronizer Diagnostic
```bash
python -m eval.test_live_interrupted_turn_livekit
```

### Step 7: Run the Official Rime 5-Minute Quickstart
```bash
python rime_quickstart.py "Hello! This is Rime speaking from RimeTrack."
```

### Step 8: Start the Live Voice Agent Worker
```bash
python -m agent.session dev
```

---

## ⚠️ 10. Known Limitations & Failure Behavior

### Known Limitations

| # | Limitation | Impact | Mitigation |
|:---:|---|---|---|
| 1 | **Synthetic Benchmark Timing** | Automated benchmark uses calibrated `asyncio.sleep` intervals for 100% determinism. Real WebRTC network jitter (15–45ms) will produce slightly different latency numbers. | Fence architecture tolerates jitter — correctness is unaffected, only latency numbers differ. |
| 2 | **LiveKit Event Correlation** | `ConversationItemAddedEvent` does not expose `speech_handle_id`. Items are attributed to the active `generation_id` at ingestion time. | Correct under single-active-speaker assumption. Multi-agent scenarios would need per-speaker fence partitioning. |
| 3 | **Uncancellable Tool Side Effects** | RimeTrack quarantines stale tool *results* from conversational state, but cannot undo external side effects (e.g., an irreversible bank transfer already committed). | External systems must use compensating transactions, sagas, or two-phase commit for irreversible operations. |
| 4 | **Rime Timestamp Race Window** | Rime's word-level timestamps arrive 500–800ms after audio starts streaming. Early interruptions (< 400ms) cause LiveKit's native synchronizer to fall back to full text. | RimeTrack's chunk-flush ledger provides Layer 2 defense during this race window. |
| 5 | **Single-Speaker Assumption** | `ConversationStateManager` assumes one active agent speaker at a time. | Multi-agent or parallel synthesis scenarios would need per-speaker fence partitioning. |
| 6 | **ChatMessage API Stability** | `item.content = [turn.text]` mutation depends on LiveKit's internal `ChatMessage` model structure. | If LiveKit changes `content` to an immutable type in a future release, the mutation path would need updating. |

### Failure Behavior (What Happens When Things Go Wrong)

| Failure Scenario | What Happens | User Impact |
|---|---|---|
| **Rime API key invalid or expired** | `preflight_check.py` catches this before startup. At runtime, `build_rime_tts()` raises connection error. Agent does not start. | Agent fails to start cleanly — no silent degradation. |
| **LiveKit Cloud unreachable** | Worker fails to connect to room. `session.py` logs error and exits. | Agent does not start. Judge can verify with preflight check. |
| **OpenAI API key invalid** | LLM calls fail. Agent connects to room but cannot generate responses. | Agent joins room but remains silent after user speaks. |
| **Deepgram API key missing** | STT transparently falls back to OpenAI Whisper. | Slightly higher STT latency, but fully functional. |
| **Rime WebSocket disconnects mid-synthesis** | `FencedRimeClient` detects connection loss. Current generation is marked stale. | Audio cuts off. Next user turn starts a fresh generation with a new WebSocket connection. |
| **Tool function raises an exception** | `ToolExecutor` catches the exception, logs it via `EventLog`, and returns a `ToolResult` with `error=True`. Fence state is not corrupted. | Agent tells user the action failed and asks them to retry. |
| **Rapid successive barge-ins (> 3 in 100ms)** | Each barge-in advances the `GenerationFence` monotonically. Only the latest generation is current. Sliding-window eviction caps cancelled ID storage at 1000. | All stale generations are fenced. Memory is bounded. |
| **Network partition during tool execution** | Uncancellable tool may complete after reconnection. Result is fenced by `generation_id` check. | Stale result is quarantined — never spoken or applied. |

---

## 📁 11. Repository Structure

```
├── docs/
│   ├── ARCHITECTURE_REPORT.md    # Comprehensive Architecture & Technical Report
│   ├── ARCHITECTURE_REPORT.tex   # Formal Publication-Grade LaTeX Research Paper
│   ├── PROSODY_ANALYSIS.md       # "Writing for the Ear" Comparative Prosody Study
│   └── architecture.md          # Sequence diagrams & data flows
├── RIME_EVIDENCE.md              # Formal voice claims, acceptance criteria & sync analysis
├── README.md                     # Master documentation, live judge token & benchmark summary
├── preflight_check.py            # Secret & configuration validator (run before deployment)
├── pyproject.toml                # Package configuration & test dependencies
├── .env.example                  # Sanitized environment template (placeholders only)
├── rime_quickstart.py            # Official Rime 5-minute HTTPS TTS quickstart
├── agent/                        # Core Voice Agent Runtime
│   ├── fence.py                  # GenerationFence (Monotonic authority, sliding-window eviction)
│   ├── tool_executor.py          # Event-driven cancellable & uncancellable tool result fencing
│   ├── tools.py                  # LiveKit function tools (book_restaurant, check_flight, weather)
│   ├── state_manager.py          # Heard-text ledger (Timestamp alignment)
│   ├── rime_ws_client.py         # FencedRimeClient (Protocol-level clear frame)
│   ├── text_normalize.py         # Pre-TTS domain phonetic normalizer (prosody rules)
│   ├── pipeline.py               # End-to-end turn simulator for benchmarking
│   ├── session.py                # LiveKit AgentSession + Rime WebSocket worker
│   └── prompts.py                # System persona & prosody instructions
├── eval/                         # Evaluation & Benchmark Suite
│   ├── metrics.py                # Formal metrics (Stale rate, stop latency)
│   ├── run_benchmark.py          # 80-trial multi-scenario benchmark runner
│   ├── prosody_evaluation.py     # Prosody comparative evaluation suite
│   ├── test_live_interrupted_turn_livekit.py # Live WebSocket timestamp diagnostic
│   ├── baselines/naive.py        # Unfenced baseline for comparison
│   └── results/                  # benchmark_summary.json & benchmark_trials.csv
├── tests/stress/                 # Unit & Stress Test Suite (61/61 Passing)
│   ├── test_full_duplex_proof.py # Full-duplex rubric integration proof (tool delay + barge-in + change)
│   ├── test_fence.py             # GenerationFence thread-safety & eviction
│   ├── test_tools.py             # Tool execution & result fencing tests
│   ├── test_state_manager.py     # Heard-text ledger & truncation tests
│   ├── test_rime_client.py       # Rime WebSocket clear operation tests
│   ├── test_rime_quickstart.py   # Rime quickstart validation tests
│   ├── test_session_wiring.py    # LiveKit event bridge & content setter regression tests
│   ├── test_text_normalize.py    # Phonetic normalizer domain expansion tests
│   └── test_pipeline_scenarios.py# Multi-turn scenario matrix tests
├── client/                       # Visual Debug HUD
│   └── index.html                # Interactive Mission Control & Web Audio spectrum visualizer
└── demo/                         # Demo Assets & Recording Script
    └── DEMO_GUIDE.md             # 4-minute video recording timeline
```

---

## 📋 12. Judging Criteria Alignment Matrix

| Hackathon Criterion | Weight | How RimeTrack Excels | Supporting Evidence |
|---|:---:|---|---|
| **Problem & Necessity of Voice** | 25% | Hands-busy workflow where removing speech destroys usability; solves context poisoning and stale tool bleed. | [`README.md §1`](#-1-problem--necessity-of-voice-judging-weight-25), [`RIME_EVIDENCE.md §1`](RIME_EVIDENCE.md) |
| **Hard Voice Engineering** | 25% | Monotonic GenerationFence, event-driven tool cancellation (<= 0.08ms), protocol-level WebSocket buffer clearing. | [`agent/fence.py`](agent/fence.py), [`agent/tool_executor.py`](agent/tool_executor.py), [`docs/ARCHITECTURE_REPORT.md`](docs/ARCHITECTURE_REPORT.md) |
| **Rime Integration & Experience** | 20% | Primary spoken output over WebSocket using `coda`/`astra`; per-word timestamp alignment; Writing for the Ear prompt engineering. | [`agent/session.py`](agent/session.py), [`agent/rime_ws_client.py`](agent/rime_ws_client.py), [`docs/PROSODY_ANALYSIS.md`](docs/PROSODY_ANALYSIS.md) |
| **Evidence & Reproducibility** | 20% | 80-trial empirical benchmark with 0.0% stale rate vs 100.0% baseline; 61 passing tests; raw trial CSV committed; live diagnostic script; preflight checker. | [`eval/results/benchmark_summary.json`](eval/results/benchmark_summary.json), [`eval/test_live_interrupted_turn_livekit.py`](eval/test_live_interrupted_turn_livekit.py), [`preflight_check.py`](preflight_check.py) |
| **Demo Clarity** | 10% | LiveKit Agents Playground direct token access, 4-minute video recording blueprint, and interactive Visual HUD. | [`README.md §LIVE DEMO`](#-live-demo--judge-testing-instructions), [`demo/DEMO_GUIDE.md`](demo/DEMO_GUIDE.md), [`client/index.html`](client/index.html) |

---

## ⚖️ License
MIT License. Built for the DataForge × Rime Hackathon Challenge (2026).

