from __future__ import annotations

from dataclasses import dataclass, field

_DATA_TYPES = {"beliefs", "outcomes", "traces", "usage", "values"}


@dataclass
class ConsentStore:
    grants: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(_DATA_TYPES, False))

    def grant(self, data_type: str) -> None:
        _validate_data_type(data_type)
        self.grants[data_type] = True

    def revoke(self, data_type: str) -> None:
        _validate_data_type(data_type)
        self.grants[data_type] = False

    def status(self, data_type: str) -> bool:
        _validate_data_type(data_type)
        return self.grants[data_type]

    def export(self) -> dict[str, bool]:
        return dict(self.grants)


def _validate_data_type(data_type: str) -> None:
    if data_type not in _DATA_TYPES:
        raise ValueError(f"unknown consent data type: {data_type}")


__all__ = ["ConsentStore"]
