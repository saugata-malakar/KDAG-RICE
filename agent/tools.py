"""
Fence-aware tool functions for the live RimeTrack agent.

These tools demonstrate the hackathon's required proof:
"Introduce a fixed delay into a tool call. While the agent is speaking or waiting,
interrupt it and change one part of the request. Verify that queued Rime audio stops
promptly, the updated instruction reaches the application, stale tool results are
not spoken as current, background work is cancelled or reconciled correctly, and
the final spoken response reflects what the user actually heard and requested."

Each tool uses a deliberate asyncio.sleep() delay, and is wrapped by the
ToolExecutor (from tool_executor.py) which checks GenerationFence staleness
before allowing the result to re-enter conversation state.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Callable

from livekit.agents import llm
from .fence import GenerationFence
from .tool_executor import ToolExecutor, ToolResult


@dataclass
class BookingResult:
    booking_id: str
    restaurant: str
    time: str
    party_size: int
    confirmed: bool


@dataclass
class FlightInfo:
    flight_number: str
    status: str
    gate: str
    departure_time: str


@dataclass
class WeatherInfo:
    city: str
    temperature_f: int
    condition: str
    humidity_pct: int


async def book_restaurant(name: str, time: str, party_size: int, *, delay: float = 3.0) -> BookingResult:
    """Simulate a restaurant booking with a deliberate 3.0-second delay.
    This is the uncancellable tool that demonstrates result fencing:
    once submitted, the booking goes through, but the fence quarantines
    the result if the user interrupted to change their request."""
    await asyncio.sleep(delay)  # Deliberate delay per hackathon requirement
    booking_id = f"BK-{random.randint(1000, 9999)}"
    return BookingResult(
        booking_id=booking_id,
        restaurant=name,
        time=time,
        party_size=party_size,
        confirmed=True,
    )


async def check_flight_status(flight_number: str, *, delay: float = 1.5) -> FlightInfo:
    """Simulate a flight status lookup with a 1.5-second delay.
    This is a cancellable tool: the lookup can be aborted mid-request
    when the user interrupts to change or cancel their query."""
    await asyncio.sleep(delay)
    return FlightInfo(
        flight_number=flight_number,
        status="On Time",
        gate=f"B{random.randint(1, 30)}",
        departure_time="14:30",
    )


async def check_weather(city: str, *, delay: float = 0.5) -> WeatherInfo:
    """Simulate a weather check with a 0.5-second delay.
    Fast cancellable tool for testing rapid barge-in scenarios."""
    await asyncio.sleep(delay)
    return WeatherInfo(
        city=city,
        temperature_f=random.randint(60, 95),
        condition=random.choice(["Sunny", "Partly Cloudy", "Clear"]),
        humidity_pct=random.randint(30, 80),
    )


def build_agent_tools(executor: ToolExecutor, fence: GenerationFence) -> list[llm.FunctionTool]:
    """Factory creating LiveKit @llm.function_tool instances wired to GenerationFence."""

    @llm.function_tool(
        name="book_restaurant",
        description="Book a table at a restaurant. Has a 3-second delay to test interruption handling.",
    )
    async def _book_restaurant(name: str, time: str, party_size: int) -> str:
        gen_id = fence.current_generation_id or "G0"
        result = await executor.run_uncancellable(
            lambda: book_restaurant(name, time, party_size),
            generation_id=gen_id,
            tool_name="book_restaurant",
        )
        if result.cancelled:
            return "Reservation was cancelled or superseded by an interruption."
        if result.error:
            return f"Reservation failed: {result.error}"
        val: BookingResult = result.value
        return f"Confirmed table for {val.party_size} at {val.restaurant} at {val.time}. Confirmation: {val.booking_id}."

    @llm.function_tool(
        name="check_flight_status",
        description="Check status for a flight. Has a 1.5-second lookup delay.",
    )
    async def _check_flight_status(flight_number: str) -> str:
        gen_id = fence.current_generation_id or "G0"
        result = await executor.run_cancellable(
            lambda: check_flight_status(flight_number),
            generation_id=gen_id,
            tool_name="check_flight_status",
        )
        if result.cancelled:
            return "Flight check aborted due to user interruption."
        if result.error:
            return f"Flight check error: {result.error}"
        val: FlightInfo = result.value
        return f"Flight {val.flight_number} is {val.status}, departing at {val.departure_time} from Gate {val.gate}."

    @llm.function_tool(
        name="check_weather",
        description="Get current weather for a city. Has a 0.5-second lookup delay.",
    )
    async def _check_weather(city: str) -> str:
        gen_id = fence.current_generation_id or "G0"
        result = await executor.run_cancellable(
            lambda: check_weather(city),
            generation_id=gen_id,
            tool_name="check_weather",
        )
        if result.cancelled:
            return "Weather lookup aborted."
        if result.error:
            return f"Weather check error: {result.error}"
        val: WeatherInfo = result.value
        return f"Weather in {val.city}: {val.temperature_f}F, {val.condition}."

    return [_book_restaurant, _check_flight_status, _check_weather]


# Backwards-compatible class wrapper
class RimeTrackTools:
    def __init__(self, executor: ToolExecutor, fence: GenerationFence | None = None):
        self.executor = executor
        self.fence = fence or getattr(executor, "_fence", None)
        self.tools = build_agent_tools(executor, self.fence) if self.fence else []
