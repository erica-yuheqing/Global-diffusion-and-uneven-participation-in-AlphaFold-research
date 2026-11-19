#!/usr/bin/env python3
"""Merge the locked v5 Pilot canonicals with validated v6 delta reviews.

The program first proves that the declared changed-ID cohort is exactly the
packet-level difference between v5 and v6.  It then replaces only those
records, revalidates every model response against the v6 packet and current
schema, preserves record-level provenance, and rebuilds the blinded Model C
queues.  It never calls a model provider.
"""

from __future__ import annotations

import argparse
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

DEFAULT_LOCK = PROJECT_ROOT / "fulltext/pilot/calibration/pilot_150_v6_incremental_merge.lock.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "fulltext/pilot/adjudication_v6"

DEFAULT_PATHS = {
    "input_v5": "fulltext/pilot/model_inputs_v5/pilot_model_inputs.jsonl",
    "input_v6": "fulltext/pilot/model_inputs_v6/pilot_model_inputs.jsonl",
    "changed_ids": "fulltext/pilot/model_inputs_v6/changed_from_v5_work_ids.txt",
    "prompt": "config/af_review_prompt_v4.txt",
    "schema": "config/af_review_output_schema_v2.json",
    "runner": "code/08_run_model_review.py",
    "support": "code/fulltext_pipeline/model_review_support.py",
    "comparison_helper": "code/17_build_pilot_adjudication.py",
    "upstream_lock": "fulltext/pilot/calibration/pilot_150_v4_1_merge.lock.json",
}

DEFAULT_MODELS = {
    "model_a": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "base": "fulltext/pilot/adjudication_v4_1/model_a_canonical_150.jsonl",
        "deltas": [
            "fulltext/pilot/model_outputs_v6_delta/model_a_delta17_high_v6.jsonl",
        ],
    },
    "model_b": {
        "provider": "zhipu_cn",
        "model": "glm-5.3-flash",
        "base": "fulltext/pilot/adjudication_v4_1/model_b_canonical_150.jsonl",
        "deltas": [
            "fulltext/pilot/model_outputs_v6_delta/model_b_delta17_high_v6.jsonl",
            "fulltext/pilot/model_outputs_v6_delta/model_b_delta2_high_v6_validatorfix_v1.jsonl",
            "fulltext/pilot/model_outputs_v6_delta/model_b_delta1_high_v6_validatorfix_v2.jsonl",
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--create-lock",
        action="store_true",
        help="Freeze the current inputs and source artifacts, then exit.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing outputs.")
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


def json_fingerprint(value: Any) -> str:
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
    checksum = f"{digest}  {path.name}\n".encode("ascii")
    checksum_path = path.with_suffix(path.suffix + ".sha256")
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


def locked_file(path_value: str | Path, *, records: bool = False) -> dict[str, Any]:
    path = resolve(path_value)
    if not path.is_file():
        raise ValueError(f"Missing required file: {path}")
    result: dict[str, Any] = {"path": relative(path), "sha256": sha256_file(path)}
    if records:
        result["records"] = len(read_jsonl(path))
    return result


def require_locked_file(entry: dict[str, Any], label: str) -> Path:
    path = resolve(entry["path"])
    if not path.is_file():
        raise ValueError(f"{label}: missing file {path}")
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        raise ValueError(f"{label}: SHA-256 mismatch; expected {entry['sha256']}, got {actual}")
    return path


def artifact_specs(delta_paths: list[str]) -> list[dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for delta_value in delta_paths:
        delta_path = resolve(delta_value)
        for record in read_jsonl(delta_path):
            artifact_value = record.get("run_artifact")
            run_id = record.get("run_id")
            if not isinstance(artifact_value, str) or not isinstance(run_id, str):
                raise ValueError(f"Delta record lacks run artifact/run ID: {record.get('work_id')}")
            artifact_input = Path(artifact_value)
            artifact = (
                artifact_input.resolve()
                if artifact_input.is_absolute()
                else (delta_path.parent / artifact_input).resolve()
            )
            manifest = artifact / "run_manifest.json"
            if not manifest.is_file():
                raise ValueError(f"Missing run manifest: {manifest}")
            manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
            if manifest_value.get("run_id") != run_id:
                raise ValueError(f"Run ID mismatch in {manifest}")
            key = str(manifest.resolve())
            artifacts[key] = {
                "path": relative(artifact),
                "run_id": run_id,
                "manifest_path": relative(manifest),
                "manifest_sha256": sha256_file(manifest),
            }
    return sorted(artifacts.values(), key=lambda item: (item["run_id"], item["path"]))


def create_lock(path: Path) -> dict[str, Any]:
    input_v5 = locked_file(DEFAULT_PATHS["input_v5"], records=True)
    input_v6 = locked_file(DEFAULT_PATHS["input_v6"], records=True)
    changed_path = resolve(DEFAULT_PATHS["changed_ids"])
    changed_ids = [line.strip() for line in changed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(changed_ids) != len(set(changed_ids)):
        raise ValueError("Changed-ID file contains duplicates")

    models: dict[str, Any] = {}
    for name, spec in DEFAULT_MODELS.items():
        delta_entries = [locked_file(value, records=True) for value in spec["deltas"]]
        models[name] = {
            "provider": spec["provider"],
            "model": spec["model"],
            "base": locked_file(spec["base"], records=True),
            "deltas": delta_entries,
            "artifacts": artifact_specs(spec["deltas"]),
        }

    lock = {
        "schema_version": "af-pilot-v6-incremental-merge-lock-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected": {"records": 150, "model_eligible": 142, "forced_u": 8, "changed": 17},
        "input_v5": input_v5,
        "input_v6": input_v6,
        "changed_ids": {
            "path": relative(changed_path),
            "sha256": sha256_file(changed_path),
            "records": len(changed_ids),
        },
        "prompt": locked_file(DEFAULT_PATHS["prompt"]),
        "schema": locked_file(DEFAULT_PATHS["schema"]),
        "validator": {
            "runner": locked_file(DEFAULT_PATHS["runner"]),
            "support": locked_file(DEFAULT_PATHS["support"]),
        },
        "merge_implementation": {
            "script": locked_file(Path(__file__).resolve()),
            "comparison_helper": locked_file(DEFAULT_PATHS["comparison_helper"]),
        },
        "upstream_v5_merge_lock": locked_file(DEFAULT_PATHS["upstream_lock"]),
        "models": models,
        "selection_policy": (
            "The declared changed cohort must equal the exact packet-level v5/v6 difference. "
            "For each model, replace exactly those records with locked v6 API outputs; retain the "
            "locked v5 canonical response only for byte-semantically unchanged packets. Revalidate "
            "all non-forced responses against the locked v6 input, schema, and validator."
        ),
        "model_c_policy": (
            "Core includes A/B decision disagreements; recommended includes decision or observed-action "
            "disagreements; expanded additionally includes review-flag disagreements or either model "
            "requesting review. Forced-U records are excluded from Model C pending evidence recovery."
        ),
    }
    write_json(path, lock)
    return lock


def verify_artifacts(entries: list[dict[str, Any]], label: str) -> None:
    for entry in entries:
        artifact = resolve(entry["path"])
        manifest = resolve(entry["manifest_path"])
        if not artifact.is_dir() or not manifest.is_file():
            raise ValueError(f"{label}: missing artifact or manifest: {artifact}")
        if sha256_file(manifest) != entry["manifest_sha256"]:
            raise ValueError(f"{label}: run manifest SHA-256 mismatch: {manifest}")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        if value.get("run_id") != entry["run_id"]:
            raise ValueError(f"{label}: run ID mismatch: {manifest}")


def build_model(
    name: str,
    spec: dict[str, Any],
    packets_in_order: list[dict[str, Any]],
    changed_review_ids: set[str],
    runner: Any,
    validator: Draft202012Validator,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_path = require_locked_file(spec["base"], f"{name}.base")
    base_records = read_jsonl(base_path)
    if len(base_records) != int(spec["base"]["records"]):
        raise ValueError(f"{name}.base: record count differs from lock")
    base = unique(base_records, f"{name}.base")

    delta: dict[str, tuple[dict[str, Any], Path, dict[str, Any]]] = {}
    for index, entry in enumerate(spec["deltas"]):
        path = require_locked_file(entry, f"{name}.delta[{index}]")
        records = read_jsonl(path)
        if len(records) != int(entry["records"]):
            raise ValueError(f"{name}.delta[{index}]: record count differs from lock")
        for record in records:
            review_id = record.get("review_id")
            if not isinstance(review_id, str) or not review_id:
                raise ValueError(f"{name}.delta[{index}]: record without review_id")
            if review_id in delta:
                raise ValueError(f"{name}: duplicate delta review_id {review_id}")
            delta[review_id] = (record, path, entry)

    if set(delta) != changed_review_ids:
        raise ValueError(
            f"{name}: delta IDs do not exactly cover changed packets; "
            f"missing={sorted(changed_review_ids-set(delta))}, "
            f"extra={sorted(set(delta)-changed_review_ids)}"
        )
    verify_artifacts(spec["artifacts"], f"{name}.artifacts")

    canonical: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    for packet in packets_in_order:
        review_id = packet["review_id"]
        packet_sha = json_fingerprint(packet)
        if review_id in delta:
            source, source_path, source_entry = delta[review_id]
            if source.get("provider") != spec["provider"] or source.get("model") != spec["model"]:
                raise ValueError(f"{name}/{review_id}: provider/model mismatch")
            if source.get("input_packet_sha256") != packet_sha:
                raise ValueError(f"{name}/{review_id}: v6 input fingerprint mismatch")
            response = source.get("response")
            source_type = "v6_delta_api_review"
            provenance = {
                "source_path": str(source_path),
                "source_file_sha256": source_entry["sha256"],
                "source_record_sha256": json_fingerprint(source),
                "source_run_id": source.get("run_id"),
                "source_artifact": source.get("run_artifact"),
                "source_run_signature": source.get("run_signature"),
            }
        else:
            source = base.get(review_id)
            if source is None:
                raise ValueError(f"{name}/{review_id}: absent from base canonical")
            response = source.get("response")
            source_type = "v5_canonical_unchanged_packet"
            provenance = {
                "source_path": str(base_path),
                "source_file_sha256": spec["base"]["sha256"],
                "source_record_sha256": json_fingerprint(source),
                "upstream_source_type": source.get("source_type"),
                "upstream_provenance": copy.deepcopy(source.get("provenance")),
            }

        if source.get("work_id") != packet.get("work_id"):
            raise ValueError(f"{name}/{review_id}: work_id mismatch")
        if packet.get("model_eligible") is False:
            if review_id in delta:
                raise ValueError(f"{name}/{review_id}: forced-U packet unexpectedly present in delta")
            if response != packet.get("forced_decision") or source.get("validation_status") != "forced_u":
                raise ValueError(f"{name}/{review_id}: forced-U response differs from v6 packet")
            validation_status = "forced_u"
        else:
            if not isinstance(response, dict):
                raise ValueError(f"{name}/{review_id}: response missing")
            errors = runner.validate_review(copy.deepcopy(response), packet, validator)
            if errors:
                raise ValueError(f"{name}/{review_id}: current v6 validation failed: {errors}")
            validation_status = "valid"

        source_counts[source_type] += 1
        canonical.append({
            "schema_version": "af-pilot-canonical-model-review-v2",
            "review_id": review_id,
            "work_id": packet["work_id"],
            "provider": spec["provider"],
            "model": spec["model"],
            "evidence_tier": packet.get("evidence_tier"),
            "input_packet_sha256": packet_sha,
            "validation_status": validation_status,
            "source_type": source_type,
            "provenance": provenance,
            "response": response,
        })

    return canonical, {
        "provider": spec["provider"],
        "model": spec["model"],
        "records": len(canonical),
        "validated": sum(row["validation_status"] == "valid" for row in canonical),
        "forced_u": sum(row["validation_status"] == "forced_u" for row in canonical),
        "source_counts": dict(source_counts),
    }


def main() -> int:
    args = parse_args()
    lock_path = resolve(args.lock)
    output_dir = resolve(args.output_dir)
    if args.create_lock:
        lock = create_lock(lock_path)
        print(f"Lock written:             {lock_path}")
        print(f"Lock SHA-256:            {sha256_file(lock_path)}")
        print(f"Changed records:         {lock['changed_ids']['records']}")
        print("No model requests were made.")
        return 0

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != "af-pilot-v6-incremental-merge-lock-v1":
        raise ValueError("Unsupported or missing v6 incremental merge lock schema")
    for label, entry in (
        ("prompt", lock["prompt"]),
        ("schema", lock["schema"]),
        ("validator.runner", lock["validator"]["runner"]),
        ("validator.support", lock["validator"]["support"]),
        ("merge.script", lock["merge_implementation"]["script"]),
        ("merge.comparison_helper", lock["merge_implementation"]["comparison_helper"]),
        ("upstream_v5_merge_lock", lock["upstream_v5_merge_lock"]),
    ):
        require_locked_file(entry, label)

    input_v5_path = require_locked_file(lock["input_v5"], "input_v5")
    input_v6_path = require_locked_file(lock["input_v6"], "input_v6")
    changed_path = require_locked_file(lock["changed_ids"], "changed_ids")
    schema_path = require_locked_file(lock["schema"], "schema")
    runner = load_module(resolve(lock["validator"]["runner"]["path"]), "af_review_runner_v6")
    helper = load_module(
        resolve(lock["merge_implementation"]["comparison_helper"]["path"]),
        "af_pilot_comparison_helper_v6",
    )

    packets_v5 = [runner.prepare_packet(row) for row in read_jsonl(input_v5_path)]
    packets_v6 = [runner.prepare_packet(row) for row in read_jsonl(input_v6_path)]
    expected = lock["expected"]
    if len(packets_v5) != expected["records"] or len(packets_v6) != expected["records"]:
        raise ValueError("Input record count differs from lock")
    pairs_v5 = [(row["review_id"], row["work_id"]) for row in packets_v5]
    pairs_v6 = [(row["review_id"], row["work_id"]) for row in packets_v6]
    if pairs_v5 != pairs_v6:
        raise ValueError("v5/v6 packet identity or order differs")
    declared_changed_work_ids = [
        line.strip() for line in changed_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len(declared_changed_work_ids) != int(lock["changed_ids"]["records"]):
        raise ValueError("Changed-ID count differs from lock")
    actual_changed_work_ids = [
        new["work_id"]
        for old, new in zip(packets_v5, packets_v6, strict=True)
        if json_fingerprint(old) != json_fingerprint(new)
    ]
    if set(actual_changed_work_ids) != set(declared_changed_work_ids):
        raise ValueError(
            "Declared changed cohort is not the exact v5/v6 packet difference; "
            f"declared_only={sorted(set(declared_changed_work_ids)-set(actual_changed_work_ids))}, "
            f"actual_only={sorted(set(actual_changed_work_ids)-set(declared_changed_work_ids))}"
        )
    packet_by_work = {row["work_id"]: row for row in packets_v6}
    changed_review_ids = {packet_by_work[work_id]["review_id"] for work_id in declared_changed_work_ids}
    if len(changed_review_ids) != expected["changed"]:
        raise ValueError("Changed review-ID count differs from lock")
    eligible = sum(bool(row.get("model_eligible")) for row in packets_v6)
    forced = len(packets_v6) - eligible
    if eligible != expected["model_eligible"] or forced != expected["forced_u"]:
        raise ValueError("v6 eligibility counts differ from lock")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    canonical: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, Any] = {}
    for name in ("model_a", "model_b"):
        records, summary = build_model(
            name,
            lock["models"][name],
            packets_v6,
            changed_review_ids,
            runner,
            validator,
        )
        if (summary["records"], summary["validated"], summary["forced_u"]) != (
            expected["records"], expected["model_eligible"], expected["forced_u"]
        ):
            raise ValueError(f"{name}: canonical counts differ from v6 expectations")
        canonical[name] = records
        summaries[name] = summary

    packets_by_review = unique(packets_v6, "input_v6")
    comparison, queue_rows, model_c_scopes, human_rows = helper.compare(
        canonical["model_a"], canonical["model_b"], packets_by_review
    )

    print(f"Changed cohort verified: {len(changed_review_ids)} exact packet differences")
    print(f"Canonical model A:       {summaries['model_a']['validated']} validated + {summaries['model_a']['forced_u']} forced-U")
    print(f"Canonical model B:       {summaries['model_b']['validated']} validated + {summaries['model_b']['forced_u']} forced-U")
    print(f"A/B decision agreement: {comparison['model_eligible_decision_fields_exact']}/{eligible} eligible")
    print(f"A/B action agreement:   {comparison['model_eligible_observed_actions_exact']}/{eligible} eligible")
    print(f"Model C core queue:      {comparison['model_c_core_records']}")
    print(f"Model C recommended:     {comparison['model_c_recommended_records']}")
    print(f"Model C expanded:        {comparison['model_c_expanded_records']}")
    print(f"Human-review flags:      {comparison['human_review_queue_records']}")
    if args.dry_run:
        print("Dry run: no adjudication outputs were written.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    model_outputs: dict[str, Any] = {}
    for name in ("model_a", "model_b"):
        path = output_dir / f"{name}_canonical_150_v6.jsonl"
        digest = write_jsonl(path, canonical[name])
        model_outputs[name] = {**summaries[name], "path": str(path), "sha256": digest}

    queue_path = output_dir / "pilot_150_ab_adjudication_queue_v6.csv"
    queue_sha = helper.write_csv(queue_path, queue_rows, list(queue_rows[0]))
    human_path = output_dir / "pilot_150_human_review_queue_v6.csv"
    human_sha = helper.write_csv(human_path, human_rows, list(queue_rows[0]))
    model_c_outputs: dict[str, Any] = {}
    for scope, scope_packets in model_c_scopes.items():
        input_path = output_dir / f"pilot_150_model_c_{scope}_inputs_v6.jsonl"
        input_sha = write_jsonl(input_path, scope_packets)
        meta_path = output_dir / f"pilot_150_model_c_{scope}_inputs_v6.meta.json"
        meta = {
            "schema_version": "af-model-c-input-manifest-v2",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "records": len(scope_packets),
            "input_path": str(input_path),
            "input_sha256": input_sha,
            "ordered_review_ids": [row["review_id"] for row in scope_packets],
            "ordered_work_id_sha256": sha256_bytes(
                "\n".join(row["work_id"] for row in scope_packets).encode("utf-8")
            ),
            "blinding": (
                "Packets are copied byte-semantically from the locked blinded v6 input; "
                "A/B decisions and historical labels are absent."
            ),
            "selection_policy": lock["model_c_policy"],
        }
        meta_sha = write_json(meta_path, meta)
        model_c_outputs[scope] = {
            "records": len(scope_packets),
            "path": str(input_path),
            "sha256": input_sha,
            "meta_path": str(meta_path),
            "meta_sha256": meta_sha,
        }

    report_path = output_dir / "pilot_150_ab_comparison_v6.json"
    report = {
        "schema_version": "af-pilot-ab-adjudication-report-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "merge_lock": {"path": str(lock_path), "sha256": sha256_file(lock_path)},
        "merge_script": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "input_v5": {"path": str(input_v5_path), "sha256": sha256_file(input_v5_path)},
        "input_v6": {"path": str(input_v6_path), "sha256": sha256_file(input_v6_path)},
        "changed_cohort": {
            "records": len(changed_review_ids),
            "ordered_work_ids": actual_changed_work_ids,
            "work_id_sha256": sha256_bytes("\n".join(actual_changed_work_ids).encode("utf-8")),
        },
        "models": model_outputs,
        "comparison": comparison,
        "adjudication_queue": {"path": str(queue_path), "sha256": queue_sha},
        "human_review_queue": {"path": str(human_path), "sha256": human_sha},
        "model_c_inputs": model_c_outputs,
        "interpretation": (
            "A/B agreement is not human-reference accuracy. Model C is an independent third assessment, "
            "not a substitute for blinded human validation or evidence recovery for forced-U records."
        ),
    }
    report_sha = write_json(report_path, report)
    print(f"Report SHA-256:          {report_sha}")
    print(f"Output directory:        {output_dir}")
    print("No model requests were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
