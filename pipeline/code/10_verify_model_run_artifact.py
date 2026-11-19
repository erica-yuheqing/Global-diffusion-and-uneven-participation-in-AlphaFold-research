#!/usr/bin/env python3
"""Verify a frozen model-review run artifact without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="Directory containing run_manifest.json")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Accept running/interrupted/failed manifests after verifying available records",
    )
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def safe_artifact_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Snapshot escapes artifact directory: {relative}") from exc
    return candidate


def verify_file(root: Path, entry: dict[str, Any], label: str) -> Path:
    relative = entry.get("snapshot_path")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label}: missing snapshot_path")
    path = safe_artifact_path(root, relative)
    if not path.is_file():
        raise ValueError(f"{label}: missing file {relative}")
    data = path.read_bytes()
    if sha256_bytes(data) != entry.get("sha256"):
        raise ValueError(f"{label}: SHA-256 mismatch for {relative}")
    if len(data) != entry.get("bytes"):
        raise ValueError(f"{label}: byte-count mismatch for {relative}")
    return path


def verify_manifest_checksum(manifest_path: Path) -> None:
    checksum_path = manifest_path.with_suffix(manifest_path.suffix + ".sha256")
    if not checksum_path.is_file():
        raise ValueError(f"Missing manifest checksum: {checksum_path.name}")
    fields = checksum_path.read_text(encoding="ascii").strip().split()
    if len(fields) != 2 or fields[1] != manifest_path.name:
        raise ValueError("Malformed manifest checksum file")
    if sha256_bytes(manifest_path.read_bytes()) != fields[0]:
        raise ValueError("run_manifest.json checksum mismatch")


def protocol_code_hash(entries: list[tuple[dict[str, Any], Path]]) -> str:
    sources = [
        (entry, path)
        for entry, path in entries
        if entry.get("protocol_code") is True
    ]
    digest = hashlib.sha256()
    for entry, path in sorted(sources, key=lambda pair: pair[0]["snapshot_path"]):
        relative = Path(entry["snapshot_path"])
        try:
            identity = relative.relative_to("source")
        except ValueError as exc:
            raise ValueError(f"Invalid source snapshot path: {relative}") from exc
        digest.update(str(identity).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_jsonl(
    path: Path,
    *,
    expected_records: int,
    run_id: str,
    label: str,
) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label}:{line_number}: invalid JSON: {exc}") from exc
            if record.get("run_id") != run_id:
                raise ValueError(f"{label}:{line_number}: run_id mismatch")
            if record.get("event") == "request_started":
                request_body = record.get("request_body")
                if not isinstance(request_body, dict):
                    raise ValueError(f"{label}:{line_number}: request body missing")
                if fingerprint(request_body) != record.get("request_body_sha256"):
                    raise ValueError(f"{label}:{line_number}: request body hash mismatch")
            visible_text = record.get("visible_response_text")
            if visible_text is not None:
                if not isinstance(visible_text, str):
                    raise ValueError(f"{label}:{line_number}: visible response is not text")
                if sha256_bytes(visible_text.encode("utf-8")) != record.get(
                    "visible_response_sha256"
                ):
                    raise ValueError(f"{label}:{line_number}: visible response hash mismatch")
            count += 1
    if count != expected_records:
        raise ValueError(
            f"{label}: expected {expected_records} records from manifest, found {count}"
        )
    return count


def main() -> int:
    args = parse_args()
    root = args.artifact.resolve()
    manifest_path = root / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing run_manifest.json under {root}")
    verify_manifest_checksum(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "af-model-run-manifest-v1":
        raise ValueError("Unsupported run-manifest schema")
    status = manifest.get("status")
    complete_statuses = {"completed", "completed_with_failures"}
    if status not in complete_statuses and not args.allow_incomplete:
        raise ValueError(
            f"Artifact status is {status!r}; use --allow-incomplete only for recovery/audit"
        )
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Manifest run_id is missing")

    snapshots = manifest.get("snapshots", {})
    verified_files = 0
    for label in ("input", "input_metadata", "prompt", "schema"):
        entry = snapshots.get(label)
        if entry is not None:
            verify_file(root, entry, f"snapshots.{label}")
            verified_files += 1
    source_entries: list[tuple[dict[str, Any], Path]] = []
    for index, entry in enumerate(snapshots.get("source_and_locks", [])):
        path = verify_file(root, entry, f"snapshots.source_and_locks[{index}]")
        source_entries.append((entry, path))
        verified_files += 1

    signature = manifest.get("run_signature", {})
    if protocol_code_hash(source_entries) != signature.get("protocol_code_sha256"):
        raise ValueError("Protocol-code aggregate hash mismatch")
    prompt_entry = snapshots.get("prompt")
    schema_entry = snapshots.get("schema")
    if prompt_entry and prompt_entry.get("sha256") != signature.get("prompt_sha256"):
        raise ValueError("Prompt signature does not match prompt snapshot")
    if schema_entry and schema_entry.get("sha256") != signature.get("schema_sha256"):
        raise ValueError("Schema signature does not match schema snapshot")
    uv_entries = [
        entry for entry, path in source_entries if path.name == "uv.lock"
    ]
    expected_lock = signature.get("dependency_lock_sha256")
    if expected_lock is not None and (
        len(uv_entries) != 1 or uv_entries[0].get("sha256") != expected_lock
    ):
        raise ValueError("Dependency-lock signature does not match uv.lock snapshot")

    record_count = 0
    for label, entry in manifest.get("archived_records", {}).items():
        path = verify_file(root, entry, f"archived_records.{label}")
        record_count += verify_jsonl(
            path,
            expected_records=entry.get("records"),
            run_id=run_id,
            label=label,
        )
        verified_files += 1

    print(f"Artifact status:        {status}")
    print(f"Run ID:                 {run_id}")
    print(f"Verified files:         {verified_files}")
    print(f"Verified JSONL records: {record_count}")
    print("Integrity check:        PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
