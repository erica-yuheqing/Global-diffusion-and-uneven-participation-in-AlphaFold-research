#!/usr/bin/env python3
"""Compare locally validated model outputs with a signed Pilot calibration CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELDS = {
    "primary_label": "proposed_primary_label",
    "relevance_level": "proposed_relevance_level",
    "evidence_level": "evidence_level",
    "af_use_label": "af_use_label",
    "adoption_eligible": "adoption_eligible",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument(
        "--model-output",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="Locally revalidated JSONL; repeat for independent models",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            records.append(record)
    return records


def parse_model_arg(value: str) -> tuple[str, Path]:
    name, separator, path = value.partition("=")
    if not separator or not name.strip() or not path.strip():
        raise ValueError(f"Expected NAME=PATH for --model-output, got {value!r}")
    return name.strip(), Path(path).resolve()


def actions(value: str | list[str]) -> list[str]:
    values = value.split("|") if isinstance(value, str) else value
    return sorted(item for item in values if item)


def atomic_write_with_checksum(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    checksum = f"{sha256_bytes(data)}  {path.name}\n".encode("ascii")
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_temporary = checksum_path.with_suffix(checksum_path.suffix + ".part")
    checksum_temporary.write_bytes(checksum)
    checksum_temporary.replace(checksum_path)


def main() -> int:
    args = parse_args()
    calibration_path = args.calibration.resolve()
    with calibration_path.open(newline="", encoding="utf-8") as handle:
        calibration_rows = list(csv.DictReader(handle))
    expected = {row["review_id"]: row for row in calibration_rows}
    expected_order = [row["review_id"] for row in calibration_rows]

    model_paths = dict(parse_model_arg(value) for value in args.model_output)
    if len(model_paths) != len(args.model_output):
        raise ValueError("Each model name must be unique")
    model_reviews: dict[str, dict[str, dict[str, Any]]] = {}
    report_models: dict[str, Any] = {}
    for name, path in model_paths.items():
        envelopes = read_jsonl(path)
        by_id = {record["review_id"]: record for record in envelopes}
        if set(by_id) != set(expected):
            missing = sorted(set(expected) - set(by_id))
            extra = sorted(set(by_id) - set(expected))
            raise ValueError(f"{name}: calibration cohort mismatch; missing={missing}, extra={extra}")
        reviews: dict[str, dict[str, Any]] = {}
        field_matches = {field: 0 for field in FIELDS}
        action_matches = 0
        mismatches = []
        local_valid = 0
        for review_id in expected_order:
            envelope = by_id[review_id]
            if envelope.get("local_validation_valid") is True:
                local_valid += 1
            review = envelope.get("response")
            if not isinstance(review, dict):
                raise ValueError(f"{name}/{review_id}: response object missing")
            reviews[review_id] = review
            differences: dict[str, Any] = {}
            for actual_field, expected_field in FIELDS.items():
                actual = review.get(actual_field)
                wanted = expected[review_id][expected_field]
                if actual == wanted:
                    field_matches[actual_field] += 1
                else:
                    differences[actual_field] = {"expected": wanted, "actual": actual}
            wanted_actions = actions(expected[review_id]["proposed_actions"])
            actual_actions = actions(review.get("observed_actions", []))
            if actual_actions == wanted_actions:
                action_matches += 1
            else:
                differences["observed_actions"] = {
                    "expected": wanted_actions,
                    "actual": actual_actions,
                    "missing": sorted(set(wanted_actions) - set(actual_actions)),
                    "extra": sorted(set(actual_actions) - set(wanted_actions)),
                }
            if differences:
                mismatches.append({
                    "review_id": review_id,
                    "work_id": expected[review_id]["work_id"],
                    "differences": differences,
                })
        total = len(expected_order)
        report_models[name] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "records": total,
            "locally_validated": local_valid,
            "exact_matches": {**field_matches, "observed_actions_set": action_matches},
            "mismatches": mismatches,
        }
        model_reviews[name] = reviews

    pairwise: dict[str, Any] = {}
    names = list(model_reviews)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1:]:
            matches = {field: 0 for field in FIELDS}
            action_matches = 0
            mismatches = []
            for review_id in expected_order:
                a = model_reviews[left][review_id]
                b = model_reviews[right][review_id]
                differences: dict[str, Any] = {}
                for field in FIELDS:
                    if a.get(field) == b.get(field):
                        matches[field] += 1
                    else:
                        differences[field] = {left: a.get(field), right: b.get(field)}
                a_actions = actions(a.get("observed_actions", []))
                b_actions = actions(b.get("observed_actions", []))
                if a_actions == b_actions:
                    action_matches += 1
                else:
                    differences["observed_actions"] = {left: a_actions, right: b_actions}
                if differences:
                    mismatches.append({"review_id": review_id, "differences": differences})
            pairwise[f"{left}__{right}"] = {
                "records": len(expected_order),
                "exact_matches": {**matches, "observed_actions_set": action_matches},
                "mismatches": mismatches,
            }

    report = {
        "schema_version": "af-pilot-calibration-comparison-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "calibration": {
            "path": str(calibration_path),
            "sha256": sha256_file(calibration_path),
            "records": len(expected_order),
            "status_note": (
                "The calibration file has single-researcher sign-off; it is not an "
                "independent double-annotated gold standard."
            ),
        },
        "models": report_models,
        "pairwise": pairwise,
    }
    atomic_write_with_checksum(args.output.resolve(), report)
    total = len(expected_order)
    for name, summary in report_models.items():
        exact = summary["exact_matches"]
        print(
            f"{name}: local validation {summary['locally_validated']}/{total}; "
            f"primary/R {exact['primary_label']}/{total}/{exact['relevance_level']}/{total}; "
            f"actions {exact['observed_actions_set']}/{total}"
        )
    for pair, summary in pairwise.items():
        exact = summary["exact_matches"]
        print(
            f"{pair}: primary/R {exact['primary_label']}/{total}/{exact['relevance_level']}/{total}; "
            f"actions {exact['observed_actions_set']}/{total}"
        )
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
