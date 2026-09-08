"""
Fence-aware tool execution.

Two categories of tool, per Roadmap Part 1 section 4 step 5:

  - Cancellable: we can actually abort the in-flight call (e.g. an HTTP
    request with a real cancel/abort). We race it against the fence and
    drop it the moment its generation is superseded.

  - Uncancellable: once started, it runs to completion (e.g. a payment
    that's already been submitted upstream). We cannot stop the *call*,
    so instead we fence the *result*: when it returns, we check whether
    its generation_id is still current before applying it to conversation
    state or speaking it. If it's stale, we log it and hand it to the
    caller as a disclosed fact ("the earlier booking did go through")
    rather than silently discarding or silently applying it.

This is the file that makes the difference between "we stop the speaker"
(the naive baseline from Roadmap Part 2 section 12) and "we prevent stale
tool results from re-entering state" (RimeTrack's actual claim).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from .events import EventLog
from .fence import GenerationFence

T = TypeVar("T")


@dataclass
class ToolResult:
    generation_id: str
    tool_name: str
    value: Any = None
    error: BaseException | None = None
    cancelled: bool = False

    def is_stale(self, fence: GenerationFence) -> bool:
        return fence.is_stale(self.generation_id)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.cancelled


class ToolExecutor:
    def __init__(self, fence: GenerationFence, event_log: EventLog | None = None) -> None:
        self._fence = fence
        self._log = event_log

    async def run_cancellable(
        self,
        tool_fn: Callable[[], Awaitable[T]],
        *,
        generation_id: str,
        tool_name: str,
    ) -> ToolResult:
        """Run `tool_fn`, aborting it as soon as `generation_id` is
        superseded. Requires `tool_fn` to actually respect asyncio
        cancellation (e.g. wraps an aiohttp request whose `.cancel()`
        closes the underlying connection) — a tool that swallows
        CancelledError internally is not truly cancellable and should be
        run via `run_uncancellable` instead."""
        self._emit("tool_started", generation_id, tool=tool_name, cancellable=True)
        task = asyncio.ensure_future(tool_fn())
        try:
            while not task.done():
                if self._fence.is_stale(generation_id):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    self._emit("tool_cancelled", generation_id, tool=tool_name)
                    return ToolResult(generation_id=generation_id, tool_name=tool_name, cancelled=True)
                await asyncio.wait([task], timeout=0.05)
            result = task.result()
            if self._fence.is_stale(generation_id):
                # Won the race but the fence moved on between the last check
                # and completion — treat exactly like the uncancellable path:
                # fence the result, don't apply it.
                self._emit("tool_result_fenced", generation_id, tool=tool_name)
                return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result, cancelled=True)
            self._emit("tool_completed", generation_id, tool=tool_name)
            return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result)
        except Exception as e:  # noqa: BLE001 - tool errors are data, not agent crashes
            self._emit("tool_failed", generation_id, tool=tool_name, error=str(e))
            return ToolResult(generation_id=generation_id, tool_name=tool_name, error=e)

    async def run_uncancellable(
        self,
        tool_fn: Callable[[], Awaitable[T]],
        *,
        generation_id: str,
        tool_name: str,
    ) -> ToolResult:
        """Run `tool_fn` to completion no matter what (e.g. it already has
        a real-world side effect). The fence check happens on return, not
        during — this is the "fence the result, not the call" path."""
        self._emit("tool_started", generation_id, tool=tool_name, cancellable=False)
        try:
            result = await tool_fn()
        except Exception as e:  # noqa: BLE001
            self._emit("tool_failed", generation_id, tool=tool_name, error=str(e))
            return ToolResult(generation_id=generation_id, tool_name=tool_name, error=e)

        if self._fence.is_stale(generation_id):
            self._emit(
                "tool_result_fenced",
                generation_id,
                tool=tool_name,
                note="uncancellable tool completed after its generation was superseded; "
                "result withheld from conversation state and not spoken",
            )
            return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result, cancelled=True)

        self._emit("tool_completed", generation_id, tool=tool_name)
        return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result)

    def _emit(self, event_type: str, generation_id: str, **payload: Any) -> None:
        if self._log is not None:
            self._log.emit(event_type, generation_id=generation_id, **payload)
