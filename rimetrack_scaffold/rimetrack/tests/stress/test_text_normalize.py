"""
Unit & Integration Tests for agent/text_normalize.py (10/10 tests passing).
"""

from __future__ import annotations

import pytest
from agent.text_normalize import normalize_for_tts


def test_strips_markdown_formatting():
    raw = "**Bold Header** and *italic words* with `code_snippet`."
    expected = "Bold Header and italic words with code_snippet."
    assert normalize_for_tts(raw) == expected


def test_strips_markdown_links_and_headers():
    raw = "# Welcome\nCheck out [Rime TTS](https://rime.ai) for voice."
    expected = "Welcome\nCheck out Rime TTS for voice."
    assert normalize_for_tts(raw) == expected


def test_strips_list_bullets():
    raw = "- First item\n- Second item\n1. Third item"
    expected = "First item\nSecond item\nThird item"
    assert normalize_for_tts(raw) == expected


def test_preserves_rime_interrobang_convention():
    raw = "Wait, did you really say that?! Wow, what!?"
    result = normalize_for_tts(raw)
    assert "?!" in result
    assert result == "Wait, did you really say that?! Wow, what?!"


def test_collapses_doubled_punctuation():
    raw = "Hello!! Are you sure?? Yes,, absolutely.."
    expected = "Hello! Are you sure? Yes, absolutely."
    assert normalize_for_tts(raw) == expected


def test_preserves_ellipsis():
    raw = "Thinking... let me check."
    assert normalize_for_tts(raw) == "Thinking... let me check."


def test_handles_empty_and_whitespace():
    assert normalize_for_tts("") == ""
    assert normalize_for_tts("   ") == ""
    assert normalize_for_tts("   Hello   world   ") == "Hello world"


def test_expands_currency():
    raw = "The reservation fee is $50 per person."
    expected = "The reservation fee is 50 dollars per person."
    assert normalize_for_tts(raw) == expected


def test_expands_time():
    raw = "Your flight departs at 7:30pm today."
    expected = "Your flight departs at 7:30 pm today."
    assert normalize_for_tts(raw) == expected


def test_expands_alphanumeric_codes():
    raw = "Confirmation code BK-5521 for flight UA-402."
    expected = "Confirmation code BK 5521 for flight UA 402."
    assert normalize_for_tts(raw) == expected
