"""
Unit tests for GenerationFence and ToolExecutor.

These cover the deterministic scenarios from Roadmap Part 2, section 10,
that don't require a live LiveKit/Rime connection:

  - single interruption
  - interruption during a cancellable tool call
  - interruption during an uncancellable tool call (the important one —
    proves result-fencing, not just task-cancellation)
  - rapid consecutive interruptions (monotonic generation_id correctness)
  - late/duplicate events after supersession

Run with: pytest tests/stress/test_fence.py -v
(repeat 10x per the roadmap's flakiness-hunting rule, e.g.:
 pytest tests/stress/test_fence.py -v --count=10   [requires pytest-repeat])
"""

from __future__ import annotations

import asyncio

import pytest

from agent.fence import GenerationFence, StaleResultError
from agent.tool_executor import ToolExecutor


def test_advance_produces_monotonic_ids():
    fence = GenerationFence()
    g1 = fence.advance()
    g2 = fence.advance()
    g3 = fence.advance()
    assert [g1, g2, g3] == ["G1", "G2", "G3"]
    assert fence.current_generation_id == "G3"


def test_only_current_generation_is_current():
    fence = GenerationFence()
    g1 = fence.advance()
    assert fence.is_current(g1)
    g2 = fence.advance()
    assert not fence.is_current(g1)
    assert fence.is_current(g2)


def test_single_interruption_cancels_old_and_starts_new():
    """Scenario: single interruption, mid-response."""
    fence = GenerationFence()
    g1 = fence.advance()
    assert fence.is_current(g1)

    old_id, new_id = fence.interrupt_current(reason="user_barge_in")

    assert old_id == g1
    assert not fence.is_current(g1)
    assert fence.is_current(new_id)
    assert new_id != g1


def test_late_chunk_after_supersession_is_dropped():
    """Scenario: late network packet arrives after the generation that
    produced it has already been superseded."""
    fence = GenerationFence()
    g1 = fence.advance()
    fence.interrupt_current()  # g1 is now stale

    # Simulate a late audio/token chunk tagged g1 arriving at a consumer.
    assert fence.is_stale(g1)
    # The consumer's job is simply: check before acting.
    consumed = fence.is_current(g1)
    assert consumed is False


def test_duplicate_cancel_is_idempotent():
    fence = GenerationFence()
    g1 = fence.advance()
    fence.cancel(g1)
    fence.cancel(g1)  # must not raise
    assert fence.is_stale(g1)


def test_rapid_consecutive_interruptions_stay_consistent():
    """Scenario: 3 interruptions in quick succession must not corrupt the
    fence — only the *last* generation should ever be current, and every
    prior one must be considered stale, regardless of order of arrival of
    late events referencing them."""
    fence = GenerationFence()
    ids = []
    g0 = fence.advance()
    ids.append(g0)
    for _ in range(3):
        old_id, new_id = fence.interrupt_current()
        ids.append(new_id)

    current = fence.current_generation_id
    assert current == ids[-1]
    for stale_id in ids[:-1]:
        assert fence.is_stale(stale_id)


def test_interruption_exactly_at_completion_boundary():
    """Scenario: interruption arrives exactly as a response finishes.
    Model this as: the fence advances (interrupt) either just before or
    just after a 'final chunk played' check — either ordering must leave
    the system in a well-defined state, never both generations "current"
    simultaneously."""
    fence = GenerationFence()
    g1 = fence.advance()

    # Ordering A: completion check happens first, then barge-in.
    completed_while_current = fence.is_current(g1)
    fence.interrupt_current()
    assert completed_while_current is True
    assert fence.is_stale(g1)

    # Ordering B: barge-in happens first, then a late completion check.
    fence2 = GenerationFence()
    g2 = fence2.advance()
    _, g3 = fence2.interrupt_current()
    completed_after_interrupt = fence2.is_current(g2)
    assert completed_after_interrupt is False
    assert fence2.is_current(g3)


# ---------------------------------------------------------------------------
# ToolExecutor scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellable_tool_stops_when_superseded():
    """Scenario: interruption during tool execution (cancellable tool)."""
    fence = GenerationFence()
    executor = ToolExecutor(fence)
    g1 = fence.advance()

    cancelled_inside = False

    async def slow_cancellable_tool():
        nonlocal cancelled_inside
        try:
            await asyncio.sleep(5)
            return "should not reach here"
        except asyncio.CancelledError:
            cancelled_inside = True
            raise

    async def interrupt_soon():
        await asyncio.sleep(0.1)
        fence.interrupt_current()

    result, _ = await asyncio.gather(
        executor.run_cancellable(slow_cancellable_tool, generation_id=g1, tool_name="lookup"),
        interrupt_soon(),
    )

    assert result.cancelled is True
    assert cancelled_inside is True


@pytest.mark.asyncio
async def test_uncancellable_tool_result_is_fenced_not_applied():
    """Scenario: interruption during tool execution (uncancellable tool) —
    the central correctness test. The tool runs to completion and returns
    a real value, but because its generation was superseded while it was
    running, the result must be marked stale and never treated as
    something to speak or apply to conversation state."""
    fence = GenerationFence()
    executor = ToolExecutor(fence)
    g1 = fence.advance()

    async def uncancellable_booking_call():
        await asyncio.sleep(0.1)
        return {"booking_id": "BK-1234", "time": "7pm"}

    async def interrupt_mid_call():
        await asyncio.sleep(0.03)
        fence.interrupt_current()  # user says "actually, 6pm" before BK-1234 comes back

    result, _ = await asyncio.gather(
        executor.run_uncancellable(uncancellable_booking_call, generation_id=g1, tool_name="book"),
        interrupt_mid_call(),
    )

    # The call DID complete and DID return a real booking...
    assert result.value == {"booking_id": "BK-1234", "time": "7pm"}
    # ...but it must be flagged stale so the caller never speaks/applies it
    # as if it were the outcome of the current (post-interrupt) turn.
    assert result.cancelled is True
    assert result.is_stale(fence) is True


@pytest.mark.asyncio
async def test_tool_completing_before_interruption_is_applied_normally():
    """Control case: no interruption occurs, result must NOT be fenced."""
    fence = GenerationFence()
    executor = ToolExecutor(fence)
    g1 = fence.advance()

    async def fast_tool():
        return 42

    result = await executor.run_uncancellable(fast_tool, generation_id=g1, tool_name="calc")
    assert result.ok
    assert result.value == 42
    assert result.is_stale(fence) is False


@pytest.mark.asyncio
async def test_tool_failure_does_not_corrupt_fence_state():
    """Scenario: tool failure. An exception in the tool must not leave the
    fence in an inconsistent state or crash the executor."""
    fence = GenerationFence()
    executor = ToolExecutor(fence)
    g1 = fence.advance()

    async def failing_tool():
        raise RuntimeError("upstream API error")

    result = await executor.run_uncancellable(failing_tool, generation_id=g1, tool_name="flaky")
    assert not result.ok
    assert isinstance(result.error, RuntimeError)
    # fence itself is untouched and still consistent
    assert fence.is_current(g1)
