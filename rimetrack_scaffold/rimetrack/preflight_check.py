"""
RimeTrack Preflight Configuration Check

Validates all required environment variables, API key formats, organizer-
provided Rime configuration, and scans for accidentally committed secrets
before running any tests or deploying the agent.

Usage:
    python preflight_check.py

Exit codes:
    0 — All checks passed (warnings are acceptable).
    1 — One or more REQUIRED checks failed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

# ──────────────────────────────────────────────────────────────
# Check definitions
# ──────────────────────────────────────────────────────────────

PASS = "OK"
FAIL = "FAIL"
WARN = "WARN"

results: list[tuple[str, str, str]] = []  # (status, name, message)


def check_required(name: str, *, prefix: str | None = None, placeholder: str | None = None) -> str | None:
    """Check that an env var is set, non-empty, not a placeholder, and optionally has the right prefix."""
    val = os.environ.get(name, "").strip()
    if not val:
        results.append((FAIL, name, "Missing — this variable is REQUIRED"))
        return None
    if placeholder and val == placeholder:
        results.append((FAIL, name, f"Still set to placeholder value '{placeholder}'"))
        return None
    if prefix and not val.startswith(prefix):
        results.append((FAIL, name, f"Expected prefix '{prefix}', got '{val[:12]}...'"))
        return None
    return val


def check_optional(name: str, *, fallback_msg: str = "Missing") -> str | None:
    """Check that an optional env var is set. Warns (not fails) if absent."""
    val = os.environ.get(name, "").strip()
    if not val:
        results.append((WARN, name, f"{fallback_msg}"))
        return None
    return val


def check_exact(name: str, expected: str, *, label: str = "") -> bool:
    """Check that an env var matches an exact expected value."""
    val = os.environ.get(name, "").strip()
    if not val:
        results.append((FAIL, name, f"Missing — expected '{expected}'"))
        return False
    if val != expected:
        results.append((WARN, name, f"Got '{val}', expected organizer spec '{expected}'"))
        return False
    desc = f"{val} (matches organizer spec)" if not label else f"{val} ({label})"
    results.append((PASS, name, desc))
    return True


def scan_readme_for_secrets() -> bool:
    """Scan README.md for accidentally committed raw API secrets."""
    readme_path = Path(__file__).parent / "README.md"
    if not readme_path.exists():
        results.append((WARN, "README Secret Scan", "README.md not found — skipping"))
        return True

    content = readme_path.read_text(encoding="utf-8", errors="replace")

    # Patterns that should NEVER appear in README.md
    dangerous_patterns = [
        (r"sk-proj-[A-Za-z0-9_-]{20,}", "OpenAI API key (sk-proj-...)"),
        (r"sk-[A-Za-z0-9_-]{40,}", "OpenAI API key (sk-...)"),
        (r"LIVEKIT_API_SECRET\s*=\s*[A-Za-z0-9_-]{20,}", "Raw LIVEKIT_API_SECRET value"),
        (r"RIME_API_KEY\s*=\s*[A-Za-z0-9_-]{20,}", "Raw RIME_API_KEY value"),
        (r"DEEPGRAM_API_KEY\s*=\s*[A-Za-z0-9_-]{20,}", "Raw DEEPGRAM_API_KEY value"),
    ]

    leaked = []
    for pattern, desc in dangerous_patterns:
        # Exclude patterns inside code blocks that are clearly placeholders
        matches = re.findall(pattern, content)
        real_matches = [m for m in matches if "xxxx" not in m.lower() and "your_" not in m.lower() and "placeholder" not in m.lower()]
        if real_matches:
            leaked.append(f"{desc} ({len(real_matches)} occurrence(s))")

    if leaked:
        results.append((FAIL, "README Secret Scan", "LEAKED SECRETS FOUND: " + "; ".join(leaked)))
        return False

    results.append((PASS, "README Secret Scan", "No raw API secrets found in README.md"))
    return True


def scan_env_example_no_real_secrets() -> bool:
    """Verify .env.example contains only placeholders, never real keys."""
    env_example_path = Path(__file__).parent / ".env.example"
    if not env_example_path.exists():
        results.append((FAIL, ".env.example Exists", ".env.example not found"))
        return False

    content = env_example_path.read_text(encoding="utf-8", errors="replace")

    # Check that all API key values are placeholders
    real_key_patterns = [
        (r"RIME_API_KEY\s*=\s*[A-Za-z0-9_-]{20,}", "RIME_API_KEY"),
        (r"LIVEKIT_API_SECRET\s*=\s*[A-Za-z0-9_-]{20,}", "LIVEKIT_API_SECRET"),
        (r"OPENAI_API_KEY\s*=\s*sk-proj-[A-Za-z0-9_-]{20,}", "OPENAI_API_KEY"),
    ]

    leaked = []
    for pattern, name in real_key_patterns:
        matches = re.findall(pattern, content)
        for m in matches:
            val = m.split("=", 1)[1].strip() if "=" in m else m
            if "xxxx" not in val.lower() and "your_" not in val.lower() and "placeholder" not in val.lower():
                leaked.append(name)

    if leaked:
        results.append((FAIL, ".env.example Hygiene", "Real secrets found in .env.example: " + ", ".join(leaked)))
        return False

    results.append((PASS, ".env.example Hygiene", "Contains only placeholder values"))
    return True


# ──────────────────────────────────────────────────────────────
# Run all checks
# ──────────────────────────────────────────────────────────────

def main() -> int:
    print()
    print("=" * 55)
    print("  RimeTrack Preflight Configuration Check")
    print("=" * 55)

    # --- Rime (organizer-provided configuration) ---
    rime_key = check_required("RIME_API_KEY", placeholder="your_rime_api_key_here")
    if rime_key:
        results.append((PASS, "RIME_API_KEY", "Present (not placeholder)"))
    check_exact("RIME_MODEL", "coda", label="matches organizer spec")
    check_exact("RIME_SPEAKER", "astra", label="matches organizer spec")
    check_exact("RIME_LANG", "eng")

    # --- LiveKit ---
    lk_url = check_required("LIVEKIT_URL", prefix="wss://", placeholder="wss://your-project.livekit.cloud")
    if lk_url:
        results.append((PASS, "LIVEKIT_URL", lk_url))
    lk_key = check_required("LIVEKIT_API_KEY", prefix="API", placeholder="APIxxxxxxxxxxxxxxxxx")
    if lk_key:
        results.append((PASS, "LIVEKIT_API_KEY", "Present (API prefix OK)"))
    lk_secret = check_required("LIVEKIT_API_SECRET", placeholder="your_livekit_api_secret_here")
    if lk_secret:
        results.append((PASS, "LIVEKIT_API_SECRET", "Present (not placeholder)"))

    # --- OpenAI ---
    oai_key = check_required("OPENAI_API_KEY", prefix="sk-", placeholder="sk-proj-xxxxxxxxxxxxxxxxxxxx")
    if oai_key:
        results.append((PASS, "OPENAI_API_KEY", "Present (sk- prefix OK)"))

    # --- Deepgram (optional) ---
    dg_key = check_optional("DEEPGRAM_API_KEY", fallback_msg="Missing (will fall back to OpenAI Whisper)")
    if dg_key:
        results.append((PASS, "DEEPGRAM_API_KEY", "Present"))

    # --- File hygiene checks ---
    scan_readme_for_secrets()
    scan_env_example_no_real_secrets()

    # --- Display results ---
    print()
    passed = sum(1 for s, _, _ in results if s == PASS)
    failed = sum(1 for s, _, _ in results if s == FAIL)
    warned = sum(1 for s, _, _ in results if s == WARN)

    for status, name, msg in results:
        if status == PASS:
            icon = "+"
        elif status == FAIL:
            icon = "X"
        else:
            icon = "!"
        print(f"  [{icon}] {name:24s} -- {msg}")

    print()
    print("=" * 55)
    if failed > 0:
        print(f"  Result: {passed}/{passed + failed + warned} PASSED, {failed} FAILED, {warned} WARNING(s)")
        print("  !! Configuration has errors. Fix the FAILED items above.")
        print("=" * 55)
        print()
        return 1
    else:
        print(f"  Result: {passed}/{passed + warned} PASSED, {failed} FAILED, {warned} WARNING(s)")
        print("  OK - Configuration is ready for deployment.")
        print("=" * 55)
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
