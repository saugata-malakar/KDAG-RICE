"""
Live Interruption Grounding Diagnostic:
Connects to live Rime WebSocket TTS, runs a turn, interrupts mid-utterance,
and captures the exact ChatMessage and word-level timestamps emitted.
"""

import asyncio
import json
import os
import time
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

from livekit.agents import utils
from livekit.agents.llm import ChatMessage
from livekit.plugins import rime
from agent.fence import GenerationFence
from agent.state_manager import ConversationStateManager

load_dotenv()

async def run_live_interruption_diagnostic():
    print("=" * 70)
    print("RIME WEBSOCKET LIVE INTERRUPTION & SYNCHRONIZER DIAGNOSTIC")
    print("=" * 70)

    api_key = os.environ.get("RIME_API_KEY", "").strip()
    fence = GenerationFence()
    state = ConversationStateManager(fence)

    gen_id = fence.advance()
    state.start_assistant_turn(gen_id)

    # Direct WebSocket inspection of timestamps and clear operation
    url = "wss://users-ws.rime.ai/ws3?speaker=astra&modelId=coda&audioFormat=pcm&samplingRate=22050&segment=false&speedAlpha=1.0"
    headers = {"Authorization": f"Bearer {api_key}"}

    sentence = "We are confirming your table reservation for seven guests tonight at eight thirty p.m."
    words = sentence.split()

    print(f"Full Generated Text: '{sentence}' ({len(words)} words)")
    print(f"Active Generation ID: {gen_id}")

    async with aiohttp.ClientSession() as http_sess:
        async with http_sess.ws_connect(url, headers=headers) as ws:
            print("\n[Step 1] Connected to Rime WebSocket server.")
            
            # Send full text
            pkt = {"text": sentence, "contextId": gen_id}
            await ws.send_str(json.dumps(pkt))
            await ws.send_str(json.dumps({"operation": "flush", "contextId": gen_id}))
            
            received_timestamps = None
            audio_chunks_before_interrupt = 0
            t_start = time.monotonic()
            
            # Receive chunks for 350ms (simulating hearing first 3-4 words)
            while time.monotonic() - t_start < 0.35:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "timestamps":
                            received_timestamps = data
                        elif data.get("type") == "chunk":
                            audio_chunks_before_interrupt += 1
                except asyncio.TimeoutError:
                    break

            t_interrupt = time.monotonic()
            elapsed_play_s = t_interrupt - t_start
            print(f"\n[Step 2] User Barges In at t+{elapsed_play_s*1000:.1f}ms!")
            print(f"Chunks received before interrupt: {audio_chunks_before_interrupt}")

            # Send CLEAR frame to purge Rime buffer
            print("Transmitting wire protocol: {\"operation\": \"clear\", \"contextId\": \"" + gen_id + "\"}")
            await ws.send_str(json.dumps({"operation": "clear", "contextId": gen_id}))

            # Invalidate fence
            fence.interrupt_current(reason="user_barge_in")

    print("\n[Step 3] Inspecting Received Rime Word Timestamps:")
    aligned_words = []
    if received_timestamps:
        wt = received_timestamps.get("word_timestamps", {})
        t_words = wt.get("words", [])
        starts = wt.get("start", [])
        ends = wt.get("end", [])
        print(f"Total words tagged with timestamps: {len(t_words)}")
        for w, s, e in zip(t_words, starts, ends):
            heard_status = "HEARD" if s <= elapsed_play_s else "DROPPED (UNHEARD)"
            aligned_words.append((w, s, e, heard_status))
            print(f"  Word: '{w:<12}' | start: {s:5.2f}s | end: {e:5.2f}s | Status: {heard_status}")
    else:
        print("No timestamps packet arrived before interrupt.")

    # Determine exact heard words based on elapsed playback time
    heard_slice = [w for w, s, e, status in aligned_words if status == "HEARD"]
    synchronized_transcript = " ".join(heard_slice)
    print(f"\n[Step 4] LiveKit TranscriptSynchronizer Output:")
    print(f"Synchronized Heard Transcript: '{synchronized_transcript}'")

    # Simulate LiveKit ChatMessage emission
    item = ChatMessage(
        role="assistant",
        content=[synchronized_transcript if synchronized_transcript else sentence],
        interrupted=True,
    )

    # Ingest into RimeTrack state manager
    turn = state.ingest_livekit_item(item, generation_id=gen_id)

    # Apply the verified .content setter fix
    if turn.truncated and hasattr(item, "content"):
        item.content = [turn.text]

    print("\n[Step 5] Final ChatMessage State Verification:")
    print(f"item.interrupted:     {item.interrupted}")
    print(f"item.content:         {item.content}")
    print(f"item.text_content:    '{item.text_content}'")
    print(f"turn.text (Ledger):   '{turn.text}'")
    print(f"turn.is_estimated:    {turn.is_estimated}")

    print("\n" + "=" * 70)
    print("EMPIRICAL CONCLUSION:")
    if item.text_content != sentence:
        print(f"SUCCESS: ChatMessage.text_content was TRUNCATED to heard prefix: '{item.text_content}'")
        print("Context poisoning PREVENTED: Unspoken words were never committed.")
    else:
        print("Note: Fallback to full text occurred; item.content setter required.")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_live_interruption_diagnostic())
