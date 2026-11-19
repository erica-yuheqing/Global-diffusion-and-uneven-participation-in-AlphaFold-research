#!/usr/bin/env python3
"""Validate and freeze the 187 production direct-human adjudications.

This local-only program consumes the Artifact Tool workbook extraction, checks
the immutable source columns against the frozen production packet and routing
queue, validates every final response against the production schema and exact
evidence anchors, and writes canonical human decisions with provenance.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

DEFAULT_EXTRACT = PROJECT_ROOT / "outputs/production_direct_human_20260915/completed/production_direct_human_adjudication_187_v1_completed.extracted.json"
DEFAULT_QUEUE = PROJECT_ROOT / "fulltext/production/adjudication_v1/production_direct_human_queue_v1.csv"
DEFAULT_INPUTS = PROJECT_ROOT / "fulltext/production/model_inputs_v1/full_model_inputs.jsonl"
DEFAULT_SCHEMA = PROJECT_ROOT / "config/af_review_output_schema_v2.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext/production/direct_human_finalization_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-records", type=int, default=187)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(as_text(item) for item in value if as_text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def parse_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raw = text(value).lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"invalid boolean value {value!r}")


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            yield line_number, value


def load_legacy_validator() -> Any:
    path = CODE_ROOT / "41_finalize_model_c_human_adjudication.py"
    spec = importlib.util.spec_from_file_location("direct_human_legacy_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("direct_human_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_queue(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    seen: set[str] = set()
    for row in rows:
        review_id = row.get("review_id", "").strip()
        if not review_id or review_id != row.get("work_id", "").strip() or review_id in seen:
            raise ValueError(f"Invalid queue identity {review_id!r}")
        seen.add(review_id)
    return rows


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="ascii"
    )
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    with temporary.open("wb") as handle:
        for row in rows:
            data = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode()
            handle.write(data)
            digest.update(data)
    temporary.replace(path)
    value = digest.hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{value}  {path.name}\n", encoding="ascii"
    )
    return value


def write_audit(path: Path, rows: list[dict[str, Any]]) -> str:
    fields = ["row_number", "review_id", "work_id", "findings"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, buffer.getvalue().encode())


def material_available(packet: dict[str, Any]) -> str:
    material = packet.get("input_material") or {}
    quality = packet.get("input_quality") or {}
    has_abstract = quality.get("abstract_status") == "usable" and bool(text(material.get("abstract")))
    has_blocks = bool(material.get("evidence_blocks"))
    if has_abstract and has_blocks:
        return "abstract + supplied body blocks"
    if has_blocks:
        return "supplied body blocks only"
    if has_abstract:
        return "abstract only"
    return "no usable supplied text"


def compare_source_columns(
    row: dict[str, Any], queue: dict[str, str], packet: dict[str, Any], order: int
) -> list[str]:
    material = packet.get("input_material") or {}
    quality = packet.get("input_quality") or {}
    forced = packet.get("forced_decision") or {}
    expected = {
        "adjudication_order": order,
        "review_id": queue["review_id"],
        "work_id": queue["work_id"],
        "title": material.get("title") or "",
        "route": queue.get("route", ""),
        "queue_reasons": queue.get("queue_reasons", ""),
        "evidence_tier": packet.get("evidence_tier") or "",
        "model_eligible": bool(packet.get("model_eligible")),
        "material_available": material_available(packet),
        "abstract_status": quality.get("abstract_status") or "",
        "fulltext_body_available": bool(quality.get("fulltext_body_available")),
        "quality_flags": as_text(quality.get("flags")),
        "publication_year": material.get("publication_year"),
        "doi": material.get("doi") or "",
        "work_type": material.get("work_type") or "",
        "domain_labels": as_text(material.get("domain_labels")),
        "estimated_input_tokens": packet.get("estimated_input_tokens"),
        "forced_primary_label": forced.get("primary_label") or "",
        "forced_relevance_level": forced.get("relevance_level") or "",
        "forced_evidence_level": forced.get("evidence_level") or "",
        "forced_af_related_label": forced.get("af_related_label") or "",
        "forced_af_use_label": forced.get("af_use_label") or "",
        "forced_adoption_eligible": forced.get("adoption_eligible") or "",
        "forced_reason": forced.get("reason") or "",
        "input_packet_sha256": fingerprint(packet),
    }
    errors: list[str] = []
    bool_fields = {"model_eligible", "fulltext_body_available"}
    numeric_fields = {"adjudication_order", "publication_year", "estimated_input_tokens"}
    for field, wanted in expected.items():
        actual = row.get(field)
        if field in bool_fields:
            try:
                matches = parse_boolish(actual) == wanted
            except ValueError:
                matches = False
        elif field in numeric_fields:
            actual_number = None if actual is None or text(actual) == "" else float(actual)
            wanted_number = None if wanted is None else float(wanted)
            matches = actual_number == wanted_number
        else:
            matches = text(actual) == text(wanted)
        if not matches:
            errors.append(f"immutable source field changed: {field}")
    try:
        context_policy = json.loads(text(row.get("context_policy")))
        if context_policy != (packet.get("context_policy") or {}):
            errors.append("immutable source field changed: context_policy")
    except json.JSONDecodeError:
        errors.append("immutable source field invalid: context_policy")
    return errors


def main() -> int:
    args = parse_args()
    extract_path = resolve(args.extract)
    queue_path = resolve(args.queue)
    input_path = resolve(args.inputs)
    schema_path = resolve(args.schema)
    output_dir = resolve(args.output_dir)
    for path in (extract_path, queue_path, input_path, schema_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    extract = json.loads(extract_path.read_text(encoding="utf-8"))
    rows = extract.get("rows")
    if not isinstance(rows, list) or len(rows) != args.expected_records:
        raise ValueError(f"Expected {args.expected_records} extracted rows")
    if extract.get("complete_count") != args.expected_records or extract.get("pending_count") != 0:
        raise ValueError("Workbook is not fully marked complete")
    queue = read_queue(queue_path)
    if len(queue) != args.expected_records:
        raise ValueError(f"Expected {args.expected_records} queue rows")
    queue_ids = [item["review_id"] for item in queue]
    row_ids = [text(item.get("review_id")) for item in rows]
    if row_ids != queue_ids:
        raise ValueError("Completed workbook IDs/order differ from the locked direct-human queue")

    wanted_ids = set(queue_ids)
    packets: dict[str, dict[str, Any]] = {}
    for line_number, packet in iter_jsonl(input_path):
        review_id = packet.get("review_id")
        if review_id not in wanted_ids:
            continue
        if review_id != packet.get("work_id") or review_id in packets:
            raise ValueError(f"input:{line_number}: invalid identity")
        packets[review_id] = packet
    if set(packets) != wanted_ids:
        raise ValueError("Frozen production inputs do not cover the 187-record queue")

    legacy = load_legacy_validator()
    runner = load_runner()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[dict[str, Any]] = []
    semantic_warnings: list[dict[str, Any]] = []
    canonical: list[dict[str, Any]] = []
    adjudicator_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()

    for index, (row, queue_row) in enumerate(zip(rows, queue, strict=True), 1):
        row_number = index + 1
        review_id = queue_row["review_id"]
        packet = packets[review_id]
        row_errors = compare_source_columns(row, queue_row, packet, index)
        if text(row.get("adjudication_status")).lower() != "complete":
            row_errors.append("adjudication_status is not complete")
        try:
            response = legacy.response_from_row(row)
            runner_findings = runner.validate_review(copy.deepcopy(response), packet, validator)
            row_errors.extend(item for item in runner_findings if not item.startswith("semantic:"))
            row_errors.extend(legacy.validate_human_consistency(response))
            warnings = [item for item in runner_findings if item.startswith("semantic:")]
            if warnings:
                semantic_warnings.append({
                    "row_number": row_number,
                    "review_id": review_id,
                    "work_id": review_id,
                    "findings": json.dumps(warnings, ensure_ascii=False),
                })
            adjudication_date = legacy.parse_date(row.get("adjudication_date"))
            adjudicator_id = text(row.get("adjudicator_id"))
            if not adjudicator_id:
                row_errors.append("adjudicator_id is blank")
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            row_errors.append(str(exc))
            response = None
            adjudication_date = ""
            adjudicator_id = text(row.get("adjudicator_id"))

        if row_errors:
            errors.append({
                "row_number": row_number,
                "review_id": review_id,
                "work_id": text(row.get("work_id")),
                "findings": json.dumps(row_errors, ensure_ascii=False),
            })
            continue
        canonical.append({
            "schema_version": "af-production-canonical-model-review-v1",
            "review_id": review_id,
            "work_id": review_id,
            "provider": "human_adjudication",
            "model": None,
            "validation_status": "valid",
            "source_model": "direct_human_adjudication",
            "source_route": queue_row["route"],
            "provenance": {
                "workbook_path": extract.get("workbook_path"),
                "workbook_sha256": extract.get("workbook_sha256"),
                "extracted_file": rel(extract_path),
                "extracted_file_sha256": sha256_file(extract_path),
                "workbook_row_number": row_number,
                "input_packet_sha256": fingerprint(packet),
                "adjudicator_id": adjudicator_id,
                "adjudication_date": adjudication_date,
                "queue_route": queue_row["route"],
                "queue_reasons": queue_row.get("queue_reasons", ""),
            },
            "response": response,
        })
        adjudicator_counts[adjudicator_id] += 1
        label_counts[response["primary_label"]] += 1
        route_counts[queue_row["route"]] += 1

    error_path = output_dir / "production_direct_human_validation_errors_v1.csv"
    if errors:
        if not args.dry_run:
            write_audit(error_path, errors)
        print(f"Human records: {len(rows)}")
        print(f"Valid: {len(canonical)}")
        print(f"Errors: {len(errors)}")
        for item in errors[:30]:
            print(f"  row {item['row_number']} {item['review_id']}: {item['findings']}")
        if not args.dry_run:
            print(f"Error report: {error_path}")
        return 2

    summary = {
        "schema_version": "af-production-direct-human-complete-summary-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_only": True,
        "provider_requests_made": 0,
        "queue_records": len(queue),
        "valid_human_records": len(canonical),
        "coverage_complete": len(canonical) == args.expected_records,
        "routes": dict(route_counts),
        "adjudicators": dict(adjudicator_counts),
        "primary_labels": dict(label_counts),
        "semantic_heuristic_warning_records": len(semantic_warnings),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = output_dir / "production_direct_human_canonical_valid_v1.jsonl"
    summary_path = output_dir / "production_direct_human_complete_summary_v1.json"
    warning_path = output_dir / "production_direct_human_semantic_warnings_v1.csv"
    lock_path = output_dir / "production_direct_human_complete_v1.lock.json"
    hashes = {
        "canonical": write_jsonl(canonical_path, canonical),
        "summary": write_json(summary_path, summary),
        "semantic_warnings": write_audit(warning_path, semantic_warnings),
    }
    lock = {
        "schema_version": "af-production-direct-human-complete-lock-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "sources": {
            "extract": {"path": rel(extract_path), "sha256": sha256_file(extract_path)},
            "workbook": {"path": extract.get("workbook_path"), "sha256": extract.get("workbook_sha256")},
            "queue": {"path": rel(queue_path), "sha256": sha256_file(queue_path)},
            "inputs": {"path": rel(input_path), "sha256": sha256_file(input_path)},
            "schema": {"path": rel(schema_path), "sha256": sha256_file(schema_path)},
            "validator": {"path": rel(Path(__file__)), "sha256": sha256_file(Path(__file__))},
            "shared_human_validator": {"path": "code/41_finalize_model_c_human_adjudication.py", "sha256": sha256_file(CODE_ROOT / "41_finalize_model_c_human_adjudication.py")},
            "review_validator": {"path": "code/08_run_model_review.py", "sha256": sha256_file(CODE_ROOT / "08_run_model_review.py")},
        },
        "outputs": {
            "canonical": {"path": rel(canonical_path), "sha256": hashes["canonical"]},
            "summary": {"path": rel(summary_path), "sha256": hashes["summary"]},
            "semantic_warnings": {"path": rel(warning_path), "sha256": hashes["semantic_warnings"]},
        },
        "ordered_review_ids_sha256": sha256_bytes(("\n".join(queue_ids) + "\n").encode()),
    }
    write_json(lock_path, lock)
    if error_path.exists():
        error_path.unlink()
        checksum = error_path.with_suffix(error_path.suffix + ".sha256")
        if checksum.exists():
            checksum.unlink()
    print(f"Canonical direct-human records: {canonical_path}")
    print(f"Semantic warning audit: {warning_path}")
    print(f"Lock: {lock_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
