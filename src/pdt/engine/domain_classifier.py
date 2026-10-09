from __future__ import annotations

from dataclasses import dataclass

from pdt.core.schemas import Domain


@dataclass(frozen=True)
class DomainClassification:
    domain: Domain
    confidence: float


_DOMAIN_KEYWORDS: dict[Domain, tuple[str, ...]] = {
    Domain.CAREER: (
        "job",
        "career",
        "salary",
        "promotion",
        "offer",
        "team",
        "manager",
        "startup",
        "role",
    ),
    Domain.FINANCIAL: ("money", "finance", "budget", "investment", "rent", "mortgage"),
    Domain.RELATIONAL: ("relationship", "partner", "friend", "family", "dating", "marriage"),
    Domain.CREATIVE: ("creative", "art", "writing", "design", "portfolio"),
    Domain.ETHICAL: ("ethical", "moral", "right", "wrong", "fair", "integrity"),
    Domain.HEALTH: ("health", "doctor", "exercise", "sleep", "diet", "therapy"),
}


def classify_domain(text: str, hint: Domain | None = None) -> DomainClassification:
    lowered = text.lower()
    scores = {
        domain: sum(1 for keyword in keywords if keyword in lowered)
        for domain, keywords in _DOMAIN_KEYWORDS.items()
    }
    if hint is not None:
        scores[hint] = scores.get(hint, 0) + 2
    best_domain = max(scores, key=lambda domain: scores[domain])
    max_score = scores[best_domain]
    total = sum(scores.values())
    if max_score == 0:
        return DomainClassification(domain=hint or Domain.CROSS_DOMAIN, confidence=0.25)
    confidence = max(0.3, min(0.95, max_score / max(total, 1)))
    return DomainClassification(domain=best_domain, confidence=confidence)


__all__ = ["DomainClassification", "classify_domain"]
