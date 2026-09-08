"""
Metric calculators from Roadmap Part 2, section 11.

Each function takes a list of `Event` objects (agent/events.py) or the
higher-level TurnResult/NaiveTurnResult from a batch of trials, and
computes exactly the metric defined in the roadmap — no metric here is
invented ad hoc; each docstring points back to the formula in section 11.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.events import Event
from agent.pipeline import TurnResult
from eval.baselines.naive import NaiveTurnResult


def stale_response_rate(results: list[TurnResult], expected_full_text: list[str]) -> float:
    """count(assistant_turns containing content from a superseded
    generation_id) / count(total assistant_turns).

    For the fenced (RimeTrack) pipeline, `completed=False` already means
    the turn was truncated at the fence boundary and the *next* turn's
    LLM call is grounded in the heard prefix — so a "stale response"
    here would mean heard_text contains words that appear AFTER the
    interruption point in the originally intended response, which the
    fence is specifically designed to prevent. We detect it by checking
    whether heard_text is a prefix of the full intended text (allowing
    it to be shorter, but never containing later words the fence should
    have dropped).
    """
    if not results:
        return 0.0
    stale = 0
    for r, full_text in zip(results, expected_full_text):
        if r.completed:
            continue
        if not full_text.startswith(r.heard_text.rstrip()) and r.heard_text.strip():
            stale += 1
    return stale / len(results)


def naive_stale_response_rate(results: list[NaiveTurnResult]) -> float:
    """Same metric, computed against the naive baseline's results: a
    stale response is any interrupted turn where `applied_text` is
    non-empty — i.e. the baseline kept applying chunks to state after
    the barge-in, since `eval/baselines/naive.py::run_turn` never checks
    for interruption before appending. Under this baseline, that's true
    for every interrupted trial by construction; that IS the point being
    demonstrated (Roadmap §12) — this function makes it a measured
    number rather than an assertion.
    """
    interrupted = [r for r in results if r.interrupted]
    if not interrupted:
        return 0.0
    return sum(1 for r in interrupted if r.applied_text.strip()) / len(interrupted)


def stale_tool_result_rate(tool_results_after_cancel: list[bool]) -> float:
    """count(tool_results applied to state after their generation_id was
    superseded) / count(tool_results returned after cancellation).

    Caller passes a list of booleans: True if a tool result that
    returned after its generation was superseded was actually applied to
    state (the bug), False if it was correctly fenced out.
    """
    if not tool_results_after_cancel:
        return 0.0
    return sum(tool_results_after_cancel) / len(tool_results_after_cancel)


def interruption_stop_latency_seconds(events: list[Event]) -> list[float]:
    """time(last_audio_sample_played, gen=G_old) - time(cancel_issued, gen=G_old),
    computed per interruption from the structured event log. Returns one
    latency value per detected `fence_cancelled` event, using
    `ts_mono` for monotonic-clock accuracy (Roadmap §11's instrumentation
    note: never derive latency from wall-clock in a system that may see
    clock adjustments)."""
    latencies: list[float] = []
    cancels = {e.generation_id: e for e in events if e.event_type == "fence_cancelled"}
    for gen_id, cancel_ev in cancels.items():
        played_after = [
            e
            for e in events
            if e.event_type == "chunk_played" and e.generation_id == gen_id and e.ts_mono >= cancel_ev.ts_mono
        ]
        if played_after:
            last = max(played_after, key=lambda e: e.ts_mono)
            latencies.append(last.ts_mono - cancel_ev.ts_mono)
        else:
            latencies.append(0.0)  # nothing played after cancel — ideal case
    return latencies


@dataclass
class BenchmarkSummary:
    system: str
    trials: int
    stale_response_rate: float
    stale_tool_result_rate: float | None
    p50_stop_latency_s: float | None
    p95_stop_latency_s: float | None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(pct / 100 * (len(s) - 1))))
    return s[idx]
