"""
ConversationStateManager — the "heard-text ledger" from Roadmap Part 1,
section 4, step 7.

The problem this solves: when the agent is interrupted mid-sentence, the
LLM may have *generated* a full response, but the user only *heard*
whatever audio actually reached Playback before the stop. If the next
LLM call is grounded in the full generated text, the agent will act as
though the user heard something they didn't — a subtler version of the
same staleness bug the GenerationFence prevents at the tool layer.

Two ingestion paths are provided, discovered by reading the installed
`livekit-agents` / `livekit-plugins-rime` source directly (not assumed):

  1. `ingest_livekit_item()` — the PREFERRED path when running on
     LiveKit Agents with the Rime plugin over WebSocket
     (`use_websocket=True`). Reading `livekit/plugins/rime/tts.py`
     confirms Rime's WS protocol sends real per-word `timestamps`
     messages, which the plugin forwards via
     `output_emitter.push_timed_transcript(TimedString(...))`.
     `livekit/agents/llm/chat_context.py` confirms `ChatMessage` carries
     a native `interrupted: bool` flag and `.text_content`. LiveKit's
     own `conversation_item_added` event fires a `ChatMessage` built
     from that same timed-transcript machinery — meaning LiveKit is
     already doing real, word-timing-grounded truncation on our behalf
     when using Rime over WS, and we should ingest that rather than
     reimplement it. This is a stronger foundation than an
     estimated/flush-timestamp proxy: `is_estimated=False` is set on
     results ingested this way.

  2. `record_chunk_played()` / `truncate_on_interrupt()` — a
     LiveKit-independent, chunk-flush-timestamp FALLBACK/PROXY path for
     TTS backends or transports (e.g. HTTP fallback per Roadmap
     Part 1 §6) that don't provide aligned word timing. Results from
     this path are marked `is_estimated=True` since "chunk was handed to
     Playback" is a coarser proxy for "heard" than real per-word timing.

Both paths write into the same `_history`, so callers get one consistent
transcript regardless of which path produced any given turn — but each
`Turn`/`HeardTextResult` is honestly labeled with which path produced it.

This module has no network dependency for path 2. Path 1 only imports
`livekit.agents.llm.chat_context.ChatMessage` as a type (already a
project dependency), not the live session — so this file remains
independently unit-testable (see tests/stress/test_state_manager.py),
including path 1, by constructing real `ChatMessage` instances directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .fence import GenerationFence

if TYPE_CHECKING:
    from livekit.agents.llm.chat_context import ChatMessage

Role = Literal["user", "assistant"]


@dataclass
class Turn:
    role: Role
    text: str
    generation_id: str | None = None
    truncated: bool = False
    """True if this assistant turn was cut short by an interruption —
    `text` is the heard-prefix, not necessarily the full generated
    response."""


@dataclass
class HeardTextResult:
    generation_id: str
    heard_text: str
    is_estimated: bool = True
    """Always True with the current chunk-flush-timestamp proxy (see
    module docstring). Would become False if/when true word-level timing
    metadata from the TTS provider is wired in — kept as an explicit flag
    so downstream consumers (and RIME_EVIDENCE.md) don't overstate
    precision the system doesn't actually have."""


class ConversationStateManager:
    def __init__(self, fence: GenerationFence) -> None:
        self._fence = fence
        self._history: list[Turn] = []
        # generation_id -> list of chunks that were actually handed to
        # Playback (the "played" state) for that generation, in order.
        self._played_chunks: dict[str, list[str]] = {}

    # -- user turns ----------------------------------------------------

    def append_user_turn(self, text: str) -> None:
        self._history.append(Turn(role="user", text=text))

    # -- assistant turn lifecycle ---------------------------------------

    def start_assistant_turn(self, generation_id: str) -> None:
        self._played_chunks.setdefault(generation_id, [])

    def record_chunk_played(self, generation_id: str, text_chunk: str) -> bool:
        """Call this the moment a chunk of agent speech is handed to
        Playback (not when the LLM generates it, not when Rime returns
        bytes — see the generated/queued/played/heard distinction in the
        module docstring). Returns False (and records nothing) if the
        generation is already stale, so a straggling call after
        supersession is a safe no-op rather than silent corruption."""
        if self._fence.is_stale(generation_id):
            return False
        self._played_chunks.setdefault(generation_id, []).append(text_chunk)
        return True

    def finalize_assistant_turn(self, generation_id: str) -> Turn:
        """Call on normal (non-interrupted) completion: commits every
        played chunk as the assistant's turn."""
        text = "".join(self._played_chunks.get(generation_id, []))
        turn = Turn(role="assistant", text=text, generation_id=generation_id, truncated=False)
        self._history.append(turn)
        return turn

    def truncate_on_interrupt(self, generation_id: str) -> HeardTextResult:
        """Call when a generation is interrupted: commits only the
        chunks that were actually played before the cut, as the
        heard-text-prefix (Roadmap §4 step 7) — NOT the full response the
        LLM had generated. This is what makes the *next* LLM call grounded
        in what the user actually heard rather than what the agent was
        about to say."""
        heard_text = "".join(self._played_chunks.get(generation_id, []))
        turn = Turn(role="assistant", text=heard_text, generation_id=generation_id, truncated=True)
        self._history.append(turn)
        return HeardTextResult(generation_id=generation_id, heard_text=heard_text)

    # -- context for the next LLM call -----------------------------------

    def get_context(self) -> list[Turn]:
        return list(self._history)

    def get_context_as_chat_messages(self) -> list[dict[str, str]]:
        """Convenience for wiring into livekit.agents.llm.ChatContext or
        an OpenAI-style messages list."""
        return [{"role": t.role, "content": t.text} for t in self._history]

    # -- LiveKit-native ingestion path (preferred, see module docstring) --

    def ingest_livekit_item(self, item: "ChatMessage", generation_id: str | None) -> Turn:
        """Ingest a `ChatMessage` from LiveKit's `conversation_item_added`
        event. Only meaningful for assistant messages; user messages
        should go through `append_user_turn` from the ASR transcript
        directly (LiveKit's own user ChatMessage is a fine alternative
        source too, callers may pick either consistently).

        Uses `item.interrupted` and `item.text_content` — both confirmed
        fields on the installed `ChatMessage` model — as ground truth.
        When Rime is run over WebSocket with aligned transcripts (the
        default RimeTrack config, see agent/session.py), this text is
        already word-timing-grounded per the module docstring, so this
        path sets `is_estimated=False` on interrupted turns, unlike the
        chunk-flush proxy path.
        """
        text = item.text_content or ""
        turn = Turn(
            role="assistant",
            text=text,
            generation_id=generation_id,
            truncated=bool(item.interrupted),
        )
        self._history.append(turn)
        return turn
