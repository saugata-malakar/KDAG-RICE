"""
Unit tests for ConversationStateManager (agent/state_manager.py).

Covers Roadmap Part 2, section 10 rows:
  - "user changing their mind" / heard-text ledger correctness
  - late chunk after supersession is dropped (mirrors test_fence.py's
    version of this scenario, but at the state-manager layer)
"""

from __future__ import annotations

from agent.fence import GenerationFence
from agent.state_manager import ConversationStateManager


def test_normal_completion_commits_full_text():
    fence = GenerationFence()
    state = ConversationStateManager(fence)
    g1 = fence.advance()

    state.append_user_turn("What's the weather like?")
    state.start_assistant_turn(g1)
    for chunk in ["It's sunny ", "and about ", "seventy degrees."]:
        assert state.record_chunk_played(g1, chunk) is True

    turn = state.finalize_assistant_turn(g1)

    assert turn.text == "It's sunny and about seventy degrees."
    assert turn.truncated is False
    assert state.get_context()[-1] is turn


def test_interruption_mid_sentence_commits_only_heard_prefix():
    """Central scenario: the LLM 'generated' a full sentence, but the
    user only 'heard' part of it before interrupting — the ledger must
    reflect the heard prefix, not the full generated text."""
    fence = GenerationFence()
    state = ConversationStateManager(fence)
    g1 = fence.advance()

    state.append_user_turn("Book me a table for 7pm.")
    state.start_assistant_turn(g1)

    # Chunks actually flushed to Playback before the user interrupts...
    state.record_chunk_played(g1, "Sure, booking a table for ")
    state.record_chunk_played(g1, "seven ")
    # ...user interrupts right here, before "pm at your usual place." plays.
    fence.interrupt_current(reason="user_barge_in")

    # A straggling chunk that was already in flight when cancel fired
    # must NOT be appended — record_chunk_played checks the fence itself.
    recorded = state.record_chunk_played(g1, "pm at your usual place.")
    assert recorded is False

    result = state.truncate_on_interrupt(g1)

    assert result.heard_text == "Sure, booking a table for seven "
    assert result.is_estimated is True

    last_turn = state.get_context()[-1]
    assert last_turn.role == "assistant"
    assert last_turn.truncated is True
    assert last_turn.text == "Sure, booking a table for seven "
    assert "usual place" not in last_turn.text


def test_next_llm_call_is_grounded_in_heard_prefix_not_full_response():
    """After truncation, the context handed to the next LLM call must
    contain the heard prefix as history, and the new user utterance
    appended after it — this is what lets the follow-up response be
    coherent with what was actually said aloud."""
    fence = GenerationFence()
    state = ConversationStateManager(fence)
    g1 = fence.advance()

    state.append_user_turn("Book me a table for 7pm.")
    state.start_assistant_turn(g1)
    state.record_chunk_played(g1, "Sure, booking a table for seven ")
    fence.interrupt_current()
    state.truncate_on_interrupt(g1)

    state.append_user_turn("Actually, make that six.")

    messages = state.get_context_as_chat_messages()
    assert messages == [
        {"role": "user", "content": "Book me a table for 7pm."},
        {"role": "assistant", "content": "Sure, booking a table for seven "},
        {"role": "user", "content": "Actually, make that six."},
    ]


def test_chunks_for_a_generation_that_never_started_are_rejected():
    """Defensive check: recording a chunk against a generation_id the
    fence has never seen as current is treated the same as stale — the
    ledger must not silently accept it."""
    fence = GenerationFence()
    state = ConversationStateManager(fence)
    fence.advance()  # G1 is current, but we never call start_assistant_turn

    accepted = state.record_chunk_played("G999-never-existed", "ghost chunk")
    assert accepted is False


def test_rapid_consecutive_interruptions_each_get_correct_heard_prefix():
    """Scenario: multiple interruptions in a row, each must produce its
    own correctly-scoped heard-text-prefix without bleeding into the
    next generation's ledger."""
    fence = GenerationFence()
    state = ConversationStateManager(fence)

    g1 = fence.advance()
    state.start_assistant_turn(g1)
    state.record_chunk_played(g1, "First attempt at ")
    fence.interrupt_current()
    r1 = state.truncate_on_interrupt(g1)

    g2 = fence.current_generation_id
    state.start_assistant_turn(g2)
    state.record_chunk_played(g2, "Second attempt, ")
    state.record_chunk_played(g2, "slightly longer ")
    fence.interrupt_current()
    r2 = state.truncate_on_interrupt(g2)

    assert r1.heard_text == "First attempt at "
    assert r2.heard_text == "Second attempt, slightly longer "
    assert r1.generation_id != r2.generation_id


# ---------------------------------------------------------------------------
# LiveKit-native ingestion path (uses REAL ChatMessage instances, not mocks —
# see agent/state_manager.py's module docstring for why this path exists and
# what it's grounded in: livekit/plugins/rime/tts.py's word_timestamps ->
# push_timed_transcript wiring, confirmed by reading the installed package).
# ---------------------------------------------------------------------------


def test_ingest_livekit_item_non_interrupted():
    from livekit.agents.llm.chat_context import ChatMessage

    fence = GenerationFence()
    state = ConversationStateManager(fence)
    g1 = fence.advance()

    item = ChatMessage(
        role="assistant",
        content=["It's sunny and about seventy degrees."],
        interrupted=False,
    )
    turn = state.ingest_livekit_item(item, generation_id=g1)

    assert turn.text == "It's sunny and about seventy degrees."
    assert turn.truncated is False
    assert state.get_context()[-1] is turn


def test_ingest_livekit_item_interrupted_uses_native_truncated_text():
    """The central claim of the LiveKit-native path: when LiveKit itself
    marks a ChatMessage as interrupted, its `.text_content` is ALREADY
    the word-timing-truncated heard text (per Rime's aligned transcript
    over WS) — we ingest it as-is rather than re-deriving it, and we
    mark the resulting Turn as truncated so downstream LLM context
    reflects it correctly."""
    from livekit.agents.llm.chat_context import ChatMessage

    fence = GenerationFence()
    state = ConversationStateManager(fence)
    g1 = fence.advance()

    item = ChatMessage(
        role="assistant",
        content=["Sure, booking a table for seven"],  # LiveKit already cut it here
        interrupted=True,
    )
    turn = state.ingest_livekit_item(item, generation_id=g1)

    assert turn.truncated is True
    assert turn.text == "Sure, booking a table for seven"
    assert "usual place" not in turn.text


def test_ingest_livekit_item_then_new_user_turn_produces_grounded_context():
    from livekit.agents.llm.chat_context import ChatMessage

    fence = GenerationFence()
    state = ConversationStateManager(fence)
    g1 = fence.advance()

    state.append_user_turn("Book me a table for 7pm.")
    item = ChatMessage(
        role="assistant",
        content=["Sure, booking a table for seven"],
        interrupted=True,
    )
    state.ingest_livekit_item(item, generation_id=g1)
    state.append_user_turn("Actually, make that six.")

    messages = state.get_context_as_chat_messages()
    assert messages == [
        {"role": "user", "content": "Book me a table for 7pm."},
        {"role": "assistant", "content": "Sure, booking a table for seven"},
        {"role": "user", "content": "Actually, make that six."},
    ]
