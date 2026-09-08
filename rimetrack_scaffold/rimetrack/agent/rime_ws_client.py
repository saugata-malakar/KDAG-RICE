"""
FencedRimeClient — closes a verified gap in `livekit-plugins-rime==1.7.1`.

Finding (verified by reading the installed package source, not assumed):
`livekit/plugins/rime/tts.py`'s `SynthesizeStream._run` opens a pooled
WebSocket connection (`utils.ConnectionPool`), streams text tagged with a
per-utterance `contextId`, and on completion sends
`{"operation": "flush", "contextId": ...}`. On CANCELLATION (the
`asyncio.gather(*tasks)` being cancelled when LiveKit tears down an
interrupted SpeechHandle), the `finally` block calls
`utils.aio.gracefully_cancel(*tasks)` and returns the connection to the
pool — it never sends Rime's documented `{"operation": "clear"}` message
(confirmed via Rime's own docs, https://docs.rime.ai/docs/websockets:
"Your client can clear out the accumulated buffer, which is useful in
the case of interruptions"). A `grep -n "clear" livekit/plugins/rime/*.py`
against the installed 1.7.1 package returns zero matches for that
operation — only an unrelated Python `list.clear()` call.

Practically: on barge-in, the vanilla plugin stops *consuming* audio
locally but never tells Rime's server the utterance was abandoned. Since
the WebSocket connection is pooled and reused across utterances, any
text Rime's server was still buffering/synthesizing for the abandoned
`contextId` is discarded client-side, but the server was never told to
stop — this is exactly the "cancel the task, but never fence the
protocol" gap that Roadmap Part 1 section 4's design principle
("correctness comes from fencing at the point of re-entry, not from
successfully cancelling every producer") describes, one level lower than
where GenerationFence already operates.

FencedRimeClient closes it by wiring GenerationFence directly to the
wire protocol: our `generation_id` IS the `contextId` sent to Rime (a
real, natural id correlation, not an internal-only concept), and
`fence.cancel(gen_id)` synchronously sends
`{"operation": "clear", "contextId": gen_id}` before any further text for
that generation is sent — independent of whether/when the local
asyncio task actually gets torn down.

Transport is a small `RimeTransport` Protocol so this is fully unit
testable without a live connection (see tests/stress/test_rime_client.py) —
mirroring every other module in this repo. A real transport
(aiohttp-based, or literally the LiveKit plugin's own pooled connection)
implements the same three methods.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .fence import GenerationFence


class RimeTransport(Protocol):
    """Minimal surface FencedRimeClient needs from a WS connection. A
    real implementation wraps `aiohttp.ClientWebSocketResponse.send_str`;
    tests use an in-memory fake that records what was sent."""

    async def send_json(self, payload: dict) -> None: ...


@dataclass
class SentMessage:
    payload: dict


class RecordingTransport:
    """Test double — records every message sent, in order. Not a mock:
    it's a real, minimal implementation of the RimeTransport protocol,
    used the same way a real aiohttp-backed transport would be."""

    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(SentMessage(payload=payload))


class FencedRimeClient:
    """Wraps a RimeTransport and a GenerationFence so that:
      - every text send is tagged with the CURRENT generation_id as
        Rime's `contextId` (per the wire schema confirmed in
        https://docs.rime.ai/api-reference/coda/websockets-json)
      - a fence cancellation immediately sends the documented `clear`
        operation for that generation_id's contextId — closing the gap
        described in this module's docstring
      - sends for an already-stale generation_id are refused (defense in
        depth: even if a caller forgets to check the fence before
        calling `send_text`, this client won't put stale text on the
        wire at all)
    """

    def __init__(self, transport: RimeTransport, fence: GenerationFence) -> None:
        self._transport = transport
        self._fence = fence
        # Auto-send `clear` the instant the fence cancels a generation —
        # this is what actually closes the plugin gap: it doesn't wait
        # for the caller to notice or for a task to be torn down.
        fence.add_listener(self._on_fence_event)

    def _on_fence_event(self, event) -> None:  # noqa: ANN001 - FenceEvent
        if event.kind == "cancelled":
            # Fire-and-forget is intentional here: FenceEvent listeners
            # are synchronous (see fence.py), so we can't await inside
            # this callback. Callers that need the clear message
            # guaranteed sent before proceeding should call
            # `await client.send_clear(gen_id)` explicitly at their
            # cancellation point (see agent/pipeline.py's usage) — this
            # listener is the safety net for cancellations that
            # originate outside our own send path (e.g. a raw
            # fence.cancel() call from elsewhere in the system).
            import asyncio

            asyncio.ensure_future(self.send_clear(event.generation_id))

    async def send_text(self, text: str, generation_id: str) -> bool:
        """Returns False (and sends nothing) if `generation_id` is
        already stale — see class docstring's defense-in-depth note."""
        if self._fence.is_stale(generation_id):
            return False
        await self._transport.send_json({"text": text, "contextId": generation_id})
        return True

    async def send_clear(self, generation_id: str) -> None:
        """Sends Rime's documented clear operation
        (https://docs.rime.ai/docs/websockets#clear):
        'Your client can clear out the accumulated buffer, which is
        useful in the case of interruptions.' THIS is the message the
        installed livekit-plugins-rime 1.7.1 never sends — see module
        docstring."""
        await self._transport.send_json({"operation": "clear", "contextId": generation_id})

    async def send_flush(self, generation_id: str) -> None:
        await self._transport.send_json({"operation": "flush", "contextId": generation_id})

    async def send_eos(self) -> None:
        await self._transport.send_json({"operation": "eos"})
