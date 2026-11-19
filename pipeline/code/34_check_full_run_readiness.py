#!/usr/bin/env python3
"""Read-only readiness audit for the full-corpus model review."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

from fulltext_pipeline.common import DEFAULT_DB_PATH, PROJECT_ROOT


DEFAULT_PROTOCOL = PROJECT_ROOT / "config" / "af_production_protocol_v1.json"
DEFAULT_INPUTS = PROJECT_ROOT / "fulltext" / "production" / "model_inputs_v1" / "full_model_inputs.jsonl"
REQUIRED_LOCAL_FILES = (
    PROJECT_ROOT / "config" / "af_review_prompt_v4.txt",
    PROJECT_ROOT / "config" / "af_review_output_schema_v2.json",
    PROJECT_ROOT / "code" / "08_run_model_review.py",
    PROJECT_ROOT / "code" / "33_build_full_model_packets.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--minimum-free-gib", type=float, default=30.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    blockers: list[str] = []
    warnings: list[str] = []
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol.get("schema_version") != "af-production-protocol-v1":
        blockers.append("unexpected or missing production protocol")
    missing_files = [str(path) for path in REQUIRED_LOCAL_FILES if not path.is_file()]
    if missing_files:
        blockers.append("missing required local files: " + ", ".join(missing_files))

    uri = f"file:{args.db.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT parse_status, fetch_status,
                   CASE WHEN abstract IS NULL OR trim(abstract)='' THEN 0 ELSE 1 END AS has_abstract
            FROM works WHERE in_current_corpus=1
            """
        ).fetchall()
    finally:
        connection.close()
    total = len(rows)
    parse_counts = Counter(row["parse_status"] for row in rows)
    fetch_counts = Counter(row["fetch_status"] for row in rows)
    manifest_parse_success = parse_counts["success"]
    abstract_fallback_candidates = sum(
        row["parse_status"] != "success" and row["has_abstract"] for row in rows
    )
    manifest_no_evidence = sum(
        row["parse_status"] != "success" and not row["has_abstract"] for row in rows
    )
    if parse_counts["error"]:
        warnings.append(
            f"{parse_counts['error']:,} full-text parses remain errors; usable abstracts may provide fallback"
        )
    if manifest_no_evidence:
        warnings.append(
            f"at least {manifest_no_evidence:,} records have neither manifest-level parsed full text "
            "nor abstract; final forced-U counts are determined after packet quality checks"
        )

    usage = shutil.disk_usage(PROJECT_ROOT)
    free_gib = usage.free / (1024 ** 3)
    if free_gib < args.minimum_free_gib:
        blockers.append(
            f"free disk {free_gib:.1f} GiB is below the configured safety floor "
            f"of {args.minimum_free_gib:.1f} GiB"
        )
    if not args.inputs.is_file():
        blockers.append("frozen full-corpus input JSONL has not been generated")

    key_status = {
        name: bool(os.environ.get(name))
        for name in ("DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "OPENROUTER_API_KEY")
    }
    if not key_status["DEEPSEEK_API_KEY"]:
        blockers.append("DEEPSEEK_API_KEY is not configured in this shell")
    if not key_status["ZHIPU_API_KEY"]:
        blockers.append("ZHIPU_API_KEY is not configured in this shell")
    if not key_status["OPENROUTER_API_KEY"]:
        warnings.append("OPENROUTER_API_KEY is not configured; it is only needed after the Model C queue exists")

    print(f"Corpus records:        {total:,}")
    print(f"Manifest parse success:{manifest_parse_success:,}")
    print(f"Abstract fallbacks:    {abstract_fallback_candidates:,}")
    print(f"Manifest no evidence:  {manifest_no_evidence:,}")
    print(f"Parse statuses:        {dict(parse_counts)}")
    print(f"Fetch statuses:        {dict(fetch_counts)}")
    print(f"Free disk:             {free_gib:.1f} GiB")
    print(f"Frozen inputs present: {args.inputs.is_file()}")
    print(f"API key presence:      {key_status}")
    print(f"Warnings:              {len(warnings)}")
    for value in warnings:
        print(f"  WARN: {value}")
    print(f"Blockers:              {len(blockers)}")
    for value in blockers:
        print(f"  BLOCK: {value}")
    print(f"Ready for full API run:{not blockers}")
    raise SystemExit(1 if blockers else 0)


if __name__ == "__main__":
    main()
