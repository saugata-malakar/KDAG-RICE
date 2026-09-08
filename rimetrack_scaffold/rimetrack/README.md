# RimeTrack: Real-Time Interruption Recovery & Tool Fencing for Voice Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 44/44 Passing](https://img.shields.io/badge/Tests-44%2F44%20Passing-brightgreen.svg)](tests/)
[![Rime TTS: Coda / Astra](https://img.shields.io/badge/Rime%20TTS-Coda%20%2F%20Astra%20(WS)-orange.svg)](https://rime.ai)

> **Submission for DataForge × Rime Hackathon Challenge (September 2026)**  
> **Primary Spoken Output Provider:** Rime TTS over WebSocket (`coda` / `astra` / `eng`).  
> **Repository:** [https://github.com/saugata-malakar/KDAG-RICE](https://github.com/saugata-malakar/KDAG-RICE)

---

## 🚀 Live Testing & Playground

Test the live full-duplex agent directly in your browser:

* **LiveKit Agents Playground:** [https://agents-playground.livekit.io/](https://agents-playground.livekit.io/)
* **Interactive Visual Debug HUD:** Open [`client/index.html`](client/index.html) in any browser to simulate speech streaming, barge-ins, and generation fencing in real-time.

### Quick Connection Parameters (LiveKit Playground):
| Field | Value |
|---|---|
| **LiveKit WebSocket URL** | `wss://rice-h02i5ol6.livekit.cloud` |
| **API Key** | `APIRJcVk6hmRMaN` |
| **API Secret** | `6BblsnTLhDteD4eQpjqyqAPeTJCAARCgho0IqliOeqcD` |

*(Connect with your microphone enabled to talk to RimeTrack and test real-time voice interruptions!)*

---

## 🎯 The Hard Voice Problem Solved

In hands-busy, mission-critical voice workflows (dispatch, field operations, real-time booking), voice is essential — removing speech destroys product usability. Humans interrupt, change constraints mid-sentence, and correct parameters while asynchronous tools execute in the background.

Standard voice agent frameworks suffer from two user-visible failure modes upon interruption:
1. **Context Poisoning (Hallucinated Grounding):** When an agent is interrupted mid-utterance, standard LLM histories store the *full generated text* instead of the *heard-text prefix*. The agent acts as though the user heard words that were never spoken aloud.
2. **Stale Tool Bleed (Phantom Side Effects):** When a slow background tool (e.g. database reservation, external API call) completes *after* the user interrupted to change their request, standard frameworks unconditionally apply the stale tool output to conversational state and speak the obsolete confirmation aloud.

### RimeTrack's Core Architectural Solutions:
* **`GenerationFence` (`agent/fence.py`):** Monotonically increasing generation IDs (`G1`, `G2`, `G3`, ...) gate all in-flight LLM tokens and tool execution results at the exact point of re-entry into shared conversation state.
* **Heard-Text Ledger (`agent/state_manager.py`):** Grounded directly in Rime's real-time per-word timestamp alignment over WebSocket (`push_timed_transcript`), recording strictly what reached audible playback before the interruption cut.
* **Protocol-Level Clear Operation (`agent/rime_ws_client.py`):** Binds to Rime's WebSocket wire protocol, transmitting `{"operation": "clear", "contextId": ...}` to immediately flush server-side synthesis buffers upon barge-in.
* **Pre-TTS Text Normalization (`agent/text_normalize.py`):** Strips LLM markdown artifacts and preserves Rime's `?!` interrobang prosody conventions.
* **Prosody Guidance (`agent/prompts.py`):** Direct prompt guidance on punctuation-as-pitch, conversational false-starts, and natural speech fillers.

---

## 📊 Empirical Benchmark Results (80 Trials per System, 160 Total)

We evaluated RimeTrack against the standard **Naive Baseline** across 80 empirical benchmark trials per system across 4 distinct failure scenarios using [`eval/run_benchmark.py`](eval/run_benchmark.py):

| Scenario Tested | Trials | RimeTrack Stale Response Rate | RimeTrack Stale Tool Bleed | Naive Baseline Stale Rate |
|---|:---:|:---:|:---:|:---:|
| **1. Mid-Speech Barge-In (3 of 10 words)** | 20 | **0.0%** (0/20) | 0.0% | **100.0%** (20/20) |
| **2. Cancellable Tool Interruption** | 20 | **0.0%** (0/20) | **0.0%** (20/20 aborted) | **100.0%** (20/20 applied) |
| **3. Uncancellable Tool (Result Fencing)** | 20 | **0.0%** (0/20) | **0.0%** (20/20 quarantined) | **100.0%** (20/20 applied) |
| **4. Rapid Double Barge-In** | 20 | **0.0%** (0/20) | 0.0% | **100.0%** (20/20 corrupted) |
| **OVERALL AGGREGATE** | **80** | **0.0%** | **0.0%** | **100.0% Stale Bleed** |

*Raw data files committed: [`eval/results/benchmark_summary.json`](eval/results/benchmark_summary.json) and [`eval/results/benchmark_trials.csv`](eval/results/benchmark_trials.csv).*

---

## 🛠️ Quickstart & Local Reproduction

### 1. Clone & Install
```bash
git clone https://github.com/saugata-malakar/KDAG-RICE.git
cd KDAG-RICE

# Create & activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in credentials:
```bash
cp .env.example .env
```

```ini
# --- LiveKit Cloud ---
LIVEKIT_URL=wss://rice-h02i5ol6.livekit.cloud
LIVEKIT_API_KEY=APIRJcVk6hmRMaN
LIVEKIT_API_SECRET=6BblsnTLhDteD4eQpjqyqAPeTJCAARCgho0IqliOeqcD

# --- Rime TTS (Primary Voice Provider) ---
RIME_API_KEY=your_rime_api_key
RIME_MODEL=coda
RIME_SPEAKER=astra
RIME_LANG=eng

# --- STT & LLM ---
OPENAI_API_KEY=your_openai_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key  # Optional: defaults to OpenAI Whisper STT if omitted
```

### 3. Run the Official Rime 5-Minute Quickstart
```bash
python rime_quickstart.py "Hello! This is Rime speaking from RimeTrack."
# Windows: start output.wav | macOS: afplay output.wav | Linux: aplay output.wav
```

### 4. Run the Full Test Suite (44/44 Passing)
```bash
$env:PYTHONPATH="." ; pytest -v
```

### 5. Run the Multi-Scenario Empirical Benchmark (80 Trials)
```bash
python -m eval.run_benchmark
```

### 6. Start the Live Voice Agent Worker
```bash
python -m agent.session dev
```

---

## 📁 Repository Structure

```
├── RIME_EVIDENCE.md          # Formal voice engineering claims, acceptance tests & evidence
├── README.md                 # Project documentation & quickstart guide
├── pyproject.toml            # Package configuration & dependencies
├── .env.example              # Sanitized credentials template
├── rime_quickstart.py        # Official Rime 5-minute HTTPS TTS quickstart script
├── agent/                    # Realtime Voice Agent Runtime
│   ├── fence.py              # GenerationFence (Monotonic authority & event bus)
│   ├── tool_executor.py      # Cancellable & uncancellable tool result fencing
│   ├── state_manager.py      # Heard-text ledger (Word-aligned truncation)
│   ├── rime_ws_client.py     # FencedRimeClient (Protocol-level clear operation gap fix)
│   ├── text_normalize.py     # Pre-TTS text normalization (markdown stripping, ?! prosody)
│   ├── pipeline.py           # End-to-end turn simulator for benchmarking
│   ├── session.py            # LiveKit AgentSession + Rime WebSocket worker
│   └── prompts.py            # System persona & Rime prosody instructions
├── eval/                     # Evaluation & Benchmark Suite
│   ├── metrics.py            # Formal metrics (Stale response rate, stop latency)
│   ├── run_benchmark.py      # Multi-scenario automated benchmark runner (80 trials)
│   ├── baselines/naive.py    # Naive baseline pipeline for comparison
│   └── results/              # benchmark_summary.json & benchmark_trials.csv
├── tests/stress/             # Unit & Integration Test Suite (44/44 Passing)
│   ├── test_fence.py         # GenerationFence race condition & staleness unit tests
│   ├── test_state_manager.py # Heard-text ledger & ChatMessage truncation tests
│   ├── test_rime_client.py   # Rime WebSocket clear operation & protocol tests
│   ├── test_rime_quickstart.py # Rime 5-min quickstart payload & header tests
│   ├── test_text_normalize.py# Text normalization & interrobang prosody tests
│   ├── test_session_wiring.py# LiveKit AgentSession event bridge integration tests
│   └── test_pipeline_scenarios.py # Multi-turn scenario matrix tests
├── client/                   # Interactive Visual Debug HUD
│   └── index.html            # Standalone visual simulation dashboard
├── demo/                     # Demo Assets & Recording Guide
│   └── DEMO_GUIDE.md         # 4-minute video recording script & walkthrough
└── docs/                     # Architectural Documentation
    └── architecture.md       # Sequence diagrams, data flows, and state machines
```

---

## ⚖️ License
MIT License. Built for the DataForge × Rime Hackathon Challenge (2026).
