#!/usr/bin/env python3
"""Capture the local analysis environment without running any analysis."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import ANALYSIS_DIR, OUT_DIR, PROJECT_ROOT, atomic_write_json, sha256_file


OUTPUT = OUT_DIR / "environment.json"
PACKAGES = ("duckdb", "pandas", "pyarrow", "matplotlib", "marimo", "numpy")
PIPELINE_FILES = (
    "common.py",
    "config.json",
    "environment.py",
    "prepare.py",
    "validate.py",
    "summarize_uncertain_use.py",
    "descriptive.py",
    "figures.py",
    "tables.py",
    "DATA_DICTIONARY.md",
    "README.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> None:
    args = parse_args()
    lock_path = PROJECT_ROOT / "uv.lock"
    tracked_files = [ANALYSIS_DIR / name for name in PIPELINE_FILES]
    missing = [str(path) for path in tracked_files if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing analysis files: " + ", ".join(missing))
    payload = {
        "schema_version": "af-final-analysis-environment-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "platform": platform.platform(),
        "packages": {name: package_version(name) for name in PACKAGES},
        "uv_lock": {
            "path": str(lock_path),
            "sha256": sha256_file(lock_path) if lock_path.is_file() else None,
        },
        "analysis_files": {
            str(path.relative_to(PROJECT_ROOT)): sha256_file(path) for path in tracked_files
        },
        "old_notebook_modified_by_this_pipeline": False,
    }
    atomic_write_json(OUTPUT, payload, force=args.force)
    print(f"Environment record:     {OUTPUT}")


if __name__ == "__main__":
    main()
