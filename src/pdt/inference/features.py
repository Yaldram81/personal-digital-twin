import json

from pdt.core.schemas import SCHWARTZ_DIMENSIONS

FEATURE_MAP: dict[str, tuple[str, ...]] = {
    "learning": ("self_direction", "achievement"),
    "autonomy": ("self_direction",),
    "salary": ("power", "security"),
    "security": ("security",),
    "loyalty": ("benevolence", "tradition"),
    "original": ("self_direction", "stimulation"),
    "risk": ("stimulation",),
    "information": ("security", "self_direction"),
}


def trace_to_feature_vector(trace_json: str) -> dict[str, float]:
    trace = json.loads(trace_json)
    vector = dict.fromkeys(SCHWARTZ_DIMENSIONS, 0.0)
    factors = trace.get("factors_cited", [])
    for factor in factors:
        factor_name = str(factor.get("factor", "")).lower()
        for key, dims in FEATURE_MAP.items():
            if key in factor_name:
                for dim in dims:
                    vector[dim] += 1.0
    total = sum(vector.values()) or 1.0
    return {dim: value / total for dim, value in vector.items()}
