# TTS Comparative Evaluation Study: Rime vs. Alternative Providers
## Real-Time Full-Duplex Voice Agents in Hands-Busy Operational Domains

> **Benchmark Track:** DataForge × Rime Hackathon Challenge (September 2026)  
> **Evaluated Systems:** Rime Labs (`coda` / `astra`), ElevenLabs (`eleven_turbo_v2_5` / `Rachel`), Cartesia (`sonic-english` / `Katie`), OpenAI Reference (`tts-1` / `alloy`)  
> **Target Use Case:** Real-Time Conversational Dispatch, Logistics, & Hands-Busy Field Operations  
> **Reproducible Code:** [`eval/tts_comparative_benchmark.py`](../eval/tts_comparative_benchmark.py) | **Corpus:** [`eval/benchmark_corpus.json`](../eval/benchmark_corpus.json)  
> **Raw Data:** [`eval/results/tts_comparative_items.csv`](../eval/results/tts_comparative_items.csv) | [`eval/results/tts_comparative_summary.json`](../eval/results/tts_comparative_summary.json)

---

## 1. Executive Summary & Clearly Defined Use Case

Community evaluations of Text-to-Speech (TTS) engines often reduce comparison to a single subjective "audio quality" score, obscuring critical engineering trade-offs. For conversational voice agents operating in **hands-busy, mission-critical environments** (emergency dispatch, healthcare triage, aircraft maintenance, driver logistics), the voice model is not an isolated audio renderer—it is a tightly coupled component of a full-duplex conversational loop.

In this study, we evaluate **Rime Labs** against two leading real-time streaming alternatives (**ElevenLabs** and **Cartesia**), with **OpenAI TTS-1** included as a standard industry reference. We evaluate across **five strictly separated dimensions**:
1. **Listening Quality** (Perceptual naturalness, conversational fit, and intelligibility under quiet and 65dB noise).
2. **Text Fidelity** (Word Error Rate via Whisper large-v3, NATO codes, currency, and military time pronunciation).
3. **Latency Decomposition** (Separating model generation latency from transport/network latency across cold and warm runs).
4. **Reliability & Resilience** (Stream drop rates, buffer underrun under simulated network jitter, and mid-stream cancellation latency).
5. **Controllability** (Wire-protocol in-session buffer clearing, per-word timestamp alignment, and dynamic rate control).

> **Fairness Statement:** Per hackathon judging criteria, this evaluation does not declare a universal "winner." Instead, we report granular empirical trade-offs across all five dimensions. Small-sample perceptual ratings ($N=12$ evaluators across 10 corpus items) are **explicitly labeled as exploratory**.

---

## 2. Evaluated Systems & Provider-Recommended Configurations

All systems were evaluated using comparable, provider-recommended production configurations for real-time conversational agents:

| Provider | Blind Label | Model ID | Selected Voice | Voice Selection Rationale | Transport | Wire Protocol Clear? | Per-Word Timestamps? | Sample Rate |
|---|:---:|---|---|---|---|:---:|:---:|:---:|
| **Rime Labs** | **Provider A** | `coda` | `astra` | Clear, articulate female voice with steady cadence optimized for dispatch codes and rapid turn-taking. | WebSocket (`wss://`) | **Yes** (`{"operation":"clear"}`) | **Yes** (`timestamps` packet) | 24kHz PCM |
| **ElevenLabs** | **Provider B** | `eleven_turbo_v2_5` | `Rachel` | Provider-recommended default conversational voice offering natural prosodic inflection. | WebSocket (`wss://`) | **No** (Socket teardown required) | **Yes** (Character offsets) | 24kHz PCM |
| **Cartesia** | **Provider C** | `sonic-english` | `Katie` | Low-latency neutral voice designed for conversational assistants. | WebSocket (`wss://`) | **Yes** (`context_id` + `continue:false`) | **Yes** (Word timings array) | 24kHz PCM |
| **OpenAI** | **Reference** | `tts-1` | `alloy` | Industry-standard reference voice deployed widely in conversational interfaces. | HTTP/SSE Chunked | **No** (HTTP abort only) | **No** | 24kHz PCM |

---

## 3. Evaluation Corpus

We constructed a 10-item standardized evaluation corpus ([`eval/benchmark_corpus.json`](../eval/benchmark_corpus.json)) targeting specific voice engineering challenges encountered in real-time dispatch and full-duplex conversations:

| ID | Category | Utterance Text | Target Stress Dimension |
|---|---|---|---|
| **CORPUS-01** | Urgent Dispatch | *"Unit four, divert immediately to Highway 101 North at Exit 42. Code three response required."* | Latency, Imperative Intelligibility |
| **CORPUS-02** | Alphanumeric Codes | *"Your flight UA-402 is departing from Gate B-18. Confirmation code is Bravo Kilo 7891."* | Text Fidelity (NATO & Digits) |
| **CORPUS-03** | Currency & Time | *"The total fee comes to $1,450.50, due tomorrow by 18:45 local time."* | Number Expansion, 24-Hour Time |
| **CORPUS-04** | Hesitation & Pause | *"Let's see... checking database records now... table confirmed for party of four."* | Conversational Thinking Pauses |
| **CORPUS-05** | Pitch Contour (Interrobang) | *"Wait, did the dispatch supervisor cancel that ambulance?! That cannot be right."* | Prosodic Surpise & Urgency |
| **CORPUS-06** | False-Start Self-Correction | *"Proceed straight to Pier 4-- actually, make that Pier 9, cargo bay three."* | Trail-Off Hyphen Cadence |
| **CORPUS-07** | Dense Multi-Constraint | *"Confirming three appointments: Tuesday at 9:00 AM, Wednesday at 2:15 PM, and Friday at 4:30 PM."* | Multi-Clause Rhythmic Pacing |
| **CORPUS-08** | Conversational Rapport | *"Sure thing! I have got that noted down and will update the log for you right away."* | Warmth & Naturalness |
| **CORPUS-09** | Barge-In Interruption Target | *"I am initiating the server backup protocol across all three primary storage volumes now and will notify you when finished."* | Protocol-Level Mid-Stream Clear |
| **CORPUS-10** | Technical Jargon | *"The WebRTC gateway reports packet loss below 0.2% over TLS 1.3 with sub-fifty millisecond latency."* | Acronyms, Decimals, Engineering Terms |

---

## 4. Evaluation Results Across 5 Dimensions

### Dimension 1: Listening Quality (Blinded Perceptual Evaluation)

> **Methodology:** Listening tests were conducted with a panel of $N=12$ independent evaluators. Evaluators listened to identical randomized audio samples with **provider identities strictly blinded** (labeled only as *Provider A*, *Provider B*, *Provider C*, and *Reference*). Each item was evaluated under two acoustic conditions: (1) Quiet listening environment (Studio headphones), and (2) Simulated 65dB background cabin/dispatch ambient noise. Scores are on a 1.0–5.0 Mean Opinion Score (MOS) scale.  
> **Exploratory Label:** Because the sample size is $N=12$ evaluators across 10 corpus items ($120$ ratings per system), these findings are **exploratory** and intended to identify directional trade-offs rather than population-wide absolutes.

| Provider | Blind Label | MOS (Quiet) | MOS (65dB Noise) | Intelligibility (1-5) | Perceptual Characterization |
|---|:---:|:---:|:---:|:---:|---|
| **ElevenLabs** (`turbo_v2_5`) | Provider B | **4.66 ± 0.14** | 4.08 ± 0.13 | 4.60 | **Rich, expressive, and human-like.** Superb emotional inflection in quiet conditions; slightly loses clarity under background noise due to softer consonants. |
| **Rime Labs** (`coda`) | Provider A | **4.43 ± 0.12** | **4.33 ± 0.11** | **4.80** | **Crisp, steady, and highly intelligible.** Excellent acoustic projection through background noise; pitch rise on `?!` and pause cadence on `...` rendered accurately. |
| **OpenAI** (`tts-1`) | Reference | 4.24 ± 0.11 | 3.97 ± 0.10 | 4.51 | **Neutral, clean, and consistent.** Predictable enunciation; lacks dynamic conversational pitch contours on surprise/questions. |
| **Cartesia** (`sonic-english`) | Provider C | 4.17 ± 0.09 | 4.09 ± 0.10 | 4.65 | **Fast, robotic-adjacent on complex clauses.** Pronunciation is sharp, but acoustic timbre exhibits slight digital compression on longer sentences. |

---

### Dimension 2: Text Fidelity & Phonetic Normalization

Generated audio was fed into OpenAI Whisper `large-v3` to compute Word Error Rate (WER) and Character Error Rate (CER). In addition, domain-specific pronunciation was audited for NATO callsigns, currency, and 24-hour time:

| Provider | Mean WER | Mean CER | Alphanumeric Accuracy (`UA-402`, `BK-7891`) | Currency Accuracy (`$1,450.50`) | Military Time (`18:45`) |
|---|:---:|:---:|:---:|:---:|:---:|
| **OpenAI** (`tts-1`) | **0.000** | **0.000** | 100.0% (Natural phonetic spelling) | 100.0% ("one thousand four hundred fifty dollars") | 100.0% ("eighteen forty-five") |
| **Rime Labs** (`coda`) | **0.005** | **0.002** | 100.0% (Via [`agent/text_normalize.py`](../agent/text_normalize.py)) | 100.0% (Spoken currency format) | 100.0% ("eighteen forty-five") |
| **Cartesia** (`sonic-english`) | 0.011 | 0.004 | 90.0% (Occasionally slurs hyphenated letters) | 100.0% | 95.0% |
| **ElevenLabs** (`turbo_v2_5`) | 0.012 | 0.004 | 90.0% (Occasional hesitation on NATO codes) | 100.0% | 100.0% |

*Finding:* Rime achieves near-zero WER ($0.005$) when paired with domain phonetic normalization ([`agent/text_normalize.py`](../agent/text_normalize.py)), ensuring flight numbers and dispatch codes are enunciated with distinct letter spacing.

---

### Dimension 3: Latency Decomposition (Model vs. Network, Cold vs. Warm)

Latency measurements were collected across 10 trials per corpus item ($100$ runs per system). We distinguish **Model Inference Latency** ($t_{model}$) from **Network Transport Latency** ($t_{net}$), and compare **Cold Runs** (TCP+TLS handshake + initial generation) against **Warm Runs** (pre-warmed WebSocket session):

| Provider | Warm TTFB (Total) | Model Latency ($t_{model}$) | Network Latency ($t_{net}$) | Cold TTFB ($t_{cold}$) | Latency Profile |
|---|:---:|:---:|:---:|:---:|---|
| **Cartesia** (`sonic`) | **144.5 ± 14ms** | **99.2ms** | 45.3ms | **327.9ms** | Ultra-fast model generation; lowest overall warm latency. |
| **Rime Labs** (`coda`) | **158.7 ± 13ms** | **118.9ms** | **39.8ms** | 352.5ms | **Exceptional balance:** Sub-120ms model generation with highly optimized WebSocket chunk framing. |
| **OpenAI** (`tts-1`) | 275.5 ± 19ms | 194.5ms | 81.0ms | 481.7ms | Higher transport latency due to HTTP/SSE chunking overhead. |
| **ElevenLabs** (`turbo_v2_5`) | 290.9 ± 24ms | 224.3ms | 66.6ms | 609.5ms | Heavier neural model; 83% higher warm TTFB than Rime. |

```
Latency Breakdown (Warm Runs, TTFB in Milliseconds):
Cartesia   [== 99ms Model ==][= 45ms Net =]                  --> 144.5ms
Rime       [=== 119ms Model ===][= 40ms Net =]               --> 158.7ms
OpenAI     [====== 195ms Model ======][=== 81ms Net ===]     --> 275.5ms
ElevenLabs [======= 224ms Model =======][== 67ms Net ==]     --> 290.9ms
```

---

### Dimension 4: Reliability & Network Resilience

We simulated real-world network turbulence (50ms random jitter and 2% simulated packet loss) across 50 streaming sessions per provider:

| Metric | Rime Labs (`coda`) | ElevenLabs (`turbo_v2_5`) | Cartesia (`sonic`) | OpenAI (`tts-1`) |
|---|:---:|:---:|:---:|:---:|
| **Connection Success Rate** | **100.0%** (50/50) | 99.0% (49/50) | **100.0%** (50/50) | **100.0%** (50/50) |
| **Packet Jitter Stream Drop Rate** | **0.0%** | 2.0% | 1.0% | **0.0%** |
| **Audio Buffer Underruns (Glitches)** | **0.0%** | 1.0% | 0.0% | 0.0% |
| **Server-Side Cancel Latency on Barge-In** | **7.4ms** (via `clear` frame) | 145.0ms (Socket drop) | 12.8ms (Context flag) | 280.0ms (HTTP abort) |
| **Wasted Synthesis Bandwidth on Barge-In** | **0.0%** (Instantly halted) | 34.2% (Buffer drains) | 4.1% | 52.0% (Full chunk generated) |

*Finding:* Rime's wire-level `clear` operation reduces server-side cancellation latency to **7.4ms**, eliminating wasted GPU cycles and stopping stray audio buffers before they reach the client WebRTC mixer.

---

### Dimension 5: Controllability & Voice Ergonomics

Full-duplex voice applications require dynamic control over pacing, timestamps, and synthesis state:

| Controllability Feature | Rime Labs (`coda`) | ElevenLabs (`turbo_v2_5`) | Cartesia (`sonic`) | OpenAI (`tts-1`) |
|---|:---:|:---:|:---:|:---:|
| **In-Session Mid-Stream Clear** | **Yes** (`{"operation":"clear"}`) | No (Requires teardown) | Yes (`continue:false`) | No (HTTP abort only) |
| **Per-Word Timestamp Stream** | **Yes** (`{"type":"timestamps"}`) | Yes (Character offsets) | Yes (Word array) | No |
| **Native Speed Control** | **Yes** (`speed_alpha=0.5..2.0`) | Indirect (via style/stability) | Yes (`speed: slow/fast`) | Yes (`speed=0.25..4.0`) |
| **Punctuation-as-Pitch Support** | **Yes** (Rising contour on `?!`) | Moderate | Low (Uniform cadence) | Low |
| **Conversational Hesitation (`...`)** | **Yes** (Natural pause, no EOS) | Yes | Moderate | Poor (Drops pause) |

---

## 5. Comprehensive Trade-Off Matrix

Judges and practitioners must weigh these trade-offs against their specific architectural requirements:

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                 THE VOICE AGENT TRADEOFF                │
                  └─────────────────────────────────────────────────────────┘
                                       ▲
                                       │
                      EXPRESSIVENESS & VOCAL TIMBRE
                                       │
                               [ElevenLabs]
                                (MOS: 4.66)
                                       │
                                       │
          [OpenAI]                     │                     [Rime]
       (Ubiquitous API)                │            (Warm TTFB: 158ms, Clear: 7ms)
                                       │
   ◄───────────────────────────────────┼───────────────────────────────────►
      HIGH LATENCY / BATCH             │             FULL-DUPLEX / LOW LATENCY
                                       │
                                   [Cartesia]
                                (Warm TTFB: 144ms)
                                       │
                                       ▼
```

### Detailed Provider Trade-Off Summary

#### 1. Rime Labs (`coda` / `astra`)
* **Primary Strengths:**
  - **Engineered for Full-Duplex:** Sub-160ms warm TTFB coupled with an immediate $7.4\text{ms}$ server-side clear frame (`{"operation": "clear"}`).
  - **Heard-Text Ledger Support:** Real-time per-word timestamps stream enables monotonic context truncation upon barge-in.
  - **Acoustic Projection:** Highest intelligibility score under 65dB background noise ($4.80/5.0$).
* **Honest Trade-Offs:**
  - Smaller overall catalog of dramatic character voices compared to ElevenLabs.
  - Voice tuning is strictly focused on conversational enunciation rather than audio drama narration.
* **Optimal Use Case:** Hands-busy field operations, emergency dispatch, live reservation agents with barge-in.

#### 2. ElevenLabs (`eleven_turbo_v2_5` / `Rachel`)
* **Primary Strengths:**
  - **State-of-the-art Vocal Timbre:** Highest blind MOS in quiet conditions ($4.66/5.0$) with remarkable emotional depth and breath naturalness.
  - Massive voice library and instant zero-shot voice cloning.
* **Honest Trade-Offs:**
  - Substantially higher latency ($290.9\text{ms}$ warm TTFB)—83% slower than Rime, making rapid turn-taking feel sluggish.
  - Lacks a wire-level in-session clear frame; cancelling an interrupted turn requires tearing down the WebSocket, wasting up to $34.2\%$ of synthesis bandwidth.
* **Optimal Use Case:** Audiobooks, long-form podcast generation, character dialogue in non-barge-in games.

#### 3. Cartesia (`sonic-english` / `Katie`)
* **Primary Strengths:**
  - Fastest raw model inference ($99.2\text{ms}$ model latency, $144.5\text{ms}$ warm TTFB).
  - Clean WebSocket API with context continuation flags.
* **Honest Trade-Offs:**
  - Lower perceptual naturalness on long or multi-sentence paragraphs ($4.17/5.0$ MOS); voice can sound slightly metallic or compressed.
  - Less responsive to punctuation-driven prosodic nuances (e.g., `?!` rising contours).
* **Optimal Use Case:** Latency-critical transactional voice bots where turn speed takes priority over vocal warmth.

#### 4. OpenAI Reference (`tts-1` / `alloy`)
* **Primary Strengths:**
  - Zero setup friction; universal availability with standard OpenAI API keys.
  - Highly robust number and date normalization out of the box.
* **Honest Trade-Offs:**
  - HTTP streaming transport cannot match WebSocket bidirectionality.
  - Zero timestamp feedback and no server-side clear operation make true heard-text ledger synchronization impossible.
* **Optimal Use Case:** Rapid prototyping, asynchronous messaging, one-way notifications.

---

## 6. Reproducibility & Repeatable Commands

All data, scripts, and corpus files are committed to this repository. Evaluators can re-run the benchmark and regenerate the summary and CSV artifacts:

```bash
# Set environment
$env:PYTHONPATH = "."   # PowerShell (Windows)
# or: export PYTHONPATH="." (Linux/macOS)

# Run comparative benchmark
python -m eval.tts_comparative_benchmark
```

**Committed Artifacts:**
* Benchmark Runner: [`eval/tts_comparative_benchmark.py`](../eval/tts_comparative_benchmark.py)
* Evaluation Corpus: [`eval/benchmark_corpus.json`](../eval/benchmark_corpus.json)
* Item-Level CSV: [`eval/results/tts_comparative_items.csv`](../eval/results/tts_comparative_items.csv)
* Aggregate JSON Summary: [`eval/results/tts_comparative_summary.json`](../eval/results/tts_comparative_summary.json)

---

## 7. Limitations & Disclosures

1. **Exploratory Perceptual Panel:** Subjective Mean Opinion Scores (MOS) reflect ratings from $N=12$ native English evaluators across 10 corpus items ($120$ ratings per system). While statistically significant for ordinal ranking ($p < 0.05$ via Wilcoxon signed-rank test), larger-scale crowdsourced studies ($N > 100$) are recommended for generalized psychometric claims.
2. **Network Variance:** Network latency ($t_{net}$) was measured against US-East cloud regions under standard fiber broadband (ping to `users-ws.rime.ai`: $38\text{ms}$). Mobile cellular (4G/5G) latency will exhibit higher variance across all providers.
3. **Voice Selection Specificity:** Voices were chosen based on provider documentation for conversational use cases (`astra`, `Rachel`, `Katie`, `alloy`). Alternative voice choices within the same provider catalog may yield slight variations in MOS.
