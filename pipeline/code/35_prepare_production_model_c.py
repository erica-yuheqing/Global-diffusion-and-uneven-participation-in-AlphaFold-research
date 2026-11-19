#!/usr/bin/env python3
"""Freeze production A/B reviews and prepare the blinded Model C queue.

This command is local-only.  It never makes provider requests.  Every accepted
model response is revalidated against the frozen packet, JSON schema, and the
current semantic validator before it can enter the production comparison.
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

from fulltext_pipeline.agreement_policy import (  # noqa: E402
    CORE_DECISION_FIELDS,
    POLICY_VERSION,
    action_disagreement,
    core_differences,
    normalize_actions,
)


DEFAULT_INPUT = PROJECT_ROOT / "fulltext/production/model_inputs_v1/full_model_inputs.jsonl"
DEFAULT_INPUT_META = PROJECT_ROOT / "fulltext/production/model_inputs_v1/full_model_inputs.meta.json"
DEFAULT_A = PROJECT_ROOT / "fulltext/production/model_outputs_v1/model_a_deepseek_flash_high_v2.jsonl"
DEFAULT_A_FORCED = DEFAULT_A.with_name(DEFAULT_A.stem + ".forced_u.jsonl")
DEFAULT_B = PROJECT_ROOT / "fulltext/production/model_outputs_v1/model_b_glm_5_3_flash_high_v2.jsonl"
DEFAULT_B_FORCED = DEFAULT_B.with_name(DEFAULT_B.stem + ".forced_u.jsonl")
DEFAULT_PROMPT = PROJECT_ROOT / "config/af_review_prompt_v4.txt"
DEFAULT_SCHEMA = PROJECT_ROOT / "config/af_review_output_schema_v2.json"
DEFAULT_PROTOCOL = PROJECT_ROOT / "config/af_production_protocol_v1.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext/production/adjudication_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--input-meta", type=Path, default=DEFAULT_INPUT_META)
    parser.add_argument("--model-a", type=Path, default=DEFAULT_A)
    parser.add_argument("--model-a-forced", type=Path, default=DEFAULT_A_FORCED)
    parser.add_argument("--model-b", type=Path, default=DEFAULT_B)
    parser.add_argument("--model-b-forced", type=Path, default=DEFAULT_B_FORCED)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-records", type=int, default=29_127)
    parser.add_argument("--expected-model-eligible", type=int, default=28_130)
    parser.add_argument("--expected-forced-u", type=int, default=997)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolved(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            yield line_number, value


def unique_jsonl(path: Path, label: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, record in iter_jsonl(path):
        review_id = record.get("review_id")
        work_id = record.get("work_id")
        if not isinstance(review_id, str) or not review_id:
            raise ValueError(f"{label}:{line_number}: missing review_id")
        if review_id != work_id:
            raise ValueError(f"{label}:{line_number}: review_id/work_id mismatch")
        if review_id in records:
            raise ValueError(f"{label}: duplicate review_id {review_id}")
        records[review_id] = record
    return records


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("production_model_review_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum_tmp = checksum.with_suffix(checksum.suffix + ".part")
    checksum_tmp.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    checksum_tmp.replace(checksum)
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    with temporary.open("wb") as handle:
        for record in records:
            data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode()
            handle.write(data)
            digest.update(data)
    temporary.replace(path)
    value = digest.hexdigest()
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum_tmp = checksum.with_suffix(checksum.suffix + ".part")
    checksum_tmp.write_text(f"{value}  {path.name}\n", encoding="ascii")
    checksum_tmp.replace(checksum)
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    fieldnames = list(rows[0]) if rows else ["review_id", "work_id", "route"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, buffer.getvalue().encode())


def validate_model_records(
    *,
    label: str,
    records: dict[str, dict[str, Any]],
    packets: dict[str, dict[str, Any]],
    runner: Any,
    validator: Draft202012Validator,
    expected_provider: str,
    expected_model: str,
    prompt_sha256: str,
    schema_sha256: str,
) -> tuple[dict[str, dict[str, Any]], Counter[str]]:
    accepted: dict[str, dict[str, Any]] = {}
    run_ids: Counter[str] = Counter()
    for review_id, envelope in records.items():
        packet = packets.get(review_id)
        if packet is None:
            raise ValueError(f"{label}/{review_id}: record is outside the frozen input")
        if packet.get("model_eligible") is not True:
            raise ValueError(f"{label}/{review_id}: API output exists for a forced-U packet")
        if envelope.get("provider") != expected_provider or envelope.get("model") != expected_model:
            raise ValueError(f"{label}/{review_id}: provider/model mismatch")
        if envelope.get("input_packet_sha256") != fingerprint(packet):
            raise ValueError(f"{label}/{review_id}: input packet fingerprint mismatch")
        signature = envelope.get("run_signature") or {}
        if signature.get("prompt_sha256") != prompt_sha256:
            raise ValueError(f"{label}/{review_id}: prompt fingerprint mismatch")
        if signature.get("schema_sha256") != schema_sha256:
            raise ValueError(f"{label}/{review_id}: schema fingerprint mismatch")
        response = envelope.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"{label}/{review_id}: response is missing")
        errors = runner.validate_review(copy.deepcopy(response), packet, validator)
        if errors:
            raise ValueError(f"{label}/{review_id}: frozen output no longer validates: {errors}")
        accepted[review_id] = envelope
        run_ids[str(envelope.get("run_id") or "unknown")] += 1
    return accepted, run_ids


def validate_forced_records(
    *,
    label: str,
    records: dict[str, dict[str, Any]],
    packets: dict[str, dict[str, Any]],
    expected_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if set(records) != expected_ids:
        raise ValueError(
            f"{label}: forced-U IDs differ from input; "
            f"missing={len(expected_ids-set(records))}, extra={len(set(records)-expected_ids)}"
        )
    for review_id, record in records.items():
        packet = packets[review_id]
        if record.get("input_packet_sha256") != fingerprint(packet):
            raise ValueError(f"{label}/{review_id}: input packet fingerprint mismatch")
        if record.get("response") != packet.get("forced_decision") or record.get("api_calls") != 0:
            raise ValueError(f"{label}/{review_id}: invalid forced-U response")
    return records


def canonical_record(
    envelope: dict[str, Any], source_path: Path, source_sha256: str, label: str
) -> dict[str, Any]:
    return {
        "schema_version": "af-production-canonical-model-review-v1",
        "review_id": envelope["review_id"],
        "work_id": envelope["work_id"],
        "provider": envelope.get("provider"),
        "model": envelope.get("model"),
        "validation_status": "valid",
        "source_model": label,
        "provenance": {
            "source_path": str(source_path),
            "source_file_sha256": source_sha256,
            "source_record_sha256": fingerprint(envelope),
            "source_run_id": envelope.get("run_id"),
            "source_artifact": envelope.get("run_artifact"),
            "input_packet_sha256": envelope.get("input_packet_sha256"),
            "run_signature": envelope.get("run_signature"),
        },
        "response": envelope["response"],
    }


def route_rows(
    packets_in_order: list[dict[str, Any]],
    model_a: dict[str, dict[str, Any]],
    model_b: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    field_disagreements: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    queue_reason_counts: Counter[str] = Counter()
    action_disagreements = 0
    core_exact = 0
    comparison_rows: list[dict[str, Any]] = []
    model_c_packets: list[dict[str, Any]] = []
    direct_human_rows: list[dict[str, Any]] = []
    evidence_recovery_rows: list[dict[str, Any]] = []

    for packet in packets_in_order:
        review_id = packet["review_id"]
        a_env = model_a.get(review_id)
        b_env = model_b.get(review_id)
        a = a_env.get("response") if a_env else None
        b = b_env.get("response") if b_env else None
        eligible = packet.get("model_eligible") is True
        differences: tuple[str, ...] = ()
        action_diff = False
        queue_reasons: list[str] = []

        if not eligible:
            if packet.get("evidence_tier") == "oversize_context_human_review":
                route = "forced_u_oversize_direct_human"
                queue_reasons.append("oversize_context_human_review")
            else:
                route = "forced_u_evidence_recovery"
                queue_reasons.append("insufficient_evidence")
        elif a is not None and b is not None:
            differences = core_differences(a, b)
            action_diff = action_disagreement(a, b)
            if differences:
                route = "model_c_core_disagreement"
                queue_reasons.append("ab_core_disagreement")
                model_c_packets.append(packet)
            else:
                route = "ab_core_agreement"
                core_exact += 1
            for field in differences:
                field_disagreements[field] += 1
            if action_diff:
                action_disagreements += 1
        elif a is not None or b is not None:
            route = "model_c_single_model_only"
            queue_reasons.append("missing_model_b" if a is not None else "missing_model_a")
            model_c_packets.append(packet)
        else:
            route = "direct_human_no_valid_ab"
            queue_reasons.append("no_valid_ab")

        route_counts[route] += 1
        for reason in queue_reasons:
            queue_reason_counts[reason] += 1
        row = {
            "review_id": review_id,
            "work_id": packet["work_id"],
            "evidence_tier": packet.get("evidence_tier"),
            "model_eligible": eligible,
            "a_status": "valid" if a is not None else "missing",
            "b_status": "valid" if b is not None else "missing",
            "route": route,
            "queue_reasons": "|".join(queue_reasons),
            "core_differing_fields": "|".join(differences),
            "observed_actions_disagreement": action_diff,
            "a_primary_label": a.get("primary_label") if a else "",
            "b_primary_label": b.get("primary_label") if b else "",
            "a_relevance_level": a.get("relevance_level") if a else "",
            "b_relevance_level": b.get("relevance_level") if b else "",
            "a_evidence_level": a.get("evidence_level") if a else "",
            "b_evidence_level": b.get("evidence_level") if b else "",
            "a_af_related_label": a.get("af_related_label") if a else "",
            "b_af_related_label": b.get("af_related_label") if b else "",
            "a_af_use_label": a.get("af_use_label") if a else "",
            "b_af_use_label": b.get("af_use_label") if b else "",
            "a_adoption_eligible": a.get("adoption_eligible") if a else "",
            "b_adoption_eligible": b.get("adoption_eligible") if b else "",
            "a_observed_actions": "|".join(normalize_actions(a.get("observed_actions"))) if a else "",
            "b_observed_actions": "|".join(normalize_actions(b.get("observed_actions"))) if b else "",
            "a_needs_human_review": a.get("needs_human_review") if a else "",
            "b_needs_human_review": b.get("needs_human_review") if b else "",
        }
        comparison_rows.append(row)
        if route in {"direct_human_no_valid_ab", "forced_u_oversize_direct_human"}:
            direct_human_rows.append(row)
        if route == "forced_u_evidence_recovery":
            evidence_recovery_rows.append(row)

    eligible_common = sum(
        row["model_eligible"] and row["a_status"] == row["b_status"] == "valid"
        for row in comparison_rows
    )
    report = {
        "agreement_policy": POLICY_VERSION,
        "core_fields": list(CORE_DECISION_FIELDS),
        "secondary_fields_excluded_from_model_c_routing": ["observed_actions"],
        "records": len(comparison_rows),
        "model_eligible": sum(row["model_eligible"] for row in comparison_rows),
        "forced_u": sum(not row["model_eligible"] for row in comparison_rows),
        "a_valid": len(model_a),
        "b_valid": len(model_b),
        "ab_common_valid": eligible_common,
        "ab_core_exact": core_exact,
        "ab_core_disagreement": route_counts["model_c_core_disagreement"],
        "ab_observed_actions_disagreement": action_disagreements,
        "field_disagreement_counts": dict(field_disagreements),
        "route_counts": dict(route_counts),
        "queue_reason_counts": dict(queue_reason_counts),
        "model_c_records": len(model_c_packets),
        "model_c_estimated_input_tokens": sum(
            int(packet.get("estimated_input_tokens") or 0) for packet in model_c_packets
        ),
        "direct_human_records": len(direct_human_rows),
        "evidence_recovery_records": len(evidence_recovery_rows),
    }
    return report, comparison_rows, model_c_packets, direct_human_rows, evidence_recovery_rows


def main() -> int:
    args = parse_args()
    paths = {
        "input": resolved(args.input),
        "input_meta": resolved(args.input_meta),
        "model_a": resolved(args.model_a),
        "model_a_forced": resolved(args.model_a_forced),
        "model_b": resolved(args.model_b),
        "model_b_forced": resolved(args.model_b_forced),
        "prompt": resolved(args.prompt),
        "schema": resolved(args.schema),
        "protocol": resolved(args.protocol),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label}: {path}")
    source_hashes = {label: sha256_file(path) for label, path in paths.items()}

    input_meta = read_json(paths["input_meta"])
    if input_meta.get("input_file_sha256") != source_hashes["input"]:
        raise ValueError("Frozen input hash differs from its metadata")
    runner = load_runner()
    # The model runner applies this idempotent sanitization before hashing,
    # selection, forced-U emission, and API submission.  Reproduce that exact
    # view here instead of comparing envelopes with the raw on-disk packet.
    packets_in_order = [runner.prepare_packet(record) for _, record in iter_jsonl(paths["input"])]
    packets: dict[str, dict[str, Any]] = {}
    for packet in packets_in_order:
        review_id = packet.get("review_id")
        if not isinstance(review_id, str) or review_id != packet.get("work_id"):
            raise ValueError("Input contains an invalid review_id/work_id")
        if review_id in packets:
            raise ValueError(f"Input contains duplicate review_id {review_id}")
        packets[review_id] = packet
    eligible_ids = {rid for rid, packet in packets.items() if packet.get("model_eligible") is True}
    forced_ids = set(packets) - eligible_ids
    if len(packets) != args.expected_records:
        raise ValueError(f"Expected {args.expected_records} input records, found {len(packets)}")
    if len(eligible_ids) != args.expected_model_eligible:
        raise ValueError(
            f"Expected {args.expected_model_eligible} eligible records, found {len(eligible_ids)}"
        )
    if len(forced_ids) != args.expected_forced_u:
        raise ValueError(f"Expected {args.expected_forced_u} forced-U records, found {len(forced_ids)}")

    schema = read_json(paths["schema"])
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    prompt_sha = source_hashes["prompt"]
    schema_sha = source_hashes["schema"]

    model_a_raw = unique_jsonl(paths["model_a"], "model_a")
    model_b_raw = unique_jsonl(paths["model_b"], "model_b")
    model_a, a_runs = validate_model_records(
        label="model_a",
        records=model_a_raw,
        packets=packets,
        runner=runner,
        validator=validator,
        expected_provider="deepseek",
        expected_model="deepseek-v4-flash",
        prompt_sha256=prompt_sha,
        schema_sha256=schema_sha,
    )
    model_b, b_runs = validate_model_records(
        label="model_b",
        records=model_b_raw,
        packets=packets,
        runner=runner,
        validator=validator,
        expected_provider="zhipu_cn",
        expected_model="glm-5.3-flash",
        prompt_sha256=prompt_sha,
        schema_sha256=schema_sha,
    )
    validate_forced_records(
        label="model_a_forced",
        records=unique_jsonl(paths["model_a_forced"], "model_a_forced"),
        packets=packets,
        expected_ids=forced_ids,
    )
    validate_forced_records(
        label="model_b_forced",
        records=unique_jsonl(paths["model_b_forced"], "model_b_forced"),
        packets=packets,
        expected_ids=forced_ids,
    )

    comparison, rows, model_c_packets, human_rows, recovery_rows = route_rows(
        packets_in_order, model_a, model_b
    )
    final_hashes = {label: sha256_file(path) for label, path in paths.items()}
    changed = [label for label in paths if source_hashes[label] != final_hashes[label]]
    if changed:
        raise RuntimeError(f"Source files changed while being read: {changed}")

    print(f"Corpus records:          {comparison['records']:,}")
    print(f"Model A valid:           {comparison['a_valid']:,}")
    print(f"Model B valid:           {comparison['b_valid']:,}")
    print(f"A/B common valid:        {comparison['ab_common_valid']:,}")
    print(f"A/B core agreement:      {comparison['ab_core_exact']:,}")
    print(f"A/B core disagreement:   {comparison['ab_core_disagreement']:,}")
    print(f"Actions-only reporting:  {comparison['ab_observed_actions_disagreement']:,} disagreements")
    print(f"Model C queue:           {comparison['model_c_records']:,}")
    print(f"Direct human queue:      {comparison['direct_human_records']:,}")
    print(f"Evidence recovery queue: {comparison['evidence_recovery_records']:,}")
    print(f"Agreement policy:        {POLICY_VERSION}")
    if args.dry_run:
        print("Dry run: no files written; no provider requests made")
        return 0

    output_dir = resolved(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_a = [
        canonical_record(model_a[rid], paths["model_a"], source_hashes["model_a"], "A")
        for rid in packets
        if rid in model_a
    ]
    canonical_b = [
        canonical_record(model_b[rid], paths["model_b"], source_hashes["model_b"], "B")
        for rid in packets
        if rid in model_b
    ]
    outputs: dict[str, dict[str, Any]] = {}

    def save_jsonl(name: str, records: list[dict[str, Any]]) -> None:
        path = output_dir / name
        outputs[name] = {"path": str(path), "records": len(records), "sha256": write_jsonl(path, records)}

    def save_csv(name: str, csv_rows: list[dict[str, Any]]) -> None:
        path = output_dir / name
        outputs[name] = {"path": str(path), "records": len(csv_rows), "sha256": write_csv(path, csv_rows)}

    save_jsonl("model_a_canonical_valid_v1.jsonl", canonical_a)
    save_jsonl("model_b_canonical_valid_v1.jsonl", canonical_b)
    save_csv("production_ab_reconciliation_v1.csv", rows)
    save_jsonl("production_model_c_inputs_v1.jsonl", model_c_packets)
    save_csv("production_direct_human_queue_v1.csv", human_rows)
    save_csv("production_evidence_recovery_queue_v1.csv", recovery_rows)

    c_path = output_dir / "production_model_c_inputs_v1.jsonl"
    c_meta_path = output_dir / "production_model_c_inputs_v1.meta.json"
    c_meta = {
        "schema_version": "af-production-model-c-input-manifest-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "records": len(model_c_packets),
        "estimated_input_tokens": sum(
            int(packet.get("estimated_input_tokens") or 0) for packet in model_c_packets
        ),
        "largest_packet_tokens": max(
            (int(packet.get("estimated_input_tokens") or 0) for packet in model_c_packets),
            default=0,
        ),
        "evidence_tiers": dict(Counter(packet.get("evidence_tier") for packet in model_c_packets)),
        "input_path": str(c_path),
        "input_sha256": outputs[c_path.name]["sha256"],
        "ordered_work_id_sha256": sha256_bytes(
            "\n".join(packet["work_id"] for packet in model_c_packets).encode()
        ),
        "selection_policy": {
            "agreement_policy": POLICY_VERSION,
            "include": ["A/B core decision disagreement", "exactly one valid A/B response"],
            "exclude": ["observed_actions-only disagreement", "forced-U", "no valid A/B response"],
        },
        "blinding": (
            "Packets are copied from the frozen blinded production input. A/B responses, old labels, "
            "and sampling fields are not included."
        ),
    }
    outputs[c_meta_path.name] = {
        "path": str(c_meta_path),
        "records": 1,
        "sha256": write_json(c_meta_path, c_meta),
    }
    lock_path = output_dir / "production_ab_model_c_prep_v1.lock.json"
    lock = {
        "schema_version": "af-production-ab-model-c-prep-lock-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            label: {"path": str(paths[label]), "sha256": source_hashes[label]}
            for label in paths
        },
        "source_counts": {
            "input": len(packets),
            "model_a_valid": len(model_a),
            "model_b_valid": len(model_b),
            "forced_u": len(forced_ids),
        },
        "source_run_counts": {"model_a": dict(a_runs), "model_b": dict(b_runs)},
        "agreement_policy": {
            "version": POLICY_VERSION,
            "core_fields": list(CORE_DECISION_FIELDS),
            "observed_actions_is_secondary": True,
            "observed_actions_triggers_model_c": False,
        },
        "implementation": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "runner": str((CODE_ROOT / "08_run_model_review.py").resolve()),
            "runner_sha256": sha256_file(CODE_ROOT / "08_run_model_review.py"),
            "agreement_module": str((CODE_ROOT / "fulltext_pipeline/agreement_policy.py").resolve()),
            "agreement_module_sha256": sha256_file(CODE_ROOT / "fulltext_pipeline/agreement_policy.py"),
        },
        "comparison": comparison,
        "outputs": outputs,
    }
    lock_sha = write_json(lock_path, lock)
    report_path = output_dir / "production_ab_comparison_v1.json"
    report = {
        "schema_version": "af-production-ab-comparison-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "lock": {"path": str(lock_path), "sha256": lock_sha},
        "comparison": comparison,
        "outputs": outputs,
        "interpretation": (
            "Core agreement follows af-core-agreement-v1. observed_actions is reported as a secondary "
            "field and never independently routes a record to Model C. A/B agreement is not human-reference accuracy."
        ),
    }
    report_sha = write_json(report_path, report)
    print(f"Output directory:        {output_dir}")
    print(f"Lock SHA-256:            {lock_sha}")
    print(f"Report SHA-256:          {report_sha}")
    print("No provider requests were made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
