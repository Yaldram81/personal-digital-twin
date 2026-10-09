from __future__ import annotations

from collections import defaultdict
from typing import Any

from pdt.core.schemas import DriftLog
from pdt.inference.drift import build_drift_log


def build_drift_logs_from_export(params_export: list[dict[str, Any]]) -> list[DriftLog]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in params_export:
        key = str(item["param_key"])
        grouped[key].append(item)
    return [build_drift_log(param, history) for param, history in grouped.items()]


def build_drift_log_for_param(
    params_export: list[dict[str, Any]],
    param: str,
) -> DriftLog:
    history = [item for item in params_export if str(item["param_key"]) == param]
    return build_drift_log(param, history)


__all__ = ["build_drift_log_for_param", "build_drift_logs_from_export"]
