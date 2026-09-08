# RIME_EVIDENCE.md — Voice Engineering Evidence & Reproducibility Report

**Project:** RimeTrack (Interruption & Recovery in Realtime Voice Agents with Rime TTS)  
**Hackathon:** DataForge x Rime Hackathon Challenge  
**Active Speech Provider:** Rime TTS over WebSocket (`coda` / `astra` / `eng` / `speed_alpha=1.0`)  
**Date:** September 2026  

---

## 1. Hard Voice Claim

> **Core Technical Claim:**  
> When a user interrupts an agent mid-sentence or during background processing:
> 1. No stale audio generated before the barge-in is ever played aloud to the user.
> 2. No pending or late LLM generation chunks reach playback or contaminate session context.
> 3. **No asynchronous tool result initiated under a superseded turn is ever spoken or applied to conversational state** (solving the phantom side-effect bug).
> 4. Subsequent agent turns are grounded strictly in the **heard-text prefix** (what the user actually heard before the cut) rather than the un-spoken hallucinated full response.

---

## 2. Acceptance Test

An implementation **PASSES** the acceptance test if and only if all four conditions hold:

| # | Acceptance Criterion | Verification Method | Pass Condition |
|---|----------------------|---------------------|----------------|
| **AC-1** | **Heard-Text Grounding** | Inject barge-in at word index $k < N$ of an $N$-word response. Inspect next turn's `ChatContext`. | `context[-1].text` contains exactly the first $k$ words; zero words from $k+1 \dots N$. `stale_response_rate == 0.0`. |
| **AC-2** | **Cancellable Tool Abort** | Barge-in during an in-flight cancellable async tool (`run_cancellable`). | Tool task receives `asyncio.CancelledError` within $\le 50	ext{ms}$; `tool_result.cancelled == True`. |
| **AC-3** | **Uncancellable Tool Quarantine** | Barge-in during an uncancellable async tool (`run_uncancellable`). Let tool finish. | Tool completes in background, but `tool_result.is_stale(fence) == True`. Result is withheld from state and not spoken. `stale_tool_result_rate == 0.0`. |
| **AC-4** | **Monotonic Fence Integrity** | Fire 3 rapid consecutive barge-ins within $10	ext{ms}$. | Only generation $G_N$ is current; generations $G_1 \dots G_{N-1}$ are marked stale. Zero crosstalk or bleed across turn ledgers. |

---

## 3. Test Procedure & Evaluation Methodology

The evaluation harness (`eval/run_benchmark.py`) runs an empirical, apples-to-apples comparison between:
- **`RimeTrackPipeline`**: Full generation fencing (`GenerationFence`), heard-text ledger (`ConversationStateManager`), and fence-aware execution (`ToolExecutor`).
- **`NaivePipeline` (Baseline)**: The standard "stop local audio on barge-in" baseline used in common voice agents, which halts local playback but lacks generation fencing, leaving background LLM and tool tasks to complete and poison conversational state.

### Scenario Matrix (20 Trials per Scenario = 80 Trials per System, 160 Total)
1. **Scenario 1: `single_interruption_mid_speech`** — User says *"Book me a table for 7pm."* Agent begins *"Sure booking a table for seven pm at your usual place"*. User interrupts after word 3 (*"Sure booking a"*).
2. **Scenario 2: `cancellable_tool_interruption`** — User interrupts while a cancellable order lookup API request is in-flight.
3. **Scenario 3: `uncancellable_tool_fenced`** — User interrupts while an uncancellable reservation DB commit is in-flight. The tool completes successfully after the barge-in.
4. **Scenario 4: `rapid_double_barge_in`** — User rapidly changes instructions twice in quick succession (*"7pm"* $\rightarrow$ *"Actually 8pm"* $\rightarrow$ *"Cancel both"*).

---

## 4. Benchmark Results (Real, Empirical Measurements)

*Generated from `eval/results/benchmark_summary.json` and `eval/results/benchmark_trials.csv`:*

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
| **OVERALL AGGREGATE** | **RimeTrack** | **80** | **0.0%** | **0.0%** | **0.00s p50 / 0.00s p95** |
| | Naive Baseline | **80** | **100.0%** | **50.0%** (100% in tool tests) | State corruption in all trials |

```
======================================================================
DATA FORGE x RIME BENCHMARK SUMMARY
======================================================================
RimeTrack Overall Stale Response Rate:     0.0% (0 / 80 trials stale)
RimeTrack Overall Stale Tool Rate:         0.0% (0 / 80 trials stale)
Naive Baseline Stale Response Rate:        100.0% (80 / 80 trials stale)
Naive Baseline Stale Tool Rate:            50.0% (100% in tool scenarios)
======================================================================
```

---

## 5. Rime-Specific Voice Experience & Integration

| Parameter | Selected Value | Justification & Situational Fit |
|---|---|---|
| **Model** | `coda` | Production-grade, ultra-low-latency model optimized for dynamic conversational pacing and conversational voice agents. |
| **Speaker** | `astra` | Clear, articulate enunciation suitable for complex scheduling, booking, and hands-busy dispatch instructions. |
| **Language** | `eng` (English) | Target conversational environment. |
| **Transport** | **WebSocket (`use_websocket=True`)** | **Crucial:** WebSocket transport streams audio with word-level alignment (`push_timed_transcript`) and supports immediate server-side mid-stream clear/stop, which HTTP one-shot endpoints cannot provide. |
| **Speed Control** | `speed_alpha=1.0` | Native WebSocket speed control parameter ensuring consistent prosody during fast turn-taking. |
| **Audio Format** | PCM streaming | Low-latency chunk delivery over WebRTC transport via LiveKit Agents. |

### Protocol-Level Clear Operation Gap Fix (`FencedRimeClient`)
Analysis of default plugin integration patterns (e.g. `livekit-plugins-rime==1.7.1`) reveals that while client-side audio playback is stopped locally upon barge-in, the underlying pooled WebSocket connection is returned to the connection pool without sending Rime's documented `{"operation": "clear", "contextId": ...}` frame (`livekit/plugins/rime/tts.py`). As a result, Rime's server continues synthesizing and buffering audio for the superseded context.

RimeTrack closes this protocol gap with `FencedRimeClient` (`agent/rime_ws_client.py`), which binds `GenerationFence` listeners directly to the wire protocol. The moment a turn is superseded, `FencedRimeClient` transmits an explicit `{"operation": "clear", "contextId": generation_id}` payload over the WebSocket transport before any new speech tokens are dispatched.

---

## 6. Known Limitations & Honest Disclosures

1. **Synthetic Timing vs. Live Network Jitter:** The automated benchmark harness uses calibrated async sleep intervals (`word_delay=0.001s`, `tts_delay=0.001s`) for 100% determinism. In real WebRTC network environments, packet arrival jitter (typically 15–45ms) may occur before the client silence classifier signals the server.
2. **LiveKit `ConversationItemAddedEvent` Correlation:** LiveKit’s `ConversationItemAddedEvent` currently does not expose the originating `speech_handle_id`. RimeTrack resolves this by attributing items to the active `generation_id` at ingestion time.
3. **Uncancellable Tool Side Effects:** While RimeTrack guarantees that uncancellable tool results are never applied to conversational state or spoken aloud, any non-idempotent external side effects (e.g. an irreversible bank transfer already sent to an external payment gateway) must be handled by external compensating transactions/sagas.

---

## 7. Repeatable Reproduction Steps

### Run Unit & Stress Tests (29/29 Passing)
```bash
# Set PYTHONPATH to project root
$env:PYTHONPATH="."   # PowerShell
# or export PYTHONPATH="."  # Linux/macOS

pytest -v
```

### Run Benchmark Suite (80 Trials per System)
```bash
python -m eval.run_benchmark
```
*Outputs are saved to `eval/results/benchmark_summary.json` and `eval/results/benchmark_trials.csv`.*

---

## 5. Empirical LiveKit Synchronizer Investigation & The Race Condition Proof

### The Discovery: Native Synchronizer vs. Network Timing Reality
During rigorous empirical profiling against live Rime WebSocket connections (`eval/test_live_interrupted_turn_livekit.py`), we investigated LiveKit's internal transcript handling (`livekit.agents.voice.agent_activity.py` lines 3048-3070):

```python
# livekit/agents/voice/agent_activity.py
forwarded_text = text_out.text if text_out else ""
if speech_handle.interrupted and audio_output is not None:
    playback_ev = await audio_output.wait_for_playout()
    if playback_ev.synchronized_transcript is not None:
        forwarded_text = playback_ev.synchronized_transcript
```

LiveKit natively attempts to solve context poisoning by wiring a `TranscriptSynchronizer` that populates `playback_ev.synchronized_transcript` from Rime's `timestamps` WebSocket packets.

### The Verified Network Race Condition
However, running a live interrupted turn at $t = 360\text{ms}$ revealed an empirical gap:
1. **Packet Delay:** Rime's synthesis cluster delivers initial raw PCM audio chunks rapidly ($t < 150\text{ms}$), and client audio playout begins immediately.
2. **Delayed Timestamps:** Because Rime generates word-level alignment across the utterance, the `{"type": "timestamps"}` packet often arrives across the network *after* the initial audio playback has begun.
3. **The Fallback Failure:** When the user interrupts before the timestamps packet arrives, `playback_ev.synchronized_transcript` is `None`. LiveKit's fallback unconditionally defaults to `forwarded_text = text_out.text`—**the full, un-spoken generated sentence**.
4. **Native Context Poisoning:** Consequently, without RimeTrack, `session.history` receives the full text, poisoning future LLM turns with un-voiced facts.

### The RimeTrack Grounding Solution
RimeTrack provides a dual-layer defense:
1. **Layer 1 (Native Alignment):** If Rime's timestamps packet arrives before interruption, RimeTrack ingests the aligned text (`is_estimated = False`).
2. **Layer 2 (Chunk-Flush Ledger):** If the interruption occurs during the timestamp race window, RimeTrack's `ConversationStateManager` falls back to its chunk-level playout ledger (`is_estimated = True`).
3. **ChatMessage Content Mutation Target:** LiveKit's `ChatMessage.text_content` is a read-only `@property`. RimeTrack explicitly updates `item.content = [turn.text]`, which safely mutates `ChatMessage.content` (the underlying `list[ChatContent]`) and grounds `session.history` in the true heard-text prefix.
