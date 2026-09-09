"""
Tests for Shipped Production Path & Observability.

Verifies the exact requirements from 'Rime integration and build rules':
1. 'Test the shipped path. Verify the exact endpoint, region, framework, model,
    audio format, and transport used in the final demo.'
2. 'Make fallbacks visible. Fallback behavior is allowed and encouraged for
    resilience, but it must be disclosed. Make the active speech provider
    observable, and use Rime as the default path in the judged flow.'
3. 'Design for real use. Keep spoken turns concise, define clear behavior when
    dependencies fail or input is unsupported, and use synthetic or de-identified
    data for healthcare, finance, identity, safety, and other sensitive workflows.'
"""

from __future__ import annotations

import os
from agent.prompts import SYSTEM_INSTRUCTIONS
from agent.session import build_rime_tts, get_shipped_voice_config


def test_shipped_path_exact_configuration():
    """Verify exact endpoint, region, framework, model, audio format, and transport."""
    cfg = get_shipped_voice_config()

    # Provider & Model
    assert cfg["tts_provider"] == "rime"
    assert cfg["tts_model"] == "coda"
    assert cfg["tts_speaker"] == "astra"
    assert cfg["tts_lang"] == "eng"
    assert cfg["tts_speed_alpha"] == 1.0

    # Transport & Endpoint
    assert cfg["tts_transport"] == "websocket"
    assert cfg["tts_endpoint"] == "wss://users-ws.rime.ai/ws3"
    assert cfg["tts_region"] == "us-east"

    # Audio Format
    assert cfg["tts_audio_format"] == "pcm_s16le"
    assert cfg["tts_sample_rate_hz"] == 24000
    assert cfg["tts_channels"] == 1

    # Framework & Default Flow
    assert "livekit-agents" in cfg["framework"]
    assert cfg["is_default_judged_path"] is True


def test_active_speech_provider_observable():
    """Make the active speech provider observable at runtime."""
    cfg = get_shipped_voice_config()
    assert "tts_provider" in cfg
    assert cfg["tts_provider"] == "rime"
    assert cfg["is_default_judged_path"] is True


def test_stt_fallback_is_disclosed():
    """Make fallbacks visible and disclosed."""
    # Test with placeholder / missing key -> fallback disclosed
    orig_key = os.environ.get("DEEPGRAM_API_KEY")
    try:
        os.environ["DEEPGRAM_API_KEY"] = ""
        cfg_fallback = get_shipped_voice_config()
        assert cfg_fallback["stt_fallback_active"] is True
        assert "fallback" in cfg_fallback["stt_provider"].lower()

        # Test with configured key -> primary STT
        os.environ["DEEPGRAM_API_KEY"] = "dg_live_test_key_123"
        cfg_primary = get_shipped_voice_config()
        assert cfg_primary["stt_fallback_active"] is False
        assert "deepgram" in cfg_primary["stt_provider"].lower()
    finally:
        if orig_key is not None:
            os.environ["DEEPGRAM_API_KEY"] = orig_key
        else:
            os.environ.pop("DEEPGRAM_API_KEY", None)


def test_build_rime_tts_instance_properties():
    """Verify build_rime_tts() constructs a valid LiveKit Rime TTS plugin instance."""
    tts = build_rime_tts()
    assert tts.model == "coda"
    assert getattr(tts, "_use_websocket", False) is True

    opts = getattr(tts, "_opts", None)
    if opts is not None:
        assert getattr(opts, "model", None) == "coda"
        assert getattr(opts, "speaker", None) == "astra"
        coda_opts = getattr(opts, "coda_options", None)
        if coda_opts is not None:
            assert getattr(coda_opts, "lang", None) == "eng"
            assert getattr(coda_opts, "speed_alpha", None) == 1.0


def test_design_for_real_use_in_system_prompt():
    """Verify prompts enforce concise turns, clear failure behavior, and synthetic data."""
    prompt = SYSTEM_INSTRUCTIONS

    # Concise turns
    assert "conciseness" in prompt.lower() or "brevity" in prompt.lower()
    assert "1-2 sentences" in prompt.lower() or "concise" in prompt.lower()

    # Clear failure behavior
    assert "failure" in prompt.lower() or "unsupported" in prompt.lower()

    # Synthetic / de-identified data
    assert "synthetic" in prompt.lower() or "de-identified" in prompt.lower()
