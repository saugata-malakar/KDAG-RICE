"""
Pre-TTS Text Normalization for Rime TTS (agent/text_normalize.py).

Follows Rime's house style guide and reference implementation patterns:
- Strips markdown formatting (bold, italics, code backticks, headers, links)
- Normalizes doubled/repeated punctuation while preserving Rime's `?!` interrobang prosody convention
- Cleans whitespace for smooth natural speech synthesis
"""

from __future__ import annotations

import re


def normalize_for_tts(text: str) -> str:
    """Normalizes raw LLM output text for Rime TTS synthesis.
    
    Returns clean, prosody-preserving spoken text.
    """
    if not text:
        return ""

    s = text

    # 1. Strip markdown links: [label](url) -> label
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)

    # 2. Strip code blocks / inline backticks
    s = re.sub(r"```[a-zA-Z]*\n?(.*?)\n?```", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # 3. Strip bold / italics
    s = re.sub(r"\*\*+(.*?)\*\*+", r"\1", s)
    s = re.sub(r"__+(.*?)__+", r"\1", s)
    s = re.sub(r"\*(.*?)\*", r"\1", s)
    s = re.sub(r"_(.*?)_", r"\1", s)

    # 4. Strip header markers (#, ##, etc.) at line starts
    s = re.sub(r"(?m)^#{1,6}\s+", "", s)

    # 5. Strip list bullet points at line starts (- item, * item, 1. item)
    s = re.sub(r"(?m)^\s*[-*+]\s+", "", s)
    s = re.sub(r"(?m)^\s*\d+\.\s+", "", s)

    # 6. Preserve Rime Interrobang conventions (`?!` or `!?` -> `?!`), while collapsing repeated punctuation
    # Protect interrobangs temporarily
    s = re.sub(r"\?\!+|\!+\?", " __INTERROBANG__ ", s)

    # Collapse repeated exclamation points (!! -> !) and question marks (?? -> ?)
    s = re.sub(r"\!{2,}", "!", s)
    s = re.sub(r"\?{2,}", "?", s)

    # Collapse repeated commas
    s = re.sub(r",{2,}", ",", s)

    # Collapse repeated periods (except 3 dots for ellipsis `...`)
    s = re.sub(r"(?<!\.)\.{2}(?!\.)", ".", s)  # 2 dots -> 1 dot
    s = re.sub(r"(?<!\.)\.{4,}(?!\.)", "...", s)  # 4+ dots -> ellipsis

    # Restore interrobangs as Rime's `?!`
    s = s.replace(" __INTERROBANG__ ", "?!")

    # 7. Collapse extra horizontal whitespace
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n", "\n", s)

    return s.strip()
