#!/usr/bin/env python3
"""Revalidate archived model responses locally without making provider requests.

The source run artifact remains immutable.  This command evaluates archived
visible successful responses newest-first, retains the newest response that
passes the current local validator (or the newest visible response when none
passes), and writes a checksummed derived JSONL plus metadata.
"""

from __future__ import annotations

import argparse
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
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("af_model_review_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load model-review runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="Frozen run-artifact directory")
    parser.add_argument("--output", type=Path, required=True, help="Derived JSONL path")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            records.append(value)
    return records


def verify_manifest_checksum(artifact: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = artifact / "run_manifest.json"
    checksum_path = artifact / "run_manifest.json.sha256"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise ValueError("Artifact is missing run_manifest.json or its checksum")
    fields = checksum_path.read_text(encoding="ascii").strip().split()
    if len(fields) != 2 or fields[1] != manifest_path.name:
        raise ValueError("Malformed run-manifest checksum file")
    if sha256_file(manifest_path) != fields[0]:
        raise ValueError("run_manifest.json checksum mismatch")
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def snapshot_path(artifact: Path, manifest: dict[str, Any], label: str) -> Path:
    entry = manifest.get("snapshots", {}).get(label)
    relative = entry.get("snapshot_path") if isinstance(entry, dict) else None
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"Run manifest has no snapshots.{label}.snapshot_path")
    path = (artifact / relative).resolve()
    try:
        path.relative_to(artifact)
    except ValueError as exc:
        raise ValueError(f"Snapshot escapes artifact directory: {relative}") from exc
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise ValueError(f"Missing or modified snapshots.{label}: {relative}")
    return path


def archived_path(artifact: Path, manifest: dict[str, Any], label: str) -> Path:
    entry = manifest.get("archived_records", {}).get(label)
    relative = entry.get("snapshot_path") if isinstance(entry, dict) else None
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"Run manifest has no archived_records.{label}.snapshot_path")
    path = (artifact / relative).resolve()
    try:
        path.relative_to(artifact)
    except ValueError as exc:
        raise ValueError(f"Archived record escapes artifact directory: {relative}") from exc
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise ValueError(f"Missing or modified archived_records.{label}: {relative}")
    return path


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_with_checksum(path: Path, data: bytes) -> str:
    digest = sha256_bytes(data)
    atomic_write(path, data)
    checksum = f"{digest}  {path.name}\n".encode("ascii")
    atomic_write(path.with_suffix(path.suffix + ".sha256"), checksum)
    return digest


def main() -> int:
    args = parse_args()
    artifact = args.artifact.resolve()
    output = args.output.resolve()
    if artifact == output or artifact in output.parents:
        raise ValueError("Derived output must be outside the immutable source artifact")

    manifest_path, manifest = verify_manifest_checksum(artifact)
    if manifest.get("status") not in {"completed", "completed_with_failures"}:
        raise ValueError(f"Cannot revalidate artifact status {manifest.get('status')!r}")

    input_path = snapshot_path(artifact, manifest, "input")
    schema_path = snapshot_path(artifact, manifest, "schema")
    attempts_path = archived_path(artifact, manifest, "attempts")
    runner = load_runner()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)

    packets_in_order = read_jsonl(input_path)
    packets = {record["review_id"]: record for record in packets_in_order}
    responses: dict[str, list[dict[str, Any]]] = {}
    original_validation: dict[tuple[str, int], dict[str, Any]] = {}
    for event in read_jsonl(attempts_path):
        review_id = event.get("review_id")
        attempt_number = event.get("attempt_number")
        if not isinstance(review_id, str) or not isinstance(attempt_number, int):
            continue
        if event.get("event") == "validation_result":
            original_validation[(review_id, attempt_number)] = event
        if (
            event.get("event") == "request_finished"
            and isinstance(event.get("http_status"), int)
            and 200 <= event["http_status"] < 300
            and isinstance(event.get("visible_response_text"), str)
            and event["visible_response_text"].strip()
        ):
            responses.setdefault(review_id, []).append(event)

    validator_paths = [
        CODE_ROOT / "08_run_model_review.py",
        CODE_ROOT / "fulltext_pipeline" / "model_review_support.py",
    ]
    validator_files = {
        str(path.relative_to(CODE_ROOT)): sha256_file(path) for path in validator_paths
    }
    validator_fingerprint = sha256_bytes(
        json.dumps(validator_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    created_at = utc_now()
    run_signature = manifest.get("run_signature", {})
    provider = manifest.get("provider") or run_signature.get("provider")
    model = manifest.get("model") or run_signature.get("model")
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for packet in packets_in_order:
        review_id = packet.get("review_id")
        candidates = responses.get(review_id, [])
        if not candidates:
            continue
        selected: tuple[
            dict[str, Any], dict[str, Any] | None, str | None, list[str]
        ] | None = None
        latest_evaluated: tuple[
            dict[str, Any], dict[str, Any] | None, str | None, list[str]
        ] | None = None
        for event in reversed(candidates):
            parse_error = None
            review: dict[str, Any] | None = None
            try:
                review = runner.parse_json_object(event["visible_response_text"])
                errors = runner.validate_review(review, packets[review_id], validator)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                parse_error = str(exc)
                errors = [f"response parsing: {exc}"]
            evaluated = (event, review, parse_error, errors)
            if latest_evaluated is None:
                latest_evaluated = evaluated
            if not errors:
                selected = evaluated
                break
        selected = selected or latest_evaluated
        assert selected is not None
        event, review, parse_error, errors = selected
        valid = not errors
        counts["validated" if valid else "failed"] += 1
        old = original_validation.get((review_id, event["attempt_number"]), {})
        records.append({
            "schema_version": "af-model-local-revalidation-envelope-v1",
            "created_at_utc": created_at,
            "source_artifact": str(artifact),
            "source_run_id": manifest.get("run_id"),
            "provider": provider,
            "model": model,
            "review_id": review_id,
            "work_id": packet.get("work_id"),
            "source_attempt_number": event["attempt_number"],
            "archived_visible_responses_considered": len(candidates),
            "selection_policy": "latest archived HTTP 2xx visible response passing the current validator; otherwise latest visible response",
            "source_response_sha256": event.get("visible_response_sha256"),
            "source_validation_valid": old.get("valid"),
            "source_validation_errors": old.get("errors", []),
            "local_validator_fingerprint": validator_fingerprint,
            "local_validation_valid": valid,
            "local_validation_errors": errors,
            "parse_error": parse_error,
            "response": review,
        })

    jsonl = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    ).encode("utf-8")
    output_sha = write_with_checksum(output, jsonl)
    meta_path = output.with_suffix(".meta.json")
    metadata = {
        "schema_version": "af-model-local-revalidation-manifest-v1",
        "created_at_utc": created_at,
        "source_artifact": str(artifact),
        "source_manifest_sha256": sha256_file(manifest_path),
        "source_attempts_sha256": sha256_file(attempts_path),
        "source_input_sha256": sha256_file(input_path),
        "source_schema_sha256": sha256_file(schema_path),
        "source_run_id": manifest.get("run_id"),
        "provider": provider,
        "model": model,
        "local_validator_files": validator_files,
        "local_validator_fingerprint": validator_fingerprint,
        "reviewed_responses": len(records),
        "local_validated": counts["validated"],
        "local_failed": counts["failed"],
        "response_selection_policy": "latest archived HTTP 2xx visible response passing the current validator; otherwise latest visible response",
        "output_path": str(output),
        "output_sha256": output_sha,
        "interpretation": (
            "Derived local validation only; the frozen provider run and its original "
            "validation history remain unchanged. Scientific label agreement must be "
            "assessed separately."
        ),
    }
    meta_bytes = (
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    write_with_checksum(meta_path, meta_bytes)

    print(f"Source run:              {manifest.get('run_id')}")
    print(f"Responses revalidated:   {len(records)}")
    print(f"Locally validated:       {counts['validated']}/{len(records)}")
    print(f"Locally failed:          {counts['failed']}")
    print(f"Validator fingerprint:   {validator_fingerprint}")
    print(f"Derived output:          {output}")
    print(f"Metadata:                {meta_path}")
    print("Provider API requests:   0")
    return 0 if not counts["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
