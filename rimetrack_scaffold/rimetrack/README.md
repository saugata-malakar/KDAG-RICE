# RimeTrack 🎙️
### Real-Time Interruption Recovery & Tool Fencing for Full-Duplex Voice Agents

> **DataForge × Rime Hackathon Challenge (September 2026)**  
> **Primary Voice Provider:** Rime Labs WebSocket Neural TTS (`coda` / `astra` / `eng`)  
> **Official Repository:** [https://github.com/saugata-malakar/KDAG-RICE](https://github.com/saugata-malakar/KDAG-RICE)  
> **Architecture & Research Paper:** [`docs/ARCHITECTURE_REPORT.md`](docs/ARCHITECTURE_REPORT.md) | [`docs/ARCHITECTURE_REPORT.tex`](docs/ARCHITECTURE_REPORT.tex)  
> **Empirical Evidence & Acceptance Criteria:** [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 55/55 Passing](https://img.shields.io/badge/Tests-55%2F55%20Passing-brightgreen.svg)](tests/)
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

### Option 2: Live Hackathon Acceptance Test Flow
Once connected, test the exact stress challenge defined in the hackathon brief:
1. **Trigger Normal Flow with Tool Delay:**  
   Say aloud: *"Book a table for two at Olive Garden at 7:00 PM."*  
   *(The agent initiates `book_restaurant` with a deliberate 3.0-second delay).*
2. **Interrupt Mid-Turn (Barge-In):**  
   While the agent speaks or waits, interrupt clearly:  
   *"Wait, change that to 8:30 PM for four people!"*
3. **Verify Acceptance Criteria:**  
   - ✅ **Acoustic cut-off:** Audio halts instantly (<= 1ms) via Rime WebSocket `{"operation": "clear"}` frame.
   - ✅ **No Stale Tool Bleed:** The 7:00 PM booking is **quarantined by the `GenerationFence`** and never spoken.
   - ✅ **Grounded Context:** The agent completes the revised 8:30 PM reservation without context poisoning.

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

| Criterion | What is Tested | Acceptance Condition | Status |
|---|---|---|:---:|
| **AC-1: Heard-Text Grounding** | Barge-in mid-sentence during Rime speech playback | Next turn's prompt context contains **only the words the user actually heard** before the interrupt. | ✅ Verified |
| **AC-2: Cancellable Tool Abort** | Barge-in while an async API call is in-flight | In-flight background task receives cancellation within <= 1.0ms; no stale audio is synthesized. | ✅ Verified |
| **AC-3: Uncancellable Tool Fencing** | Fixed delay in an irreversible DB tool completes *after* interrupt | Tool finishes in background, but the result is **quarantined by the `GenerationFence`** and never spoken aloud. | ✅ Verified |
| **AC-4: Protocol-Level WS Clearing** | Rapid back-to-back user barge-ins | Explicit `{"operation": "clear", "contextId": ...}` is sent over Rime WebSocket to clear server synthesis buffers. | ✅ Verified |

---

## 🔊 5. Rime Integration & Voice Experience (Judging Weight: 20%)

* **Production Model & Speaker:** `coda` model with `astra` speaker, configured for natural, conversational prosody (`speed_alpha=1.0`).
* **Transport:** Full-duplex WebSocket streaming (`use_websocket=True`) to enable mid-stream cancellation and per-word timestamp alignment.
* **Writing for the Ear Compliance:** System prompt in [`agent/prompts.py`](agent/prompts.py) implements Brooke Larson's guidelines for punctuation-as-pitch, conversational fillers, and register pacing.
* **Pre-TTS Normalization:** [`agent/text_normalize.py`](agent/text_normalize.py) expands domain flight codes (`UA-402` -> `UA 402`), tracking IDs (`BK-5521` -> `BK 5521`), currency, and times into spoken form while preserving Rime's `?!` interrobang inflection convention.
* **Prosody Analysis Report:** Full comparative evaluation in [`docs/PROSODY_ANALYSIS.md`](docs/PROSODY_ANALYSIS.md).
* **Transparent Fallback Disclosure:** Speech recognition defaults to Deepgram (`nova-3`), transparently falling back to OpenAI Whisper STT when Deepgram is unavailable.

---

## 🛠️ 6. Quickstart & Local Reproduction

### 1. Installation
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

### 2. Configure Credentials (Local Mode)
Copy `.env.example` to `.env` and provide your credentials (excluded from git):
```bash
cp .env.example .env
```
Environment variables supported:
* `LIVEKIT_URL`: LiveKit Cloud project URL (`wss://...`)
* `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`: LiveKit credentials
* `RIME_API_KEY`: Rime Labs API Key
* `RIME_MODEL`: `coda` (default)
* `RIME_SPEAKER`: `astra` (default)
* `OPENAI_API_KEY`: OpenAI Key (for LLM and STT fallback)
* `DEEPGRAM_API_KEY`: Deepgram Key (optional; falls back to OpenAI Whisper)

### 3. Run the Full Test Suite (55/55 Passing)
```bash
pytest tests/ -v
```

### 4. Run the 80-Trial Empirical Benchmark Suite
```bash
python -m eval.run_benchmark
```

### 5. Run the Live Interruption Synchronizer Diagnostic
```bash
python -m eval.test_live_interrupted_turn_livekit
```

### 6. Run the Official Rime 5-Minute Quickstart
```bash
python rime_quickstart.py "Hello! This is Rime speaking from RimeTrack."
```

### 7. Start the Live Voice Agent Worker
```bash
python -m agent.session dev
```

---

## 📁 7. Repository Structure

```
├── docs/
│   ├── ARCHITECTURE_REPORT.md    # Comprehensive Architecture & Technical Report
│   ├── ARCHITECTURE_REPORT.tex   # Formal Publication-Grade LaTeX Research Paper
│   ├── PROSODY_ANALYSIS.md       # "Writing for the Ear" Comparative Prosody Study
│   └── architecture.md          # Sequence diagrams & data flows
├── RIME_EVIDENCE.md              # Formal voice claims, acceptance criteria & sync analysis
├── README.md                     # Master documentation, live judge token & benchmark summary
├── pyproject.toml                # Package configuration & test dependencies
├── .env.example                  # Sanitized environment template
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
├── tests/stress/                 # Unit & Stress Test Suite (55/55 Passing)
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

## 📋 8. Judging Criteria Alignment Matrix

| Hackathon Criterion | Weight | How RimeTrack Excels | Supporting Evidence |
|---|:---:|---|---|
| **Problem & Necessity of Voice** | 25% | Hands-busy workflow where removing speech destroys usability; solves context poisoning and stale tool bleed. | [`README.md §1`](#1-problem--necessity-of-voice-judging-weight-25), [`RIME_EVIDENCE.md §1`](RIME_EVIDENCE.md) |
| **Hard Voice Engineering** | 25% | Monotonic GenerationFence, event-driven tool cancellation (<= 0.08ms), protocol-level WebSocket buffer clearing. | [`agent/fence.py`](agent/fence.py), [`agent/tool_executor.py`](agent/tool_executor.py), [`docs/ARCHITECTURE_REPORT.md`](docs/ARCHITECTURE_REPORT.md) |
| **Rime Integration & Experience** | 20% | Primary spoken output over WebSocket using `coda`/`astra`; per-word timestamp alignment; Writing for the Ear prompt engineering. | [`agent/session.py`](agent/session.py), [`agent/rime_ws_client.py`](agent/rime_ws_client.py), [`docs/PROSODY_ANALYSIS.md`](docs/PROSODY_ANALYSIS.md) |
| **Evidence & Reproducibility** | 20% | 80-trial empirical benchmark with 0.0% stale rate vs 100.0% baseline; 55 passing tests; raw trial CSV committed; live diagnostic script. | [`eval/results/benchmark_summary.json`](eval/results/benchmark_summary.json), [`eval/test_live_interrupted_turn_livekit.py`](eval/test_live_interrupted_turn_livekit.py) |
| **Demo Clarity** | 10% | LiveKit Agents Playground direct token access, 4-minute video recording blueprint, and interactive Visual HUD. | [`README.md §LIVE DEMO`](#live-demo--judge-testing-instructions), [`demo/DEMO_GUIDE.md`](demo/DEMO_GUIDE.md), [`client/index.html`](client/index.html) |

---

## ⚖️ License
MIT License. Built for the DataForge × Rime Hackathon Challenge (2026).
