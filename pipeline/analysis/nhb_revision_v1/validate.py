"""Independent integrity/relational checks on prepared work-level foundations."""
from __future__ import annotations

import argparse
from pathlib import Path

from common import (DEFAULT_OUT, MODULE, SCHEMA, assert_unchanged, connect, literal, output_dir,
                    read_json, sha256, utc, write_json)
from foundations import EXPORTS, checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify-source-content", action="store_true", help="rehash all original inputs; otherwise size/mtime freshness guard")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-gib", type=int, default=4)
    args = parser.parse_args()
    directory = output_dir(args.input_dir, existing=True)
    report_path = directory / "validation_report.json"
    if report_path.exists():
        raise FileExistsError("Validation report exists; retained unchanged. Use a new prepared output for a new run.")
    manifest = read_json(directory / "prepare_manifest.json")
    if manifest["schema_version"] != SCHEMA or set(manifest["outputs"]) != {f"{t}.parquet" for t in EXPORTS}:
        raise ValueError("Unknown/incomplete preparation manifest")
    # Use matching rule implementations: source edits cannot silently validate an older run differently.
    for name in ("common.py", "foundations.py", "validate.py"):
        if sha256(MODULE / name) != manifest["code_and_protocol"][name]["sha256"]:
            raise ValueError(f"Validation rules changed since preparation: {name}; review a new version")
    for name, rec in manifest["code_and_protocol"].items():
        path = directory / "code_and_protocol" / name
        if Path(name).name != name or path.is_symlink() or sha256(path) != rec["sha256"]:
            raise ValueError(f"Archived code/protocol integrity failure: {name}")
    assert_unchanged(manifest["inputs"])
    if args.verify_source_content:
        for rec in manifest["inputs"]:
            if sha256(Path(rec["path"])) != rec["sha256"]:
                raise ValueError(f"Source content changed: {rec['path']}")
    con = connect(args.threads, args.memory_gib)
    try:
        for name, rec in manifest["outputs"].items():
            path = directory / name
            if path.is_symlink() or path.stat().st_size != rec["size_bytes"] or sha256(path) != rec["sha256"]:
                raise ValueError(f"Output integrity failure: {name}")
            table = path.stem
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({literal(path)})")
            if con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] != rec["rows"]:
                raise ValueError(f"Output row count differs: {name}")
        result = checks(con, manifest["config"]["weight_tolerance"])
    finally:
        con.close()
    assert_unchanged(manifest["inputs"])
    blockers = [x for x in result if not x["passed"]]
    report = {
        "schema_version": "nhb-foundations-validation-v2", "created_at_utc": utc(),
        "prepare_manifest_sha256": sha256(directory / "prepare_manifest.json"),
        "original_source_content_rehashed": args.verify_source_content,
        "output_content_hashes_verified": True, "checks": result, "blockers": blockers,
        "work_level_foundations_ready": not blockers, "final_study_analysis_ready": False,
        "pending": manifest["pending"], "warnings": manifest["warnings"],
    }
    write_json(report_path, report)
    print(f"Foundation checks: {len(result)}; blockers: {len(blockers)}")
    print(f"Work-level foundations ready: {not blockers}")
    print("Study-deduplicated analysis / follow-up / RR ready: False")
    print(f"Validation report: {report_path}")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
