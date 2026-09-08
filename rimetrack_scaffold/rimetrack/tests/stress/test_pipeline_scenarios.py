"""
Phase 7 — end-to-end scenario tests, driving the full RimeTrackPipeline
(LLM stream -> TTS -> Playback -> state, with an optional tool call),
not just isolated fence/state-manager unit behavior. These are the
scripted, deterministic equivalents of Roadmap Part 2 section 10's rows,
using synthetic timing instead of live audio (per that section's own
"use synthetic audio/text injection... for determinism" instruction).
"""

from __future__ import annotations

import asyncio

import pytest

from agent.events import EventLog
from agent.fence import GenerationFence
from agent.pipeline import RimeTrackPipeline
from agent.state_manager import ConversationStateManager


def _new_pipeline(**kwargs) -> RimeTrackPipeline:
    fence = GenerationFence()
    state = ConversationStateManager(fence)
    event_log = EventLog(session_id="test")
    return RimeTrackPipeline(fence, state, event_log, **kwargs)


@pytest.mark.asyncio
async def test_normal_conversation_no_interruption():
    """Scenario: normal conversation, no interruption."""
    pipeline = _new_pipeline()
    result = await pipeline.run_turn("What's the weather?", "It is sunny today")

    assert result.completed is True
    assert result.heard_text == "It is sunny today "
    assert pipeline.fence.is_current(result.generation_id)


@pytest.mark.asyncio
async def test_single_interruption_mid_response():
    """Scenario: single interruption, mid-response — the pipeline-level
    version of test_state_manager.py's unit test, now driven through the
    actual async word-by-word streaming loop instead of directly calling
    ledger methods."""
    pipeline = _new_pipeline()
    result = await pipeline.run_turn(
        "Book me a table for 7pm.",
        "Sure booking a table for seven pm at your usual place",
        interrupt_after_words=3,
    )

    assert result.completed is False
    assert result.heard_text.split() == ["Sure", "booking", "a"]
    assert "usual" not in result.heard_text
    assert "place" not in result.heard_text


@pytest.mark.asyncio
async def test_interruption_during_cancellable_tool_call():
    """Scenario: interruption during tool execution (cancellable tool)."""
    cancelled_inside = False

    async def slow_lookup():
        nonlocal cancelled_inside
        try:
            await asyncio.sleep(2)
            return "should not complete"
        except asyncio.CancelledError:
            cancelled_inside = True
            raise

    pipeline = _new_pipeline(word_delay=0.01, tts_delay_per_chunk=0.01)
    result = await pipeline.run_turn(
        "What's my order status?",
        "Let me check that for you now",
        tool_fn=slow_lookup,
        tool_name="order_lookup",
        tool_cancellable=True,
        interrupt_after_words=2,
    )

    assert result.completed is False
    assert result.tool_result is not None
    assert result.tool_result.cancelled is True
    assert cancelled_inside is True


@pytest.mark.asyncio
async def test_interruption_during_uncancellable_tool_call():
    """Scenario: interruption during tool execution (uncancellable tool)
    — the central correctness test at the full-pipeline level: the
    booking DOES complete, but must never be spoken/applied as current."""

    async def uncancellable_booking():
        await asyncio.sleep(0.05)
        return {"booking_id": "BK-7788", "time": "7pm"}

    pipeline = _new_pipeline(word_delay=0.005, tts_delay_per_chunk=0.005)
    result = await pipeline.run_turn(
        "Book me a table for 7pm.",
        "Sure booking that now for seven pm",
        tool_fn=uncancellable_booking,
        tool_name="book_table",
        tool_cancellable=False,
        interrupt_after_words=2,
    )

    assert result.completed is False
    assert result.tool_result is not None
    assert result.tool_result.value == {"booking_id": "BK-7788", "time": "7pm"}
    assert result.tool_result.is_stale(pipeline.fence) is True
    # And critically: the heard text must not claim the booking happened.
    assert "BK-7788" not in result.heard_text


@pytest.mark.asyncio
async def test_rapid_consecutive_requests_no_stale_bleed():
    """Scenario: rapid consecutive user requests — running two turns
    back to back (second starting immediately, simulating the user
    talking over the tail of the first) must not let the first turn's
    late chunks bleed into the second turn's ledger."""
    pipeline = _new_pipeline(word_delay=0.005, tts_delay_per_chunk=0.005)

    turn1_task = asyncio.ensure_future(
        pipeline.run_turn("Set a timer.", "Setting a timer for five minutes now", interrupt_after_words=2)
    )
    await asyncio.sleep(0.02)  # let turn1 get partway through
    result1 = await turn1_task

    result2 = await pipeline.run_turn("Actually cancel that.", "Okay cancelled")

    assert result1.completed is False
    assert result2.completed is True
    assert result2.generation_id != result1.generation_id
    assert pipeline.fence.is_current(result2.generation_id)
    assert pipeline.fence.is_stale(result1.generation_id)
    # Turn 2's context must not contain turn 1's un-played tail.
    assert "minutes" not in result2.heard_text


@pytest.mark.asyncio
async def test_tool_failure_does_not_crash_the_turn():
    """Scenario: tool failure — the pipeline must surface it as a failed
    ToolResult, not raise out of run_turn."""

    async def flaky():
        raise RuntimeError("upstream 500")

    pipeline = _new_pipeline()
    result = await pipeline.run_turn(
        "Check the price.", "Let me look that up", tool_fn=flaky, tool_cancellable=False
    )

    assert result.tool_result is not None
    assert not result.tool_result.ok
    assert isinstance(result.tool_result.error, RuntimeError)
    # The speech portion still completes normally since no interruption occurred.
    assert result.completed is True
