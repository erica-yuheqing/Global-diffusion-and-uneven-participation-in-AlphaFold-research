#!/usr/bin/env python3
"""Freeze and finalize the v6 Pilot 2+1 machine ensemble.

This combines the locked v6 A/B canonical reviews with 58 revalidated Model C
responses and 10 fresh v6 Model C responses.  It never calls a model API and
does not modify historical human-annotation workbooks.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
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

DEFAULT_LOCK = PROJECT_ROOT / "fulltext/pilot/calibration/pilot_150_ensemble_v6.lock.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "fulltext/pilot/ensemble_v6"
PATHS = {
    "ab_report": "fulltext/pilot/adjudication_v6/pilot_150_ab_comparison_v6.json",
    "model_a": "fulltext/pilot/adjudication_v6/model_a_canonical_150_v6.jsonl",
    "model_b": "fulltext/pilot/adjudication_v6/model_b_canonical_150_v6.jsonl",
    "c_input": "fulltext/pilot/adjudication_v6/pilot_150_model_c_recommended_inputs_v6.jsonl",
    "c_input_meta": "fulltext/pilot/adjudication_v6/pilot_150_model_c_recommended_inputs_v6.meta.json",
    "c_reused": "fulltext/pilot/model_c_transition_v6/model_c_reused_unchanged_v6.jsonl",
    "c_transition": "fulltext/pilot/model_c_transition_v6/model_c_transition_manifest_v6.json",
    "c_delta": "fulltext/pilot/model_outputs_v6_delta/model_c_delta10_openrouter_xhigh_v6.jsonl",
    "c_delta_attempts": "fulltext/pilot/model_outputs_v6_delta/model_c_delta10_openrouter_xhigh_v6.attempts.jsonl",
    "c_delta_errors": "fulltext/pilot/model_outputs_v6_delta/model_c_delta10_openrouter_xhigh_v6.errors.jsonl",
    "pilot": "fulltext/pilot/pilot_150.csv",
    "input": "fulltext/pilot/model_inputs_v6/pilot_model_inputs.jsonl",
    "schema": "config/af_review_output_schema_v2.json",
    "runner": "code/08_run_model_review.py",
    "support": "code/fulltext_pipeline/model_review_support.py",
    "helper": "code/21_finalize_pilot_ensemble.py",
    "verifier": "code/10_verify_model_run_artifact.py",
}
TRANSPORT = {
    "provider": "openrouter",
    "model": "openai/gpt-5.6-luna",
    "endpoint": "https://openrouter.ai/api/v1/responses",
    "api_style": "responses",
    "reasoning_effort": "xhigh",
    "response_format": "json_schema",
    "thinking": "none",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--create-lock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(encoded.encode("utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            records.append(value)
    return records


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    return value


def unique(records: list[dict[str, Any]], label: str, key: str = "review_id") -> dict[str, dict[str, Any]]:
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
    checksum_tmp = checksum_path.with_suffix(checksum_path.suffix + ".part")
    checksum_tmp.write_bytes(f"{digest}  {path.name}\n".encode("ascii"))
    checksum_tmp.replace(checksum_path)
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    data = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    ).encode("utf-8")
    return atomic_write(path, data)


def locked_file(path_value: str | Path, records: bool = False) -> dict[str, Any]:
    path = resolve(path_value)
    if not path.is_file():
        raise ValueError(f"Missing required file: {path}")
    entry: dict[str, Any] = {"path": relative(path), "sha256": sha256_file(path)}
    if records:
        entry["records"] = len(read_jsonl(path))
    return entry


def require_locked(entry: dict[str, Any], label: str) -> Path:
    path = resolve(entry["path"])
    if not path.is_file():
        raise ValueError(f"{label}: missing file {path}")
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        raise ValueError(f"{label}: SHA-256 mismatch; expected {entry['sha256']}, got {actual}")
    return path


def artifact_root(source_path: Path, artifact_value: str) -> Path:
    artifact = Path(artifact_value)
    return artifact.resolve() if artifact.is_absolute() else (source_path.parent / artifact).resolve()


def collect_artifacts(reused_path: Path, delta_path: Path) -> list[dict[str, Any]]:
    refs: dict[str, tuple[Path, str]] = {}
    for record in read_jsonl(reused_path):
        provenance = record.get("provenance") or {}
        source_path = resolve(provenance.get("source_path", ""))
        artifact_value = provenance.get("source_artifact")
        run_id = provenance.get("source_run_id")
        if not isinstance(artifact_value, str) or not isinstance(run_id, str):
            raise ValueError(f"Reused C record lacks artifact provenance: {record.get('work_id')}")
        refs[run_id] = (artifact_root(source_path, artifact_value), run_id)
    for record in read_jsonl(delta_path):
        artifact_value = record.get("run_artifact")
        run_id = record.get("run_id")
        if not isinstance(artifact_value, str) or not isinstance(run_id, str):
            raise ValueError(f"Delta C record lacks artifact provenance: {record.get('work_id')}")
        refs[run_id] = (artifact_root(delta_path, artifact_value), run_id)
    entries: list[dict[str, Any]] = []
    for root, run_id in sorted(refs.values(), key=lambda item: item[1]):
        manifest = root / "run_manifest.json"
        if not manifest.is_file():
            raise ValueError(f"Missing artifact run manifest: {manifest}")
        value = read_json(manifest)
        if value.get("run_id") != run_id:
            raise ValueError(f"Artifact run ID mismatch: {manifest}")
        entries.append({
            "run_id": run_id,
            "root": relative(root),
            "manifest_path": relative(manifest),
            "manifest_sha256": sha256_file(manifest),
        })
    return entries


def create_lock(lock_path: Path) -> dict[str, Any]:
    sources = {name: locked_file(path, name in {
        "model_a", "model_b", "c_input", "c_reused", "c_delta",
        "c_delta_attempts", "c_delta_errors", "input",
    }) for name, path in PATHS.items()}
    artifacts = collect_artifacts(resolve(PATHS["c_reused"]), resolve(PATHS["c_delta"]))
    lock = {
        "schema_version": "af-pilot-ensemble-lock-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected": {
            "pilot_records": 150,
            "model_eligible": 142,
            "forced_u": 8,
            "model_c_records": 68,
            "model_c_reused": 58,
            "model_c_delta": 10,
        },
        "sources": sources,
        "model_c_transport": TRANSPORT,
        "model_c_artifacts": artifacts,
        "finalizer": locked_file(Path(__file__).resolve()),
        "ensemble_policy": {
            "name": "2+1 exact-majority Pilot machine consensus v6",
            "model_c_scope": "recommended: any A/B core-decision or observed-action disagreement; forced-U excluded",
            "core_vote_unit": [
                "primary_label", "relevance_level", "evidence_level", "af_related_label",
                "af_use_label", "adoption_eligible", "exclusion_reason", "future_or_hypothetical_only",
            ],
            "action_vote_unit": "exact normalized observed_actions set",
            "majority_rule": "A/B consensus when C was not selected; otherwise exact 2-of-3 or 3-of-3 values are required independently for core and actions.",
            "representative_rule": "Use a valid response common to both winning coalitions, preferring C then A then B; never synthesize evidence across models.",
            "mandatory_human_rule": "Require human review for no-majority core/actions, any U/RU or E0/E1, abstract-only actual use, model-declared review reasons, or forced-U.",
            "interpretation": "Machine agreement is not human-reference accuracy; human-required records remain provisional or unresolved.",
        },
        "audit_policy": {
            "seed": 20260907,
            "method": "Deterministic SHA-256 ranking within ensemble-route strata; sample size is ceiling(N*rate).",
            "ab_consensus_rate": 0.05,
            "abc_majority_rate": 0.15,
            "pilot_requirement": "Retain all 150 records in a separate double-annotation queue.",
        },
    }
    write_json(lock_path, lock)
    return lock


def expected_transport(signature: dict[str, Any], transport: dict[str, Any], label: str) -> None:
    for field in ("endpoint", "api_style", "reasoning_effort", "response_format", "thinking"):
        if signature.get(field) != transport[field]:
            raise ValueError(f"{label}: Model C run signature {field} mismatch")


def build_model_c(
    c_packets_in_order: list[dict[str, Any]],
    reused_records: list[dict[str, Any]],
    delta_records: list[dict[str, Any]],
    reused_path: Path,
    delta_path: Path,
    runner: Any,
    validator: Draft202012Validator,
    transport: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    reused = unique(reused_records, "model_c.reused")
    delta = unique(delta_records, "model_c.delta")
    c_packet_ids = {row["review_id"] for row in c_packets_in_order}
    if set(reused) & set(delta) or set(reused) | set(delta) != c_packet_ids:
        raise ValueError("Reused and delta Model C cohorts do not form the exact v6 C queue")
    reused_file_sha = sha256_file(reused_path)
    delta_file_sha = sha256_file(delta_path)
    result: list[dict[str, Any]] = []
    run_counts: Counter[str] = Counter()
    for packet_raw in c_packets_in_order:
        packet = runner.prepare_packet(packet_raw)
        review_id = packet["review_id"]
        packet_sha = fingerprint(packet)
        if review_id in reused:
            source = reused[review_id]
            response = source.get("response")
            provenance = copy.deepcopy(source.get("provenance") or {})
            run_id = provenance.get("source_run_id")
            signature = provenance.get("source_run_signature") or {}
            source_type = "historical_v4_3_response_unchanged_v6_packet"
            source_record_sha = fingerprint(source)
            source_path, source_sha = reused_path, reused_file_sha
        else:
            source = delta[review_id]
            response = source.get("response")
            run_id = source.get("run_id")
            signature = source.get("run_signature") or {}
            source_type = "fresh_v6_delta_api_review"
            source_record_sha = fingerprint(source)
            source_path, source_sha = delta_path, delta_file_sha
            provenance = {
                "source_run_id": run_id,
                "source_artifact": source.get("run_artifact"),
                "source_run_signature": signature,
            }
        if source.get("work_id") != packet["work_id"]:
            raise ValueError(f"Model C/{review_id}: work_id mismatch")
        if source.get("input_packet_sha256") != packet_sha:
            raise ValueError(f"Model C/{review_id}: input fingerprint mismatch")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError(f"Model C/{review_id}: run ID missing")
        expected_transport(signature, transport, f"Model C/{review_id}")
        if not isinstance(response, dict):
            raise ValueError(f"Model C/{review_id}: response missing")
        errors = runner.validate_review(copy.deepcopy(response), packet, validator)
        if errors:
            raise ValueError(f"Model C/{review_id}: current validation failed: {errors}")
        run_counts[run_id] += 1
        result.append({
            "schema_version": "af-pilot-canonical-model-review-v2",
            "review_id": review_id,
            "work_id": packet["work_id"],
            "provider": transport["provider"],
            "model": transport["model"],
            "evidence_tier": packet.get("evidence_tier"),
            "input_packet_sha256": packet_sha,
            "validation_status": "valid",
            "source_type": source_type,
            "provenance": {
                **provenance,
                "source_path": str(source_path),
                "source_file_sha256": source_sha,
                "source_record_sha256": source_record_sha,
            },
            "response": response,
        })
    return result, run_counts


def main() -> int:
    args = parse_args()
    lock_path = resolve(args.lock)
    output_dir = resolve(args.output_dir)
    if args.create_lock:
        lock = create_lock(lock_path)
        print(f"Lock written:             {lock_path}")
        print(f"Lock SHA-256:            {sha256_file(lock_path)}")
        print(f"Model C artifacts:      {len(lock['model_c_artifacts'])}")
        print("No model requests were made.")
        return 0

    lock = read_json(lock_path)
    if lock.get("schema_version") != "af-pilot-ensemble-lock-v2":
        raise ValueError("Unsupported Pilot v6 ensemble lock")
    require_locked(lock["finalizer"], "finalizer")
    paths = {name: require_locked(entry, f"source.{name}") for name, entry in lock["sources"].items()}
    helper = load_module(paths["helper"], "af_ensemble_helper_v6")
    runner = load_module(paths["runner"], "af_review_runner_ensemble_v6")
    verifier = load_module(paths["verifier"], "af_artifact_verifier_ensemble_v6")
    schema = read_json(paths["schema"])
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)

    input_records = [runner.prepare_packet(row) for row in read_jsonl(paths["input"])]
    packets = unique(input_records, "input")
    model_a = unique(read_jsonl(paths["model_a"]), "model_a")
    model_b = unique(read_jsonl(paths["model_b"]), "model_b")
    c_packets_in_order = read_jsonl(paths["c_input"])
    c_packets = unique(c_packets_in_order, "model_c.input")
    pilot_rows = helper.read_csv(paths["pilot"])
    pilot_by_work = helper.unique_by_id(pilot_rows, "pilot", key="work_id")
    expected = lock["expected"]
    expected_ids = set(packets)
    if len(input_records) != expected["pilot_records"] or set(model_a) != expected_ids or set(model_b) != expected_ids:
        raise ValueError("A/B/input cohorts are not the exact 150-record Pilot")
    if len(pilot_by_work) != expected["pilot_records"] or len(c_packets) != expected["model_c_records"]:
        raise ValueError("Pilot or Model C cohort count differs from lock")
    meta = read_json(paths["c_input_meta"])
    if meta.get("input_sha256") != sha256_file(paths["c_input"]):
        raise ValueError("Model C input hash differs from metadata")
    if meta.get("ordered_review_ids") != [row["review_id"] for row in c_packets_in_order]:
        raise ValueError("Model C ordered review IDs differ from metadata")

    reused_records = read_jsonl(paths["c_reused"])
    delta_records = read_jsonl(paths["c_delta"])
    if len(reused_records) != expected["model_c_reused"] or len(delta_records) != expected["model_c_delta"]:
        raise ValueError("Model C reuse/delta counts differ from lock")
    model_c_records, c_run_counts = build_model_c(
        c_packets_in_order, reused_records, delta_records, paths["c_reused"], paths["c_delta"],
        runner, validator, lock["model_c_transport"],
    )
    model_c = unique(model_c_records, "model_c.canonical")

    artifact_summaries: list[dict[str, Any]] = []
    for entry in lock["model_c_artifacts"]:
        manifest_path = require_locked(
            {"path": entry["manifest_path"], "sha256": entry["manifest_sha256"]},
            f"artifact.{entry['run_id']}",
        )
        summary = helper.verify_artifact(manifest_path.parent, verifier)
        if summary["run_id"] != entry["run_id"]:
            raise ValueError(f"Artifact run ID differs from lock: {entry['run_id']}")
        artifact_summaries.append(summary)
    if set(c_run_counts) != {entry["run_id"] for entry in lock["model_c_artifacts"]}:
        raise ValueError("Canonical Model C run IDs differ from locked artifacts")
    historical_errors = read_jsonl(paths["c_delta_errors"])
    unresolved_error_ids = {
        row["work_id"] for row in historical_errors if row.get("work_id")
    } - {row["work_id"] for row in delta_records}
    if unresolved_error_ids:
        raise ValueError(f"Unresolved v6 Model C errors remain: {sorted(unresolved_error_ids)}")

    ensemble_rows: list[dict[str, Any]] = []
    core_routes: Counter[str] = Counter()
    action_routes: Counter[str] = Counter()
    human_reasons: Counter[str] = Counter()
    pair_core: Counter[str] = Counter()
    pair_actions: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    relevance_counts: Counter[str] = Counter()
    use_counts: Counter[str] = Counter()
    adoption_counts: Counter[str] = Counter()
    for packet in input_records:
        rid, wid = packet["review_id"], packet["work_id"]
        a_env, b_env = model_a[rid], model_b[rid]
        responses = {"A": a_env["response"], "B": b_env["response"]}
        forced_u = a_env.get("validation_status") == "forced_u"
        if forced_u != (b_env.get("validation_status") == "forced_u"):
            raise ValueError(f"{rid}: A/B forced-U mismatch")
        if rid in model_c:
            responses["C"] = model_c[rid]["response"]
        available = [model for model in helper.MODEL_ORDER if model in responses]
        core_vote = helper.vote({model: helper.core_value(response) for model, response in responses.items()})
        action_vote = helper.vote({model: helper.action_value(response) for model, response in responses.items()})
        core_route = helper.route_name(core_vote, available)
        action_route = helper.route_name(action_vote, available)
        core_routes[core_route] += 1
        action_routes[action_route] += 1
        representative = helper.choose_representative(core_vote, action_vote)
        risks = helper.human_risk_reasons(responses, core_vote, action_vote, forced_u=forced_u)
        human_reasons.update(risks)
        if not core_vote["resolved"] or not action_vote["resolved"]:
            status = "unresolved_human_required"
        elif risks:
            status = "provisional_human_required"
        else:
            status = "automatic_low_risk"
        decision = core_vote["value"] or {}
        if core_vote["resolved"]:
            label_counts[str(decision["primary_label"])] += 1
            relevance_counts[str(decision["relevance_level"])] += 1
            use_counts[str(decision["af_use_label"])] += 1
            adoption_counts[str(decision["adoption_eligible"])] += 1
        else:
            for counter in (label_counts, relevance_counts, use_counts, adoption_counts):
                counter["UNRESOLVED"] += 1
        for left, right in (("A", "B"), ("A", "C"), ("B", "C")):
            if left in responses and right in responses:
                key = f"{left}-{right}"
                pair_core[key] += helper.core_value(responses[left]) == helper.core_value(responses[right])
                pair_actions[key] += helper.action_value(responses[left]) == helper.action_value(responses[right])
        pilot = pilot_by_work[wid]
        c_env = model_c.get(rid)
        ensemble_rows.append({
            "schema_version": "af-pilot-machine-consensus-v2",
            "review_id": rid,
            "work_id": wid,
            "pilot_order": int(pilot["pilot_order"]),
            "evidence_tier": packet.get("evidence_tier"),
            "model_c_used": c_env is not None,
            "available_models": available,
            "forced_u": forced_u,
            "core_vote": helper.compact_vote(core_vote, core_route),
            "action_vote": helper.compact_vote(action_vote, action_route),
            "representative_model": representative,
            "ensemble_response": copy.deepcopy(responses[representative]) if representative else None,
            "machine_status": status,
            "mandatory_human_review": bool(risks),
            "human_review_reasons": risks,
            "model_votes": {model: helper.model_vote_summary(response) for model, response in responses.items()},
            "model_provenance": {
                "A": {"provider": a_env.get("provider"), "model": a_env.get("model"), "source_type": a_env.get("source_type"), "source_record_sha256": fingerprint(a_env)},
                "B": {"provider": b_env.get("provider"), "model": b_env.get("model"), "source_type": b_env.get("source_type"), "source_record_sha256": fingerprint(b_env)},
                **({"C": {"provider": c_env.get("provider"), "model": c_env.get("model"), "source_type": c_env.get("source_type"), "source_run_id": c_env.get("provenance", {}).get("source_run_id"), "source_artifact": c_env.get("provenance", {}).get("source_artifact"), "source_record_sha256": fingerprint(c_env)}} if c_env else {}),
            },
            "sampling": {
                "retrieval_sampling_stratum": pilot.get("af_usage_level"),
                "year_band": pilot.get("year_band"),
                "work_type": pilot.get("work_type"),
                "inclusion_probability": float(pilot["inclusion_probability"]),
                "sampling_weight": float(pilot["sampling_weight"]),
                "note": "Development-Pilot diagnostic weight; not a locked-validation weight.",
            },
        })

    audit = helper.select_route_stratified_audit(
        ensemble_rows,
        int(lock["audit_policy"]["seed"]),
        {"ab_consensus": float(lock["audit_policy"]["ab_consensus_rate"]), "abc_majority": float(lock["audit_policy"]["abc_majority_rate"])},
    )
    for row in ensemble_rows:
        row["audit"] = audit.get(row["review_id"], {
            "audit_stratum": "mandatory_human", "audit_rate_target": None,
            "audit_rank": None, "audit_selected": False,
            "audit_inclusion_probability": 1.0, "audit_sampling_weight": 1.0,
            "audit_score_sha256": None,
        })

    flat_rows: list[dict[str, Any]] = []
    operational_rows: list[dict[str, Any]] = []
    double_rows: list[dict[str, Any]] = []
    for row in ensemble_rows:
        decision = row["core_vote"]["value"] or {}
        flat = {
            "pilot_order": row["pilot_order"], "review_id": row["review_id"], "work_id": row["work_id"],
            "evidence_tier": row["evidence_tier"], "model_c_used": row["model_c_used"],
            "core_route": row["core_vote"]["route"], "action_route": row["action_vote"]["route"],
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
            "audit_stratum": row["audit"]["audit_stratum"], "audit_selected": row["audit"]["audit_selected"],
            "audit_inclusion_probability": row["audit"]["audit_inclusion_probability"],
            "audit_sampling_weight": row["audit"]["audit_sampling_weight"],
            "retrieval_sampling_stratum": row["sampling"]["retrieval_sampling_stratum"],
            "year_band": row["sampling"]["year_band"], "pilot_sampling_weight": row["sampling"]["sampling_weight"],
        }
        flat_rows.append(flat)
        if row["mandatory_human_review"] or row["audit"]["audit_selected"]:
            operational_rows.append({**flat, "queue_reason": "mandatory_human_review" if row["mandatory_human_review"] else "route_stratified_random_audit", "reviewer_id": "", "reviewed_at": "", "human_primary_label": "", "human_relevance_level": "", "human_evidence_level": "", "human_af_related_label": "", "human_af_use_label": "", "human_adoption_eligible": "", "human_observed_actions": "", "human_evidence_quotes_valid": "", "human_review_status": "pending", "human_notes": ""})
        double_rows.append({**flat, "annotation_priority": "P0_mandatory" if row["mandatory_human_review"] else "P1_random_audit" if row["audit"]["audit_selected"] else "P2_remaining_pilot", **{key: "" for key in ("annotator_1_id", "annotator_1_primary_label", "annotator_1_relevance_level", "annotator_1_evidence_level", "annotator_1_af_related_label", "annotator_1_af_use_label", "annotator_1_adoption_eligible", "annotator_1_observed_actions", "annotator_1_evidence_quotes_valid", "annotator_1_notes", "annotator_2_id", "annotator_2_primary_label", "annotator_2_relevance_level", "annotator_2_evidence_level", "annotator_2_af_related_label", "annotator_2_af_use_label", "annotator_2_adoption_eligible", "annotator_2_observed_actions", "annotator_2_evidence_quotes_valid", "annotator_2_notes", "adjudicator_id", "adjudicated_primary_label", "adjudicated_relevance_level", "adjudicated_evidence_level", "adjudicated_af_related_label", "adjudicated_af_use_label", "adjudicated_adoption_eligible", "adjudicated_observed_actions", "adjudicated_evidence_quotes_valid", "adjudication_notes")}, "human_annotation_status": "pending"})

    status_counts = Counter(row["machine_status"] for row in ensemble_rows)
    print(f"Pilot records:           {len(ensemble_rows)}")
    print(f"Model C canonical:       {len(model_c_records)} ({len(reused_records)} reused + {len(delta_records)} fresh)")
    print(f"Machine status:          {dict(status_counts)}")
    print(f"Core unresolved:         {sum(not row['core_vote']['resolved'] for row in ensemble_rows)}")
    print(f"Actions unresolved:      {sum(not row['action_vote']['resolved'] for row in ensemble_rows)}")
    print(f"Mandatory human review: {sum(row['mandatory_human_review'] for row in ensemble_rows)}")
    print(f"Operational queue:       {len(operational_rows)}")
    if args.dry_run:
        print("Dry run: no ensemble outputs were written.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    c_path = output_dir / "model_c_canonical_68_v6.jsonl"
    ensemble_path = output_dir / "pilot_150_machine_consensus_v6.jsonl"
    flat_path = output_dir / "pilot_150_machine_consensus_v6.csv"
    operational_path = output_dir / "pilot_150_operational_human_queue_v6.csv"
    double_path = output_dir / "pilot_150_double_annotation_queue_v6.csv"
    c_sha = write_jsonl(c_path, model_c_records)
    ensemble_sha = write_jsonl(ensemble_path, ensemble_rows)
    flat_sha = helper.write_csv(flat_path, flat_rows, list(flat_rows[0]))
    operational_sha = helper.write_csv(operational_path, operational_rows, list(operational_rows[0]))
    double_sha = helper.write_csv(double_path, double_rows, list(double_rows[0]))
    report_path = output_dir / "pilot_150_machine_consensus_report_v6.json"
    report = {
        "schema_version": "af-pilot-machine-consensus-report-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": "Frozen 2+1 machine consensus, not human-reference accuracy or an independently double-annotated gold standard.",
        "policy": lock["ensemble_policy"],
        "sources": {"lock": {"path": str(lock_path), "sha256": sha256_file(lock_path)}, **{name: {"path": str(path), "sha256": sha256_file(path)} for name, path in paths.items()}},
        "cohort": {"records": len(ensemble_rows), "model_eligible": sum(not row["forced_u"] for row in ensemble_rows), "forced_u": sum(row["forced_u"] for row in ensemble_rows), "model_c_records": len(model_c_records), "model_c_reused": len(reused_records), "model_c_fresh": len(delta_records)},
        "model_c_provenance": {"records_by_run_id": dict(c_run_counts), "artifacts": artifact_summaries, "historical_delta_errors": len(historical_errors), "unresolved_delta_errors": sorted(unresolved_error_ids)},
        "agreement": {"core_routes": dict(core_routes), "action_routes": dict(action_routes), "pairwise_core_exact": {"A-B": {"matches": pair_core["A-B"], "denominator": 150}, "A-C": {"matches": pair_core["A-C"], "denominator": len(model_c_records)}, "B-C": {"matches": pair_core["B-C"], "denominator": len(model_c_records)}}, "pairwise_action_exact": {"A-B": {"matches": pair_actions["A-B"], "denominator": 150}, "A-C": {"matches": pair_actions["A-C"], "denominator": len(model_c_records)}, "B-C": {"matches": pair_actions["B-C"], "denominator": len(model_c_records)}}},
        "machine_consensus": {"status_counts": dict(status_counts), "core_unresolved": sum(not row["core_vote"]["resolved"] for row in ensemble_rows), "actions_unresolved": sum(not row["action_vote"]["resolved"] for row in ensemble_rows), "mandatory_human_review": sum(row["mandatory_human_review"] for row in ensemble_rows), "human_reason_counts": dict(human_reasons), "primary_label_counts": dict(label_counts), "relevance_level_counts": dict(relevance_counts), "af_use_label_counts": dict(use_counts), "adoption_eligible_counts": dict(adoption_counts)},
        "outputs": {"model_c_canonical": {"path": str(c_path), "sha256": c_sha}, "ensemble_jsonl": {"path": str(ensemble_path), "sha256": ensemble_sha}, "ensemble_csv": {"path": str(flat_path), "sha256": flat_sha}, "operational_human_queue": {"path": str(operational_path), "sha256": operational_sha, "records": len(operational_rows)}, "double_annotation_queue": {"path": str(double_path), "sha256": double_sha, "records": len(double_rows)}},
    }
    report_sha = write_json(report_path, report)
    print(f"Report SHA-256:          {report_sha}")
    print(f"Output directory:        {output_dir}")
    print("No model requests were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
