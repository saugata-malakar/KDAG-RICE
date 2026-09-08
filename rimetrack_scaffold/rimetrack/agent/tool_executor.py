"""
Fence-aware tool execution with event-driven cancellation.

Two categories of tool, per Roadmap Part 1 section 4 step 5:

  - Cancellable: we can actually abort the in-flight call (e.g. an HTTP
    request with a real cancel/abort). We race it against the fence using
    asyncio.Event listeners and drop it instantly the microsecond its
    generation is superseded (<1ms latency, zero polling loop).

  - Uncancellable: once started, it runs to completion (e.g. a payment
    or reservation write that has already been dispatched). We cannot
    stop the call, so we fence the result: when it returns, we check
    whether its generation_id is still current before applying it to
    conversation state or speaking it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from .events import EventLog
from .fence import FenceEvent, GenerationFence

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
        """Run `tool_fn`, aborting it instantly via event dispatch as soon as
        `generation_id` is superseded (sub-millisecond reaction time)."""
        self._emit("tool_started", generation_id, tool=tool_name, cancellable=True)
        task = asyncio.ensure_future(tool_fn())

        loop = asyncio.get_running_loop()
        cancel_event = asyncio.Event()

        def _on_fence_event(ev: FenceEvent) -> None:
            if self._fence.is_stale(generation_id):
                loop.call_soon_threadsafe(cancel_event.set)

        self._fence.add_listener(_on_fence_event)
        if self._fence.is_stale(generation_id):
            cancel_event.set()

        cancel_waiter = asyncio.ensure_future(cancel_event.wait())
        try:
            done, _ = await asyncio.wait([task, cancel_waiter], return_when=asyncio.FIRST_COMPLETED)
            if cancel_event.is_set():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self._emit("tool_cancelled", generation_id, tool=tool_name)
                return ToolResult(generation_id=generation_id, tool_name=tool_name, cancelled=True)

            result = task.result()
            if self._fence.is_stale(generation_id):
                self._emit("tool_result_fenced", generation_id, tool=tool_name)
                return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result, cancelled=True)

            self._emit("tool_completed", generation_id, tool=tool_name)
            return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result)
        except Exception as e:  # noqa: BLE001
            self._emit("tool_failed", generation_id, tool=tool_name, error=str(e))
            return ToolResult(generation_id=generation_id, tool_name=tool_name, error=e)
        finally:
            if not cancel_waiter.done():
                cancel_waiter.cancel()
            self._fence.remove_listener(_on_fence_event)

    async def run_uncancellable(
        self,
        tool_fn: Callable[[], Awaitable[T]],
        *,
        generation_id: str,
        tool_name: str,
    ) -> ToolResult:
        """Run `tool_fn` to completion. The fence check happens on return,
        guaranteeing that completed results for superseded generations are
        quarantined and withheld from conversational memory."""
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
                "result quarantined from conversation state and not spoken",
            )
            return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result, cancelled=True)

        self._emit("tool_completed", generation_id, tool=tool_name)
        return ToolResult(generation_id=generation_id, tool_name=tool_name, value=result)

    def _emit(self, event_type: str, generation_id: str, **payload: Any) -> None:
        if self._log is not None:
            self._log.emit(event_type, generation_id=generation_id, **payload)
