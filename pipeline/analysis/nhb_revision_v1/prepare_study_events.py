"""Prepare approved-link study records and institution entry/follow-up. User-run, offline."""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from baseline_features import fingerprint
from common import (DEFAULT_OUT, MODULE, assert_unchanged, connect, environment, literal,
                    output_dir, read_json, sha256, utc, write_json)
from study_events import CONFIG, DECISIONS, EXPORTS, attach_sources, build_histories, build_studies, load_inputs

CODE_FILES = ("common.py", "baseline_features.py", "study_events.py", "prepare_study_events.py",
              "validate_study_events.py", "test_study_events.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--feature-dir", type=Path, default=MODULE / "baseline_features_v1")
    parser.add_argument("--output-dir", type=Path, default=MODULE / "study_events_v1")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-gib", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.threads <= 16 or not 1 <= args.memory_gib <= 32:
        parser.error("threads 1..16; memory-gib 1..32")
    source = output_dir(args.input_dir, existing=True)
    features = output_dir(args.feature_dir, existing=True)
    destination = output_dir(args.output_dir)
    if any(destination.resolve().is_relative_to(d.resolve()) for d in (source, features)):
        raise ValueError("Output cannot be inside frozen source directories")
    print("Checking validated foundations/prior features, protocol and user decision chain...", flush=True)
    c, inv = load_inputs(source, features)
    inv += [fingerprint(MODULE / name) for name in CODE_FILES]
    if args.dry_run:
        print("Dry run: selected source hashes, schemas and approvals checked; no study/event aggregation or files")
        print("Only approved P0/P1 links; other works remain singletons; fixed cutoff 2025-12-31")
        return 0
    if shutil.disk_usage(destination.parent).free < c["minimum_free_disk_gib"] * 1024**3:
        raise ValueError("Free disk below safety floor; no staging created")
    stage = Path(tempfile.mkdtemp(prefix=".study-events-incomplete-", dir=destination.parent))
    print(f"Staging (retained on failure): {stage}", flush=True)
    con = None
    try:
        con = connect(args.threads, args.memory_gib, spill=stage / ".spill")
        attach_sources(con, source, features)
        print("Constructing approved study links and coherent representative records...", flush=True)
        studies = build_studies(con, read_json(DECISIONS)["decisions"])
        print("Constructing institution-specific dates and observed follow-up states...", flush=True)
        histories = build_histories(con)
        outputs = {}
        import pyarrow.parquet as pq
        for name, order in EXPORTS.items():
            path = stage / f"{name}.parquet"
            con.execute(f"COPY (SELECT * FROM {name} ORDER BY {order}) TO {literal(path)} (FORMAT PARQUET,COMPRESSION ZSTD)")
            outputs[path.name] = {"sha256": sha256(path), "size_bytes": path.stat().st_size,
                                  "rows": pq.ParquetFile(path).metadata.num_rows}
        status_counts = dict(con.execute("SELECT followup_status,count(*) FROM institution_participation_history GROUP BY 1 ORDER BY 1").fetchall())
        interval_counts = {str(key): value for key, value in con.execute("""SELECT intervals_covered_24m,count(*)
          FROM institution_participation_history WHERE eligible_24m_distribution GROUP BY 1 ORDER BY 1""").fetchall()}
        fixed_interval_counts = {str(key): value for key, value in con.execute("""SELECT intervals_covered_24m,count(*)
          FROM institution_participation_history WHERE eligible_24m_fixed_cohort GROUP BY 1 ORDER BY 1""").fetchall()}
        con.close()
        con = None
        archive = stage / "code_and_protocol"
        archive.mkdir()
        snapshots = {}
        sources = [MODULE / name for name in CODE_FILES] + [CONFIG, DECISIONS]
        sources += [Path(r["path"]) for r in inv if Path(r["path"]).suffix == ".md"]
        sources += [MODULE / "baseline_features_config_v1.json",
                    MODULE / "review_materials_v1" / "version_decisions_template.json"]
        by_name = {Path(r["path"]).name: r for r in inv}
        for path in sources:
            target = archive / path.name
            if target.exists():
                continue
            shutil.copyfile(path, target)
            if sha256(target) != by_name[path.name]["sha256"]:
                raise ValueError("Snapshot differs from run input")
            snapshots[f"code_and_protocol/{path.name}"] = {"sha256": sha256(target), "size_bytes": target.stat().st_size}
        assert_unchanged(inv)
        manifest = {"schema_version": "nhb-study-events-run-v1", "created_at_utc": utc(),
                    "foundation_directory": str(source), "feature_directory": str(features), "config": c,
                    "inputs": inv, "outputs": outputs, "snapshots": snapshots, "environment": environment(),
                    "execution": {"threads": args.threads, "memory_gib": args.memory_gib},
                    "study_counts": studies, "history_counts": histories,
                    "followup_status_counts": status_counts, "eligible_24m_interval_counts": interval_counts,
                    "fixed_cohort_eligible_24m_interval_counts": fixed_interval_counts,
                    "version_decisions_applied_in_derived_tables_only": True,
                    "original_final_database_modified": False, "formal_models_ready": False,
                    "limitations": ["Only two explicitly approved groups merged; singletons not certified independent studies",
                                    "No generic same-DOI or title-similarity auto-merges",
                                    "Annual/citation representative attribution is not the union of versions",
                                    "Institution entry comes only from its observed confirmed version",
                                    "Earlier P1 member date inconsistent with override is unusable for timing",
                                    "Missing dates, possible events and short follow-up not coded as no participation",
                                    "Observed known-date intervals are not causal persistence or actual technology-use measurements",
                                    "Baseline work-level features unchanged: approved links are main-period only",
                                    "Activities/leadership/RR/citation analyses still require their own checks"]}
        write_json(stage / "prepare_manifest.json", manifest)
        if destination.exists():
            raise FileExistsError("Destination appeared; staging retained")
        stage.rename(destination)
        print(f"Work records / derived study units: {studies['work_records']:,} / {studies['study_units_after_approved_links']:,}")
        print(f"Confirmed AF main study units:      {studies['confirmed_af_main_study_units']:,}")
        print(f"Unmerged same-DOI leads:            {studies['unmerged_same_doi_groups']:,}")
        print(f"Institution event rows:            {histories['institution_event_rows']:,}")
        print(f"Complete identifiable 24m cohort:  {histories['complete_identifiable_main_entry_24m_institutions']:,}")
        print(f"  Fixed baseline cohort subset:    {histories['fixed_cohort_complete_identifiable_24m_institutions']:,}")
        print(f"Saved: {destination}; NEXT validate_study_events.py; no formal analysis run")
    except BaseException:
        if con is not None:
            con.close()
        print(f"INCOMPLETE retained: {stage}; no published study/event directory", flush=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
