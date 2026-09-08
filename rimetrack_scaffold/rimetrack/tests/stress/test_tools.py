"""
Tests for fence-aware tool functions.

Verifies that:
1. Tools complete normally when not interrupted
2. Cancellable tools abort promptly on fence staleness
3. Uncancellable tools complete but results are quarantined
4. Concurrent tools are both fenced on interruption
5. Tool errors don't crash the executor
6. build_agent_tools properly exports FunctionTool list
"""

from __future__ import annotations

import asyncio
import pytest

from agent.events import EventLog
from agent.fence import GenerationFence
from agent.tool_executor import ToolExecutor
from agent.tools import (
    book_restaurant,
    check_flight_status,
    check_weather,
    build_agent_tools,
    BookingResult,
    FlightInfo,
    WeatherInfo,
)


@pytest.fixture
def fence():
    return GenerationFence()


@pytest.fixture
def executor(fence):
    return ToolExecutor(fence, EventLog(session_id="test-tools"))


async def test_book_restaurant_normal_completion(fence, executor):
    gen_id = fence.advance()
    result = await executor.run_uncancellable(
        lambda: book_restaurant("Olive Garden", "7:00 PM", 2, delay=0.01),
        generation_id=gen_id,
        tool_name="book_restaurant",
    )
    assert result.ok
    assert not result.cancelled
    assert result.value.confirmed is True
    assert result.value.restaurant == "Olive Garden"
    assert result.value.party_size == 2


async def test_book_restaurant_interrupted_mid_delay(fence, executor):
    gen_id = fence.advance()

    async def run_with_delay():
        return await book_restaurant("Olive Garden", "7:00 PM", 2, delay=0.08)

    async def interrupt_after_delay():
        await asyncio.sleep(0.02)
        fence.interrupt_current(reason="barge_in")

    interrupt_task = asyncio.ensure_future(interrupt_after_delay())
    result = await executor.run_uncancellable(
        run_with_delay,
        generation_id=gen_id,
        tool_name="book_restaurant",
    )
    await interrupt_task

    # Result completed in background but was quarantined (cancelled=True)
    assert result.cancelled
    assert result.value is not None
    assert result.value.restaurant == "Olive Garden"


async def test_flight_status_returns_data(fence, executor):
    gen_id = fence.advance()
    result = await executor.run_cancellable(
        lambda: check_flight_status("UA402", delay=0.01),
        generation_id=gen_id,
        tool_name="check_flight_status",
    )
    assert result.ok
    assert result.value.flight_number == "UA402"
    assert result.value.status == "On Time"


async def test_tool_result_fenced_after_interruption(fence, executor):
    gen_id = fence.advance()

    async def slow_task():
        await asyncio.sleep(2.0)
        return {"should": "never_reach"}

    async def interrupt_soon():
        await asyncio.sleep(0.02)
        fence.interrupt_current(reason="barge_in")

    interrupt_task = asyncio.ensure_future(interrupt_soon())
    result = await executor.run_cancellable(
        slow_task,
        generation_id=gen_id,
        tool_name="slow_lookup",
    )
    await interrupt_task

    assert result.cancelled
    assert result.value is None


async def test_concurrent_tools_both_fenced_on_interrupt(fence, executor):
    gen_id = fence.advance()

    async def tool_a():
        await asyncio.sleep(2.0)
        return "result_a"

    async def tool_b():
        await asyncio.sleep(2.0)
        return "result_b"

    async def interrupt_soon():
        await asyncio.sleep(0.02)
        fence.interrupt_current(reason="barge_in")

    interrupt_task = asyncio.ensure_future(interrupt_soon())
    result_a, result_b = await asyncio.gather(
        executor.run_cancellable(tool_a, generation_id=gen_id, tool_name="tool_a"),
        executor.run_cancellable(tool_b, generation_id=gen_id, tool_name="tool_b"),
    )
    await interrupt_task

    assert result_a.cancelled
    assert result_b.cancelled


async def test_tool_error_handling(fence, executor):
    gen_id = fence.advance()

    async def failing_tool():
        raise ValueError("API connection failed")

    result = await executor.run_cancellable(
        failing_tool,
        generation_id=gen_id,
        tool_name="failing_tool",
    )
    assert not result.ok
    assert result.error is not None
    assert "API connection failed" in str(result.error)
    assert not result.cancelled


async def test_build_agent_tools(fence, executor):
    tools = build_agent_tools(executor, fence)
    assert len(tools) == 3
    tool_names = [t.info.name for t in tools]
    assert "book_restaurant" in tool_names
    assert "check_flight_status" in tool_names
    assert "check_weather" in tool_names
