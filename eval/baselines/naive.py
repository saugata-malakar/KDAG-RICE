"""
NaivePipeline — the "obvious fix" baseline from Roadmap Part 2, section 12.

Local playback stops on interruption (we just stop appending to the
transcript the "user" sees), but the LLM stream and any tool call
continue to completion in the background and their results ARE applied
to conversation state when they finish — there is no fence, no
generation_id, no result-fencing. This is deliberately the same turn
shape as agent/pipeline.py::RimeTrackPipeline so the two are a fair,
apples-to-apples comparison for eval/run_benchmark.py — the only
difference is the presence/absence of the fence check.

This file intentionally does NOT import GenerationFence for its
staleness logic (only to detect that a barge-in occurred at all, since
we still need to know a barge-in happened to know playback should stop
locally) — the whole point is to demonstrate what breaks when only the
fence's "did a barge-in happen" signal is used, without ever checking
"is this specific piece of work still current" before applying results.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from agent.events import EventLog
from agent.fence import GenerationFence


@dataclass
class NaiveTurnResult:
    interrupted: bool
    """Whether a barge-in occurred at all during this turn."""
    applied_text: str
    """The full text that ended up applied to conversation state —
    under the naive baseline this is the FULL response even if a
    barge-in occurred partway through, which is exactly the bug
    RimeTrack's fence exists to prevent."""
    tool_value: object | None = None
    tool_applied_after_interrupt: bool = False
    """True if a tool result was applied to state even though a
    barge-in happened before the tool call finished — the naive
    baseline's core failure mode."""


class NaivePipeline:
    def __init__(
        self,
        fence: GenerationFence,
        event_log: EventLog,
        *,
        word_delay: float = 0.01,
        tts_delay_per_chunk: float = 0.01,
    ) -> None:
        # The fence is used ONLY to detect "did a barge-in happen", never
        # to gate what gets applied — see module docstring.
        self.fence = fence
        self.event_log = event_log
        self._word_delay = word_delay
        self._tts_delay = tts_delay_per_chunk

    async def run_turn(
        self,
        user_text: str,
        response_text: str,
        *,
        tool_fn: Callable[[], Awaitable[object]] | None = None,
        interrupt_after_words: int | None = None,
    ) -> NaiveTurnResult:
        gen_id = self.fence.advance()
        self.event_log.emit("generation_started", generation_id=gen_id)

        tool_task = asyncio.ensure_future(tool_fn()) if tool_fn is not None else None

        applied_chunks: list[str] = []
        interrupted = False
        words = response_text.split(" ")
        for i, word in enumerate(words):
            await asyncio.sleep(self._word_delay)
            await asyncio.sleep(self._tts_delay)
            # NO fence check here — the naive baseline keeps generating
            # and keeps applying to state regardless of what the local
            # speaker is doing.
            applied_chunks.append(word + " ")
            self.event_log.emit("chunk_applied_naive", generation_id=gen_id, word=word)

            if interrupt_after_words is not None and i + 1 == interrupt_after_words:
                self.fence.interrupt_current(reason="user_barge_in")
                interrupted = True
                self.event_log.emit("barge_in_injected", generation_id=gen_id, after_word_index=i)
                # Local playback would stop here in a real system, but
                # note: applied_chunks keeps growing below regardless —
                # that's the point of this baseline.

        tool_value = None
        tool_applied_after_interrupt = False
        if tool_task is not None:
            tool_value = await tool_task
            # Naive baseline applies the tool result unconditionally,
            # with no check for whether the generation that requested it
            # is still current.
            tool_applied_after_interrupt = interrupted
            self.event_log.emit(
                "tool_result_applied_naive",
                generation_id=gen_id,
                stale=interrupted,
            )

        return NaiveTurnResult(
            interrupted=interrupted,
            applied_text="".join(applied_chunks),
            tool_value=tool_value,
            tool_applied_after_interrupt=tool_applied_after_interrupt,
        )
