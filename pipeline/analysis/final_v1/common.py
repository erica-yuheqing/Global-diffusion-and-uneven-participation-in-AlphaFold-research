"""Shared, local-only helpers for the final-v1 analysis pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = PROJECT_ROOT / "analysis" / "final_v1"
OUT_DIR = ANALYSIS_DIR / "out"
CONFIG_PATH = ANALYSIS_DIR / "config.json"
FINAL_CSV = (
    PROJECT_ROOT
    / "fulltext/production/final_database_v2/af_research_database_final_v2.csv"
)
FINAL_JSONL = (
    PROJECT_ROOT
    / "fulltext/production/final_database_v2/af_research_database_final_v2.jsonl"
)
FINAL_LOCK = (
    PROJECT_ROOT
    / "fulltext/production/final_database_v2/af_research_database_final_v2.lock.json"
)
WORKS_GLOB = PROJECT_ROOT / "derived_tables" / "works" / "*.parquet"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_config() -> dict[str, Any]:
    return load_json(CONFIG_PATH)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_json(path: Path, value: Any, *, force: bool = False) -> str:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {path}; pass --force explicitly")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    return sha256_bytes(data)


def require_regular_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label}: {path}")
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")


def sql_path(path: Path | str) -> str:
    """Quote a local path for a DuckDB string literal."""
    return str(path).replace("'", "''")


def normalized_type_sql(column: str = "work_type") -> str:
    return f"replace(lower(coalesce({column}, '')), '_', '-')"
