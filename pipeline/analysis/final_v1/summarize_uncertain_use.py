#!/usr/bin/env python3
"""Summarize why final production records have uncertain AF-use status.

This script is read-only with respect to the frozen final database.  It writes
one reproducible JSON summary under analysis/final_v1/out/.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import require_regular_file, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT = (
    PROJECT_ROOT
    / "fulltext/production/final_database_v2/af_research_database_final_v2.jsonl"
)
OUTPUT = PROJECT_ROOT / "analysis/final_v1/out/uncertain_use_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def increment(counter: Counter[str], value: Any) -> None:
    if value is None or value == "":
        counter["<missing>"] += 1
    else:
        counter[str(value)] += 1


def sorted_counts(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    return [
        {
            "value": value,
            "count": count,
            "percent": round(100.0 * count / total, 3) if total else 0.0,
        }
        for value, count in counter.most_common()
    ]


def main() -> None:
    args = parse_args()
    require_regular_file(INPUT, "final database JSONL")
    if OUTPUT.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}; pass --force explicitly")
    counters: dict[str, Counter[str]] = {
        name: Counter()
        for name in (
            "decision_route",
            "source_route",
            "primary_label",
            "relevance_level",
            "evidence_level",
            "exclusion_reason",
            "evidence_tier",
            "abstract_status",
            "fulltext_body_available",
            "observed_actions_status",
            "human_review_reason",
            "input_quality_flag",
            "semantic_warning",
        )
    }
    total_records = 0
    uncertain_records = 0
    joint_route_evidence: Counter[str] = Counter()
    joint_exclusion_evidence: Counter[str] = Counter()

    with INPUT.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            total_records += 1
            final = record.get("final_decision") or {}
            if final.get("af_use_label") != "uncertain":
                continue
            uncertain_records += 1
            input_evidence = record.get("input_evidence") or {}
            input_quality = input_evidence.get("input_quality") or {}
            support = record.get("support") or {}

            increment(counters["decision_route"], record.get("decision_route"))
            increment(counters["source_route"], record.get("source_route"))
            for field in (
                "primary_label",
                "relevance_level",
                "evidence_level",
                "exclusion_reason",
                "observed_actions_status",
            ):
                increment(counters[field], final.get(field))
            increment(counters["evidence_tier"], input_evidence.get("evidence_tier"))
            increment(counters["abstract_status"], input_quality.get("abstract_status"))
            increment(
                counters["fulltext_body_available"],
                input_quality.get("fulltext_body_available"),
            )

            human_reasons = support.get("human_review_reasons") or []
            forced = support.get("forced_decision") or {}
            if forced.get("needs_human_review") and not human_reasons:
                human_reasons = ["insufficient_evidence_forced_u"]
            if not human_reasons:
                human_reasons = ["<none>"]
            for value in human_reasons:
                increment(counters["human_review_reason"], value)

            flags = input_quality.get("flags") or []
            if not flags:
                flags = ["<none>"]
            for value in flags:
                increment(counters["input_quality_flag"], value)

            warnings = record.get("semantic_heuristic_warnings") or []
            if not warnings:
                warnings = ["<none>"]
            for value in warnings:
                increment(counters["semantic_warning"], value)

            route = str(record.get("decision_route") or "<missing>")
            evidence = str(final.get("evidence_level") or "<missing>")
            exclusion = str(final.get("exclusion_reason") or "<missing>")
            joint_route_evidence[f"{route}|{evidence}"] += 1
            joint_exclusion_evidence[f"{exclusion}|{evidence}"] += 1

    if total_records != 29_127:
        raise ValueError(f"Expected 29,127 final records, found {total_records:,}")
    if uncertain_records != 7_838:
        raise ValueError(f"Expected 7,838 uncertain-use records, found {uncertain_records:,}")

    result = {
        "schema_version": "af-uncertain-use-summary-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(INPUT),
        "source_sha256": sha256_file(INPUT),
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "total_final_records": total_records,
        "uncertain_use_records": uncertain_records,
        "uncertain_use_percent_of_final": round(
            100.0 * uncertain_records / total_records, 3
        ),
        "distributions": {
            name: sorted_counts(counter, uncertain_records)
            for name, counter in counters.items()
        },
        "joint_distributions": {
            "decision_route_by_evidence_level": sorted_counts(
                joint_route_evidence, uncertain_records
            ),
            "exclusion_reason_by_evidence_level": sorted_counts(
                joint_exclusion_evidence, uncertain_records
            ),
        },
        "interpretation_guardrail": (
            "uncertain means available evidence does not justify yes or no; "
            "it must not be recoded as confirmed non-use."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".part")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(f"Final records:          {total_records:,}")
    print(f"Uncertain AF use:       {uncertain_records:,}")
    print(f"Share of final corpus:  {result['uncertain_use_percent_of_final']:.3f}%")
    print(f"Summary written to:     {OUTPUT}")


if __name__ == "__main__":
    main()
