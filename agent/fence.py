"""
GenerationFence — RimeTrack's core contribution.

Every agent turn (LLM generation, its TTS output, any tool calls it
triggers) is tagged with a monotonically-increasing generation_id. Any
producer (LLM stream consumer, TTS consumer, tool executor) must check
`fence.is_current(gen_id)` before it lets its output reach shared
conversation state or the speaker. This is what prevents a stale result —
one computed under a turn that has since been superseded by a barge-in —
from silently re-entering the conversation.

Design note (see Roadmap Part 1, section 4): correctness comes from
fencing at the point of re-entry into shared state, NOT from successfully
cancelling every upstream task. Cancellation (asyncio.Task.cancel(), a
Rime WS stop message, an aborted tool HTTP request) is a *latency*
optimization layered on top — it makes stale work stop producing sooner,
but the fence check is what guarantees a stale result can never be
spoken or applied even if cancellation itself fails or races.

This module is pure logic — no network, no LiveKit, no Rime — so it can
be unit tested in isolation (see tests/stress/test_fence.py).
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FenceEvent:
    kind: str  # "advanced" | "cancelled"
    generation_id: str
    reason: str | None = None


class GenerationFence:
    """Thread-safe (async-safe) authority on which generation_id is current.

    Not itself async — callers await their own I/O and just check/advance
    the fence synchronously at each decision point, which keeps this class
    trivial to unit test and impossible to get wrong via forgotten awaits.
    """

    def __init__(self, *, id_prefix: str = "G") -> None:
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._current_id: str | None = None
        self._cancelled_ids: set[str] = set()
        self._id_prefix = id_prefix
        self._listeners: list[Callable[[FenceEvent], None]] = []

    # -- observation -----------------------------------------------------

    @property
    def current_generation_id(self) -> str | None:
        with self._lock:
            return self._current_id

    def is_current(self, generation_id: str | None) -> bool:
        """True iff `generation_id` is the live turn and has not been
        cancelled. A None generation_id (work that started before any
        turn existed) is never current."""
        if generation_id is None:
            return False
        with self._lock:
            return (
                generation_id == self._current_id
                and generation_id not in self._cancelled_ids
            )

    def is_stale(self, generation_id: str | None) -> bool:
        return not self.is_current(generation_id)

    # -- mutation ----------------------------------------------------------

    def advance(self) -> str:
        """Start a new turn. Returns the new generation_id and implicitly
        supersedes (but does not necessarily cancel) the previous one —
        callers that want the old turn's work stopped should also call
        `cancel(old_id, reason=...)`.
        """
        with self._lock:
            new_id = f"{self._id_prefix}{next(self._counter)}"
            self._current_id = new_id
        self._notify(FenceEvent(kind="advanced", generation_id=new_id))
        return new_id

    def cancel(self, generation_id: str, *, reason: str = "barge_in") -> None:
        """Mark a generation as cancelled. Idempotent — cancelling twice,
        or cancelling an id that was never current, is a no-op beyond
        bookkeeping (defensive: late/duplicate cancel signals must never
        raise)."""
        with self._lock:
            self._cancelled_ids.add(generation_id)
        self._notify(FenceEvent(kind="cancelled", generation_id=generation_id, reason=reason))

    def interrupt_current(self, *, reason: str = "barge_in") -> tuple[str | None, str]:
        """Convenience for the common barge-in path: cancel whatever is
        current, then advance to a new generation. Returns
        (old_generation_id, new_generation_id)."""
        with self._lock:
            old_id = self._current_id
        if old_id is not None:
            self.cancel(old_id, reason=reason)
        new_id = self.advance()
        return old_id, new_id

    # -- listeners (wire to EventLog from events.py in the agent session) --

    def add_listener(self, fn: Callable[[FenceEvent], None]) -> None:
        self._listeners.append(fn)

    def _notify(self, event: FenceEvent) -> None:
        for fn in self._listeners:
            fn(event)


class StaleResultError(Exception):
    """Raised (or caught and logged) when a result arrives for a
    generation_id the fence no longer considers current. Callers decide
    whether to raise-and-drop or log-and-drop depending on context (see
    ToolResult.check() in tool_executor.py for the non-raising path used
    with uncancellable tools)."""

    def __init__(self, generation_id: str, current_id: str | None) -> None:
        self.generation_id = generation_id
        self.current_id = current_id
        super().__init__(
            f"stale result for generation {generation_id!r}; "
            f"current generation is {current_id!r}"
        )
