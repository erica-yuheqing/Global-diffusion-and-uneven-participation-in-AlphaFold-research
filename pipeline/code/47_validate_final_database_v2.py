#!/usr/bin/env python3
"""Validate the provenance-only v1-to-v2 final-database repair."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
V1_DIR = PROJECT_ROOT / "fulltext/production/final_database_v1"
V2_DIR = PROJECT_ROOT / "fulltext/production/final_database_v2"
DEFAULT_V1_CSV = V1_DIR / "af_research_database_final_v1.csv"
DEFAULT_V1_JSONL = V1_DIR / "af_research_database_final_v1.jsonl"
DEFAULT_V2_CSV = V2_DIR / "af_research_database_final_v2.csv"
DEFAULT_V2_JSONL = V2_DIR / "af_research_database_final_v2.jsonl"
DEFAULT_V2_LOCK = V2_DIR / "af_research_database_final_v2.lock.json"
DEFAULT_REPORT = V2_DIR / "af_research_database_final_validation_v2.json"
EXPECTED_RECORDS = 29_127
REPAIRED_FIELDS = {"selected_source_models", "selected_providers"}
EXPECTED_AF_USE = {"yes": 16_902, "no": 4_387, "uncertain": 7_838}
EXPECTED_ADOPTION = {"yes": 16_884, "no": 4_402, "uncertain": 7_841}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-csv", type=Path, default=DEFAULT_V1_CSV)
    parser.add_argument("--v1-jsonl", type=Path, default=DEFAULT_V1_JSONL)
    parser.add_argument("--v2-csv", type=Path, default=DEFAULT_V2_CSV)
    parser.add_argument("--v2-jsonl", type=Path, default=DEFAULT_V2_JSONL)
    parser.add_argument("--v2-lock", type=Path, default=DEFAULT_V2_LOCK)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def resolved(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            yield value


def ordered_pipe(values: Iterable[Any]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value is None or value == "":
            continue
        text = str(value)
        if text not in seen:
            seen.add(text)
            ordered.append(text)
    return "|".join(ordered)


def atomic_write_report(path: Path, value: dict[str, Any], *, force: bool) -> str:
    if (path.exists() or path.with_suffix(path.suffix + ".sha256").exists()) and not force:
        raise FileExistsError(f"Refusing to overwrite {path}; pass --force explicitly")
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    digest = hashlib.sha256(data).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar_tmp = sidecar.with_suffix(sidecar.suffix + ".part")
    sidecar_tmp.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    os.replace(sidecar_tmp, sidecar)
    return digest


def main() -> int:
    args = parse_args()
    paths = {
        "v1_csv": resolved(args.v1_csv),
        "v1_jsonl": resolved(args.v1_jsonl),
        "v2_csv": resolved(args.v2_csv),
        "v2_jsonl": resolved(args.v2_jsonl),
        "v2_lock": resolved(args.v2_lock),
    }
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"{label}: expected regular non-symlink file: {path}")
    lock = load_json(paths["v2_lock"])
    failures: list[str] = []

    source_hash_checks: dict[str, bool] = {}
    for label, item in lock.get("sources", {}).items():
        source = Path(item["path"])
        valid = source.is_file() and sha256_file(source) == item.get("sha256")
        source_hash_checks[label] = valid
        if not valid:
            failures.append(f"source hash mismatch: {label}")
    output_hash_checks: dict[str, bool] = {}
    for label, item in lock.get("outputs", {}).items():
        output = Path(item["path"])
        valid = output.is_file() and sha256_file(output) == item.get("sha256")
        output_hash_checks[label] = valid
        if not valid:
            failures.append(f"output hash mismatch: {label}")

    if sha256_file(paths["v1_jsonl"]) != sha256_file(paths["v2_jsonl"]):
        failures.append("v2 JSONL is not byte-identical to v1 JSONL")

    af_use: Counter[str] = Counter()
    adoption: Counter[str] = Counter()
    records = 0
    nonrepair_field_differences = 0
    provenance_mismatches = 0
    generator_strings_remaining = 0
    work_ids: list[str] = []
    with paths["v1_csv"].open(encoding="utf-8", newline="") as v1_handle, paths[
        "v2_csv"
    ].open(encoding="utf-8", newline="") as v2_handle:
        v1_reader = csv.DictReader(v1_handle)
        v2_reader = csv.DictReader(v2_handle)
        if v1_reader.fieldnames != v2_reader.fieldnames:
            failures.append("v1/v2 CSV headers differ")
        for triple in zip_longest(v1_reader, v2_reader, iter_jsonl(paths["v2_jsonl"])):
            v1_row, v2_row, record = triple
            if v1_row is None or v2_row is None or record is None:
                failures.append("v1 CSV, v2 CSV and v2 JSONL counts differ")
                break
            records += 1
            work_id = str(record.get("work_id") or "")
            work_ids.append(work_id)
            if v1_row.get("work_id") != work_id or v2_row.get("work_id") != work_id:
                failures.append(f"row order mismatch at {work_id or records}")
                break
            for field in v2_row:
                if field not in REPAIRED_FIELDS and v1_row.get(field) != v2_row.get(field):
                    nonrepair_field_differences += 1
            provenance = record.get("provenance") or {}
            selected = provenance.get("selected_sources") or []
            expected_models = ordered_pipe(item.get("source_model") for item in selected)
            expected_providers = ordered_pipe(item.get("provider") for item in selected)
            if v2_row.get("selected_source_models") != expected_models:
                provenance_mismatches += 1
            if v2_row.get("selected_providers") != expected_providers:
                provenance_mismatches += 1
            if "<generator object" in (v2_row.get("selected_source_models") or ""):
                generator_strings_remaining += 1
            if "<generator object" in (v2_row.get("selected_providers") or ""):
                generator_strings_remaining += 1
            af_use[str(v2_row.get("af_use_label") or "<missing>")] += 1
            adoption[str(v2_row.get("adoption_eligible") or "<missing>")] += 1

    if records != EXPECTED_RECORDS or len(set(work_ids)) != EXPECTED_RECORDS:
        failures.append(f"expected {EXPECTED_RECORDS:,} unique records, found {records:,}")
    if nonrepair_field_differences:
        failures.append(f"non-repair CSV field differences: {nonrepair_field_differences:,}")
    if provenance_mismatches:
        failures.append(f"repaired provenance mismatches: {provenance_mismatches:,}")
    if generator_strings_remaining:
        failures.append(f"generator strings remaining: {generator_strings_remaining:,}")
    if dict(af_use) != EXPECTED_AF_USE:
        failures.append(f"AF-use counts differ: {dict(af_use)}")
    if dict(adoption) != EXPECTED_ADOPTION:
        failures.append(f"adoption counts differ: {dict(adoption)}")

    report = {
        "schema_version": "af-production-final-database-validation-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "records": records,
        "unique_work_ids": len(set(work_ids)),
        "jsonl_byte_identical_to_v1": sha256_file(paths["v1_jsonl"])
        == sha256_file(paths["v2_jsonl"]),
        "nonrepair_csv_field_differences": nonrepair_field_differences,
        "repaired_provenance_mismatches": provenance_mismatches,
        "generator_strings_remaining": generator_strings_remaining,
        "af_use_label_counts": dict(sorted(af_use.items())),
        "adoption_eligible_counts": dict(sorted(adoption.items())),
        "source_hash_checks": source_hash_checks,
        "output_hash_checks": output_hash_checks,
        "implementation": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
    }
    report_path = resolved(args.report)
    report_digest = atomic_write_report(report_path, report, force=args.force)
    print(f"Validation status:      {report['status']}")
    print(f"Records:                {records:,}")
    print(f"Non-repair differences: {nonrepair_field_differences:,}")
    print(f"Provenance mismatches:  {provenance_mismatches:,}")
    print(f"Generator strings:      {generator_strings_remaining:,}")
    print(f"Validation report:      {report_path}")
    print(f"Report SHA-256:         {report_digest}")
    if failures:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
