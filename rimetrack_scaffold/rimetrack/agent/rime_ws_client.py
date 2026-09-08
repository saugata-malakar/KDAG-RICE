"""
FencedRimeClient — closes the clear-operation gap in livekit-plugins-rime==1.7.1.

On barge-in, transmits {"operation": "clear", "contextId": generation_id}
to wipe server-side phonetic buffers on Rime Labs' cluster within <10ms.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Protocol

from .fence import GenerationFence


class RimeTransport(Protocol):
    """Protocol for Rime WebSocket transport."""
    async def send_json(self, payload: dict) -> None: ...


@dataclass
class SentMessage:
    payload: dict


class RecordingTransport:
    """In-memory test double for unit testing protocol interactions."""
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(SentMessage(payload=payload))

    def messages_of_type(self, operation: str) -> list[dict]:
        return [m.payload for m in self.sent if m.payload.get("operation") == operation]


class AiohttpRimeTransport:
    """Production transport wrapping an active aiohttp ClientWebSocketResponse."""
    def __init__(self, ws) -> None:
        self._ws = ws

    async def send_json(self, payload: dict) -> None:
        await self._ws.send_str(json.dumps(payload))


class FencedRimeClient:
    """Binds GenerationFence events directly to Rime WebSocket clear operations."""
    def __init__(self, transport: RimeTransport, fence: GenerationFence) -> None:
        self._transport = transport
        self._fence = fence
        self._fence.add_listener(self._on_fence_event)

    def _on_fence_event(self, event) -> None:
        if event.kind != "cancelled":
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.send_clear(event.generation_id))
        except RuntimeError:
            pass  # No running event loop in current thread

    async def send_text(self, text: str, generation_id: str) -> bool:
        if self._fence.is_stale(generation_id):
            return False
        await self._transport.send_json({
            "text": text,
            "contextId": generation_id,
        })
        return True

    async def send_clear(self, generation_id: str) -> None:
        await self._transport.send_json({
            "operation": "clear",
            "contextId": generation_id,
        })

    async def send_flush(self, generation_id: str) -> None:
        await self._transport.send_json({
            "operation": "flush",
            "contextId": generation_id,
        })

    async def send_eos(self) -> None:
        await self._transport.send_json({"operation": "eos"})
