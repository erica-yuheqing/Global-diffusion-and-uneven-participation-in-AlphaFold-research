"""Freeze existing local sources and prepare WORK-level audit foundations.

Run manually. Does not publish final study-deduplicated scientific results.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from common import (DEFAULT_OUT, MODULE, SCHEMA, assert_unchanged, config, connect, environment,
                    input_paths, inventory, literal, output_dir, sha256, upstream, utc, write_json)
from foundations import EXPORTS, build


def load_sources(con, sources: dict) -> None:
    for role, view in (("master", "master"), ("authorships", "authors_raw"),
                       ("authorship_countries", "countries_raw"), ("work_institutions", "institutions_raw")):
        files = "[" + ",".join(literal(p) for p in sources[role]) + "]"
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet({files},union_by_name=true)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-gib", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="metadata/source-lock checks only; no full scan or files")
    args = parser.parse_args()
    if not 1 <= args.threads <= 16 or not 1 <= args.memory_gib <= 32:
        parser.error("threads 1..16; memory-gib 1..32")
    c = config()
    destination = output_dir(args.output_dir)
    sources = input_paths(c)
    print("Checking input schemas / upstream locks...", flush=True)
    inv = inventory(sources, full=not args.dry_run)
    prep = upstream(sources, inv, full=not args.dry_run)
    print(f"Master rows (metadata): {prep['counts']['master_records']:,}")
    print(f"Source files:           {len(inv)}")
    print("Scope: 2015–2019 baseline; 2020–2025 main; article/review/preprint; both AF labels yes")
    print("No R&D groups, API calls, automatic version merges or formal statistics")
    if args.dry_run:
        print("Dry run: metadata / final CSV lock checked; master content and derived counts NOT checked; no files written")
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(destination.parent).free / 2**30
    if free < c["minimum_free_disk_gib"]:
        raise ValueError(f"Free disk {free:.1f} GiB < safety floor {c['minimum_free_disk_gib']} GiB")
    stage = Path(tempfile.mkdtemp(prefix=".prepare-incomplete-", dir=destination.parent))
    print(f"Staging (retained on failure): {stage}", flush=True)
    con = None
    try:
        snapshot = stage / "code_and_protocol"
        snapshot.mkdir()
        for name in ("config.json", "common.py", "foundations.py", "prepare.py", "validate.py", "test_foundations.py", "audit_coverage.py", "test_coverage_audit.py", "README.md"):
            shutil.copyfile(MODULE / name, snapshot / name)
        shutil.copyfile(sources["protocol"][0], snapshot / "protocol_v1.2.1.md")
        shutil.copyfile(sources["master_summary"][0], snapshot / "upstream_prepare_summary.json")
        database = stage / ".working.duckdb"
        con = connect(args.threads, args.memory_gib, str(database), stage / ".spill")
        load_sources(con, sources)
        print("Preparing work scopes, relations, weights and audit panels...", flush=True)
        counts, checks = build(con, c)
        outputs = {}
        for table, ordering in EXPORTS.items():
            path = stage / f"{table}.parquet"
            con.execute(f"COPY (SELECT * FROM {table} ORDER BY {ordering}) TO {literal(path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
            outputs[path.name] = {"rows": con.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
                                  "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        con.close()
        con = None
        # Only the exact engine file created by this run is removed, never an input or broad directory.
        database.unlink()
        spill = stage / ".spill"
        if spill.exists() and not any(spill.iterdir()):
            spill.rmdir()
        assert_unchanged(inv)
        archive = {p.name: {"size_bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(snapshot.iterdir())}
        manifest = {
            "schema_version": SCHEMA, "created_at_utc": utc(), "status": "prepared_pending_independent_validation",
            "unit": "OpenAlex work; not fully deduplicated study", "config": c,
            "inputs": inv, "code_and_protocol": archive, "outputs": outputs,
            "environment": environment(), "runtime": {"threads": args.threads, "memory_gib": args.memory_gib},
            "counts": counts, "internal_checks": checks, "inputs_modified": False,
            "ready_for_final_scientific_results": False,
            "pending": ["review clear study-version links", "freeze potential-institution denominator after coverage review",
                        "approve related-expertise topic mapping", "build validated study events and 24-month follow-up states",
                        "leadership common-complete cohort and RR", "activity adjudication and bounded quality checks"],
            "warnings": ["Work-level counts include unreviewed version duplicates; not manuscript final study counts",
                         "First/last authorship relations preserved but leadership validity not yet adjudicated",
                         "Institution-year tables are sparse; absent rows are not automatically zero before observability is defined",
                         "Two-letter country codes preserve source regions; no external sovereignty/economy mapping implied",
                         "Existing cited_by_count zeros are reported zeros, not full provenance verification"],
        }
        write_json(stage / "prepare_manifest.json", manifest)
        if destination.exists():
            raise FileExistsError("Destination appeared during run; staging retained")
        stage.rename(destination)
        print(f"Eligible work records: {counts['eligible_work_records']:,}")
        print(f"Confirmed AF main:     {counts['confirmed_af_main_work_records']:,} (work-level)")
        print(f"Action review queue:   {counts['action_review_work_records']:,} (work-level; membership checked)")
        print(f"Prepared: {destination}; NEXT validate.py. Study events / final analysis NOT ready.")
    except BaseException:
        if con is not None:
            con.close()
        print(f"INCOMPLETE: retained {stage}; no final output published", flush=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
