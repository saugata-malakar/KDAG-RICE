"""
RimeTrack agent worker entrypoint.

Implements full-duplex voice with Rime over WebSocket, with GenerationFence
and ToolExecutor wired to LiveKit's native session events.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, llm
from livekit.plugins import deepgram, openai, rime, silero

from .events import EventLog
from .fence import GenerationFence
from .prompts import SYSTEM_INSTRUCTIONS
from .state_manager import ConversationStateManager
from .tool_executor import ToolExecutor
from .tools import build_agent_tools

load_dotenv()

logger = logging.getLogger("rimetrack.session")


def build_rime_tts() -> rime.TTS:
    return rime.TTS(
        model=os.environ.get("RIME_MODEL", "coda"),
        speaker=os.environ.get("RIME_SPEAKER", "astra"),
        lang=os.environ.get("RIME_LANG", "eng"),
        use_websocket=True,
        speed_alpha=1.0,
        api_key=os.environ.get("RIME_API_KEY"),
    )


class RimeTrackAgent(Agent):
    def __init__(self, tools: list[llm.FunctionTool] | None = None) -> None:
        super().__init__(instructions=SYSTEM_INSTRUCTIONS, tools=tools)


def wire_fence_to_session(
    session: AgentSession,
    fence: GenerationFence,
    event_log: EventLog,
    state: ConversationStateManager,
) -> None:
    fence.add_listener(
        lambda ev: event_log.emit(
            f"fence_{ev.kind}", generation_id=ev.generation_id, reason=ev.reason
        )
    )

    @session.on("speech_created")
    def _on_speech_created(ev) -> None:
        gen_id = fence.advance()
        state.start_assistant_turn(gen_id)
        event_log.emit(
            "generation_started",
            generation_id=gen_id,
            speech_handle_id=ev.speech_handle.id,
            source=ev.source,
        )

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev) -> None:
        item = ev.item
        if getattr(item, "type", None) != "message" or getattr(item, "role", None) != "assistant":
            return
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
    def _on_false_interruption(ev) -> None:
        event_log.emit("false_interruption_resumed")

    @session.on("user_state_changed")
    def _on_user_state_changed(ev) -> None:
        if getattr(ev, "new_state", None) == "speaking":
            current = fence.current_generation_id
            event_log.emit("user_speech_started", generation_id=current)

    @session.on("user_input_transcribed")
    def _on_user_transcribed(ev) -> None:
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

    tool_executor = ToolExecutor(fence, event_log)
    tools = build_agent_tools(tool_executor, fence)

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

    await session.start(agent=RimeTrackAgent(tools=tools), room=ctx.room)
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
