from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

NarrationState = Literal[
    "intake",
    "options",
    "factors",
    "weighting",
    "counterfactual",
    "review",
    "submit",
]


NARRATION_STATES: tuple[NarrationState, ...] = (
    "intake",
    "options",
    "factors",
    "weighting",
    "counterfactual",
    "review",
    "submit",
)


@dataclass
class NarrationSession:
    session_id: str
    state: NarrationState = "intake"
    responses: dict[str, str] = field(default_factory=dict)

    def advance(self, field_name: str, value: str) -> NarrationState:
        self.responses[field_name] = value
        idx = NARRATION_STATES.index(self.state)
        if idx < len(NARRATION_STATES) - 1:
            self.state = NARRATION_STATES[idx + 1]
        return self.state

    def to_narration_text(self) -> str:
        ordered_fields = [
            "intake",
            "options",
            "factors",
            "weighting",
            "counterfactual",
            "review",
        ]
        parts = [
            self.responses.get(name, "")
            for name in ordered_fields
            if self.responses.get(name, "")
        ]
        return "\n".join(parts).strip()
