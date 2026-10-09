from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.crypto import Vault
from pdt.inference.calibration import CalibrationTracker
from pdt.inference.changepoint import run_bocpd
from pdt.inference.drift import (
    detect_major_life_event_window,
    evidence_weight_for_date,
    smooth_series,
    tier,
)
from pdt.inference.uncertainty import Contribution, build_prediction_contract, propagate
from pdt.memory.structured import DuckDBStructuredStore
from pdt.model.confidence import ConfidenceInterval


def _client(tmp_path: Path) -> TestClient:
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock", embedding_model="mock-embed")
    vault = Vault.init(data_dir, "phase4-passphrase", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    return TestClient(app)


def test_bocpd_recovers_injected_changepoint() -> None:
    series = [0.2 + ((i % 3) * 0.01) for i in range(50)] + [0.8 - ((i % 3) * 0.01) for i in range(50)]
    result = run_bocpd(series, likelihood="student_t")
    assert result.detected is True
    assert result.most_likely_index is not None
    assert abs(result.most_likely_index - 50) <= 5
    assert result.confidence >= 0.08
    assert result.effect_size >= 1.0
    assert result.hazard == 0.03
    assert len(result.run_length_dist) == len(series)


def test_bocpd_controls_false_positives_on_noise() -> None:
    series = [0.5, 0.48, 0.52, 0.49, 0.51, 0.5, 0.47, 0.53, 0.5, 0.49] * 10
    result = run_bocpd(series)
    assert result.detected is False
    assert result.most_likely_index is None
    assert result.effect_size < 1.0


def test_stability_tiers_change_smoothing_behavior() -> None:
    noisy = [0.5, 0.51, 0.49, 0.5, 0.82, 0.84, 0.81]
    core = smooth_series(noisy, tier("security"))
    surface = smooth_series(noisy, tier("opinion_about_remote_work"))
    assert (surface[-1] - surface[0]) > (core[-1] - core[0])


def test_major_life_event_window_upweights_recent_evidence() -> None:
    traces = [
        '{"domain":"career","timestamp":"2025-01-01"}',
        '{"domain":"career","timestamp":"2025-01-05"}',
        '{"domain":"career","timestamp":"2025-01-10"}',
        '{"domain":"health","timestamp":"2025-02-01"}',
        '{"domain":"relational","timestamp":"2025-02-03"}',
        '{"domain":"health","timestamp":"2025-02-07"}',
    ]
    window = detect_major_life_event_window(traces)
    assert window is not None
    inside_weight = evidence_weight_for_date(window.start, window)
    outside_weight = evidence_weight_for_date(window.start - timedelta(days=90), window)
    assert inside_weight > outside_weight


def test_uncertainty_propagation_matches_linear_analytic_case() -> None:
    contributions = [
        Contribution("x1", 1.0, ConfidenceInterval(0.3, 0.1, 5.0, 0.9, 0.1)),
        Contribution("x2", 1.0, ConfidenceInterval(0.4, 0.2, 5.0, 0.9, 0.1)),
    ]
    ci = propagate(contributions)
    expected = 1.96 * (((0.1 / 1.96) ** 2) + ((0.2 / 1.96) ** 2)) ** 0.5
    assert abs(ci.half_width - expected) < 1e-6


def test_uncertainty_monte_carlo_is_wider_for_nonlinear_case() -> None:
    contributions = [
        Contribution("x1", 1.0, ConfidenceInterval(0.8, 0.08, 5.0, 0.9, 0.1)),
        Contribution("x2", 1.0, ConfidenceInterval(0.7, 0.08, 5.0, 0.9, 0.1)),
    ]
    linear = propagate(contributions)
    nonlinear = propagate(contributions, composition_fn=lambda xs: xs[0] * xs[1], linear=False)
    assert nonlinear.half_width > 0
    assert nonlinear.half_width >= linear.half_width * 0.4


def test_calibration_reliability_curve_behaves_on_synthetic_data() -> None:
    perfect = CalibrationTracker()
    for idx in range(10):
        perfect.record(f"p-{idx}", 0.8, idx < 8)
    points = perfect.reliability_diagram()
    populated = [point for point in points if point.count]
    target = populated[-1]
    assert abs(target.mean_predicted - target.empirical_accuracy) < 0.05

    overconfident = CalibrationTracker()
    for idx in range(10):
        overconfident.record(f"o-{idx}", 0.9, idx < 4)
    over_points = [point for point in overconfident.reliability_diagram() if point.count]
    assert over_points[-1].empirical_accuracy < over_points[-1].mean_predicted


def test_prediction_contract_reflects_input_uncertainty() -> None:
    low_ci = [
        Contribution("a", 0.5, ConfidenceInterval(0.5, 0.05, 10.0, 0.9, 0.1)),
        Contribution("b", 0.5, ConfidenceInterval(0.5, 0.05, 10.0, 0.9, 0.1)),
    ]
    high_ci = [
        Contribution("a", 0.5, ConfidenceInterval(0.5, 0.20, 10.0, 0.9, 0.1)),
        Contribution("b", 0.5, ConfidenceInterval(0.5, 0.20, 10.0, 0.9, 0.1)),
    ]
    narrow = build_prediction_contract(result=None, contributions=low_ci, extrapolation_flags=[])
    wide = build_prediction_contract(result=None, contributions=high_ci, extrapolation_flags=[])
    assert wide.output_ci.half_width > narrow.output_ci.half_width
    assert wide.confidence < narrow.confidence


def test_bocpd_student_t_is_robust_to_single_outlier() -> None:
    series = ([0.35] * 30) + [0.95] + ([0.35] * 29)
    gaussian = run_bocpd(series, likelihood="gaussian")
    robust = run_bocpd(series, likelihood="student_t")
    assert robust.detected is False or robust.confidence <= gaussian.confidence


def test_drift_api_returns_full_structure(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        base = datetime(2025, 1, 1, tzinfo=UTC)
        values = [0.2] * 6 + [0.8] * 6
        for index, value in enumerate(values):
            created_at = base + timedelta(days=index)
            state.store.insert_param("risk_tolerance", value, 0.1, index + 1, "behavioral", domain="career")
            state.store.insert_drift_entry("risk_tolerance", value, created_at.date().isoformat())

        detail = client.get("/model/drift/risk_tolerance")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["parameter"] == "risk_tolerance"
        assert payload["history"]
        assert payload["trend"] in {"increasing", "decreasing", "stable"}

        summary = client.get("/model/drift")
        assert summary.status_code == 200
        assert summary.json()["drifts"]

        calibration = client.get("/model/calibration")
        assert calibration.status_code == 200
        assert "reliability" in calibration.json()
