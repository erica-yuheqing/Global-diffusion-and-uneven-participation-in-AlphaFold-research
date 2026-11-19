#!/usr/bin/env python3
"""Validate private subagent annotation fragments before filling a workbook."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = ROOT / "fulltext/pilot/human_annotation_v4_3/pilot_150_human_packets_blinded_v4_3.jsonl"
VALIDATOR_PATH = ROOT / "code/23_validate_pilot_human_annotations.py"


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("human_annotation_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import validator from {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        records.append(value)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--chunks-dir", type=Path, required=True)
    parser.add_argument("--packet-file", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validator = load_validator()
    workbook = load_workbook(args.workbook, read_only=True, data_only=False)
    base_rows = validator.annotation_rows(workbook)
    packets = {record["review_id"]: record for record in read_jsonl(args.packet_file)}

    chunk_files = sorted(args.chunks_dir.glob("*.jsonl"))
    fragment_rows = [record for path in chunk_files for record in read_jsonl(path)]
    by_order: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    for record in fragment_rows:
        try:
            order = int(record.get("assignment_order"))
        except (TypeError, ValueError):
            errors.append(f"invalid assignment_order {record.get('assignment_order')!r}")
            continue
        if order in by_order:
            errors.append(f"duplicate assignment_order {order}")
        by_order[order] = record

    expected_orders = set(range(1, len(base_rows) + 1))
    missing = sorted(expected_orders - set(by_order))
    unexpected = sorted(set(by_order) - expected_orders)
    if missing:
        errors.append(f"missing assignment_order values: {missing}")
    if unexpected:
        errors.append(f"unexpected assignment_order values: {unexpected}")

    validated = 0
    for row_number, base in enumerate(base_rows, 2):
        order = row_number - 1
        fragment = by_order.get(order)
        if fragment is None:
            continue
        for field in ("assignment_order", "reviewer_record_id", "review_id", "work_id"):
            if validator.norm(base[field]) != validator.norm(fragment.get(field)):
                errors.append(
                    f"row {row_number} {field}: workbook={base[field]!r} fragment={fragment.get(field)!r}"
                )
        merged = dict(base)
        merged.update(fragment)
        packet = packets.get(validator.norm(base["review_id"]))
        if packet is None:
            errors.append(f"row {row_number}: missing blinded packet for {base['review_id']}")
            continue
        errors.extend(validator.validate_completed_row(merged, packet, row_number))
        if validator.norm(merged.get("status")) != "complete":
            errors.append(f"row {row_number} status: expected complete")
        validated += 1

    report = {
        "schema_version": "af-private-subagent-jsonl-validation-v1",
        "workbook": str(args.workbook.resolve()),
        "packet_file": str(args.packet_file.resolve()),
        "chunk_files": [str(path.resolve()) for path in chunk_files],
        "expected_records": len(base_rows),
        "fragment_records": len(fragment_rows),
        "validated_records": validated,
        "error_count": len(errors),
        "errors": errors,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Expected records:         {len(base_rows)}")
    print(f"Fragment records:         {len(fragment_rows)}")
    print(f"Validated records:        {validated}")
    print(f"Validation errors:        {len(errors)}")
    for error in errors[:100]:
        print(f"  - {error}")
    if len(errors) > 100:
        print(f"  ... {len(errors) - 100} more errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
