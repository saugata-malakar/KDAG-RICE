"""
Tests for FencedRimeClient (agent/rime_ws_client.py).

The central test here, `test_interruption_sends_documented_clear_operation`,
is a regression test for a REAL, VERIFIED gap: reading
`livekit/plugins/rime/tts.py` in the installed `livekit-plugins-rime==1.7.1`
package shows it never sends Rime's documented `{"operation": "clear"}`
message on interruption (see rime_ws_client.py's module docstring for the
full trace). This test asserts our own client does not have that gap.
"""

from __future__ import annotations

import asyncio

import pytest

from agent.fence import GenerationFence
from agent.rime_ws_client import FencedRimeClient, RecordingTransport


@pytest.mark.asyncio
async def test_text_send_tags_current_generation_as_context_id():
    fence = GenerationFence()
    transport = RecordingTransport()
    client = FencedRimeClient(transport, fence)
    g1 = fence.advance()

    sent = await client.send_text("Sure, booking a table", g1)

    assert sent is True
    assert transport.sent[0].payload == {"text": "Sure, booking a table", "contextId": g1}


@pytest.mark.asyncio
async def test_send_text_for_stale_generation_is_refused():
    fence = GenerationFence()
    transport = RecordingTransport()
    client = FencedRimeClient(transport, fence)
    g1 = fence.advance()
    fence.interrupt_current()  # g1 now stale

    sent = await client.send_text("late straggling text", g1)

    assert sent is False
    assert transport.sent == []  # nothing hit the wire for a stale generation


@pytest.mark.asyncio
async def test_interruption_sends_documented_clear_operation():
    """THE regression test for the verified livekit-plugins-rime 1.7.1
    gap: FencedRimeClient must send {"operation": "clear", "contextId": g1}
    the moment the fence cancels g1 — not "eventually", not "only if the
    caller remembers to call something", but as a direct, automatic
    consequence of the fence transition itself (see
    FencedRimeClient._on_fence_event)."""
    fence = GenerationFence()
    transport = RecordingTransport()
    client = FencedRimeClient(transport, fence)
    g1 = fence.advance()
    await client.send_text("Sure, booking a table for seven", g1)

    fence.interrupt_current(reason="user_barge_in")
    # The listener dispatches via asyncio.ensure_future (fence.py's
    # listeners are synchronous, see rime_ws_client.py's docstring) —
    # yield control once so the scheduled task actually runs.
    await asyncio.sleep(0)

    clear_messages = [m.payload for m in transport.sent if m.payload.get("operation") == "clear"]
    assert clear_messages == [{"operation": "clear", "contextId": g1}]


@pytest.mark.asyncio
async def test_explicit_send_clear_does_not_depend_on_listener_timing():
    """Callers that need the clear message guaranteed sent before
    proceeding (e.g. agent/pipeline.py at its own cancellation point)
    should call send_clear directly rather than relying on the
    fire-and-forget listener's scheduling — this test exercises that
    explicit path."""
    fence = GenerationFence()
    transport = RecordingTransport()
    client = FencedRimeClient(transport, fence)
    g1 = fence.advance()

    await client.send_clear(g1)

    assert transport.sent[-1].payload == {"operation": "clear", "contextId": g1}


@pytest.mark.asyncio
async def test_flush_and_eos_use_documented_schema():
    fence = GenerationFence()
    transport = RecordingTransport()
    client = FencedRimeClient(transport, fence)
    g1 = fence.advance()

    await client.send_flush(g1)
    await client.send_eos()

    assert transport.sent[-2].payload == {"operation": "flush", "contextId": g1}
    assert transport.sent[-1].payload == {"operation": "eos"}


@pytest.mark.asyncio
async def test_rapid_reinterruption_sends_clear_for_each_superseded_generation():
    """Scenario: 2 interruptions in quick succession — each superseded
    generation must get its own clear message with its own contextId,
    not a single clear for whichever generation happened to be current
    last."""
    fence = GenerationFence()
    transport = RecordingTransport()
    client = FencedRimeClient(transport, fence)

    g1 = fence.advance()
    await client.send_text("first attempt", g1)
    fence.interrupt_current()
    await asyncio.sleep(0)

    g2 = fence.current_generation_id
    await client.send_text("second attempt", g2)
    fence.interrupt_current()
    await asyncio.sleep(0)

    clears = [m.payload["contextId"] for m in transport.sent if m.payload.get("operation") == "clear"]
    assert clears == [g1, g2]
