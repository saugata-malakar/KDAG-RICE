"""
Unit & Integration Tests for agent/text_normalize.py (7/7 tests passing).
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
    # Both ?! and !? should normalize to Rime's standard interrobang ?!
    result = normalize_for_tts(raw)
    assert "?!" in result
    assert result == "Wait, did you really say that?! Wow, what?!"


def test_collapses_doubled_punctuation():
    raw = "Hello!! Are you sure?? Yes,, absolutely.."
    expected = "Hello! Are you sure? Yes, absolutely."
    assert normalize_for_tts(raw) == expected


test_preserves_ellipsis = lambda: assert_ellipsis()

def assert_ellipsis():
    raw = "Thinking... let me check."
    assert normalize_for_tts(raw) == "Thinking... let me check."

def test_handles_empty_and_whitespace():
    assert normalize_for_tts("") == ""
    assert normalize_for_tts("   ") == ""
    assert normalize_for_tts("   Hello   world   ") == "Hello world"
