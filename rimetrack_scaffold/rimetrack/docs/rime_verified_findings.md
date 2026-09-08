# RimeTrack — Verified Findings & the Core Contribution

This document is the output of actually reading Rime's current documentation
(fetched live from docs.rime.ai, not recalled from memory) and the installed
`livekit-plugins-rime==1.7.1` package source, cross-referenced against each
other. It corrects/tightens the earlier design doc's assumptions and — more
importantly — surfaces a **real, verified gap** in the standard integration
path that RimeTrack closes. This is the strongest "hard voice engineering"
evidence in the whole project: it's not a synthetic scenario, it's a bug in
the actual stack every other team using LiveKit + Rime will also have.

---

## 1. Verified Rime wire protocol (was previously "verify at build time" — now confirmed)

Source: [docs.rime.ai/docs/websockets](https://docs.rime.ai/docs/websockets),
[docs.rime.ai/api-reference/coda/websockets-json](https://docs.rime.ai/api-reference/coda/websockets-json)

- **Endpoint:** `/ws3` is Rime's actively-developed, recommended endpoint — supports Coda + all Mist versions, JSON framing, word-level timestamps, and is the one Rime "will continue to extend." (`/ws2` is Mist-only legacy; `/ws` is binary-only, no timestamps, no context IDs.)
- **Client → server operations**, exact schema:
  - `{"text": "...", "contextId": "<id>"}` — send text for synthesis, tagged with a caller-chosen context id.
  - `{"operation": "clear"}` — **discards the buffered/in-flight utterance. This is the documented interruption primitive**: *"Your client can clear out the accumulated buffer, which is useful in the case of interruptions."*
  - `{"operation": "flush"}` — forces synthesis of whatever's buffered right now.
  - `{"operation": "eos"}` — synthesize remaining buffer, emit final `done`, close connection.
- **Server → client events:** `chunk` (base64 audio, tagged with `contextId`), `timestamps` (per-word `words`/`start`/`end` arrays, **English and Spanish only** — silently absent for fr/de/ja/pt/ar/hi, so don't block playback waiting for it), `done` (per-utterance completion), `error` (non-fatal, connection stays open).
- **`contextId` semantics (important, previously unknown):** Rime does **not** track multiple simultaneous context ids — the *next* audio/timestamp event carries whichever `contextId` was most recently attached to a `text` message, and that id persists across subsequent messages that omit one. **This means `contextId` is a single mutable "current label," not a per-message durable tag** — so it cannot, by itself, be used the way our `generation_id` fence uses ids (to unambiguously mark which *specific* piece of work a given late chunk belongs to, even after several turns have passed). It's still valuable as a *server-side hint for the clear/flush scope*, but our own `GenerationFence` remains the actual source of truth for staleness — this is a real, disclosed limitation, not a gap in our design.
- **Segmentation (`segment` param):** `bySentence` (default, waits for sentence boundaries — natural prosody, small added latency), `immediate` (synthesize as text arrives — lowest latency, choppier prosody), `never` (only synthesizes on explicit `flush`/`eos` — full manual control). **Recommendation for RimeTrack: `immediate` or `never` with our own sentence-boundary chunker** (already built in the Phase 3 roadmap), since we want fine-grained control over exactly when a chunk is committed, for the heard-text ledger to be precise.
- **Latency (real numbers, replacing the earlier "sub-200ms" approximation):** Coda TTFA is **96ms P50 / 98ms P90 at 1 concurrent request**, degrading to **150ms P50 / 181ms P90 at 12 concurrent** (H100 SXM benchmark). Mist v3 is far lower (37ms/56ms) but lower conversational quality. Add 25–50ms typical US network RTT via the cloud API. **This directly informs the demo's latency budget: with Coda, realistic TTFA is ~120–230ms end-to-end depending on load — the <250ms interruption-stop-latency target from the original design doc is still right, but should be stated against Coda specifically, and the "why Coda not Mist v3" tradeoff should be an explicit line in RIME_EVIDENCE.md.**

## 2. THE finding: `livekit-plugins-rime==1.7.1` never sends `clear`

Verified by reading the installed package source directly (`grep -n "clear" .venv/lib/python3.12/site-packages/livekit/plugins/rime/tts.py` → zero matches for the operation; the one hit is an unrelated Python `list.clear()` call).

**What actually happens today, if you just use the stock LiveKit + Rime integration:** `SynthesizeStream._run` opens a pooled WebSocket connection, streams text under a per-utterance `contextId`, and on normal completion sends `{"operation": "flush", ...}`. **On interruption** (LiveKit cancels the asyncio task backing an abandoned `SpeechHandle`), the `finally` block runs `gracefully_cancel(*tasks)` and returns the connection to the pool — **it never sends Rime's documented `clear` message.** The client simply stops *reading* from the socket; nothing tells Rime's server the utterance was abandoned.

**Why this matters, precisely:** the WebSocket connection is pooled and reused for the *next* utterance. If Rime's server was still buffering or synthesizing text for the abandoned `contextId` when the client stopped reading, that work either (a) continues server-side burning compute for audio nobody will hear, or (b) in a worst case, its `chunk`/`timestamps`/`done` events could still be in flight on the same reused connection when the *next* utterance's messages start arriving — exactly the "late network packet after supersession" race our `GenerationFence` is designed to catch at the *consumer* side, but which the vanilla plugin doesn't even attempt to prevent at the *source*.

**This is a genuinely strong, judge-legible claim for the "Rime integration and voice experience" (20%) and "Hard voice engineering" (25%) categories**, because it's checkable: `grep -n "clear" $(python -c "import livekit.plugins.rime, os; print(os.path.dirname(livekit.plugins.rime.__file__))")/tts.py` returns nothing, on the record, in front of a judge if asked.

## 3. The fix: `agent/rime_ws_client.py` — `FencedRimeClient`

Implemented and tested (`tests/stress/test_rime_client.py`, 6/6 passing). Two things it does that the stock plugin doesn't:

1. **Uses `generation_id` as `contextId` directly** — a real, natural correlation between our internal fence and Rime's own wire-level id, rather than treating them as unrelated concepts.
2. **Sends `{"operation": "clear", "contextId": g}` the instant `fence.cancel(g)` fires** — via a listener wired directly to `GenerationFence`, so it's not contingent on the local asyncio task actually getting torn down in time. `test_interruption_sends_documented_clear_operation` is the regression test that would fail if this ever regressed to the stock plugin's behavior.

This can be adopted two ways depending on how much of the LiveKit plugin you want to keep:
- **Minimal patch:** subclass/monkeypatch `livekit.plugins.rime.tts.TTS.SynthesizeStream` to send `clear` in its cancellation path — smallest diff, but coupled to the plugin's internals (version 1.7.1 specifically; **re-verify this gap against whatever version you pin at submission time**, since it could be fixed upstream).
- **Full replacement (what's built here):** use `FencedRimeClient` directly against a raw `aiohttp` WebSocket connection, bypassing the LiveKit TTS plugin entirely for the Rime leg. More code, but total control and a cleaner demo story ("we didn't just call a library, we read the wire protocol and fixed a real gap in it").

**Recommendation given hackathon time constraints: do the minimal patch, but keep `FencedRimeClient`'s tested clear-on-cancel logic as the reference implementation** — cite it and its test in `RIME_EVIDENCE.md` as the acceptance-test-backed evidence for the claim, whichever integration path you actually ship.

## 4. Grounded, paper-backed ideas to strengthen the ML story (prioritized)

Given hackathon time, in priority order:

1. **(Do this) The `clear`-gap fix above.** Highest leverage-to-effort ratio: it's real, verified, checkable, and already implemented and tested. This alone is a legitimate, differentiated "hard voice engineering" claim most competing teams will not have, since it requires reading the plugin's source rather than trusting it.

2. **(Do this if time allows) A real semantic barge-in classifier**, grounded in Zhang et al.'s four-state semantic-VAD framing (arXiv:2502.14145) rather than relying purely on LiveKit's built-in adaptive interruption as a black box. Concretely: a small logistic/gradient-boosted classifier over cheap features — (a) ASR partial-hypothesis word count and (b) duration since VAD-onset (both already available from LiveKit's turn-handling config, §Phase 4) plus (c) a lexical cue feature (is the partial transcript one of a small set of backchannel tokens: "mm-hmm", "yeah", "okay", "right"). Train/tune it on ~50–100 labeled examples you record yourselves (5 minutes of scripted "uh-huh" vs. "wait, stop" utterances). This gives you a *demonstrable, inspectable* decision boundary to show judges — "here's our own barge-in/backchannel classifier, not just a config flag" — directly citable to the paper.

3. **(Stretch) Use the confirmed `timestamps` event as ground truth for a quantitative "heard accuracy" metric.** Since word-level timing is now a *confirmed* real field (not a proxy), you can compute, per interrupted turn, the exact playback-position-at-interrupt in milliseconds, and report "heard-text truncation accuracy" as a measured quantity (compare the ledger's committed text against the `timestamps` event's `start`/`end` arrays) rather than an estimated one. This upgrades `HeardTextResult.is_estimated` from `True` to `False` for real, and is a genuine quantitative strengthening of the evaluation methodology (§11) using data Rime already gives you for free.

4. **(Optional, if pursuing the benchmark-project track)** Rime's docs explicitly reward comparing Coda vs. Mist v3 on latency/quality tradeoffs for your specific use case (§1's numbers above are a start) — pairing that with the brief's own benchmark-project rules (blind listening tests, published corpus) would satisfy that alternate scoring path, but is a full extra workstream — only pursue if the interruption-recovery work is already solid with time to spare.

**What NOT to add:** don't reach for a bigger/fancier ML model (e.g. fine-tuning a full turn-taking transformer) — it's not buildable credibly in a hackathon timeframe, judges will ask how you validated it, and it displaces time from the fix in §3 which is both more novel and more defensible. The `livekit-plugins-rime` gap is a better "groundbreaking" story than a hastily-trained model would be, precisely because it's verified and checkable rather than asserted.
