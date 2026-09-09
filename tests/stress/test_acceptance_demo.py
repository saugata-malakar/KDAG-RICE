"""
Unit and Regression Tests for the Defined Acceptance Demo & Prosody Variant Evaluation.

Validates the hackathon requirements:
1. Define the acceptance test before the demo.
2. Run a normal interaction and one deliberate stress or failure case.
3. Measure what the user experiences (stop latency, audible word count, stale leakage).
4. Disclose limitations and unsupported input.
5. Pairwise prosody claims hold model/voice constant, save clips, and explain wording/punctuation.
"""

import json
from pathlib import Path
import pytest
import wave

from demo.run_acceptance_demo import (
    ACCEPTANCE_SPEC,
    run_normal_interaction,
    run_deliberate_stress_case,
    run_deliberate_failure_case,
)
from eval.generate_prosody_clips import PROSODY_PAIRS, generate_all_prosody_clips


@pytest.mark.asyncio
async def test_acceptance_spec_defines_criteria_and_discloses_limitations():
    """Verifies that the acceptance spec defines all six criteria and explicitly discloses limitations."""
    assert "AC-1" in ACCEPTANCE_SPEC
    assert "AC-2" in ACCEPTANCE_SPEC
    assert "AC-3" in ACCEPTANCE_SPEC
    assert "AC-4" in ACCEPTANCE_SPEC
    assert "AC-5" in ACCEPTANCE_SPEC
    assert "AC-6" in ACCEPTANCE_SPEC

    # Verifies explicit disclosure of limitations and unsupported input
    assert "EXPLICIT DISCLOSURE OF LIMITATIONS & UNSUPPORTED INPUT" in ACCEPTANCE_SPEC
    assert "Acoustic Limitations" in ACCEPTANCE_SPEC
    assert "SNR >= 12 dB" in ACCEPTANCE_SPEC
    assert "Overlapping multi-speaker babble" in ACCEPTANCE_SPEC
    assert "Rate Limitations" in ACCEPTANCE_SPEC
    assert "Tool Limitations" in ACCEPTANCE_SPEC


@pytest.mark.asyncio
async def test_acceptance_demo_normal_interaction():
    """Runs the normal interaction step and verifies user experience metrics."""
    res = await run_normal_interaction()
    assert res["status"] == "PASS"
    assert res["words_heard"] > 0
    assert res["stale_words_heard"] == 0
    assert res["grounded_history_match"] is True


@pytest.mark.asyncio
async def test_acceptance_demo_deliberate_stress_case():
    """
    Runs the deliberate stress case (3.0s tool delay, barge-in, request change)
    and verifies what the user actually experiences.
    """
    res = await run_deliberate_stress_case()
    assert res["status"] == "PASS"
    assert res["audio_stop_latency_ms"] < 50.0  # sub-millisecond execution in practice
    assert res["g1_words_spoken"] == 4
    assert res["stale_words_spoken_to_user"] == 0
    assert res["stale_tool_quarantined"] is True
    assert res["final_response_matched_request"] is True


@pytest.mark.asyncio
async def test_acceptance_demo_deliberate_failure_case():
    """
    Runs the deliberate dependency failure case and verifies clean recovery
    without crashing.
    """
    res = await run_deliberate_failure_case()
    assert res["status"] == "PASS"
    assert res["handled_cleanly"] is True
    assert res["agent_crashed"] is False
    assert "TimeoutError" in res["error_captured"]


def test_prosody_clips_hold_model_voice_constant_and_explain_changes():
    """
    Verifies that all prosody clips hold model ('coda') and voice ('astra') constant,
    clips exist on disk as valid WAV files, and metadata explains wording/punctuation changes.
    """
    clips_dir = Path("eval/clips")
    assert clips_dir.exists(), "eval/clips/ directory must exist"

    results = generate_all_prosody_clips(output_dir=clips_dir, force_recreate=False)
    assert len(results) >= 4

    meta_file = Path("eval/results/prosody_clips_metadata.json")
    assert meta_file.exists()
    metadata = json.loads(meta_file.read_text(encoding="utf-8"))

    for item in metadata:
        # Constant model and speaker
        assert item["model"] == "coda"
        assert item["speaker"] == "astra"

        # Wording and punctuation explanation must be non-empty and descriptive
        assert len(item["wording_and_punctuation_change"]) > 50
        assert "punct" in item["wording_and_punctuation_change"].lower() or "wording" in item["wording_and_punctuation_change"].lower()

        # Both variant WAV files must exist and be valid WAV files
        for var_key in ("variant_a", "variant_b"):
            v = item["variants"][var_key]
            wav_path = clips_dir / v["file_name"]
            assert wav_path.exists(), f"Audio clip {wav_path} must exist"
            assert wav_path.stat().st_size > 1000

            with wave.open(str(wav_path), "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getframerate() == 24000
                assert wf.getsampwidth() == 2

            # Metric verification
            metrics = v["metrics"]
            assert metrics["duration_sec"] > 1.0
            assert metrics["rms_amplitude"] > 0.0
            assert metrics["peak_amplitude"] > 0.0
