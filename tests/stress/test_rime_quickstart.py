"""
Unit tests for rime_quickstart.py verifying compliance with official Rime 5-min quickstart.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from rime_quickstart import generate_rime_speech


def test_quickstart_requires_valid_api_key():
    with pytest.raises(ValueError, match="RIME_API_KEY is missing or invalid"):
        generate_rime_speech(api_key="")


def test_quickstart_payload_and_headers_structure(tmp_path):
    mock_wav_bytes = b"RIFF" + b"\x00" * 40 + b"WAVEfmt " + b"\x00" * 1000

    mock_resp = MagicMock()
    mock_resp.read.side_effect = [mock_wav_bytes, b""]
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    out_file = tmp_path / "test_out.wav"

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        saved = generate_rime_speech(
            text="Testing Rime speech synthesis",
            speaker="celeste",
            model_id="coda",
            output_path=str(out_file),
            api_key="test_key_123",
        )

        assert saved.exists()
        assert saved.stat().st_size > 44

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://users.rime.ai/v1/rime-tts"
        assert req.headers["Accept"] == "audio/wav"
        assert req.headers["Authorization"] == "Bearer test_key_123"
        assert req.headers["Content-type"] == "application/json"
