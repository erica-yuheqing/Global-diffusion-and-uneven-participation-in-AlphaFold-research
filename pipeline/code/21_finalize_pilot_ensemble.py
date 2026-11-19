#!/usr/bin/env python3
"""Freeze and combine the Pilot A/B/C reviews into an auditable machine consensus.

This program does not create a human gold standard. It applies the frozen 2+1
policy, identifies records without a valid majority or with high-risk evidence,
and writes both a minimum operational review queue and the full Pilot double-
annotation queue required by the validation plan.
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
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

CORE_FIELDS = (
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "exclusion_reason",
    "future_or_hypothetical_only",
)
MODEL_ORDER = ("A", "B", "C")
PREFERRED_REPRESENTATIVE_ORDER = ("C", "A", "B")
HIGH_RISK_REVIEW_REASONS = {
    "abstract_only",
    "insufficient_evidence",
    "boundary_R2_R3",
    "boundary_R3_R4",
    "original_vs_downstream",
    "conflicting_evidence",
    "citation_link_uncertain",
    "low_confidence",
    "prediction_origin_unclear",
    "input_quality",
    "other",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=PROJECT_ROOT / "fulltext/pilot/calibration/pilot_150_ensemble_v4_3.lock.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "fulltext/pilot/ensemble_v4_3",
    )
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_fingerprint(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def unique_by_id(
    records: list[dict[str, Any]], label: str, *, key: str = "review_id"
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get(key)
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"{label}: record without {key}")
        if record_id in result:
            raise ValueError(f"{label}: duplicate {key} {record_id}")
        result[record_id] = record
    return result


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
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
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
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


def core_value(response: dict[str, Any]) -> dict[str, Any]:
    return {field: response.get(field) for field in CORE_FIELDS}


def action_value(response: dict[str, Any]) -> list[str]:
    return sorted(str(item) for item in (response.get("observed_actions") or []))


def vote(values: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic two- or three-model exact-value vote."""

    if len(values) not in {2, 3}:
        raise ValueError(f"Expected two or three votes, got {len(values)}")
    groups: dict[str, list[str]] = defaultdict(list)
    decoded: dict[str, Any] = {}
    for model, value in values.items():
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        groups[key].append(model)
        decoded[key] = value
    ordered_groups = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    winning_key, supporters = ordered_groups[0]
    threshold = len(values) // 2 + 1
    resolved = len(supporters) >= threshold
    if resolved:
        status = "unanimous" if len(supporters) == len(values) else "majority"
        winning_value = decoded[winning_key]
    else:
        status = "no_majority"
        winning_value = None
        supporters = []
    return {
        "status": status,
        "resolved": resolved,
        "value": winning_value,
        "supporting_models": sorted(supporters, key=MODEL_ORDER.index),
        "dissenting_models": [model for model in MODEL_ORDER if model in values and model not in supporters],
        "votes": {model: values[model] for model in MODEL_ORDER if model in values},
    }


def route_name(vote_result: dict[str, Any], available_models: list[str]) -> str:
    supporters = set(vote_result["supporting_models"])
    if not vote_result["resolved"]:
        return "no_majority"
    if len(supporters) == len(available_models):
        return "ab_consensus" if available_models == ["A", "B"] else "abc_unanimous"
    mapping = {
        frozenset({"A", "B"}): "ab_majority",
        frozenset({"A", "C"}): "ac_majority",
        frozenset({"B", "C"}): "bc_majority",
    }
    return mapping.get(frozenset(supporters), "resolved")


def choose_representative(core_vote: dict[str, Any], action_vote: dict[str, Any]) -> str | None:
    if not core_vote["resolved"] or not action_vote["resolved"]:
        return None
    common = set(core_vote["supporting_models"]) & set(action_vote["supporting_models"])
    for model in PREFERRED_REPRESENTATIVE_ORDER:
        if model in common:
            return model
    return None


def model_vote_summary(response: dict[str, Any]) -> dict[str, Any]:
    return {
        **core_value(response),
        "observed_actions": action_value(response),
        "needs_human_review": bool(response.get("needs_human_review")),
        "human_review_reasons": sorted(response.get("human_review_reasons") or []),
        "confidence": response.get("confidence"),
        "response_sha256": json_fingerprint(response),
    }


def human_risk_reasons(
    responses: dict[str, dict[str, Any]],
    core_vote: dict[str, Any],
    action_vote: dict[str, Any],
    *,
    forced_u: bool,
) -> list[str]:
    reasons: set[str] = set()
    if forced_u:
        reasons.update({"forced_u", "insufficient_evidence"})
    if not core_vote["resolved"]:
        reasons.add("three_model_core_no_majority")
    if not action_vote["resolved"]:
        reasons.add("three_model_action_no_majority")
    for model, response in responses.items():
        if response.get("primary_label") == "uncertain" or response.get("relevance_level") == "RU":
            reasons.add("any_model_uncertain")
        if response.get("evidence_level") in {"E0", "E1"}:
            reasons.add("any_model_e0_e1")
        if response.get("evidence_level") == "E2" and response.get("af_use_label") == "yes":
            reasons.add("abstract_only_actual_use")
        if response.get("needs_human_review"):
            declared = response.get("human_review_reasons") or ["other"]
            for reason in declared:
                normalized = str(reason)
                if normalized in HIGH_RISK_REVIEW_REASONS:
                    reasons.add(f"model_flag:{normalized}")
                else:
                    reasons.add(f"model_flag:other:{normalized}")
    return sorted(reasons)


def deterministic_score(seed: int, review_id: str) -> str:
    return hashlib.sha256(f"{seed}|{review_id}".encode("utf-8")).hexdigest()


def select_route_stratified_audit(
    rows: list[dict[str, Any]], seed: int, rates: dict[str, float]
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["machine_status"] != "automatic_low_risk":
            continue
        stratum = "ab_consensus" if row["model_c_used"] is False else "abc_majority"
        by_stratum[stratum].append(row)
    for stratum, candidates in sorted(by_stratum.items()):
        rate = rates[stratum]
        sample_n = min(len(candidates), max(1, math.ceil(len(candidates) * rate)))
        ranked = sorted(candidates, key=lambda row: deterministic_score(seed, row["review_id"]))
        probability = sample_n / len(candidates)
        for rank, row in enumerate(ranked, 1):
            selected[row["review_id"]] = {
                "audit_stratum": stratum,
                "audit_rate_target": rate,
                "audit_rank": rank,
                "audit_selected": rank <= sample_n,
                "audit_inclusion_probability": probability,
                "audit_sampling_weight": 1 / probability,
                "audit_score_sha256": deterministic_score(seed, row["review_id"]),
            }
    return selected


def verify_artifact(root: Path, verifier: Any) -> dict[str, Any]:
    manifest_path = root / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing run manifest under {root}")
    verifier.verify_manifest_checksum(manifest_path)
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != "af-model-run-manifest-v1":
        raise ValueError(f"Unsupported artifact schema under {root}")
    if manifest.get("status") not in {"completed", "completed_with_failures"}:
        raise ValueError(f"Artifact {root.name} is not complete")
    source_entries: list[tuple[dict[str, Any], Path]] = []
    verified_files = 0
    for label in ("input", "input_metadata", "prompt", "schema"):
        entry = manifest.get("snapshots", {}).get(label)
        if entry is not None:
            verifier.verify_file(root, entry, f"snapshots.{label}")
            verified_files += 1
    for index, entry in enumerate(manifest.get("snapshots", {}).get("source_and_locks", [])):
        path = verifier.verify_file(root, entry, f"snapshots.source_and_locks[{index}]")
        source_entries.append((entry, path))
        verified_files += 1
    signature = manifest.get("run_signature", {})
    if verifier.protocol_code_hash(source_entries) != signature.get("protocol_code_sha256"):
        raise ValueError(f"Artifact {root.name}: protocol-code hash mismatch")
    archived_records = 0
    for label, entry in manifest.get("archived_records", {}).items():
        path = verifier.verify_file(root, entry, f"archived_records.{label}")
        archived_records += verifier.verify_jsonl(
            path,
            expected_records=entry.get("records"),
            run_id=manifest["run_id"],
            label=label,
        )
        verified_files += 1
    return {
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "verified_files": verified_files,
        "verified_jsonl_records": archived_records,
        "outcome": manifest.get("outcome"),
    }


def validate_c_records(
    c_records: list[dict[str, Any]],
    c_packets: dict[str, dict[str, Any]],
    runner: Any,
    validator: Draft202012Validator,
    transport_lock: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, int]]:
    by_id = unique_by_id(c_records, "model_c.output")
    if set(by_id) != set(c_packets):
        raise ValueError(
            "Model C cohort mismatch; "
            f"missing={sorted(set(c_packets) - set(by_id))}, "
            f"extra={sorted(set(by_id) - set(c_packets))}"
        )
    run_counts: Counter[str] = Counter()
    routed_model_counts: Counter[str] = Counter()
    transport = transport_lock["transport"]
    for review_id, envelope in by_id.items():
        packet = c_packets[review_id]
        if envelope.get("work_id") != packet.get("work_id"):
            raise ValueError(f"Model C/{review_id}: work_id mismatch")
        if envelope.get("provider") != transport["provider"]:
            raise ValueError(f"Model C/{review_id}: provider mismatch")
        if envelope.get("model") != transport["model"]:
            raise ValueError(f"Model C/{review_id}: requested model mismatch")
        signature = envelope.get("run_signature") or {}
        expected_signature = {
            "endpoint": transport["endpoint"],
            "api_style": transport["api_style"],
            "reasoning_effort": transport["reasoning_effort"],
            "response_format": transport["response_format"],
            "thinking": "none",
        }
        for field, expected in expected_signature.items():
            if signature.get(field) != expected:
                raise ValueError(f"Model C/{review_id}: run signature {field} mismatch")
        response = envelope.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"Model C/{review_id}: response missing")
        errors = runner.validate_review(copy.deepcopy(response), packet, validator)
        if errors:
            raise ValueError(f"Model C/{review_id}: current validation failed: {errors}")
        run_id = envelope.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError(f"Model C/{review_id}: run ID missing")
        run_counts[run_id] += 1
        metadata = envelope.get("provider_response_metadata") or {}
        openrouter = metadata.get("openrouter_metadata") or {}
        for endpoint in (openrouter.get("endpoints") or {}).get("available", []):
            if endpoint.get("selected") is True:
                identity = f"{endpoint.get('provider')} / {endpoint.get('model')}"
                routed_model_counts[identity] += 1
    return by_id, dict(run_counts), dict(routed_model_counts)


def compact_vote(vote_result: dict[str, Any], route: str) -> dict[str, Any]:
    return {
        "status": vote_result["status"],
        "route": route,
        "resolved": vote_result["resolved"],
        "value": vote_result["value"],
        "supporting_models": vote_result["supporting_models"],
        "dissenting_models": vote_result["dissenting_models"],
    }


def main() -> int:
    args = parse_args()
    lock_path = args.lock.resolve()
    output_dir = args.output_dir.resolve()
    lock = read_json(lock_path)
    if lock.get("schema_version") != "af-pilot-ensemble-lock-v1":
        raise ValueError("Unsupported Pilot ensemble lock")
    require_locked_file(lock["finalizer"], "finalizer")
    ab_report_path = require_locked_file(lock["ab_report"], "ab_report")
    c_output_path = require_locked_file(lock["model_c"]["output"], "model_c.output")
    c_attempts_path = require_locked_file(lock["model_c"]["attempts"], "model_c.attempts")
    c_errors_path = require_locked_file(lock["model_c"]["historical_errors"], "model_c.errors")
    c_transport_lock_path = require_locked_file(
        lock["model_c"]["transport_lock"], "model_c.transport_lock"
    )
    pilot_path = require_locked_file(lock["pilot"], "pilot")
    input_path = require_locked_file(lock["input"], "input")
    schema_path = require_locked_file(lock["schema"], "schema")
    runner_path = require_locked_file(lock["validator"]["runner"], "validator.runner")
    require_locked_file(lock["validator"]["support"], "validator.support")
    verifier_path = require_locked_file(lock["artifact_verifier"], "artifact_verifier")

    ab_report = read_json(ab_report_path)
    model_a_path = require_locked_file(ab_report["models"]["model_a"], "model_a.canonical")
    model_b_path = require_locked_file(ab_report["models"]["model_b"], "model_b.canonical")
    c_input_entry = ab_report["model_c_inputs"]["recommended"]
    c_input_path = require_locked_file(c_input_entry, "model_c.input")
    c_input_meta_path = require_locked_file(
        {"path": c_input_entry["meta_path"], "sha256": c_input_entry["meta_sha256"]},
        "model_c.input_meta",
    )
    c_input_meta = read_json(c_input_meta_path)

    packets_in_order = read_jsonl(input_path)
    packets = unique_by_id(packets_in_order, "input")
    model_a = unique_by_id(read_jsonl(model_a_path), "model_a.canonical")
    model_b = unique_by_id(read_jsonl(model_b_path), "model_b.canonical")
    c_packets = unique_by_id(read_jsonl(c_input_path), "model_c.input")
    pilot_rows = read_csv(pilot_path)
    pilot_by_work = unique_by_id(pilot_rows, "pilot", key="work_id")
    expected_ids = [row["review_id"] for row in packets_in_order]
    expected_set = set(expected_ids)
    for label, values in (("model_a", model_a), ("model_b", model_b)):
        if set(values) != expected_set:
            raise ValueError(f"{label}: cohort differs from the 150-record input")
    if len(pilot_by_work) != len(expected_ids):
        raise ValueError("Pilot CSV is not exactly 150 unique works")
    if c_input_meta.get("ordered_review_ids") != [row["review_id"] for row in read_jsonl(c_input_path)]:
        raise ValueError("Model C ordered review IDs differ from its metadata")

    runner = load_module(runner_path, "af_model_review_runner_for_ensemble")
    schema = read_json(schema_path)
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    transport_lock = read_json(c_transport_lock_path)
    c_by_id, c_run_counts, routed_model_counts = validate_c_records(
        read_jsonl(c_output_path), c_packets, runner, validator, transport_lock
    )
    if len(c_by_id) != int(lock["model_c"]["output"]["records"]):
        raise ValueError("Model C record count differs from lock")

    verifier = load_module(verifier_path, "af_model_artifact_verifier_for_ensemble")
    artifact_summaries = []
    for entry in lock["model_c"]["artifacts"]:
        manifest_path = require_locked_file(entry, f"artifact.{entry['run_id']}")
        summary = verify_artifact(manifest_path.parent, verifier)
        if summary["run_id"] != entry["run_id"]:
            raise ValueError(f"Artifact run ID differs from lock: {entry['run_id']}")
        artifact_summaries.append(summary)
    if set(c_run_counts) != {entry["run_id"] for entry in lock["model_c"]["artifacts"]}:
        raise ValueError("Model C output run IDs differ from locked artifacts")

    historical_errors = read_jsonl(c_errors_path)
    historical_error_ids = {
        row.get("work_id") for row in historical_errors if isinstance(row.get("work_id"), str)
    }
    resolved_error_ids = historical_error_ids & {row["work_id"] for row in c_by_id.values()}
    unresolved_error_ids = historical_error_ids - resolved_error_ids
    if unresolved_error_ids:
        raise ValueError(f"Unresolved Model C error IDs remain: {sorted(unresolved_error_ids)}")

    ensemble_rows: list[dict[str, Any]] = []
    core_route_counts: Counter[str] = Counter()
    action_route_counts: Counter[str] = Counter()
    human_reason_counts: Counter[str] = Counter()
    pairwise_core_matches: Counter[str] = Counter()
    pairwise_action_matches: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    relevance_counts: Counter[str] = Counter()
    use_counts: Counter[str] = Counter()
    adoption_counts: Counter[str] = Counter()

    for packet in packets_in_order:
        review_id = packet["review_id"]
        work_id = packet["work_id"]
        a_env, b_env = model_a[review_id], model_b[review_id]
        responses = {"A": a_env["response"], "B": b_env["response"]}
        forced_u = a_env.get("validation_status") == "forced_u"
        if forced_u != (b_env.get("validation_status") == "forced_u"):
            raise ValueError(f"{review_id}: A/B forced-U mismatch")
        if review_id in c_by_id:
            responses["C"] = c_by_id[review_id]["response"]
        available_models = [model for model in MODEL_ORDER if model in responses]
        core_vote = vote({model: core_value(response) for model, response in responses.items()})
        action_vote = vote({model: action_value(response) for model, response in responses.items()})
        core_route = route_name(core_vote, available_models)
        action_route = route_name(action_vote, available_models)
        core_route_counts[core_route] += 1
        action_route_counts[action_route] += 1
        representative_model = choose_representative(core_vote, action_vote)
        ensemble_response = (
            copy.deepcopy(responses[representative_model]) if representative_model else None
        )
        risks = human_risk_reasons(
            responses, core_vote, action_vote, forced_u=forced_u
        )
        for reason in risks:
            human_reason_counts[reason] += 1
        if not core_vote["resolved"] or not action_vote["resolved"]:
            machine_status = "unresolved_human_required"
        elif risks:
            machine_status = "provisional_human_required"
        else:
            machine_status = "automatic_low_risk"

        if core_vote["resolved"]:
            decision = core_vote["value"]
            label_counts[str(decision["primary_label"])] += 1
            relevance_counts[str(decision["relevance_level"])] += 1
            use_counts[str(decision["af_use_label"])] += 1
            adoption_counts[str(decision["adoption_eligible"])] += 1
        else:
            decision = None
            label_counts["UNRESOLVED"] += 1
            relevance_counts["UNRESOLVED"] += 1
            use_counts["UNRESOLVED"] += 1
            adoption_counts["UNRESOLVED"] += 1

        for left, right in (("A", "B"), ("A", "C"), ("B", "C")):
            if left in responses and right in responses:
                key = f"{left}-{right}"
                if core_value(responses[left]) == core_value(responses[right]):
                    pairwise_core_matches[key] += 1
                if action_value(responses[left]) == action_value(responses[right]):
                    pairwise_action_matches[key] += 1

        pilot = pilot_by_work[work_id]
        row = {
            "schema_version": "af-pilot-machine-consensus-v1",
            "review_id": review_id,
            "work_id": work_id,
            "pilot_order": int(pilot["pilot_order"]),
            "evidence_tier": packet.get("evidence_tier"),
            "model_c_used": "C" in responses,
            "available_models": available_models,
            "forced_u": forced_u,
            "core_vote": compact_vote(core_vote, core_route),
            "action_vote": compact_vote(action_vote, action_route),
            "representative_model": representative_model,
            "ensemble_response": ensemble_response,
            "machine_status": machine_status,
            "mandatory_human_review": bool(risks),
            "human_review_reasons": risks,
            "model_votes": {
                model: model_vote_summary(response) for model, response in responses.items()
            },
            "model_provenance": {
                "A": {
                    "provider": a_env.get("provider"),
                    "model": a_env.get("model"),
                    "source_type": a_env.get("source_type"),
                    "source_record_sha256": json_fingerprint(a_env),
                },
                "B": {
                    "provider": b_env.get("provider"),
                    "model": b_env.get("model"),
                    "source_type": b_env.get("source_type"),
                    "source_record_sha256": json_fingerprint(b_env),
                },
                **(
                    {
                        "C": {
                            "provider": c_by_id[review_id].get("provider"),
                            "model": c_by_id[review_id].get("model"),
                            "run_id": c_by_id[review_id].get("run_id"),
                            "run_artifact": c_by_id[review_id].get("run_artifact"),
                            "source_record_sha256": json_fingerprint(c_by_id[review_id]),
                        }
                    }
                    if review_id in c_by_id
                    else {}
                ),
            },
            "sampling": {
                "retrieval_sampling_stratum": pilot.get("af_usage_level"),
                "year_band": pilot.get("year_band"),
                "work_type": pilot.get("work_type"),
                "inclusion_probability": float(pilot["inclusion_probability"]),
                "sampling_weight": float(pilot["sampling_weight"]),
                "note": "Development-Pilot diagnostic weight; not a locked-validation weight.",
            },
        }
        ensemble_rows.append(row)

    audit = select_route_stratified_audit(
        ensemble_rows,
        int(lock["audit_policy"]["seed"]),
        {
            "ab_consensus": float(lock["audit_policy"]["ab_consensus_rate"]),
            "abc_majority": float(lock["audit_policy"]["abc_majority_rate"]),
        },
    )
    for row in ensemble_rows:
        row["audit"] = audit.get(
            row["review_id"],
            {
                "audit_stratum": "mandatory_human",
                "audit_rate_target": None,
                "audit_rank": None,
                "audit_selected": False,
                "audit_inclusion_probability": 1.0,
                "audit_sampling_weight": 1.0,
                "audit_score_sha256": None,
            },
        )

    flat_rows: list[dict[str, Any]] = []
    operational_rows: list[dict[str, Any]] = []
    double_annotation_rows: list[dict[str, Any]] = []
    for row in ensemble_rows:
        decision = row["core_vote"]["value"] or {}
        flat = {
            "pilot_order": row["pilot_order"],
            "review_id": row["review_id"],
            "work_id": row["work_id"],
            "evidence_tier": row["evidence_tier"],
            "model_c_used": row["model_c_used"],
            "core_route": row["core_vote"]["route"],
            "action_route": row["action_vote"]["route"],
            "machine_status": row["machine_status"],
            "primary_label": decision.get("primary_label", "UNRESOLVED"),
            "relevance_level": decision.get("relevance_level", "UNRESOLVED"),
            "evidence_level": decision.get("evidence_level", "UNRESOLVED"),
            "af_related_label": decision.get("af_related_label", "UNRESOLVED"),
            "af_use_label": decision.get("af_use_label", "UNRESOLVED"),
            "adoption_eligible": decision.get("adoption_eligible", "UNRESOLVED"),
            "observed_actions": "|".join(row["action_vote"]["value"] or []),
            "representative_model": row["representative_model"] or "",
            "mandatory_human_review": row["mandatory_human_review"],
            "human_review_reasons": "|".join(row["human_review_reasons"]),
            "audit_stratum": row["audit"]["audit_stratum"],
            "audit_selected": row["audit"]["audit_selected"],
            "audit_inclusion_probability": row["audit"]["audit_inclusion_probability"],
            "audit_sampling_weight": row["audit"]["audit_sampling_weight"],
            "retrieval_sampling_stratum": row["sampling"]["retrieval_sampling_stratum"],
            "year_band": row["sampling"]["year_band"],
            "pilot_sampling_weight": row["sampling"]["sampling_weight"],
        }
        flat_rows.append(flat)
        if row["mandatory_human_review"] or row["audit"]["audit_selected"]:
            operational_rows.append(
                {
                    **flat,
                    "queue_reason": (
                        "mandatory_human_review"
                        if row["mandatory_human_review"]
                        else "route_stratified_random_audit"
                    ),
                    "reviewer_id": "",
                    "reviewed_at": "",
                    "human_primary_label": "",
                    "human_relevance_level": "",
                    "human_evidence_level": "",
                    "human_af_related_label": "",
                    "human_af_use_label": "",
                    "human_adoption_eligible": "",
                    "human_observed_actions": "",
                    "human_evidence_quotes_valid": "",
                    "human_review_status": "pending",
                    "human_notes": "",
                }
            )
        double_annotation_rows.append(
            {
                **flat,
                "annotation_priority": (
                    "P0_mandatory"
                    if row["mandatory_human_review"]
                    else "P1_random_audit"
                    if row["audit"]["audit_selected"]
                    else "P2_remaining_pilot"
                ),
                "annotator_1_id": "",
                "annotator_1_primary_label": "",
                "annotator_1_relevance_level": "",
                "annotator_1_evidence_level": "",
                "annotator_1_af_related_label": "",
                "annotator_1_af_use_label": "",
                "annotator_1_adoption_eligible": "",
                "annotator_1_observed_actions": "",
                "annotator_1_evidence_quotes_valid": "",
                "annotator_1_notes": "",
                "annotator_2_id": "",
                "annotator_2_primary_label": "",
                "annotator_2_relevance_level": "",
                "annotator_2_evidence_level": "",
                "annotator_2_af_related_label": "",
                "annotator_2_af_use_label": "",
                "annotator_2_adoption_eligible": "",
                "annotator_2_observed_actions": "",
                "annotator_2_evidence_quotes_valid": "",
                "annotator_2_notes": "",
                "adjudicator_id": "",
                "adjudicated_primary_label": "",
                "adjudicated_relevance_level": "",
                "adjudicated_evidence_level": "",
                "adjudicated_af_related_label": "",
                "adjudicated_af_use_label": "",
                "adjudicated_adoption_eligible": "",
                "adjudicated_observed_actions": "",
                "adjudicated_evidence_quotes_valid": "",
                "adjudication_notes": "",
                "human_annotation_status": "pending",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    ensemble_path = output_dir / "pilot_150_machine_consensus_v4_3.jsonl"
    flat_path = output_dir / "pilot_150_machine_consensus_v4_3.csv"
    operational_path = output_dir / "pilot_150_operational_human_queue_v4_3.csv"
    double_path = output_dir / "pilot_150_double_annotation_queue_v4_3.csv"
    ensemble_sha = write_jsonl(ensemble_path, ensemble_rows)
    flat_sha = write_csv(flat_path, flat_rows, list(flat_rows[0]))
    operational_sha = write_csv(
        operational_path,
        operational_rows,
        list(operational_rows[0]) if operational_rows else list(flat_rows[0]) + ["queue_reason"],
    )
    double_sha = write_csv(double_path, double_annotation_rows, list(double_annotation_rows[0]))

    machine_status_counts = Counter(row["machine_status"] for row in ensemble_rows)
    audit_selected_counts = Counter(
        row["audit"]["audit_stratum"]
        for row in ensemble_rows
        if row["audit"]["audit_selected"]
    )
    c_records_n = len(c_by_id)
    report = {
        "schema_version": "af-pilot-machine-consensus-report-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": (
            "This is a frozen 2+1 machine-consensus result, not human-reference accuracy and not "
            "an independently double-annotated gold standard. Records marked human-required remain "
            "provisional or unresolved. The full 150-record double-annotation queue is retained."
        ),
        "policy": lock["ensemble_policy"],
        "sources": {
            "lock": {"path": str(lock_path), "sha256": sha256_file(lock_path)},
            "finalizer": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
            "ab_report": {"path": str(ab_report_path), "sha256": sha256_file(ab_report_path)},
            "model_a": {"path": str(model_a_path), "sha256": sha256_file(model_a_path)},
            "model_b": {"path": str(model_b_path), "sha256": sha256_file(model_b_path)},
            "model_c": {"path": str(c_output_path), "sha256": sha256_file(c_output_path)},
            "model_c_attempts": {"path": str(c_attempts_path), "sha256": sha256_file(c_attempts_path)},
            "model_c_historical_errors": {"path": str(c_errors_path), "sha256": sha256_file(c_errors_path)},
            "pilot": {"path": str(pilot_path), "sha256": sha256_file(pilot_path)},
            "input": {"path": str(input_path), "sha256": sha256_file(input_path)},
        },
        "cohort": {
            "records": len(ensemble_rows),
            "model_eligible": sum(not row["forced_u"] for row in ensemble_rows),
            "forced_u": sum(row["forced_u"] for row in ensemble_rows),
            "model_c_records": c_records_n,
            "model_c_unique_records": len(c_by_id),
        },
        "model_c_provenance": {
            "records_by_run_id": c_run_counts,
            "selected_upstream_routes": routed_model_counts,
            "artifacts": artifact_summaries,
            "historical_error_records": len(historical_errors),
            "historical_error_work_ids": sorted(historical_error_ids),
            "resolved_historical_error_work_ids": sorted(resolved_error_ids),
            "unresolved_error_work_ids": sorted(unresolved_error_ids),
        },
        "agreement": {
            "core_routes": dict(core_route_counts),
            "action_routes": dict(action_route_counts),
            "pairwise_core_exact": {
                "A-B": {"matches": pairwise_core_matches["A-B"], "denominator": 150},
                "A-C": {"matches": pairwise_core_matches["A-C"], "denominator": c_records_n},
                "B-C": {"matches": pairwise_core_matches["B-C"], "denominator": c_records_n},
            },
            "pairwise_action_exact": {
                "A-B": {"matches": pairwise_action_matches["A-B"], "denominator": 150},
                "A-C": {"matches": pairwise_action_matches["A-C"], "denominator": c_records_n},
                "B-C": {"matches": pairwise_action_matches["B-C"], "denominator": c_records_n},
            },
        },
        "machine_consensus": {
            "status_counts": dict(machine_status_counts),
            "core_unresolved": sum(not row["core_vote"]["resolved"] for row in ensemble_rows),
            "actions_unresolved": sum(not row["action_vote"]["resolved"] for row in ensemble_rows),
            "mandatory_human_review": sum(row["mandatory_human_review"] for row in ensemble_rows),
            "human_reason_counts": dict(human_reason_counts),
            "primary_label_counts": dict(label_counts),
            "relevance_level_counts": dict(relevance_counts),
            "af_use_label_counts": dict(use_counts),
            "adoption_eligible_counts": dict(adoption_counts),
        },
        "human_review": {
            "operational_queue_records": len(operational_rows),
            "mandatory_records": sum(row["mandatory_human_review"] for row in ensemble_rows),
            "random_audit_records": sum(
                row["audit"]["audit_selected"] for row in ensemble_rows
            ),
            "random_audit_selected_by_stratum": dict(audit_selected_counts),
            "full_pilot_double_annotation_records": len(double_annotation_rows),
            "audit_policy": lock["audit_policy"],
        },
        "outputs": {
            "machine_consensus_jsonl": {"path": str(ensemble_path), "sha256": ensemble_sha},
            "machine_consensus_csv": {"path": str(flat_path), "sha256": flat_sha},
            "operational_human_queue": {"path": str(operational_path), "sha256": operational_sha},
            "double_annotation_queue": {"path": str(double_path), "sha256": double_sha},
        },
    }
    report_path = output_dir / "pilot_150_machine_consensus_report_v4_3.json"
    report_sha = write_json(report_path, report)

    print(f"Pilot records:                 {len(ensemble_rows)}")
    print(f"Model C validated:             {len(c_by_id)}/{len(c_packets)}")
    print(f"Core vote unresolved:          {report['machine_consensus']['core_unresolved']}")
    print(f"Action vote unresolved:        {report['machine_consensus']['actions_unresolved']}")
    print(f"Automatic low-risk:            {machine_status_counts['automatic_low_risk']}")
    print(f"Provisional human-required:    {machine_status_counts['provisional_human_required']}")
    print(f"Unresolved human-required:     {machine_status_counts['unresolved_human_required']}")
    print(f"Operational human queue:       {len(operational_rows)}")
    print(f"Full double-annotation queue:  {len(double_annotation_rows)}")
    print(f"Unresolved Model C errors:     {len(unresolved_error_ids)}")
    print(f"Report SHA-256:                {report_sha}")
    print(f"Output directory:              {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
