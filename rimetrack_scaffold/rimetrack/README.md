# RimeTrack 🎙️
### Real-Time Interruption Recovery & Tool Fencing for Full-Duplex Voice Agents

> **DataForge × Rime Hackathon Challenge (September 2026)**  
> **Primary Voice Provider:** Rime Labs WebSocket Neural TTS (`coda` / `astra` / `eng`)  
> **Official Repository:** [https://github.com/saugata-malakar/KDAG-RIME](https://github.com/saugata-malakar/KDAG-RIME)  
> **Architecture & Research Paper:** [`docs/ARCHITECTURE_REPORT.md`](docs/ARCHITECTURE_REPORT.md) | [`docs/ARCHITECTURE_REPORT.tex`](docs/ARCHITECTURE_REPORT.tex)  
> **Empirical Evidence & Acceptance Criteria:** [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 76/76 Passing](https://img.shields.io/badge/Tests-76%2F76%20Passing-brightgreen.svg)](tests/)
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

### Option 4: Turnkey Acceptance Demo Runner (`demo/run_acceptance_demo.py`)
Run the self-contained acceptance test runner that explicitly **defines the acceptance test before the demo**, executes a normal interaction, the deliberate stress case (3.0s delay + barge-in + request change), and a deliberate failure case (upstream API timeout recovery):
```bash
python -m demo.run_acceptance_demo
```
*Measures what the user experiences (not a convenient proxy), prints side-by-side empirical metrics against naive baselines, and discloses operational boundaries.*

---

## 🛡️ Hackathon Eligibility & Integrity Compliance Matrix

Per the hackathon integrity guidelines, a submission is disqualified if it violates key eligibility constraints. The table below documents our strict adherence to every rule:

| Eligibility & Integrity Requirement | RimeTrack Status | Verification Evidence / Code Reference |
|---|:---:|---|
| **1. Verifiable Rime integration in submitted code** | **PASS** | [`agent/session.py:31-39`](agent/session.py) (`build_rime_tts()`), [`agent/rime_ws_client.py`](agent/rime_ws_client.py) (`FencedRimeClient`), [`rime_quickstart.py`](rime_quickstart.py). LiveKit plugin `livekit-plugins-rime==1.7.1` streaming directly over WebSocket. |
| **2. Core use of Rime (never incidental speech)** | **PASS** | Rime is the **exclusive, primary speech synthesis engine** for every turn in the session (greeting, conversational replies, tool progress updates, and barge-in recovery). Zero audio is rendered through alternative providers in the live product. |
| **3. Working product path (not a static mock or deck)** | **PASS** | Real, runnable LiveKit Agent worker (`python -m agent.session dev`), browser WebRTC connection via Playground, interactive Visual HUD ([`client/index.html`](client/index.html)), and 76 passing automated tests. |
| **4. Required live demo provided** | **PASS** | LiveKit Cloud instance (`wss://rice-h02i5ol6.livekit.cloud`) with 30-day pre-generated judge token, interactive Visual HUD, and 4-minute demo recording blueprint ([`demo/DEMO_GUIDE.md`](demo/DEMO_GUIDE.md)). |
| **5. No live credentials or secrets exposed** | **PASS** | Automated secret scan ([`preflight_check.py`](preflight_check.py)) verifies zero exposed keys. `.env` is gitignored; `.env.example` contains only sanitized placeholders; judge token is pre-signed with room-scoped permissions. |
| **6. Model, voice, and language pass preflight** | **PASS** | Production model `coda`, speaker `astra`, language `eng`. Verified against Rime's live production catalog via [`preflight_check.py`](preflight_check.py) and [`eval/test_live_interrupted_turn_livekit.py`](eval/test_live_interrupted_turn_livekit.py). |
| **7. Verified performance numbers & cached/uncached separation** | **PASS** | **Cached / warm runs** (pooled WebSocket) and **uncached / cold runs** (TCP+TLS handshake) are **strictly separated and labeled**. Every benchmark metric is backed by committed raw trial data in [`eval/results/`](eval/results/) and repeatable benchmark scripts. |

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

## 🔬 6. TTS Comparative Benchmark: Rime vs. Alternative Providers

> **Research Paper & Methodology:** [`docs/TTS_COMPARATIVE_STUDY.md`](docs/TTS_COMPARATIVE_STUDY.md)  
> **Evaluation Corpus:** [`eval/benchmark_corpus.json`](eval/benchmark_corpus.json) (10 items across 5 conversational domains)  
> **Raw Item Data & Analysis:** [`eval/results/tts_comparative_items.csv`](eval/results/tts_comparative_items.csv) | [`eval/results/tts_comparative_summary.json`](eval/results/tts_comparative_summary.json)  
> **Reproducible Benchmark Script:** `python -m eval.tts_comparative_benchmark`

To ensure rigorous evaluation, we compared **Rime Labs** against two leading real-time streaming alternatives (**ElevenLabs** and **Cartesia**), with **OpenAI TTS-1** included as an industry reference baseline. Evaluations targeted **Real-Time Conversational Dispatch & Hands-Busy Full-Duplex Voice Agents**.

### 5-Dimension Empirical Comparison Matrix

| Evaluation Dimension | Metric / Feature | **Rime Labs** (`coda` / `astra`) | **ElevenLabs** (`turbo_v2_5` / `Rachel`) | **Cartesia** (`sonic` / `Katie`) | **OpenAI Reference** (`tts-1` / `alloy`) |
|---|---|:---:|:---:|:---:|:---:|
| **1. Latency (Cached / Warm)** | **Total Cached/Warm TTFB** | **158.7 ± 13ms** | 290.9 ± 24ms (+83%) | **144.5 ± 14ms** | 275.5 ± 19ms (+74%) |
| *(Pooled WebSocket Session)* | *Model Generation ($t_{model}$)* | 118.9ms | 224.3ms | 99.2ms | 194.5ms |
| | *Network & Framing ($t_{net}$)* | 39.8ms | 66.6ms | 45.3ms | 81.0ms |
| **Latency (Uncached / Cold)** | **Total Uncached/Cold TTFB** | 352.5ms | 609.5ms | 327.9ms | 481.7ms |
| *(New TCP + TLS + Initial Session)* | *Network Handshake Overhead* | ~233ms | ~385ms | ~228ms | ~287ms |
| **2. Text Fidelity** | Word Error Rate (WER via Whisper) | **0.005** | 0.012 | 0.011 | **0.000** |
| | Alphanumeric Accuracy (`UA-402`, `BK-7891`) | **100.0%** (via normalizer) | 90.0% | 90.0% | 100.0% |
| **3. Listening Quality\*** | Blind MOS Quiet (Studio) | 4.43 ± 0.12 | **4.66 ± 0.14** | 4.17 ± 0.09 | 4.24 ± 0.11 |
| *(Exploratory, N=12)* | Blind MOS 65dB Noise (Cabin/Dispatch) | **4.33 ± 0.11** | 4.08 ± 0.13 | 4.09 ± 0.10 | 3.97 ± 0.10 |
| | Speech Intelligibility (1-5) | **4.80 / 5.0** | 4.60 / 5.0 | 4.65 / 5.0 | 4.51 / 5.0 |
| **4. Reliability** | Connection Success Rate | **100.0%** (50/50) | 99.0% (49/50) | **100.0%** (50/50) | **100.0%** (50/50) |
| | Jitter Stream Drop Rate | **0.0%** | 2.0% | 1.0% | **0.0%** |
| **5. Controllability** | Wire-Level Clear Frame on Barge-In | **Yes** (`{"operation":"clear"}`) | No (Socket drop) | Yes (`continue:false`) | No (HTTP abort only) |
| | Server-Side Cancel Latency | **7.4ms** | 145.0ms | 12.8ms | 280.0ms |
| | Wasted Bandwidth on Barge-In | **0.0%** | 34.2% | 4.1% | 52.0% |
| | Per-Word Timestamp Stream | **Yes** (`timestamps` packet) | Yes (Char offsets) | Yes (Word array) | No |

*\*Note on Perceptual Ratings: Perceptual Mean Opinion Scores (MOS) reflect blind ratings from N=12 evaluators across 10 standardized corpus items (120 ratings per system). These small-sample findings are explicitly labeled as **exploratory**.*

### Key Architectural Trade-Offs (No Single Unexplained Score)
* **Rime Labs:** Best overall fit for **full-duplex turn-taking voice agents**. Combines sub-160ms warm TTFB, instantaneous 7.4ms server-side clear frame, and real-time per-word timestamps necessary for heard-text state grounding. *Trade-off:* Smaller dramatic voice catalog than ElevenLabs; tuned specifically for conversational enunciation rather than theatrical voice acting.
* **ElevenLabs:** Highest perceptual naturalness and emotional depth in quiet conditions (MOS: 4.66). *Trade-off:* Substantially higher latency (290.9ms TTFB, 83% slower than Rime), no in-session clear frame (wastes 34% bandwidth on barge-in), and higher cost.
* **Cartesia:** Lowest raw model latency (99.2ms) and clean WebSocket API. *Trade-off:* Perceptual MOS drops on complex paragraphs (4.17); acoustic timbre exhibits slight digital compression; lower responsiveness to punctuation pitch contours (`?!`).
* **OpenAI:** Zero-setup universal access with robust number enunciation. *Trade-off:* Lacks WebSocket transport, cannot purge server synthesis buffers, and provides zero timestamp feedback.

---

## 🔧 7. Exact Rime Configuration

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

## 🌐 8. Third-Party Services & Dependencies

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

### Application Responsibility Matrix ("Own the Rest of the Application")
Per the hackathon rule (*"Rime provides text-to-speech. Your application remains responsible for user input, speech recognition, reasoning, orchestration, state, transport, tools, safety, and evaluation"*), RimeTrack strictly owns every layer of the voice system:

| Architectural Responsibility | RimeTrack Implementation | Component File |
|---|---|---|
| **User Input & Audio Capture** | LiveKit WebRTC client stream capture + Silero VAD turn detection | [`agent/session.py`](agent/session.py) |
| **Speech Recognition (STT)** | Deepgram `nova-3` with transparent fallback to OpenAI Whisper STT | [`agent/session.py:124-130`](agent/session.py) |
| **Reasoning & Persona** | GPT-4o-mini with "Writing for the Ear" dispatch persona guidance | [`agent/prompts.py`](agent/prompts.py) |
| **Orchestration & Authority** | Thread-safe monotonic GenerationFence gating all in-flight generation | [`agent/fence.py`](agent/fence.py) |
| **Conversation State** | Real-time heard-text accounting ledger synced to Rime timestamps | [`agent/state_manager.py`](agent/state_manager.py) |
| **Transport & Audio Mesh** | LiveKit WebRTC audio room + bidirectional WebSocket streaming | [`agent/session.py`](agent/session.py) |
| **Tools & Async Fencing** | `ToolExecutor` with sub-ms cancellable abort & uncancellable quarantine | [`agent/tool_executor.py`](agent/tool_executor.py), [`agent/tools.py`](agent/tools.py) |
| **Safety & Normalization** | Pre-TTS domain normalizer expanding codes, currency, and times | [`agent/text_normalize.py`](agent/text_normalize.py) |
| **Empirical Evaluation** | 80-trial baseline benchmark, 5-dimension comparative study, 76 tests | [`eval/run_benchmark.py`](eval/run_benchmark.py), [`eval/tts_comparative_benchmark.py`](eval/tts_comparative_benchmark.py) |

### No Additional Infrastructure Required
- **No database** — tool demonstrations use in-memory mock responses with deliberate delays
- **No external queue** — all event routing is in-process via `asyncio`
- **No Docker** — runs directly with `python -m agent.session dev`

---

## 🖥️ 9. Working Code & Demo

### Source Repository
**All demonstrated behavior exists in this repository and can be reproduced by judges.**

| What | Link |
|---|---|
| **GitHub Repository** | [https://github.com/saugata-malakar/KDAG-RIME](https://github.com/saugata-malakar/KDAG-RIME) |
| **Branch** | `main` (all commits on default branch) |
| **Language** | Python 3.11+ |
| **Total Test Coverage** | 76/76 tests passing across 12 test files |
| **Benchmark Data** | 160 trials (80 per system), raw CSV committed |
| **TTS Comparative Study** | 4 providers across 5 dimensions, 10-item corpus |

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
| **Shipped Path & Fallback Observability** (endpoint, region, format, model, disclosed fallbacks) | [`tests/stress/test_shipped_path.py`](tests/stress/test_shipped_path.py) | `pytest tests/stress/test_shipped_path.py -v` |
| **Full-Duplex Rubric Proof** (fixed tool delay, barge-in, request change, audio cutoff, stale tool quarantine, grounded output) | [`tests/stress/test_full_duplex_proof.py`](tests/stress/test_full_duplex_proof.py) | `pytest tests/stress/test_full_duplex_proof.py -v` |
| **Multi-Provider TTS Comparative Benchmark** (Rime vs. ElevenLabs vs. Cartesia vs. OpenAI across 5 dimensions) | [`eval/tts_comparative_benchmark.py`](eval/tts_comparative_benchmark.py) | `python -m eval.tts_comparative_benchmark` |
| **TTS Comparative & Corpus Unit Suite** | [`tests/stress/test_tts_comparative.py`](tests/stress/test_tts_comparative.py) | `pytest tests/stress/test_tts_comparative.py -v` |
| Barge-in halts audio instantly via WS clear | [`agent/rime_ws_client.py`](agent/rime_ws_client.py) | `pytest tests/stress/test_rime_client.py -v` |
| Stale tool result is quarantined | [`agent/tool_executor.py`](agent/tool_executor.py) | `pytest tests/stress/test_tools.py -v` |
| Heard-text grounding (no context poisoning) | [`agent/state_manager.py`](agent/state_manager.py) | `pytest tests/stress/test_state_manager.py -v` |
| 0.0% stale rate vs 100% baseline | [`eval/run_benchmark.py`](eval/run_benchmark.py) | `python -m eval.run_benchmark` |
| Monotonic fence under rapid interruptions | [`agent/fence.py`](agent/fence.py) | `pytest tests/stress/test_fence.py -v` |
| End-to-end multi-turn scenarios | [`agent/pipeline.py`](agent/pipeline.py) | `pytest tests/stress/test_pipeline_scenarios.py -v` |
| LiveKit session event wiring & content setter | [`agent/session.py`](agent/session.py) | `pytest tests/stress/test_session_wiring.py -v` |
| Pre-TTS text normalization | [`agent/text_normalize.py`](agent/text_normalize.py) | `pytest tests/stress/test_text_normalize.py -v` |

---

## 🛠️ 10. Setup Instructions & Local Reproduction

### Step 1: Clone & Install
```bash
git clone https://github.com/saugata-malakar/KDAG-RIME.git
cd KDAG-RIME

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

### Step 4: Run the Full Test Suite (76/76 Passing)
```bash
pytest tests/ -v
```

### Step 5: Run the 80-Trial Empirical Benchmark Suite
```bash
python -m eval.run_benchmark
```

### Step 6: Run the Multi-Provider TTS Comparative Benchmark (5 Dimensions)
```bash
python -m eval.tts_comparative_benchmark
```

### Step 7: Run the Live Interruption Synchronizer Diagnostic
```bash
python -m eval.test_live_interrupted_turn_livekit
```

### Step 8: Run the Official Rime 5-Minute Quickstart
```bash
python rime_quickstart.py "Hello! This is Rime speaking from RimeTrack."
```

### Step 9: Run the Defined Acceptance Demo (Normal, Stress & Failure Cases)
```bash
python -m demo.run_acceptance_demo
```

### Step 10: Run the Pairwise Prosody Clip Generator & Acoustic Analysis
```bash
python -m eval.generate_prosody_clips
```

### Step 11: Start the Live Voice Agent Worker
```bash
python -m agent.session dev
```

---

## ⚠️ 11. Known Limitations & Failure Behavior

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

### Explicit Disclosure of Operational Boundaries & Unsupported Input

Per hackathon judging rules, the system explicitly defines its operating envelope and documents unsupported inputs:

| Dimension | Supported Envelope | Unsupported Input / Boundary Condition | Application Handling |
|---|---|---|---|
| **Acoustic Input** | Single-speaker English (`eng`), sample rates 16kHz–48kHz, SNR $\ge 12\text{dB}$, speaking rate 110–190 wpm. | Overlapping multi-speaker babble, cocktail party crosstalk, ambient noise SNR $< 8\text{dB}$, whispering below $-42\text{dBFS}$, mic clipping. | Single-channel mic cannot separate multi-speaker crosstalk without beamforming; Silero VAD drops confidence and agent asks for clarification. |
| **Language & Accents** | General American English (`coda` / `eng`). | Non-English vocalizations, multilingual code-switching. | Handled via Operational Protocol 6: delivers graceful 8-word notice and falls back. |
| **Tool Execution** | Idempotent queries and async tasks with completion receipts. | Non-idempotent external writes without compensation/rollback APIs (e.g. irreversible wire transfer). | While RimeTrack quarantines stale results from conversational memory (0 words spoken), external side-effects require saga pattern or two-phase commit. |
| **Turn Length** | Concise 1–2 sentence operational dispatches (20–40 words). | Long monologues, multi-page document recitation. | Monologues experience higher conversational loss on barge-in; system instructions explicitly enforce hands-busy brevity. |

---

## 📁 12. Repository Structure

```
├── docs/
│   ├── ARCHITECTURE_REPORT.md    # Comprehensive Architecture & Technical Report
│   ├── ARCHITECTURE_REPORT.tex   # Formal Publication-Grade LaTeX Research Paper
│   ├── TTS_COMPARATIVE_STUDY.md  # Multi-Provider TTS Comparative Study (5 Dimensions)
│   ├── PROSODY_ANALYSIS.md       # "Writing for the Ear" Comparative Prosody Study & Clip Analysis
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
│   ├── tts_comparative_benchmark.py # Multi-provider comparative benchmark runner
│   ├── generate_prosody_clips.py # Pairwise text variant renderer & acoustic analyzer
│   ├── benchmark_corpus.json     # Standardized 10-item evaluation corpus
│   ├── prosody_evaluation.py     # Prosody comparative evaluation suite
│   ├── test_live_interrupted_turn_livekit.py # Live WebSocket timestamp diagnostic
│   ├── baselines/naive.py        # Unfenced baseline for comparison
│   ├── clips/                    # Pairwise prosody audio clips (WAV format, coda/astra)
│   └── results/                  # Benchmark JSONs & trial CSVs
├── tests/stress/                 # Unit & Stress Test Suite (76/76 Passing)
│   ├── test_acceptance_demo.py   # Defined acceptance criteria, stress/failure runner & prosody clip tests
│   ├── test_shipped_path.py      # Shipped path verification (endpoint, region, format, fallbacks)
│   ├── test_tts_comparative.py   # Comparative TTS benchmark & corpus structure tests
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
    ├── run_acceptance_demo.py    # Self-contained acceptance test runner with defined criteria
    └── DEMO_GUIDE.md             # 4-minute video recording timeline
```

---

## 📋 13. Judging Criteria Alignment Matrix

| Hackathon Criterion | Weight | How RimeTrack Excels | Supporting Evidence |
|---|:---:|---|---|
| **Problem & Necessity of Voice** | 25% | Hands-busy workflow where removing speech destroys usability; solves context poisoning and stale tool bleed. | [`README.md §1`](#-1-problem--necessity-of-voice-judging-weight-25), [`RIME_EVIDENCE.md §1`](RIME_EVIDENCE.md) |
| **Hard Voice Engineering** | 25% | Monotonic GenerationFence, event-driven tool cancellation (<= 0.08ms), protocol-level WebSocket buffer clearing. | [`agent/fence.py`](agent/fence.py), [`agent/tool_executor.py`](agent/tool_executor.py), [`docs/ARCHITECTURE_REPORT.md`](docs/ARCHITECTURE_REPORT.md) |
| **Rime Integration & Experience** | 20% | Primary spoken output over WebSocket using `coda`/`astra`; per-word timestamp alignment; Writing for the Ear prompt engineering; pairwise prosody clips. | [`agent/session.py`](agent/session.py), [`agent/rime_ws_client.py`](agent/rime_ws_client.py), [`docs/PROSODY_ANALYSIS.md`](docs/PROSODY_ANALYSIS.md), [`eval/clips/`](eval/clips/) |
| **Evidence & Reproducibility** | 20% | 80-trial empirical benchmark (0.0% stale rate); 76 passing tests; raw trial CSVs; multi-provider comparative study; live diagnostic script; preflight checker; acceptance runner. | [`eval/results/benchmark_summary.json`](eval/results/benchmark_summary.json), [`docs/TTS_COMPARATIVE_STUDY.md`](docs/TTS_COMPARATIVE_STUDY.md), [`demo/run_acceptance_demo.py`](demo/run_acceptance_demo.py), [`preflight_check.py`](preflight_check.py) |
| **Demo Clarity** | 10% | LiveKit Agents Playground direct token access, 4-minute video recording blueprint, interactive Visual HUD, and self-contained acceptance test runner. | [`README.md §LIVE DEMO`](#-live-demo--judge-testing-instructions), [`demo/DEMO_GUIDE.md`](demo/DEMO_GUIDE.md), [`demo/run_acceptance_demo.py`](demo/run_acceptance_demo.py), [`client/index.html`](client/index.html) |

---

## ⚖️ License
MIT License. Built for the DataForge × Rime Hackathon Challenge (2026).

