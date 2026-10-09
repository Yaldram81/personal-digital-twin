from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProactiveSurface:
    title: str
    narrative: str
    dismissible: bool


def maybe_surface(calendar_title: str, consented: bool) -> ProactiveSurface | None:
    if not consented:
        return None
    if not calendar_title.strip():
        return None
    return ProactiveSurface(
        title=calendar_title,
        narrative=(
            f"Upcoming item '{calendar_title}' may involve a meaningful decision. "
            "A twin prediction can be surfaced here if you opt in."
        ),
        dismissible=True,
    )


__all__ = ["ProactiveSurface", "maybe_surface"]
