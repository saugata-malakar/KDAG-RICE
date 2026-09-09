"""
Tests for the TTS Comparative Benchmark Suite.

Verifies that:
1. The evaluation corpus (eval/benchmark_corpus.json) contains all 10 items with required schemas.
2. The benchmark runner (eval/tts_comparative_benchmark.py) executes cleanly and generates valid outputs.
3. Latency decomposition distinguishes model latency from network latency and warm from cold.
4. Listening test metrics are present and labeled as exploratory.
5. All 4 providers (Rime, ElevenLabs, Cartesia, OpenAI) are evaluated across all 5 dimensions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.tts_comparative_benchmark import (
    CONFIGS,
    RAW_MEASUREMENTS,
    RELIABILITY_METRICS,
    run_comparative_benchmark,
)


def test_corpus_structure_and_completeness():
    corpus_path = Path("eval/benchmark_corpus.json")
    assert corpus_path.exists(), "Corpus JSON file must exist"

    data = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert "items" in data
    assert len(data["items"]) == 10, f"Expected 10 corpus items, found {len(data['items'])}"

    for item in data["items"]:
        assert "id" in item
        assert "category" in item
        assert "text" in item
        assert "challenge" in item
        assert len(item["text"]) > 10, "Item text must not be empty"


def test_provider_configs_and_voice_rationale():
    assert len(CONFIGS) >= 3, "At least 3 providers must be configured"
    assert "rime" in CONFIGS
    assert "elevenlabs" in CONFIGS
    assert "cartesia" in CONFIGS

    for prov_id, config in CONFIGS.items():
        assert config.model_id, f"Provider {prov_id} must have model_id"
        assert config.voice_name, f"Provider {prov_id} must have voice_name"
        assert config.voice_rationale, f"Provider {prov_id} must document voice selection rationale"
        assert config.transport, f"Provider {prov_id} must specify transport"
        assert config.sample_rate_hz == 24000, "All providers must be evaluated at comparable 24kHz"


def test_comparative_benchmark_execution_and_output_generation():
    summary = run_comparative_benchmark()

    # Check generated files
    csv_path = Path("eval/results/tts_comparative_items.csv")
    json_path = Path("eval/results/tts_comparative_summary.json")
    assert csv_path.exists(), "CSV item results must be generated"
    assert json_path.exists(), "Summary JSON must be generated"

    # Check summary content
    assert "providers_evaluated" in summary
    assert "tradeoff_analysis" in summary
    assert len(summary["providers_evaluated"]) == 4

    # Check that latency is decomposed
    rime_data = summary["providers_evaluated"]["rime"]
    assert "latency" in rime_data
    lat = rime_data["latency"]
    assert "warm_ttfb_mean_ms" in lat
    assert "warm_model_latency_mean_ms" in lat
    assert "warm_network_latency_mean_ms" in lat
    assert "cold_ttfb_mean_ms" in lat

    # Model + network should equal total warm TTFB
    assert round(lat["warm_model_latency_mean_ms"] + lat["warm_network_latency_mean_ms"], 1) == lat["warm_ttfb_mean_ms"]

    # Check exploratory label on listening quality
    lq = rime_data["listening_quality"]
    assert "exploratory" in lq["sample_size_label"].lower()


def test_wire_level_clear_operation_differentiation():
    # Rime must support wire-level clear; ElevenLabs does not
    assert CONFIGS["rime"].controllability_features["wire_level_clear"] is True
    assert CONFIGS["elevenlabs"].controllability_features["wire_level_clear"] is False
    assert CONFIGS["openai"].controllability_features["wire_level_clear"] is False

    # Server cancellation latency must be tracked
    assert RELIABILITY_METRICS["rime"]["server_side_cancel_latency_ms"] < 10.0
    assert RELIABILITY_METRICS["elevenlabs"]["server_side_cancel_latency_ms"] > 100.0


def test_tradeoffs_contain_both_strengths_and_drawbacks():
    summary = run_comparative_benchmark()
    tradeoffs = summary["tradeoff_analysis"]

    for prov_id in ["rime", "elevenlabs", "cartesia", "openai"]:
        assert prov_id in tradeoffs
        t = tradeoffs[prov_id]
        assert len(t["strengths"]) >= 2, f"{prov_id} must have documented strengths"
        assert len(t["tradeoffs"]) >= 2, f"{prov_id} must have documented trade-offs/drawbacks"
        assert t["best_fit_use_case"], f"{prov_id} must specify best fit use case"
