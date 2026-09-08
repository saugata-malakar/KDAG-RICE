# RimeTrack Demo Video Script & Judge Walkthrough Guide

**Target Video Duration:** 4 minutes 15 seconds (within the 4–5 minute requirement)  
**Hackathon:** DataForge × Rime Hackathon Challenge  
**Team Product:** RimeTrack — Interruption & Recovery Runtime for Realtime Voice Agents  

---

## Demo Overview & Flow Matrix

| Time | Section | Focus & Hackathon Criteria | On-Screen Visual | Spoken Audio / Action |
|---|---|---|---|---|
| **0:00 - 0:45** | **1. User & Problem** | *Problem & Necessity of Voice (25%)* | Visual HUD showing Dispatch / Booking Interface | Explain the critical necessity of voice in hands-busy workflows (dispatch, field ops, driving) and why interruptions break naive voice agents. |
| **0:45 - 1:45** | **2. Normal Flow with Rime** | *Rime Integration & Voice Experience (20%)* | LiveKit WebRTC Session + Rime WebSocket stream timeline | Demonstrate seamless turn: user asks for schedule, Rime `coda`/`astra` speaks with natural prosody and crisp audio. Show active provider badge. |
| **1:45 - 3:00** | **3. Hard Voice Engineering (Stress Case)** | *Hard Voice Engineering (25%)* | Side-by-Side comparison view (RimeTrack vs. Naive Baseline) | **Stress Case:** User says *"Book table at 7pm"*. Agent starts speaking and triggers slow tool. User interrupts mid-speech: *"Wait, actually make it 8pm!"*. |
| **3:00 - 3:45** | **4. Evidence & Benchmark** | *Evidence & Reproducibility (20%)* | Benchmark results table & CSV trials log | Show real computed numbers (0% stale vs 100% naive failure across 80 trials). Show sub-millisecond stop latency. |
| **3:45 - 4:15** | **5. Repo, Config & Wrap-up** | *Demo Clarity & Configuration Hygiene (10%)* | Clean repo walkthrough (`README.md`, `RIME_EVIDENCE.md`, `.env.example`) | Show credential safety, exact Rime parameters (`coda`/`astra`/WS), and repeatable test commands. |

---

## Detailed Step-by-Step Script

### Part 1: Problem & Target User (0:00 - 0:45)
* **Speaker:** "Hi judges! Voice agents in real-world environments like field dispatch, healthcare, or hands-busy booking cannot afford to be mere chatbots with a play button. When humans talk, they interrupt, correct themselves mid-sentence, and change parameters while background tools are executing. In naive voice agents, interruptions cause catastrophic state pollution: the LLM hallucinates that the user heard things they never heard, and slow background tools return seconds later to execute the wrong action. We built **RimeTrack** to solve this hard voice engineering problem once and for all."

### Part 2: Normal Flow & Rime Integration (0:45 - 1:45)
* **Speaker:** "Here is RimeTrack in action. We are using the official Rime WebSocket streaming integration with the `coda` model and `astra` voice. Notice how Rime streams audio chunks with word-level alignment timestamps, giving us immediate, expressive audio with sub-second response times."
* **Action:** Run a normal turn: *"What are my bookings today?"* $\rightarrow$ Agent responds crisply. Show the active speech provider badge indicating **Rime WebSocket (coda / astra / eng)**.

### Part 3: The Hard Voice Stress Case (1:45 - 3:00)
* **Speaker:** "Now, let's trigger our deliberate stress case. We introduce an uncancellable reservation database tool with an injected delay. Watch what happens when we barge in mid-sentence."
* **Action:**
  1. User: *"Book me a table for 7pm at the downtown bistro."*
  2. Agent starts: *"Sure, reserving a table for seven..."*
  3. User barges in: *"Wait! Make it 8pm instead!"*
* **Visual Demonstration:**
  - Show the **`GenerationFence`** instantly advance from `G1` to `G2`, marking `G1` stale.
  - Show audio stop immediately on the exact word boundary (*"seven"*).
  - Show the in-flight 7pm tool finish, but `ToolExecutor` catches the stale `G1` tag and **safely quarantines the result** instead of applying it to state.
  - Show the **Heard-Text Ledger** truncate the history to only what the user heard (*"Sure, reserving a table for seven"*), so the next GPT-4o-mini prompt is 100% grounded in audible reality.
  - Compare this with the **Naive Baseline** side-by-side, which applied the 7pm booking, told the user 7pm was booked, and hallucinated the entire unsung turn.

### Part 4: Evidence & Empirical Metrics (3:00 - 3:45)
* **Speaker:** "We don't just assert correctness — we proved it across 80 empirical benchmark trials in `eval/run_benchmark.py`.
  - In our multi-scenario matrix covering mid-speech barge-ins, cancellable API calls, uncancellable DB commits, and rapid double interruptions:
  - **RimeTrack achieved a 0.0% stale response rate and 0.0% stale tool bleed.**
  - The naive baseline failed with **100% stale response rate** and **100% stale tool bleed** in tool scenarios.
  - Our monotonic interruption stop latency is verified at a sub-millisecond local decision boundary."

### Part 5: Code Inspection & Reproducibility (3:45 - 4:15)
* **Speaker:** "All code is open, fully tested (29/29 passing pytest suite), and clean. Our credentials are strictly isolated in `.env.example`, the exact Rime configuration is documented in `README.md` and `RIME_EVIDENCE.md`, and the entire benchmark is reproducible with a single command: `python -m eval.run_benchmark`. Thank you!"
