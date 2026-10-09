from __future__ import annotations

from datetime import date

import pytest

from pdt.ingest.questionnaire import score_instrument


def test_decision_style_scoring_is_deterministic() -> None:
    responses = {f"d{i}": 4 for i in range(1, 9)}
    scored = score_instrument("decision_style", responses, as_of=date(2025, 1, 1))
    assert scored["information_seeking"].value == 0.75
    assert scored["information_seeking"].source.value == "self_report"
    assert scored["information_seeking"].evidence_strength.value == "weak"


def test_reverse_scored_item_is_handled() -> None:
    scored = score_instrument("decision_style", {**{f"d{i}": 3 for i in range(1, 9)}, "d2": 5})
    assert scored["reasoning_mode"].value == 0.0


def test_missing_response_fails() -> None:
    with pytest.raises(ValueError, match="missing response"):
        score_instrument("values", {"v1": 3})


def test_maximization_scale_scores_information_seeking() -> None:
    responses = {"ms1": 5, "ms2": 5, "ms3": 5, "ms4": 1}
    scored = score_instrument("maximization_scale", responses, as_of=date(2025, 1, 1))
    assert scored["information_seeking"].value == 1.0
    assert scored["information_seeking"].source.value == "self_report"


def test_bisbas_scores_risk_and_loss_aversion() -> None:
    responses = {"bb1": 5, "bb2": 5, "bb3": 1, "bb4": 1, "bb5": 5}
    scored = score_instrument("bisbas", responses, as_of=date(2025, 1, 1))
    assert scored["risk_tolerance"].value == 1.0
    assert scored["loss_aversion"].value == 0.0


def test_crt_binary_items_score_reasoning_mode() -> None:
    all_reflective = score_instrument("crt", {"crt1": 1, "crt2": 1, "crt3": 1})
    assert all_reflective["reasoning_mode"].value == 1.0
    all_intuitive = score_instrument("crt", {"crt1": 0, "crt2": 0, "crt3": 0})
    assert all_intuitive["reasoning_mode"].value == 0.0


def test_domain_anchors_covers_all_six_dimensions() -> None:
    responses = {f"da{i}": 3 for i in range(1, 7)}
    scored = score_instrument("domain_anchors", responses)
    expected_dims = {
        "risk_tolerance",
        "time_horizon",
        "loss_aversion",
        "ambiguity_tolerance",
        "construal_level",
        "social_proof_weight",
    }
    assert set(scored.keys()) == expected_dims
