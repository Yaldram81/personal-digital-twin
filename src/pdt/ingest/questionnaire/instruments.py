from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuestionnaireItem:
    item_id: str
    prompt: str
    dimension: str
    reverse_scored: bool = False
    min_value: int = 1
    max_value: int = 5


@dataclass(frozen=True)
class QuestionnaireInstrument:
    instrument_id: str
    title: str
    items: tuple[QuestionnaireItem, ...]


INSTRUMENTS: dict[str, QuestionnaireInstrument] = {
    "values": QuestionnaireInstrument(
        instrument_id="values",
        title="Schwartz-style value seeding",
        items=(
            QuestionnaireItem(
                "v1",
                "Independence matters more to me than fitting in.",
                "self_direction",
            ),
            QuestionnaireItem("v2", "I seek novelty and challenge in life.", "stimulation"),
            QuestionnaireItem(
                "v3",
                "Pleasure and enjoyment strongly guide my choices.",
                "hedonism",
            ),
            QuestionnaireItem("v4", "Achievement is central to my identity.", "achievement"),
            QuestionnaireItem("v5", "Status and influence matter to me.", "power"),
            QuestionnaireItem("v6", "I prefer predictability and safety.", "security"),
            QuestionnaireItem("v7", "I usually follow social expectations.", "conformity"),
            QuestionnaireItem("v8", "Tradition should shape how I live.", "tradition"),
            QuestionnaireItem(
                "v9",
                "Caring for close others is a top priority.",
                "benevolence",
            ),
            QuestionnaireItem(
                "v10",
                "Fairness for everyone matters deeply to me.",
                "universalism",
            ),
        ),
    ),
    "decision_style": QuestionnaireInstrument(
        instrument_id="decision_style",
        title="Decision style prior seeding",
        items=(
            QuestionnaireItem(
                "d1",
                "I keep searching even after finding a good option.",
                "information_seeking",
            ),
            QuestionnaireItem(
                "d2",
                "My first instinct is often good enough.",
                "reasoning_mode",
                reverse_scored=True,
            ),
            QuestionnaireItem(
                "d3",
                "I am comfortable taking meaningful risks.",
                "risk_tolerance",
            ),
            QuestionnaireItem(
                "d4",
                "I optimize for long-term outcomes over immediate gains.",
                "time_horizon",
            ),
            QuestionnaireItem("d5", "Potential losses weigh heavily on me.", "loss_aversion"),
            QuestionnaireItem(
                "d6",
                "I can decide even with incomplete information.",
                "ambiguity_tolerance",
            ),
            QuestionnaireItem(
                "d7",
                "I think abstractly about the bigger picture.",
                "construal_level",
            ),
            QuestionnaireItem(
                "d8",
                "Other people's views strongly influence my decisions.",
                "social_proof_weight",
            ),
        ),
    ),
    # Blueprint §8-P1 names this explicitly: "Maximization Scale (Schwartz et
    # al.) -> information_seeking". A short-form item bank (multi-item,
    # reduces single-item measurement error vs. the single `d1` item above;
    # fused with it in `api.app.questionnaire_submit` via evidence fusion).
    "maximization_scale": QuestionnaireInstrument(
        instrument_id="maximization_scale",
        title="Maximization Scale (Schwartz et al.)",
        items=(
            QuestionnaireItem(
                "ms1",
                "Whenever I face a choice, I try to imagine what all the other "
                "possibilities are, even ones that aren't present at the moment.",
                "information_seeking",
            ),
            QuestionnaireItem("ms2", "I never settle for second best.", "information_seeking"),
            QuestionnaireItem(
                "ms3",
                "No matter how satisfied I am with my choice, it's only right "
                "to be on the lookout for better options.",
                "information_seeking",
            ),
            QuestionnaireItem(
                "ms4",
                "A little browsing is usually enough for me to find something I like.",
                "information_seeking",
                reverse_scored=True,
            ),
        ),
    ),
    # Blueprint §8-P1: "BIS/BAS (Carver & White) -> components of
    # reasoning_mode/risk." Mapped here onto risk_tolerance and loss_aversion,
    # the two decision-style dims BIS/BAS most directly bears on.
    "bisbas": QuestionnaireInstrument(
        instrument_id="bisbas",
        title="BIS/BAS (Carver & White)",
        items=(
            QuestionnaireItem(
                "bb1",
                "Even if something bad is about to happen, I rarely experience "
                "fear or nervousness about it.",
                "risk_tolerance",
            ),
            QuestionnaireItem(
                "bb2", "When I want something, I usually go all-out to get it.", "risk_tolerance"
            ),
            QuestionnaireItem(
                "bb3",
                "Criticism or scolding hurts me quite a bit.",
                "risk_tolerance",
                reverse_scored=True,
            ),
            QuestionnaireItem(
                "bb4",
                "I worry a lot about making mistakes.",
                "loss_aversion",
            ),
            QuestionnaireItem(
                "bb5",
                "I go out of my way to get things I want, even at some risk.",
                "loss_aversion",
                reverse_scored=True,
            ),
        ),
    ),
    # Blueprint §8-P1: "Cognitive Reflection Test (CRT) -> analytical vs
    # intuitive." CRT is normally scored correct/incorrect rather than
    # Likert; modeled here as binary (0/1) items on the reasoning_mode
    # dimension, which the existing 1-5 scoring pipeline handles natively
    # since normalization is just (value - min) / (max - min).
    "crt": QuestionnaireInstrument(
        instrument_id="crt",
        title="Cognitive Reflection Test (Frederick, 2005)",
        items=(
            QuestionnaireItem(
                "crt1",
                "Bat-and-ball: answered with the reflective (non-intuitive) answer.",
                "reasoning_mode",
                min_value=0,
                max_value=1,
            ),
            QuestionnaireItem(
                "crt2",
                "Widgets/machines: answered with the reflective (non-intuitive) answer.",
                "reasoning_mode",
                min_value=0,
                max_value=1,
            ),
            QuestionnaireItem(
                "crt3",
                "Lily pads: answered with the reflective (non-intuitive) answer.",
                "reasoning_mode",
                min_value=0,
                max_value=1,
            ),
        ),
    ),
    # Blueprint §8-P1: "Domain-anchoring items for risk_tolerance,
    # time_horizon, loss_aversion, ambigu_tolerance, construal_level,
    # social_proof_weight." Phrased as concrete scenarios rather than
    # abstract self-description, per the blueprint's rationale for anchoring.
    "domain_anchors": QuestionnaireInstrument(
        instrument_id="domain_anchors",
        title="Domain-anchored calibration items",
        items=(
            QuestionnaireItem(
                "da1",
                "In a career decision, I would take a meaningful pay cut for "
                "significantly faster growth.",
                "risk_tolerance",
            ),
            QuestionnaireItem(
                "da2",
                "I plan financial decisions around a multi-year horizon rather "
                "than the next few months.",
                "time_horizon",
            ),
            QuestionnaireItem(
                "da3",
                "Losing something I already have feels worse than missing an "
                "equivalent gain.",
                "loss_aversion",
            ),
            QuestionnaireItem(
                "da4",
                "I can commit to a decision even when key information is still missing.",
                "ambiguity_tolerance",
            ),
            QuestionnaireItem(
                "da5",
                "I tend to think about decisions in terms of general principles "
                "rather than immediate specifics.",
                "construal_level",
            ),
            QuestionnaireItem(
                "da6",
                "Other people's opinions noticeably shift how I decide, even on "
                "decisions that are mine alone.",
                "social_proof_weight",
            ),
        ),
    ),
}
