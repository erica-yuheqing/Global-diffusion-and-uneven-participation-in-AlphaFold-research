#!/usr/bin/env python3
"""Partition the v6 Model C queue into auditable reuse and rerun cohorts.

No provider requests are made.  A historical Model C response is reused only
when the work remains in the v6 recommended queue, its packet is unchanged,
its recorded input fingerprint matches, and its response passes the current
schema and semantic validator.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
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

OLD_INPUT = PROJECT_ROOT / "fulltext/pilot/adjudication_v4_1/pilot_150_model_c_recommended_inputs.jsonl"
OLD_META = PROJECT_ROOT / "fulltext/pilot/adjudication_v4_1/pilot_150_model_c_recommended_inputs.meta.json"
OLD_OUTPUT = PROJECT_ROOT / "fulltext/pilot/model_outputs_v5_protocol_v4_3/model_c_recommended_openrouter_xhigh_v4_3.jsonl"
NEW_INPUT = PROJECT_ROOT / "fulltext/pilot/adjudication_v6/pilot_150_model_c_recommended_inputs_v6.jsonl"
NEW_META = PROJECT_ROOT / "fulltext/pilot/adjudication_v6/pilot_150_model_c_recommended_inputs_v6.meta.json"
CHANGED_IDS = PROJECT_ROOT / "fulltext/pilot/model_inputs_v6/changed_from_v5_work_ids.txt"
SCHEMA = PROJECT_ROOT / "config/af_review_output_schema_v2.json"
RUNNER = CODE_ROOT / "08_run_model_review.py"
OUTPUT_DIR = PROJECT_ROOT / "fulltext/pilot/model_c_transition_v6"


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


def unique(records: list[dict[str, Any]], label: str, key: str = "work_id") -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get(key)
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"{label}: record without {key}")
        if record_id in result:
            raise ValueError(f"{label}: duplicate {key} {record_id}")
        result[record_id] = record
    return result


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("af_review_runner_transition_v6", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load runner: {RUNNER}")
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


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    data = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    ).encode("utf-8")
    return atomic_write(path, data)


def write_json(path: Path, value: Any) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return atomic_write(path, data)


def verify_meta(input_path: Path, meta_path: Path, label: str) -> dict[str, Any]:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    actual = sha256_file(input_path)
    if meta.get("input_sha256") != actual:
        raise ValueError(f"{label}: input hash differs from metadata")
    if int(meta.get("records", -1)) != len(read_jsonl(input_path)):
        raise ValueError(f"{label}: record count differs from metadata")
    return meta


def main() -> int:
    for path in (OLD_INPUT, OLD_META, OLD_OUTPUT, NEW_INPUT, NEW_META, CHANGED_IDS, SCHEMA, RUNNER):
        if not path.is_file():
            raise ValueError(f"Missing required file: {path}")
    old_meta = verify_meta(OLD_INPUT, OLD_META, "old Model C input")
    new_meta = verify_meta(NEW_INPUT, NEW_META, "v6 Model C input")
    old_packets = unique(read_jsonl(OLD_INPUT), "old Model C input")
    new_packets_in_order = read_jsonl(NEW_INPUT)
    new_packets = unique(new_packets_in_order, "v6 Model C input")
    old_outputs = unique(read_jsonl(OLD_OUTPUT), "old Model C output")
    if set(old_outputs) != set(old_packets):
        raise ValueError(
            "Historical Model C output does not exactly cover its locked input; "
            f"missing={sorted(set(old_packets)-set(old_outputs))}, "
            f"extra={sorted(set(old_outputs)-set(old_packets))}"
        )
    changed_ids = {
        line.strip() for line in CHANGED_IDS.read_text(encoding="utf-8").splitlines() if line.strip()
    }
    runner = load_runner()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)

    reused: list[dict[str, Any]] = []
    delta_inputs: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    old_output_sha = sha256_file(OLD_OUTPUT)
    for packet_raw in new_packets_in_order:
        packet = runner.prepare_packet(packet_raw)
        work_id = packet["work_id"]
        reasons: list[str] = []
        old_packet = old_packets.get(work_id)
        old_output = old_outputs.get(work_id)
        if work_id in changed_ids:
            reasons.append("packet_changed_from_v5")
        if old_packet is None:
            reasons.append("new_queue_member")
        elif fingerprint(runner.prepare_packet(old_packet)) != fingerprint(packet):
            if "packet_changed_from_v5" not in reasons:
                reasons.append("packet_fingerprint_changed")
        if old_output is None:
            reasons.append("no_historical_model_c_output")
        elif not reasons:
            if old_output.get("input_packet_sha256") != fingerprint(packet):
                reasons.append("historical_input_fingerprint_mismatch")
            response = old_output.get("response")
            if not isinstance(response, dict):
                reasons.append("historical_response_missing")
            elif validation_errors := runner.validate_review(copy.deepcopy(response), packet, validator):
                reasons.append("historical_response_fails_current_validator")
                decisions.append({
                    "review_id": packet["review_id"],
                    "work_id": work_id,
                    "route": "rerun",
                    "reasons": list(dict.fromkeys(reasons)),
                    "validation_errors": validation_errors,
                })
                delta_inputs.append(packet_raw)
                for reason in dict.fromkeys(reasons):
                    reason_counts[reason] += 1
                continue

        reasons = list(dict.fromkeys(reasons))
        if reasons:
            delta_inputs.append(packet_raw)
            route = "rerun"
        else:
            assert old_output is not None
            reused.append({
                "schema_version": "af-pilot-model-c-reuse-v1",
                "review_id": packet["review_id"],
                "work_id": work_id,
                "input_packet_sha256": fingerprint(packet),
                "validation_status": "valid",
                "source_type": "historical_v4_3_response_unchanged_v6_packet",
                "provenance": {
                    "source_path": str(OLD_OUTPUT),
                    "source_file_sha256": old_output_sha,
                    "source_record_sha256": fingerprint(old_output),
                    "source_run_id": old_output.get("run_id"),
                    "source_artifact": old_output.get("run_artifact"),
                    "source_run_signature": old_output.get("run_signature"),
                },
                "response": old_output["response"],
            })
            route = "reuse"
        decisions.append({
            "review_id": packet["review_id"],
            "work_id": work_id,
            "route": route,
            "reasons": reasons,
        })
        for reason in reasons:
            reason_counts[reason] += 1

    removed_ids = sorted(set(old_packets) - set(new_packets))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reused_path = OUTPUT_DIR / "model_c_reused_unchanged_v6.jsonl"
    delta_path = OUTPUT_DIR / "model_c_delta_inputs_v6.jsonl"
    decisions_path = OUTPUT_DIR / "model_c_transition_decisions_v6.jsonl"
    reused_sha = write_jsonl(reused_path, reused)
    delta_sha = write_jsonl(delta_path, delta_inputs)
    decisions_sha = write_jsonl(decisions_path, decisions)
    manifest_path = OUTPUT_DIR / "model_c_transition_manifest_v6.json"
    manifest = {
        "schema_version": "af-pilot-model-c-transition-manifest-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "validator": {
            "runner_path": str(RUNNER),
            "runner_sha256": sha256_file(RUNNER),
            "support_path": str(CODE_ROOT / "fulltext_pipeline/model_review_support.py"),
            "support_sha256": sha256_file(CODE_ROOT / "fulltext_pipeline/model_review_support.py"),
            "schema_path": str(SCHEMA),
            "schema_sha256": sha256_file(SCHEMA),
        },
        "sources": {
            "old_input": {"path": str(OLD_INPUT), "sha256": sha256_file(OLD_INPUT), "records": old_meta["records"]},
            "old_input_meta": {"path": str(OLD_META), "sha256": sha256_file(OLD_META)},
            "old_output": {"path": str(OLD_OUTPUT), "sha256": old_output_sha, "records": len(old_outputs)},
            "new_input": {"path": str(NEW_INPUT), "sha256": sha256_file(NEW_INPUT), "records": new_meta["records"]},
            "new_input_meta": {"path": str(NEW_META), "sha256": sha256_file(NEW_META)},
            "changed_ids": {"path": str(CHANGED_IDS), "sha256": sha256_file(CHANGED_IDS), "records": len(changed_ids)},
        },
        "counts": {
            "old_recommended_queue": len(old_packets),
            "new_recommended_queue": len(new_packets),
            "reused": len(reused),
            "rerun": len(delta_inputs),
            "removed_from_queue": len(removed_ids),
        },
        "rerun_reason_counts": dict(reason_counts),
        "removed_from_queue_work_ids": removed_ids,
        "outputs": {
            "reused": {"path": str(reused_path), "sha256": reused_sha, "records": len(reused)},
            "rerun_input": {"path": str(delta_path), "sha256": delta_sha, "records": len(delta_inputs)},
            "decisions": {"path": str(decisions_path), "sha256": decisions_sha, "records": len(decisions)},
        },
        "policy": (
            "Reuse requires unchanged packet identity, an exact recorded input fingerprint, and successful "
            "revalidation under the current schema and semantic validator. All changed, new, missing, or "
            "currently invalid records are routed to a fresh Model C call."
        ),
    }
    manifest_sha = write_json(manifest_path, manifest)

    print(f"Old recommended queue:   {len(old_packets)}")
    print(f"v6 recommended queue:    {len(new_packets)}")
    print(f"Model C safely reused:   {len(reused)}")
    print(f"Model C rerun required:  {len(delta_inputs)}")
    print(f"Removed from v6 queue:   {len(removed_ids)}")
    print(f"Rerun input:             {delta_path}")
    print(f"Manifest SHA-256:        {manifest_sha}")
    print("No model requests were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
