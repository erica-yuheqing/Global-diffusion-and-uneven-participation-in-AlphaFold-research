#!/usr/bin/env python3
"""Build canonical A/B Pilot results and a blinded Model C adjudication queue."""

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
from typing import Any

from jsonschema import Draft202012Validator


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

DECISION_FIELDS = (
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "exclusion_reason",
    "future_or_hypothetical_only",
)
REVIEW_FIELDS = ("needs_human_review", "human_review_reasons")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=PROJECT_ROOT / "fulltext/pilot/calibration/pilot_150_v4_1_merge.lock.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "fulltext/pilot/adjudication_v4_1",
    )
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_fingerprint(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()


def require_locked_file(entry: dict[str, Any], label: str) -> Path:
    path = resolve(entry["path"])
    if not path.is_file():
        raise ValueError(f"{label}: missing file {path}")
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        raise ValueError(f"{label}: SHA-256 mismatch; expected {entry['sha256']}, got {actual}")
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            records.append(record)
    return records


def unique_by_id(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        review_id = record.get("review_id")
        if not isinstance(review_id, str) or not review_id:
            raise ValueError(f"{label}: record without review_id")
        if review_id in result:
            raise ValueError(f"{label}: duplicate review_id {review_id}")
        result[review_id] = record
    return result


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("af_model_review_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load model-review runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum = f"{digest}  {path.name}\n".encode("ascii")
    checksum_tmp = checksum_path.with_suffix(checksum_path.suffix + ".part")
    checksum_tmp.write_bytes(checksum)
    checksum_tmp.replace(checksum_path)
    return digest


def write_json(path: Path, value: Any) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return atomic_write(path, data)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    data = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    ).encode("utf-8")
    return atomic_write(path, data)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, buffer.getvalue().encode("utf-8"))


def normalized_actions(review: dict[str, Any]) -> list[str]:
    value = review.get("observed_actions") or []
    return sorted(str(item) for item in value)


def normalized_reasons(review: dict[str, Any]) -> list[str]:
    value = review.get("human_review_reasons") or []
    return sorted(str(item) for item in value)


def forced_u_valid(packet: dict[str, Any], record: dict[str, Any]) -> bool:
    return (
        packet.get("model_eligible") is False
        and isinstance(packet.get("forced_decision"), dict)
        and record.get("work_id") == packet.get("work_id")
        and record.get("response") == packet.get("forced_decision")
        and record.get("api_calls") == 0
    )


def build_model(
    name: str,
    spec: dict[str, Any],
    packets_in_order: list[dict[str, Any]],
    packets: dict[str, dict[str, Any]],
    runner: Any,
    validator: Draft202012Validator,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    local_path = require_locked_file(spec["local_revalidation"], f"{name}.local_revalidation")
    retry_path = require_locked_file(spec["targeted_retry"], f"{name}.targeted_retry")
    forced_path = require_locked_file(spec["forced_u"], f"{name}.forced_u")
    retry_manifest_path = require_locked_file(
        {
            "path": spec["targeted_retry"]["run_manifest_path"],
            "sha256": spec["targeted_retry"]["run_manifest_sha256"],
        },
        f"{name}.targeted_retry.run_manifest",
    )
    retry_manifest = json.loads(retry_manifest_path.read_text(encoding="utf-8"))
    if retry_manifest.get("run_id") != spec["targeted_retry"]["run_id"]:
        raise ValueError(f"{name}: targeted retry run ID differs from lock")
    local = unique_by_id(read_jsonl(local_path), f"{name}.local_revalidation")
    retry = unique_by_id(read_jsonl(retry_path), f"{name}.targeted_retry")
    forced = unique_by_id(read_jsonl(forced_path), f"{name}.forced_u")

    expected_local = int(spec["local_revalidation"]["records"])
    expected_retry = int(spec["targeted_retry"]["records"])
    expected_forced = int(spec["forced_u"]["records"])
    if (len(local), len(retry), len(forced)) != (expected_local, expected_retry, expected_forced):
        raise ValueError(
            f"{name}: source counts differ from lock: {(len(local), len(retry), len(forced))}"
        )
    local_valid_ids = {rid for rid, row in local.items() if row.get("local_validation_valid") is True}
    local_failed_ids = set(local) - local_valid_ids
    if len(local_valid_ids) != int(spec["local_revalidation"]["valid"]):
        raise ValueError(f"{name}: local valid count differs from lock")
    if set(retry) != local_failed_ids:
        raise ValueError(
            f"{name}: targeted retry IDs do not exactly replace local failures; "
            f"missing={sorted(local_failed_ids-set(retry))}, extra={sorted(set(retry)-local_failed_ids)}"
        )

    canonical: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    for packet in packets_in_order:
        review_id = packet["review_id"]
        if review_id in retry:
            source = retry[review_id]
            response = source.get("response")
            source_type = "targeted_retry_v4_1"
            provenance = {
                "source_path": str(retry_path),
                "source_file_sha256": spec["targeted_retry"]["sha256"],
                "source_record_sha256": json_fingerprint(source),
                "source_run_id": source.get("run_id"),
                "source_artifact": source.get("run_artifact"),
            }
        elif review_id in local_valid_ids:
            source = local[review_id]
            response = source.get("response")
            source_type = "local_revalidation_of_archived_v4_response"
            provenance = {
                "source_path": str(local_path),
                "source_file_sha256": spec["local_revalidation"]["sha256"],
                "source_record_sha256": json_fingerprint(source),
                "source_run_id": source.get("source_run_id"),
                "source_artifact": source.get("source_artifact"),
                "source_attempt_number": source.get("source_attempt_number"),
                "source_response_sha256": source.get("source_response_sha256"),
                "local_validator_fingerprint": source.get("local_validator_fingerprint"),
            }
        elif review_id in forced:
            source = forced[review_id]
            response = source.get("response")
            source_type = "forced_u_no_api"
            provenance = {
                "source_path": str(forced_path),
                "source_file_sha256": spec["forced_u"]["sha256"],
                "source_record_sha256": json_fingerprint(source),
                "source_run_id": source.get("run_id"),
                "source_artifact": source.get("run_artifact"),
            }
        else:
            raise ValueError(f"{name}/{review_id}: no canonical source")

        if source.get("work_id") != packet.get("work_id"):
            raise ValueError(f"{name}/{review_id}: work_id mismatch")
        if source_type == "forced_u_no_api":
            if not forced_u_valid(packet, source):
                raise ValueError(f"{name}/{review_id}: invalid forced-U record")
            validation_status = "forced_u"
        else:
            if not isinstance(response, dict):
                raise ValueError(f"{name}/{review_id}: response missing")
            errors = runner.validate_review(copy.deepcopy(response), packet, validator)
            if errors:
                raise ValueError(f"{name}/{review_id}: current validation failed: {errors}")
            validation_status = "valid"

        source_counts[source_type] += 1
        canonical.append({
            "schema_version": "af-pilot-canonical-model-review-v1",
            "review_id": review_id,
            "work_id": packet["work_id"],
            "provider": spec["provider"],
            "model": spec["model"],
            "evidence_tier": packet.get("evidence_tier"),
            "validation_status": validation_status,
            "source_type": source_type,
            "provenance": provenance,
            "response": response,
        })

    if len(canonical) != 150 or len({row["review_id"] for row in canonical}) != 150:
        raise ValueError(f"{name}: canonical output is not exactly 150 unique records")
    summary = {
        "provider": spec["provider"],
        "model": spec["model"],
        "records": len(canonical),
        "validated": sum(row["validation_status"] == "valid" for row in canonical),
        "forced_u": sum(row["validation_status"] == "forced_u" for row in canonical),
        "source_counts": dict(source_counts),
    }
    return canonical, summary


def compare(
    model_a: list[dict[str, Any]],
    model_b: list[dict[str, Any]],
    packets: dict[str, dict[str, Any]],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
]:
    by_a = unique_by_id(model_a, "model_a.canonical")
    by_b = unique_by_id(model_b, "model_b.canonical")
    field_matches: Counter[str] = Counter()
    fully_core_agree = 0
    action_agree = 0
    exact_decision_action_agree = 0
    rows: list[dict[str, Any]] = []
    model_c_core: list[dict[str, Any]] = []
    model_c_recommended: list[dict[str, Any]] = []
    model_c_expanded: list[dict[str, Any]] = []
    human_review_rows: list[dict[str, Any]] = []
    queue_reason_counts: Counter[str] = Counter()

    for review_id, packet in packets.items():
        a_env, b_env = by_a[review_id], by_b[review_id]
        a, b = a_env["response"], b_env["response"]
        forced_u = a_env["validation_status"] == "forced_u"
        if forced_u != (b_env["validation_status"] == "forced_u"):
            raise ValueError(f"{review_id}: forced-U status differs between models")

        differences: list[str] = []
        for field in DECISION_FIELDS:
            if a.get(field) == b.get(field):
                field_matches[field] += 1
            else:
                differences.append(field)
        core_agree = not differences
        if core_agree:
            fully_core_agree += 1
        a_actions, b_actions = normalized_actions(a), normalized_actions(b)
        if a_actions == b_actions:
            action_agree += 1
        else:
            differences.append("observed_actions")
        if a.get("needs_human_review") != b.get("needs_human_review"):
            differences.append("needs_human_review")
        a_reasons, b_reasons = normalized_reasons(a), normalized_reasons(b)
        if a_reasons != b_reasons:
            differences.append("human_review_reasons")
        if not differences:
            exact_decision_action_agree += 1

        either_human = bool(a.get("needs_human_review") or b.get("needs_human_review"))
        queue_reasons: list[str] = []
        decision_disagreement = any(field in differences for field in DECISION_FIELDS)
        action_disagreement = "observed_actions" in differences
        review_flag_disagreement = any(field in differences for field in REVIEW_FIELDS)
        if not forced_u:
            if decision_disagreement:
                queue_reasons.append("decision_disagreement")
            if action_disagreement:
                queue_reasons.append("action_disagreement")
            if review_flag_disagreement:
                queue_reasons.append("review_flag_disagreement")
            if either_human:
                queue_reasons.append("model_requests_human_review")
        for reason in queue_reasons:
            queue_reason_counts[reason] += 1
        send_to_c_core = not forced_u and decision_disagreement
        send_to_c_recommended = not forced_u and (decision_disagreement or action_disagreement)
        send_to_c_expanded = not forced_u and bool(queue_reasons)
        send_to_human = forced_u or either_human
        if send_to_c_core:
            model_c_core.append(packet)
        if send_to_c_recommended:
            model_c_recommended.append(packet)
        if send_to_c_expanded:
            model_c_expanded.append(packet)

        row = {
            "review_id": review_id,
            "work_id": packet["work_id"],
            "evidence_tier": packet.get("evidence_tier"),
            "forced_u": forced_u,
            "send_to_model_c_core": send_to_c_core,
            "send_to_model_c_recommended": send_to_c_recommended,
            "send_to_model_c_expanded": send_to_c_expanded,
            "send_to_human_review": send_to_human,
            "queue_reasons": "|".join(queue_reasons),
            "differing_fields": "|".join(differences),
            "a_primary_label": a.get("primary_label"),
            "b_primary_label": b.get("primary_label"),
            "a_relevance_level": a.get("relevance_level"),
            "b_relevance_level": b.get("relevance_level"),
            "a_evidence_level": a.get("evidence_level"),
            "b_evidence_level": b.get("evidence_level"),
            "a_af_use_label": a.get("af_use_label"),
            "b_af_use_label": b.get("af_use_label"),
            "a_adoption_eligible": a.get("adoption_eligible"),
            "b_adoption_eligible": b.get("adoption_eligible"),
            "a_actions": "|".join(a_actions),
            "b_actions": "|".join(b_actions),
            "a_needs_human_review": a.get("needs_human_review"),
            "b_needs_human_review": b.get("needs_human_review"),
            "a_human_review_reasons": "|".join(a_reasons),
            "b_human_review_reasons": "|".join(b_reasons),
        }
        rows.append(row)
        if send_to_human:
            human_review_rows.append(row)

    report = {
        "records": len(rows),
        "forced_u": sum(row["forced_u"] for row in rows),
        "model_eligible": sum(not row["forced_u"] for row in rows),
        "field_exact_matches": dict(field_matches),
        "all_decision_fields_exact": fully_core_agree,
        "model_eligible_decision_fields_exact": fully_core_agree - sum(row["forced_u"] for row in rows),
        "observed_actions_exact": action_agree,
        "model_eligible_observed_actions_exact": action_agree - sum(row["forced_u"] for row in rows),
        "decision_actions_and_review_flags_exact": exact_decision_action_agree,
        "model_eligible_decision_actions_and_review_flags_exact": (
            exact_decision_action_agree - sum(row["forced_u"] for row in rows)
        ),
        "model_c_core_records": len(model_c_core),
        "model_c_recommended_records": len(model_c_recommended),
        "model_c_expanded_records": len(model_c_expanded),
        "human_review_queue_records": len(human_review_rows),
        "queue_reason_counts": dict(queue_reason_counts),
        "automatic_agreement_no_review": sum(
            not row["forced_u"]
            and not row["send_to_model_c_expanded"]
            and not row["a_needs_human_review"]
            and not row["b_needs_human_review"]
            for row in rows
        ),
    }
    return report, rows, {
        "core": model_c_core,
        "recommended": model_c_recommended,
        "expanded": model_c_expanded,
    }, human_review_rows


def main() -> int:
    args = parse_args()
    lock_path = args.lock.resolve()
    output_dir = args.output_dir.resolve()
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    input_path = require_locked_file(lock["input"], "input")
    schema_path = require_locked_file(lock["schema"], "schema")
    runner_path = require_locked_file(
        {"path": lock["validator"]["runner_path"], "sha256": lock["validator"]["runner_sha256"]},
        "validator.runner",
    )
    support_path = require_locked_file(
        {"path": lock["validator"]["support_path"], "sha256": lock["validator"]["support_sha256"]},
        "validator.support",
    )
    del runner_path, support_path

    packets_in_order = read_jsonl(input_path)
    packets = unique_by_id(packets_in_order, "input")
    if len(packets_in_order) != int(lock["input"]["records"]):
        raise ValueError("Input count differs from lock")
    runner = load_runner()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)

    canonical: dict[str, list[dict[str, Any]]] = {}
    model_summaries: dict[str, Any] = {}
    canonical_hashes: dict[str, str] = {}
    for name in ("model_a", "model_b"):
        records, summary = build_model(
            name, lock["models"][name], packets_in_order, packets, runner, validator
        )
        path = output_dir / f"{name}_canonical_150.jsonl"
        digest = write_jsonl(path, records)
        canonical[name] = records
        canonical_hashes[name] = digest
        model_summaries[name] = {**summary, "path": str(path), "sha256": digest}

    comparison, queue_rows, model_c_scopes, human_review_rows = compare(
        canonical["model_a"], canonical["model_b"], packets
    )
    queue_path = output_dir / "pilot_150_ab_adjudication_queue.csv"
    queue_fields = list(queue_rows[0]) if queue_rows else []
    queue_sha = write_csv(queue_path, queue_rows, queue_fields)
    human_path = output_dir / "pilot_150_human_review_queue.csv"
    human_sha = write_csv(human_path, human_review_rows, queue_fields)
    model_c_outputs: dict[str, Any] = {}
    for scope, scope_packets in model_c_scopes.items():
        c_input_path = output_dir / f"pilot_150_model_c_{scope}_inputs.jsonl"
        c_input_sha = write_jsonl(c_input_path, scope_packets)
        c_input_meta_path = output_dir / f"pilot_150_model_c_{scope}_inputs.meta.json"
        c_meta = {
            "schema_version": "af-model-c-input-manifest-v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "records": len(scope_packets),
            "input_path": str(c_input_path),
            "input_sha256": c_input_sha,
            "ordered_review_ids": [record["review_id"] for record in scope_packets],
            "ordered_work_id_sha256": sha256_bytes(
                "\n".join(record["work_id"] for record in scope_packets).encode("utf-8")
            ),
            "blinding": "Packets are copied byte-semantically from the blinded Pilot input; A/B decisions and old labels are not included.",
            "selection_policy": lock["model_c_policy"],
        }
        c_meta_sha = write_json(c_input_meta_path, c_meta)
        model_c_outputs[scope] = {
            "records": len(scope_packets),
            "path": str(c_input_path),
            "sha256": c_input_sha,
            "meta_path": str(c_input_meta_path),
            "meta_sha256": c_meta_sha,
        }

    report_path = output_dir / "pilot_150_ab_comparison.json"
    report = {
        "schema_version": "af-pilot-ab-adjudication-report-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "merge_script": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "merge_lock": {"path": str(lock_path), "sha256": sha256_file(lock_path)},
        "input": {"path": str(input_path), "sha256": sha256_file(input_path)},
        "models": model_summaries,
        "comparison": comparison,
        "adjudication_queue": {"path": str(queue_path), "sha256": queue_sha},
        "human_review_queue": {"path": str(human_path), "sha256": human_sha},
        "model_c_inputs": model_c_outputs,
        "interpretation": (
            "A/B agreement is not human-reference accuracy. Model C is an independent third assessment, "
            "not a substitute for the planned human audit or evidence recovery for forced-U records."
        ),
    }
    report_sha = write_json(report_path, report)

    print("Canonical model A:      150/150 (139 validated + 11 forced-U)")
    print("Canonical model B:      150/150 (139 validated + 11 forced-U)")
    print(
        "A/B decision agreement: "
        f"{comparison['model_eligible_decision_fields_exact']}/139 eligible "
        f"({comparison['all_decision_fields_exact']}/150 including forced-U)"
    )
    print(
        "A/B action agreement:   "
        f"{comparison['model_eligible_observed_actions_exact']}/139 eligible "
        f"({comparison['observed_actions_exact']}/150 including forced-U)"
    )
    print(f"Model C core queue:      {comparison['model_c_core_records']}")
    print(f"Model C recommended:     {comparison['model_c_recommended_records']}")
    print(f"Model C expanded:        {comparison['model_c_expanded_records']}")
    print(f"Forced-U human queue:    {comparison['forced_u']}")
    print(f"Total human-review flag: {comparison['human_review_queue_records']}")
    print(f"Automatic no-review:     {comparison['automatic_agreement_no_review']}")
    print(f"Report SHA-256:          {report_sha}")
    print(f"Output directory:        {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
