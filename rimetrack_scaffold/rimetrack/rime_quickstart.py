"""
Official Rime 5-Minute Quickstart Implementation
Directly based on: https://docs.rime.ai/docs/quickstart-five-minute

Generates a WAV audio file with an authenticated POST request to Rime's
production text-to-speech API at https://users.rime.ai/v1/rime-tts.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def generate_rime_speech(
    text: str = "Hello! This is Rime speaking from RimeTrack.",
    speaker: str = "astra",
    model_id: str = "coda",
    output_path: str = "output.wav",
    api_key: str | None = None,
) -> Path:
    """Sends a direct authenticated POST request to Rime TTS API per the official 5-min quickstart."""
    key = os.environ.get("RIME_API_KEY") if api_key is None else api_key
    if not key or key in ("your_rime_api_key", "dummy"):
        raise ValueError(
            "RIME_API_KEY is missing or invalid. Set RIME_API_KEY in your environment or .env file.\n"
            "Get a key at: https://app.rime.ai/tokens/"
        )

    headers = {
        "Accept": "audio/wav",
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "speaker": speaker,
        "modelId": model_id,
    }

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://users.rime.ai/v1/rime-tts",
        data=data,
        headers=headers,
        method="POST",
    )

    out = Path(output_path)
    try:
        with urllib.request.urlopen(request) as response:
            with out.open("wb") as f:
                while chunk := response.read(4096):
                    f.write(chunk)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Rime API HTTP {e.code}: {e.reason}\nResponse: {body}") from e

    # Verification per official quickstart docs:
    # 1. Size check (expect tens of kilobytes, not a few hundred bytes of JSON error)
    size = out.stat().st_size
    if size < 44:
        raise ValueError(f"Output file is too small ({size} bytes). Expected WAV audio.")

    # 2. RIFF header check
    with out.open("rb") as f:
        header = f.read(4)
        if header != b"RIFF":
            f.seek(0)
            snippet = f.read(128).decode("utf-8", errors="ignore")
            raise ValueError(f"Output is not a valid RIFF WAV file. Header starts with: {snippet!r}")

    return out


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "Hello! This is Rime speaking from RimeTrack."
    speaker = os.environ.get("RIME_SPEAKER", "astra")
    model_id = os.environ.get("RIME_MODEL", "coda")
    output_file = "output.wav"

    print(f"Calling Rime TTS API (https://users.rime.ai/v1/rime-tts)...")
    print(f"Model: {model_id} | Speaker: {speaker}")
    print(f"Text: {text!r}")

    try:
        saved_path = generate_rime_speech(
            text=text,
            speaker=speaker,
            model_id=model_id,
            output_path=output_file,
        )
        print(f"\n[SUCCESS] Audio verified & saved to {saved_path} ({saved_path.stat().st_size} bytes)")
        print(f"To play: start {output_file} (Windows) | afplay {output_file} (macOS) | aplay {output_file} (Linux)")
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
