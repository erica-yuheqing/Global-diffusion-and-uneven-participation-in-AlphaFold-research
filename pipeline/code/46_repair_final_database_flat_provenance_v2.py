#!/usr/bin/env python3
"""Repair the two malformed flat provenance columns in final database v1.

This is a local-only deterministic re-export.  It does not call any provider,
rerun any model, alter the frozen v1 package, or change any adjudicated field.
The canonical v1 JSONL is copied byte-for-byte into the v2 package.  The v2 CSV
is rebuilt in the same row and column order, replacing only
``selected_source_models`` and ``selected_providers`` with values derived from
``provenance.selected_sources`` in the matching JSONL record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
V1_DIR = PROJECT_ROOT / "fulltext/production/final_database_v1"
DEFAULT_V1_JSONL = V1_DIR / "af_research_database_final_v1.jsonl"
DEFAULT_V1_CSV = V1_DIR / "af_research_database_final_v1.csv"
DEFAULT_V1_AUDIT = V1_DIR / "af_research_database_final_audit_v1.csv"
DEFAULT_V1_SUMMARY = V1_DIR / "af_research_database_final_summary_v1.json"
DEFAULT_V1_LOCK = V1_DIR / "af_research_database_final_v1.lock.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext/production/final_database_v2"
EXPECTED_RECORDS = 29_127
REPAIRED_FIELDS = ("selected_source_models", "selected_providers")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-jsonl", type=Path, default=DEFAULT_V1_JSONL)
    parser.add_argument("--v1-csv", type=Path, default=DEFAULT_V1_CSV)
    parser.add_argument("--v1-audit", type=Path, default=DEFAULT_V1_AUDIT)
    parser.add_argument("--v1-summary", type=Path, default=DEFAULT_V1_SUMMARY)
    parser.add_argument("--v1-lock", type=Path, default=DEFAULT_V1_LOCK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-records", type=int, default=EXPECTED_RECORDS)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def resolved(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object at {path}:{line_number}")
            yield line_number, value


def ordered_unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None or value == "":
            continue
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def pipe(values: Iterable[Any]) -> str:
    return "|".join(ordered_unique(values))


def write_sha256_sidecar(path: Path, digest: str) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    temporary = sidecar.with_suffix(sidecar.suffix + ".part")
    temporary.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    os.replace(temporary, sidecar)


def atomic_copy(source: Path, target: Path) -> str:
    temporary = target.with_suffix(target.suffix + ".part")
    with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle, length=4 * 1024 * 1024)
    os.replace(temporary, target)
    digest = sha256_file(target)
    write_sha256_sidecar(target, digest)
    return digest


def atomic_write_json(path: Path, value: dict[str, Any]) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    digest = sha256_bytes(data)
    write_sha256_sidecar(path, digest)
    return digest


def preflight_outputs(paths: Iterable[Path], *, force: bool) -> None:
    existing = [path for path in paths if path.exists() or path.with_suffix(path.suffix + ".sha256").exists()]
    if existing and not force:
        raise FileExistsError(
            "Refusing to overwrite v2 outputs; pass --force explicitly: "
            + ", ".join(str(path) for path in existing)
        )


def main() -> int:
    args = parse_args()
    inputs = {
        "v1_jsonl": resolved(args.v1_jsonl),
        "v1_csv": resolved(args.v1_csv),
        "v1_audit": resolved(args.v1_audit),
        "v1_summary": resolved(args.v1_summary),
        "v1_lock": resolved(args.v1_lock),
    }
    for label, path in inputs.items():
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"{label}: expected a regular non-symlink file: {path}")

    input_hashes_before = {label: sha256_file(path) for label, path in inputs.items()}
    v1_lock = load_json(inputs["v1_lock"])
    v1_summary = load_json(inputs["v1_summary"])
    if int(v1_lock.get("expected_records", -1)) != args.expected_records:
        raise ValueError("v1 lock expected-record count differs from requested count")
    for filename, key in (
        (inputs["v1_jsonl"].name, "v1_jsonl"),
        (inputs["v1_csv"].name, "v1_csv"),
        (inputs["v1_audit"].name, "v1_audit"),
        (inputs["v1_summary"].name, "v1_summary"),
    ):
        locked = v1_lock.get("outputs", {}).get(filename, {}).get("sha256")
        if locked != input_hashes_before[key]:
            raise ValueError(f"v1 lock hash mismatch for {filename}")

    output_dir = resolved(args.output_dir)
    jsonl_path = output_dir / "af_research_database_final_v2.jsonl"
    csv_path = output_dir / "af_research_database_final_v2.csv"
    audit_path = output_dir / "af_research_database_final_audit_v2.csv"
    summary_path = output_dir / "af_research_database_final_summary_v2.json"
    lock_path = output_dir / "af_research_database_final_v2.lock.json"
    output_paths = (jsonl_path, csv_path, audit_path, summary_path, lock_path)
    preflight_outputs(output_paths, force=args.force)
    output_dir.mkdir(parents=True, exist_ok=True)

    temporary_csv = csv_path.with_suffix(csv_path.suffix + ".part")
    ordered_ids: list[str] = []
    changed_rows = 0
    blank_source_models = 0
    blank_providers = 0
    model_combinations: Counter[str] = Counter()
    provider_combinations: Counter[str] = Counter()
    af_use_counts: Counter[str] = Counter()
    adoption_counts: Counter[str] = Counter()

    with inputs["v1_csv"].open(encoding="utf-8", newline="") as csv_handle, temporary_csv.open(
        "w", encoding="utf-8", newline=""
    ) as output_handle:
        reader = csv.DictReader(csv_handle)
        if not reader.fieldnames:
            raise ValueError("v1 CSV has no header")
        missing_fields = [field for field in REPAIRED_FIELDS if field not in reader.fieldnames]
        if missing_fields:
            raise ValueError(f"v1 CSV lacks repair fields: {missing_fields}")
        writer = csv.DictWriter(output_handle, fieldnames=reader.fieldnames)
        writer.writeheader()

        record_iterator = iter_jsonl(inputs["v1_jsonl"])
        for row_number, pair in enumerate(zip_longest(reader, record_iterator), 2):
            row, json_item = pair
            if row is None or json_item is None:
                raise ValueError("v1 CSV and JSONL record counts differ")
            line_number, record = json_item
            work_id = str(record.get("work_id") or "")
            if not work_id or row.get("work_id") != work_id or row.get("review_id") != work_id:
                raise ValueError(
                    f"CSV/JSONL ID or order mismatch at CSV row {row_number}, JSONL line {line_number}"
                )
            if row.get("final_record_sha256") != fingerprint(record):
                raise ValueError(f"Per-record hash mismatch for {work_id}")
            provenance = record.get("provenance")
            if not isinstance(provenance, dict):
                raise ValueError(f"Missing provenance object for {work_id}")
            selected = provenance.get("selected_sources") or []
            if not isinstance(selected, list) or any(not isinstance(item, dict) for item in selected):
                raise ValueError(f"Invalid selected_sources for {work_id}")
            source_models = pipe(item.get("source_model") for item in selected)
            providers = pipe(item.get("provider") for item in selected)
            before = (row.get("selected_source_models") or "", row.get("selected_providers") or "")
            after = (source_models, providers)
            if before != after:
                changed_rows += 1
            row["selected_source_models"] = source_models
            row["selected_providers"] = providers
            if not source_models:
                blank_source_models += 1
            if not providers:
                blank_providers += 1
            model_combinations[source_models or "<none>"] += 1
            provider_combinations[providers or "<none>"] += 1
            af_use_counts[str(row.get("af_use_label") or "<missing>")] += 1
            adoption_counts[str(row.get("adoption_eligible") or "<missing>")] += 1
            ordered_ids.append(work_id)
            writer.writerow(row)

    if len(ordered_ids) != args.expected_records or len(set(ordered_ids)) != args.expected_records:
        raise ValueError(
            f"Expected {args.expected_records:,} unique records, found {len(ordered_ids):,}"
        )
    if changed_rows != args.expected_records:
        raise ValueError(
            f"Expected both malformed flat fields to change in all records; changed {changed_rows:,}"
        )
    csv_digest = sha256_file(temporary_csv)
    os.replace(temporary_csv, csv_path)
    write_sha256_sidecar(csv_path, csv_digest)

    jsonl_digest = atomic_copy(inputs["v1_jsonl"], jsonl_path)
    audit_digest = atomic_copy(inputs["v1_audit"], audit_path)
    if jsonl_digest != input_hashes_before["v1_jsonl"]:
        raise RuntimeError("v2 JSONL is not byte-identical to canonical v1 JSONL")
    if audit_digest != input_hashes_before["v1_audit"]:
        raise RuntimeError("v2 audit CSV is not byte-identical to v1 audit CSV")

    created_at = datetime.now(timezone.utc).isoformat()
    outputs: dict[str, dict[str, Any]] = {
        jsonl_path.name: {
            "path": str(jsonl_path),
            "records": len(ordered_ids),
            "sha256": jsonl_digest,
            "byte_identical_to_v1": True,
        },
        csv_path.name: {
            "path": str(csv_path),
            "records": len(ordered_ids),
            "sha256": csv_digest,
            "only_changed_fields": list(REPAIRED_FIELDS),
        },
        audit_path.name: {
            "path": str(audit_path),
            "records": int(v1_summary.get("audit_records", 0)),
            "sha256": audit_digest,
            "byte_identical_to_v1": True,
        },
    }
    summary = {
        "schema_version": "af-production-final-database-summary-v2",
        "created_at_utc": created_at,
        "records": len(ordered_ids),
        "unique_work_ids": len(set(ordered_ids)),
        "coverage_complete": True,
        "record_schema_version": "af-production-final-record-v1",
        "canonical_jsonl_byte_identical_to_v1": True,
        "repair": {
            "reason": "v1 flat CSV serialized generator objects in two provenance columns",
            "fields": list(REPAIRED_FIELDS),
            "changed_csv_rows": changed_rows,
            "core_or_adjudicated_fields_changed": False,
            "models_or_providers_requeried": False,
        },
        "af_use_label_counts": dict(sorted(af_use_counts.items())),
        "adoption_eligible_counts": dict(sorted(adoption_counts.items())),
        "selected_source_model_combinations": dict(sorted(model_combinations.items())),
        "selected_provider_combinations": dict(sorted(provider_combinations.items())),
        "blank_selected_source_models": blank_source_models,
        "blank_selected_providers": blank_providers,
        "v1_summary_sha256": input_hashes_before["v1_summary"],
        "outputs": outputs,
    }
    summary_digest = atomic_write_json(summary_path, summary)
    outputs[summary_path.name] = {
        "path": str(summary_path),
        "records": 1,
        "sha256": summary_digest,
    }

    input_hashes_after = {label: sha256_file(path) for label, path in inputs.items()}
    if input_hashes_after != input_hashes_before:
        raise RuntimeError("One or more frozen v1 inputs changed during re-export")
    lock = {
        "schema_version": "af-production-final-database-lock-v2",
        "created_at_utc": created_at,
        "expected_records": args.expected_records,
        "ordered_work_id_sha256": sha256_bytes("\n".join(ordered_ids).encode()),
        "sources": {
            label: {"path": str(path), "sha256": input_hashes_before[label]}
            for label, path in inputs.items()
        },
        "repair_policy": {
            "canonical_source": "v1 JSONL provenance.selected_sources",
            "repaired_fields": list(REPAIRED_FIELDS),
            "source_order_preserved": True,
            "duplicate_values_removed_preserving_first_occurrence": True,
            "all_other_csv_fields_preserved": True,
            "jsonl_byte_identical_to_v1": True,
            "audit_byte_identical_to_v1": True,
            "provider_requests_made": 0,
        },
        "implementation": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "outputs": outputs,
    }
    lock_digest = atomic_write_json(lock_path, lock)

    print(f"Records:                {len(ordered_ids):,}")
    print(f"CSV rows repaired:      {changed_rows:,}")
    print(f"Blank sources/providers:{blank_source_models:,} / {blank_providers:,}")
    print(f"JSONL unchanged:        {jsonl_digest == input_hashes_before['v1_jsonl']}")
    print(f"Core labels unchanged:  True")
    print(f"Output directory:       {output_dir}")
    print(f"Final CSV SHA-256:      {csv_digest}")
    print(f"Final JSONL SHA-256:    {jsonl_digest}")
    print(f"Lock SHA-256:           {lock_digest}")
    print("Repair complete; no provider requests were made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
