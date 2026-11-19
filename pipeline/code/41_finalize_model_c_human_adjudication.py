#!/usr/bin/env python3
"""Validate completed human adjudication and freeze final Model C outputs.

This program consumes the artifact-tool JSON extraction, revalidates every
human decision against the frozen packet, and merges valid human decisions with
the 9,607 canonical Model C records. It is local-only and makes no API calls.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

DEFAULT_EXTRACT = PROJECT_ROOT / "outputs/model_c_adjudication_20260915/completed_20260915/model_c_human_adjudication_70_v1_completed.extracted.json"
DEFAULT_HUMAN_INPUTS = PROJECT_ROOT / "fulltext/production/model_c_finalization_v1/model_c_human_adjudication_inputs_v1.jsonl"
DEFAULT_CANONICAL = PROJECT_ROOT / "fulltext/production/model_c_finalization_v1/model_c_canonical_valid_v1.jsonl"
DEFAULT_MODEL_C_INPUT = PROJECT_ROOT / "fulltext/production/adjudication_v1/production_model_c_inputs_v1.jsonl"
DEFAULT_SCHEMA = PROJECT_ROOT / "config/af_review_output_schema_v2.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext/production/model_c_finalization_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--human-inputs", type=Path, default=DEFAULT_HUMAN_INPUTS)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--model-c-input", type=Path, default=DEFAULT_MODEL_C_INPUT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-human", type=int, default=70)
    parser.add_argument("--expected-final", type=int, default=9_677)
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
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            yield line_number, value


def unique_jsonl(path: Path, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line_number, row in iter_jsonl(path):
        review_id = row.get("review_id")
        if not isinstance(review_id, str) or review_id != row.get("work_id"):
            raise ValueError(f"{label}:{line_number}: invalid identity")
        if review_id in result:
            raise ValueError(f"{label}: duplicate review_id {review_id}")
        result[review_id] = row
    return result


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("human_adjudication_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def split_multi(value: Any) -> list[str]:
    raw = text(value)
    if not raw or raw.lower() in {"none", "n/a", "na"}:
        return []
    for separator in ("；", "，", ";"):
        raw = raw.replace(separator, "|")
    return [item.strip() for item in raw.split("|") if item.strip()]


def parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raw = text(value).lower()
    if raw in {"true", "yes", "1"}:
        return True
    if raw in {"false", "no", "0"}:
        return False
    raise ValueError(f"{field}: expected true/false, got {value!r}")


def parse_int_or_none(value: Any, field: str) -> int | None:
    if value is None or text(value) == "":
        return None
    number = float(value)
    if not number.is_integer() or number < 0:
        raise ValueError(f"{field}: expected non-negative integer or blank")
    return int(number)


def parse_float(value: Any, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{field}: expected a number from 0 to 1")
    return number


def parse_date(value: Any) -> str:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
    raw = text(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    raise ValueError(f"adjudication_date: invalid value {value!r}")


def parse_action_evidence(value: Any) -> list[dict[str, Any]]:
    raw = text(value)
    if not raw or raw.lower() == "none":
        return []
    result: list[dict[str, Any]] = []
    for item in raw.split("|"):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"action_evidence_map: missing ':' in {item!r}")
        action, indices_text = item.split(":", 1)
        indices = []
        for token in re.split(r"[,，]", indices_text):
            token = token.strip()
            if not token:
                continue
            slot = int(token)
            if slot not in {1, 2, 3}:
                raise ValueError(f"action_evidence_map: evidence slot must be 1–3, got {slot}")
            indices.append(slot - 1)
        if not indices:
            raise ValueError(f"action_evidence_map: no evidence slots for {action.strip()}")
        result.append({"action": action.strip(), "evidence_indices": list(dict.fromkeys(indices))})
    return result


def response_from_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for slot in range(1, 4):
        prefix = f"evidence_{slot}_"
        source_kind = text(row.get(prefix + "source_kind"))
        quote = text(row.get(prefix + "quote"))
        other = any(text(row.get(prefix + suffix)) for suffix in ("block_index", "section", "supports"))
        if not source_kind and not quote and not other:
            continue
        if not source_kind or not quote:
            raise ValueError(f"evidence_{slot}: source_kind and quote are required together")
        evidence.append({
            "source_kind": source_kind,
            "block_index": parse_int_or_none(row.get(prefix + "block_index"), prefix + "block_index"),
            "section": text(row.get(prefix + "section")) or None,
            "quote": quote,
            "supports": split_multi(row.get(prefix + "supports")),
        })
    review_id = text(row.get("review_id"))
    return {
        "schema_version": "af-model-review-output-v2",
        "review_id": review_id,
        "work_id": review_id,
        "primary_label": text(row.get("adjudicated_primary_label")),
        "relevance_level": text(row.get("adjudicated_relevance_level")),
        "evidence_level": text(row.get("adjudicated_evidence_level")),
        "af_related_label": text(row.get("adjudicated_af_related_label")),
        "af_use_label": text(row.get("adjudicated_af_use_label")),
        "adoption_eligible": text(row.get("adjudicated_adoption_eligible")),
        "observed_actions": split_multi(row.get("adjudicated_observed_actions")),
        "future_or_hypothetical_only": parse_bool(row.get("adjudicated_future_or_hypothetical_only"), "future_or_hypothetical_only"),
        "confidence": parse_float(row.get("confidence"), "confidence"),
        "needs_human_review": parse_bool(row.get("needs_human_review"), "needs_human_review"),
        "human_review_reasons": split_multi(row.get("human_review_reasons")),
        "exclusion_reason": text(row.get("adjudicated_exclusion_reason")),
        "evidence": evidence,
        "reasoning_summary": text(row.get("reasoning_summary")),
        "action_evidence": parse_action_evidence(row.get("adjudicated_action_evidence_map")),
    }


def validate_human_consistency(response: dict[str, Any]) -> list[str]:
    """Enforce deterministic codebook constraints, not lexical heuristics."""
    errors: list[str] = []
    expected = {
        "FP": ("R0", "false", "no", "no"),
        "background_only": ("R1", "background", "no", "no"),
        "review_discussion": ("R2", "related", "no", "no"),
        "database_consumption": ("R3", "related", "yes", "yes"),
        "model_application": ("R3", "related", "yes", "yes"),
        "method_development": ("R4", "related", "yes", "yes"),
        "original_platform": ("R4", "related", "yes", "no"),
    }
    primary = response["primary_label"]
    observed = (
        response["relevance_level"], response["af_related_label"],
        response["af_use_label"], response["adoption_eligible"],
    )
    if primary in expected and observed != expected[primary]:
        errors.append(f"codebook primary consistency: expected {expected[primary]}, found {observed}")
    if primary == "uncertain" and response["relevance_level"] != "RU":
        errors.append("codebook: primary_label=uncertain requires relevance_level=RU")
    actions = set(response["observed_actions"])
    actual_actions = actions - {"none", "discussion_only"}
    if "none" in actions and len(actions) > 1:
        errors.append("codebook: none cannot coexist with another observed action")
    if "discussion_only" in actions and actual_actions:
        errors.append("codebook: discussion_only cannot coexist with an actual-use action")
    if actual_actions and response["af_use_label"] != "yes":
        errors.append("codebook: actual-use action requires af_use_label=yes")
    if response["evidence_level"] in {"E0", "E1"} and (
        response["af_use_label"] == "yes" or response["adoption_eligible"] == "yes"
    ):
        errors.append("codebook: E0/E1 cannot establish actual use or adoption")
    if response["future_or_hypothetical_only"] and (
        response["af_use_label"] == "yes" or response["adoption_eligible"] == "yes" or actual_actions
    ):
        errors.append("codebook: future-only conflicts with actual use")
    if response["needs_human_review"] and not response["human_review_reasons"]:
        errors.append("codebook: needs_human_review=true requires at least one reason")
    if not response["needs_human_review"] and response["human_review_reasons"]:
        errors.append("codebook: human_review_reasons require needs_human_review=true")
    return errors


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


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
    path.with_suffix(path.suffix + ".sha256").write_text(f"{value}  {path.name}\n", encoding="ascii")
    return value


def write_errors(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["row_number", "review_id", "work_id", "errors"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, buffer.getvalue().encode())


def main() -> int:
    args = parse_args()
    extract_path = resolve(args.extract)
    human_input_path = resolve(args.human_inputs)
    canonical_path = resolve(args.canonical)
    model_c_input_path = resolve(args.model_c_input)
    schema_path = resolve(args.schema)
    output_dir = resolve(args.output_dir)
    extract = json.loads(extract_path.read_text(encoding="utf-8"))
    rows = extract.get("rows")
    if not isinstance(rows, list) or len(rows) != args.expected_human:
        raise ValueError(f"Expected {args.expected_human} extracted rows")
    if extract.get("complete_count") != args.expected_human or extract.get("pending_count") != 0:
        raise ValueError("Workbook is not fully marked complete")

    human_inputs = unique_jsonl(human_input_path, "human_inputs")
    canonical = unique_jsonl(canonical_path, "canonical")
    final_order: list[str] = []
    packets: dict[str, dict[str, Any]] = {}
    for line_number, packet in iter_jsonl(model_c_input_path):
        review_id = packet.get("review_id")
        if not isinstance(review_id, str) or review_id != packet.get("work_id") or review_id in packets:
            raise ValueError(f"model_c_input:{line_number}: invalid identity")
        final_order.append(review_id)
        packets[review_id] = packet
    if set(human_inputs) != {text(row.get("review_id")) for row in rows}:
        raise ValueError("Completed workbook IDs differ from the locked 70-record human queue")

    runner = load_runner()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[dict[str, Any]] = []
    semantic_warnings: list[dict[str, Any]] = []
    valid_human: dict[str, dict[str, Any]] = {}
    adjudicator_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    for row_number, row in enumerate(rows, 2):
        review_id = text(row.get("review_id"))
        row_errors: list[str] = []
        if text(row.get("adjudication_status")).lower() != "complete":
            row_errors.append("adjudication_status is not complete")
        try:
            response = response_from_row(row)
            packet = human_inputs[review_id]["packet"]
            if human_inputs[review_id].get("input_packet_sha256") != fingerprint(packet):
                row_errors.append("locked input packet fingerprint mismatch")
            runner_findings = runner.validate_review(copy.deepcopy(response), packet, validator)
            # Human adjudication is authoritative over lexical heuristics such
            # as explicit-run phrase detection. Schema, exact evidence
            # anchoring, and non-semantic validator findings remain blocking.
            row_errors.extend(item for item in runner_findings if not item.startswith("semantic:"))
            row_errors.extend(validate_human_consistency(response))
            warnings = [item for item in runner_findings if item.startswith("semantic:")]
            if warnings:
                semantic_warnings.append({
                    "row_number": row_number,
                    "review_id": review_id,
                    "work_id": review_id,
                    "errors": json.dumps(warnings, ensure_ascii=False),
                })
            adjudication_date = parse_date(row.get("adjudication_date"))
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
                "errors": json.dumps(row_errors, ensure_ascii=False),
            })
            continue
        valid_human[review_id] = {
            "schema_version": "af-production-canonical-model-review-v1",
            "review_id": review_id,
            "work_id": review_id,
            "provider": "human_adjudication",
            "model": None,
            "validation_status": "valid",
            "source_model": "model_c_human_adjudication",
            "source_route": "human_adjudication",
            "provenance": {
                "workbook_path": extract.get("workbook_path"),
                "workbook_sha256": extract.get("workbook_sha256"),
                "extracted_file": rel(extract_path),
                "extracted_file_sha256": sha256_file(extract_path),
                "workbook_row_number": row_number,
                "input_packet_sha256": fingerprint(human_inputs[review_id]["packet"]),
                "adjudicator_id": adjudicator_id,
                "adjudication_date": adjudication_date,
            },
            "response": response,
        }
        adjudicator_counts[adjudicator_id] += 1
        label_counts[response["primary_label"]] += 1

    error_path = output_dir / "model_c_human_adjudication_validation_errors_v1.csv"
    if errors:
        if not args.dry_run:
            write_errors(error_path, errors)
        print(f"Human records: {len(rows)}")
        print(f"Valid: {len(valid_human)}")
        print(f"Errors: {len(errors)}")
        for item in errors[:20]:
            print(f"  row {item['row_number']} {item['review_id']}: {item['errors']}")
        if not args.dry_run:
            print(f"Error report: {error_path}")
        return 2

    if set(canonical) & set(valid_human):
        raise ValueError("Canonical Model C and human adjudication records overlap")
    if set(canonical) | set(valid_human) != set(packets):
        raise ValueError("Final Model C coverage does not equal the frozen 9,677-record queue")
    final_records = [canonical.get(review_id) or valid_human[review_id] for review_id in final_order]
    if len(final_records) != args.expected_final:
        raise ValueError(f"Expected {args.expected_final} final records, found {len(final_records)}")

    summary = {
        "schema_version": "af-model-c-complete-summary-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_only": True,
        "provider_requests_made": 0,
        "frozen_model_c_records": len(packets),
        "preexisting_canonical_records": len(canonical),
        "human_adjudicated_records": len(valid_human),
        "final_records": len(final_records),
        "coverage_complete": len(final_records) == len(packets),
        "adjudicators": dict(adjudicator_counts),
        "human_primary_labels": dict(label_counts),
        "semantic_heuristic_warning_records": len(semantic_warnings),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    human_path = output_dir / "model_c_human_adjudicated_valid_v1.jsonl"
    final_path = output_dir / "model_c_canonical_complete_v1.jsonl"
    summary_path = output_dir / "model_c_complete_summary_v1.json"
    lock_path = output_dir / "model_c_complete_v1.lock.json"
    warning_path = output_dir / "model_c_human_adjudication_semantic_warnings_v1.csv"
    hashes = {
        "human": write_jsonl(human_path, [valid_human[rid] for rid in final_order if rid in valid_human]),
        "final": write_jsonl(final_path, final_records),
        "summary": write_json(summary_path, summary),
    }
    write_errors(warning_path, semantic_warnings)
    lock = {
        "schema_version": "af-model-c-complete-lock-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "sources": {
            "extract": {"path": rel(extract_path), "sha256": sha256_file(extract_path)},
            "workbook": {"path": extract.get("workbook_path"), "sha256": extract.get("workbook_sha256")},
            "human_inputs": {"path": rel(human_input_path), "sha256": sha256_file(human_input_path)},
            "canonical": {"path": rel(canonical_path), "sha256": sha256_file(canonical_path)},
            "model_c_input": {"path": rel(model_c_input_path), "sha256": sha256_file(model_c_input_path)},
            "schema": {"path": rel(schema_path), "sha256": sha256_file(schema_path)},
        },
        "outputs": {
            "human": {"path": rel(human_path), "sha256": hashes["human"]},
            "final": {"path": rel(final_path), "sha256": hashes["final"]},
            "summary": {"path": rel(summary_path), "sha256": hashes["summary"]},
            "semantic_warnings": {"path": rel(warning_path), "sha256": sha256_file(warning_path)},
        },
        "ordered_final_review_ids_sha256": sha256_bytes(("\n".join(final_order) + "\n").encode()),
    }
    write_json(lock_path, lock)
    if error_path.exists():
        error_path.unlink()
        checksum = error_path.with_suffix(error_path.suffix + ".sha256")
        if checksum.exists():
            checksum.unlink()
    print(f"Human canonical records: {human_path}")
    print(f"Complete Model C: {final_path}")
    print(f"Semantic warning audit: {warning_path}")
    print(f"Lock: {lock_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
