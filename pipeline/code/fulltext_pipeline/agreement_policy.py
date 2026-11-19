"""Versioned agreement policy for the post-Pilot AlphaFold production run."""

from __future__ import annotations

from typing import Any, Iterable


POLICY_VERSION = "af-core-agreement-v1"
CORE_DECISION_FIELDS = (
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "exclusion_reason",
    "future_or_hypothetical_only",
)
SECONDARY_FIELDS = ("observed_actions",)


def normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return " ".join(str(value).strip().split()).casefold()


def normalize_actions(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items: Iterable[Any] = value.split("|")
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = (value,)
    return tuple(sorted({normalize_scalar(item) for item in items if normalize_scalar(item)}))


def core_differences(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        field
        for field in CORE_DECISION_FIELDS
        if normalize_scalar(left.get(field)) != normalize_scalar(right.get(field))
    )


def action_disagreement(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return normalize_actions(left.get("observed_actions")) != normalize_actions(
        right.get("observed_actions")
    )


def action_jaccard(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = set(normalize_actions(left.get("observed_actions")))
    b = set(normalize_actions(right.get("observed_actions")))
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def model_c_required(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Only primary/core disagreement routes a record to Model C."""
    return bool(core_differences(left, right))

