"""
RimeTrackPipeline — an end-to-end, LiveKit-independent turn simulator.

Roadmap Phase 7 needs to exercise full scenarios (a whole turn: LLM
streaming into TTS, with an optional tool call, interruptible at any
point) rather than just the individual fence/state-manager unit
behaviors already covered in tests/stress/test_fence.py and
test_state_manager.py. This module is the thing those scenario scripts
drive.

It deliberately does NOT touch LiveKit or Rime — it simulates an LLM
token stream and a TTS "play" step with realistic async delays, so
scenarios are fully deterministic and runnable without credentials
(matching Roadmap Part 2 section 10's "use synthetic audio/text
injection... for determinism" instruction), while still exercising the
exact same fence.py / state_manager.py / tool_executor.py code paths
that agent/session.py wires against the real LiveKit session.

See eval/baselines/naive.py for the deliberately-fence-free counterpart
used to produce the baseline-vs-RimeTrack comparison from Roadmap Part 2
section 12.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from .events import EventLog
from .fence import GenerationFence
from .state_manager import ConversationStateManager
from .text_normalize import normalize_for_tts
from .tool_executor import ToolExecutor, ToolResult


@dataclass
class TurnResult:
    generation_id: str
    completed: bool
    """True if the turn finished normally; False if it was interrupted."""
    heard_text: str
    tool_result: ToolResult | None = None


class RimeTrackPipeline:
    """The real system: every stage checks the fence before letting its
    output reach Playback or conversation state."""

    def __init__(
        self,
        fence: GenerationFence,
        state: ConversationStateManager,
        event_log: EventLog,
        *,
        word_delay: float = 0.01,
        tts_delay_per_chunk: float = 0.01,
    ) -> None:
        self.fence = fence
        self.state = state
        self.event_log = event_log
        self.tool_executor = ToolExecutor(fence, event_log)
        self._word_delay = word_delay
        self._tts_delay = tts_delay_per_chunk

        # Log fence transitions to the event log so downstream consumers
        # (eval/run_benchmark.py's interruption_stop_latency_seconds)
        # have the fence_cancelled events they need — this mirrors what
        # agent/session.py::wire_fence_to_session does for the live
        # LiveKit path; kept here too since RimeTrackPipeline is meant to
        # be usable standalone in eval/tests without agent/session.py.
        fence.add_listener(
            lambda ev: event_log.emit(f"fence_{ev.kind}", generation_id=ev.generation_id, reason=ev.reason)
        )

    async def run_turn(
        self,
        user_text: str,
        response_text: str,
        *,
        tool_fn: Callable[[], Awaitable[object]] | None = None,
        tool_name: str = "tool",
        tool_cancellable: bool = True,
        interrupt_after_words: int | None = None,
    ) -> TurnResult:
        """Runs one full agent turn. If `interrupt_after_words` is set,
        a synthetic barge-in is fired after that many words have been
        handed to (simulated) Playback — this is the deterministic
        stand-in for live barge-in audio, per Roadmap Part 2 section 10.
        """
        self.state.append_user_turn(user_text)
        gen_id = self.fence.advance()
        self.state.start_assistant_turn(gen_id)
        self.event_log.emit("generation_started", generation_id=gen_id)

        tool_result: ToolResult | None = None
        if tool_fn is not None:
            run = (
                self.tool_executor.run_cancellable
                if tool_cancellable
                else self.tool_executor.run_uncancellable
            )
            tool_task = asyncio.ensure_future(
                run(tool_fn, generation_id=gen_id, tool_name=tool_name)
            )
        else:
            tool_task = None

        normalized_text = normalize_for_tts(response_text)
        words = normalized_text.split(" ")
        for i, word in enumerate(words):
            await asyncio.sleep(self._word_delay)  # simulated LLM token latency
            if self.fence.is_stale(gen_id):
                self.event_log.emit("llm_chunk_dropped_stale", generation_id=gen_id, word=word)
                break

            await asyncio.sleep(self._tts_delay)  # simulated TTS + playback latency
            if self.fence.is_stale(gen_id):
                self.event_log.emit("tts_chunk_dropped_stale", generation_id=gen_id, word=word)
                break

            self.state.record_chunk_played(gen_id, word + " ")
            self.event_log.emit("chunk_played", generation_id=gen_id, word=word)

            if interrupt_after_words is not None and i + 1 == interrupt_after_words:
                self.fence.interrupt_current(reason="user_barge_in")
                self.event_log.emit("barge_in_injected", generation_id=gen_id, after_word_index=i)

        if tool_task is not None:
            tool_result = await tool_task

        if self.fence.is_current(gen_id):
            self.state.finalize_assistant_turn(gen_id)
            heard = self.state.get_context()[-1].text
            completed = True
        else:
            result = self.state.truncate_on_interrupt(gen_id)
            heard = result.heard_text
            completed = False

        return TurnResult(generation_id=gen_id, completed=completed, heard_text=heard, tool_result=tool_result)
