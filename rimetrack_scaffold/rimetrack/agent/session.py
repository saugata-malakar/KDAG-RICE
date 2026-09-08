"""
RimeTrack agent worker entrypoint.

Implements Roadmap Phase 1 (minimal ASR -> LLM -> TTS turn) and Phase 2
(Rime swapped in over WebSocket), with the GenerationFence (fence.py)
wired to LiveKit's own interruption events so that a barge-in immediately:

  1. advances the fence to a new generation_id (agent.speech_created /
     the SpeechHandle LiveKit already tracks per turn — see below), and
  2. is logged to the structured event log (events.py) for the eval
     harness (Phase 8/10).

Design note on "why wire the fence to LiveKit's own events instead of
writing our own VAD/turn-detection from scratch": LiveKit Agents already
ships a SpeechHandle per turn (livekit.agents.voice.speech_handle) with
its own `.id` and `.interrupted` — confirmed by inspecting the installed
package. That native mechanism already governs whether a given TTS
utterance keeps playing. RimeTrack's fence is deliberately layered
*outside* that: LiveKit's SpeechHandle governs speech, but nothing in the
framework fences a tool result that completes after its turn was
abandoned from re-entering conversation state. That gap is what
tool_executor.py + fence.py exist to close (see Roadmap Part 1, section
7 — "what LiveKit gives you for free" vs. "what RimeTrack must still
build itself").

Run locally with:
    python -m agent.session dev
(requires LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET / RIME_API_KEY
 / DEEPGRAM_API_KEY / OPENAI_API_KEY in the environment — see .env.example)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions
from livekit.plugins import deepgram, openai, rime, silero

from .events import EventLog
from .fence import GenerationFence
from .prompts import SYSTEM_INSTRUCTIONS
from .state_manager import ConversationStateManager

load_dotenv()

logger = logging.getLogger("rimetrack.session")


def build_rime_tts() -> rime.TTS:
    """Rime TTS over WebSocket (Roadmap Part 1, section 6): WS is chosen
    specifically because it's the transport that supports mid-stream
    cancellation, unlike the one-shot HTTP endpoint. `speed_alpha` (not
    `time_scale_factor`/audio_speed) is the WS-compatible speed control
    per the LiveKit x Rime integration docs.
    """
    return rime.TTS(
        model=os.environ.get("RIME_MODEL", "coda"),
        speaker=os.environ.get("RIME_SPEAKER", "astra"),
        lang=os.environ.get("RIME_LANG", "eng"),
        use_websocket=True,
        speed_alpha=1.0,
        api_key=os.environ.get("RIME_API_KEY"),
    )


class RimeTrackAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_INSTRUCTIONS)


def wire_fence_to_session(
    session: AgentSession,
    fence: GenerationFence,
    event_log: EventLog,
    state: ConversationStateManager,
) -> None:
    """Bridge LiveKit's native session events to RimeTrack's fence, the
    heard-text ledger, and the structured event log. This is intentionally
    the ONLY place session wiring and fence/state logic touch each other,
    so fence.py / state_manager.py stay LiveKit-independent and
    unit-testable on their own (see tests/stress/).
    """

    # Every listener also forwards to the event log so the eval harness
    # (Roadmap Phase 8/10) has a single JSONL source of truth per session.
    fence.add_listener(
        lambda ev: event_log.emit(
            f"fence_{ev.kind}", generation_id=ev.generation_id, reason=ev.reason
        )
    )

    @session.on("speech_created")
    def _on_speech_created(ev) -> None:  # noqa: ANN001 - SpeechCreatedEvent
        gen_id = fence.advance()
        state.start_assistant_turn(gen_id)
        event_log.emit(
            "generation_started",
            generation_id=gen_id,
            speech_handle_id=ev.speech_handle.id,
            source=ev.source,
        )

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev) -> None:  # noqa: ANN001
        item = ev.item
        # Only assistant ChatMessages carry the interrupted/text_content
        # fields we care about here (see state_manager.py's module
        # docstring for why this is the PREFERRED ingestion path over
        # chunk-flush tracking when running Rime over WebSocket with
        # aligned transcripts, which build_rime_tts() above enables).
        if getattr(item, "type", None) != "message" or getattr(item, "role", None) != "assistant":
            return
        # ConversationItemAddedEvent doesn't carry a speech_handle_id, so
        # we fall back to "whichever generation is current" — correct for
        # the common one-speech-per-generation case; a fully robust
        # id-correlation scheme would need LiveKit to expose the
        # originating speech_handle_id on this event, which it doesn't
        # today. Flagged in README "Known limitations" rather than
        # silently assumed correct.
        gen_id = fence.current_generation_id
        turn = state.ingest_livekit_item(item, generation_id=gen_id)
        event_log.emit(
            "conversation_item_ingested",
            generation_id=gen_id,
            role="assistant",
            truncated=turn.truncated,
            text_len=len(turn.text),
        )

    @session.on("agent_false_interruption")
    def _on_false_interruption(ev) -> None:  # noqa: ANN001
        # LiveKit decided a detected interruption was actually a
        # backchannel/noise and is resuming — nothing to fence, just log it
        # so it's distinguishable from a real barge-in in the eval data.
        event_log.emit("false_interruption_resumed")

    @session.on("user_state_changed")
    def _on_user_state_changed(ev) -> None:  # noqa: ANN001
        if getattr(ev, "new_state", None) == "speaking":
            current = fence.current_generation_id
            # A genuine barge-in candidate: the user started speaking while
            # the current generation may still be live. We don't
            # unconditionally cancel here — LiveKit's own interruption
            # classifier (adaptive/vad, configured in AgentSession below)
            # decides whether this actually interrupts the agent's speech.
            # We just log the signal; the fence is advanced for real in
            # `speech_created` above, once LiveKit has committed to a new
            # turn following a genuine interruption.
            event_log.emit("user_speech_started", generation_id=current)

    @session.on("user_input_transcribed")
    def _on_user_transcribed(ev) -> None:  # noqa: ANN001
        if getattr(ev, "is_final", False):
            text = getattr(ev, "transcript", None)
            if text:
                state.append_user_turn(text)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    session_id = ctx.room.name or "unknown-room"
    log_path = Path(os.environ.get("RIMETRACK_LOG_DIR", "eval/results")) / f"{session_id}.jsonl"
    event_log = EventLog(session_id=session_id, path=log_path)
    fence = GenerationFence()
    state = ConversationStateManager(fence)

    # Fallback to openai.STT if DEEPGRAM_API_KEY is not configured
    dg_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if dg_key and dg_key != "your_deepgram_api_key":
        stt_plugin = deepgram.STT(model="nova-3")
    else:
        stt_plugin = openai.STT()

    session = AgentSession(
        stt=stt_plugin,
        vad=silero.VAD.load(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=build_rime_tts(),
        # Current (non-deprecated) turn-handling API, confirmed against
        # livekit.agents.voice.turn.TurnHandlingOptions on the installed
        # package. "adaptive" uses LiveKit's ML-based barge-in vs.
        # backchannel classifier (Roadmap Part 1 section 7 / Part 2
        # Phase 4); falls back to VAD-only thresholds if adaptive isn't
        # available on this deployment tier.
        turn_handling={
            "turn_detection": "vad",
            "interruption": {
                "enabled": True,
                "mode": "adaptive",
                "min_duration": 0.5,
                "min_words": 0,
                "resume_false_interruption": True,
                "false_interruption_timeout": 2.0,
                "discard_audio_if_uninterruptible": True,
            },
        },
    )

    wire_fence_to_session(session, fence, event_log, state)

    await session.start(agent=RimeTrackAgent(), room=ctx.room)
    event_log.emit("session_started")


if __name__ == "__main__":
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=os.environ.get("LIVEKIT_URL"),
            api_key=os.environ.get("LIVEKIT_API_KEY"),
            api_secret=os.environ.get("LIVEKIT_API_SECRET"),
        )
    )

