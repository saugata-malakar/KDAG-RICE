"""
Pre-TTS Text Normalization for Rime TTS (agent/text_normalize.py).

Follows Brooke Larson's "Writing for the ear" guidance and Rime house rules:
- Strips markdown formatting (bold, italics, backticks, headers, links)
- Expands domain codes, flight numbers, currency, and times into natural spoken equivalents
- Normalizes doubled/repeated punctuation while preserving Rime's `?!` interrobang
- Cleans whitespace for seamless neural audio synthesis
"""

from __future__ import annotations

import re


def expand_spoken_domain_terms(text: str) -> str:
    """Expands domain codes, times, and currency into ear-friendly spoken form."""
    s = text

    # Currency: $50 -> 50 dollars, $100.50 -> 100 dollars 50 cents
    s = re.sub(r"\$(\d+)\.(\d{2})\b", r"\1 dollars and \2 cents", s)
    s = re.sub(r"\$(\d+)\b", r"\1 dollars", s)

    # Time: 7:30pm -> 7:30 p.m., 7pm -> 7 p.m.
    s = re.sub(r"\b(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)\b", r"\1:\2 \3", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(\d{1,2})\s*([ap]\.?m\.?)\b", r"\1 \2", s, flags=re.IGNORECASE)

    # Percentages: 95% -> 95 percent
    s = re.sub(r"(\d+)%", r"\1 percent", s)

    # Flight / Alpha-numeric codes: UA-402 -> UA 402, BK-5521 -> BK 5521
    s = re.sub(r"\b([A-Z]{2,3})-(\d{3,4})\b", r"\1 \2", s)

    return s


def normalize_for_tts(text: str) -> str:
    """Normalizes raw LLM text into prosody-preserving, ear-optimized speech text."""
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

    # 6. Domain phonetic expansions
    s = expand_spoken_domain_terms(s)

    # 7. Preserve Rime Interrobang (`?!` or `!?` -> `?!`), while collapsing repeated punctuation
    s = re.sub(r"\?\!+|\!+\?", " __INTERROBANG__ ", s)
    s = re.sub(r"\!{2,}", "!", s)
    s = re.sub(r"\?{2,}", "?", s)
    s = re.sub(r",{2,}", ",", s)
    s = re.sub(r"(?<!\.)\.{2}(?!\.)", ".", s)  # 2 dots -> 1 dot
    s = re.sub(r"(?<!\.)\.{4,}(?!\.)", "...", s)  # 4+ dots -> ellipsis
    s = s.replace(" __INTERROBANG__ ", "?!")

    # 8. Collapse extra whitespace
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n", "\n", s)

    return s.strip()
