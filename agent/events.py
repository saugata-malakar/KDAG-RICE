"""
Structured event logging for RimeTrack.

Every pipeline component (turn manager, fence, tool executor, TTS client)
emits events through `log_event`. The resulting JSONL file is the evidence
artifact for RIME_EVIDENCE.md and the input to eval/metrics.py — see
Roadmap Part 2, sections 8 and 11.

Kept dependency-free (stdlib only) so it can be unit-tested without any
LiveKit/Rime credentials.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Event:
    event_type: str
    generation_id: str | None
    session_id: str
    ts_wall: float = field(default_factory=time.time)
    ts_mono: float = field(default_factory=time.monotonic)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class EventLog:
    """Append-only JSONL event log for one conversation session.

    Usage:
        log = EventLog(session_id="abc123", path=Path("logs/abc123.jsonl"))
        log.emit("generation_started", generation_id="G1")
        log.emit("cancel_issued", generation_id="G1", reason="user_barge_in")
    """

    def __init__(self, session_id: str, path: Path | None = None) -> None:
        self.session_id = session_id
        self.path = path
        self._events: list[Event] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, generation_id: str | None = None, **payload: Any) -> Event:
        ev = Event(
            event_type=event_type,
            generation_id=generation_id,
            session_id=self.session_id,
            payload=payload,
        )
        self._events.append(ev)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(ev.to_json() + "\n")
        return ev

    def events(self) -> list[Event]:
        return list(self._events)

    def events_for_generation(self, generation_id: str) -> list[Event]:
        return [e for e in self._events if e.generation_id == generation_id]
