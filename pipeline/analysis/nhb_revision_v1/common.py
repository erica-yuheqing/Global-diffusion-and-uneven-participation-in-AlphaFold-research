"""Independent local-only foundations. No import of old analysis implementations."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = Path(__file__).resolve().parent
DEFAULT_OUT = MODULE / "out_v2"
SCHEMA = "nhb-foundations-run-v2"
ACTION_STATUSES = ("ab_exact_consensus", "adjudicated", "disagreement_unadjudicated",
                   "not_assessed_insufficient_evidence")

REQUIRED = {
    "master": {"work_id", "doi", "title", "publication_year", "publication_date", "work_type",
               "candidate_reviewed", "af_use_label", "adoption_eligible", "observed_actions_status",
               "final_observed_actions", "primary_topic_id", "primary_topic_display_name",
               "primary_subfield_id", "primary_subfield_display_name", "cited_by_count",
               "journal_or_source_id", "journal_or_source_name"},
    "authorships": {"work_id", "author_id", "author_position", "is_corresponding"},
    "authorship_countries": {"work_id", "country_code", "country_source"},
    "work_institutions": {"work_id", "author_id", "institution_id", "institution_name", "country_code"},
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"Expected object: {path}")
    return obj


def write_json(path: Path, obj: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def config() -> dict:
    c = read_json(MODULE / "config.json")
    if (c["schema_version"] != "nhb-foundations-config-v2" or
        c["baseline_years"] != [2015, 2019] or c["main_years"] != [2020, 2025] or
        c["included_types"] != ["article", "review", "preprint"] or
        c["confirmed_af"] != "candidate_reviewed AND af_use_label=yes AND adoption_eligible=yes" or
        c["screen_negative"] != "NOT candidate_reviewed" or
        c["related_expertise_mapping"]["status"] != "pending_review_after_topic_inventory"):
        raise ValueError("Protocol/config change needs a separately reviewed implementation")
    policy = c["action_status_policy"]
    if (policy["unadjudicated_status"] != "disagreement_unadjudicated" or
        policy["allowed_reviewed_statuses"] != list(ACTION_STATUSES) or
        policy["unknown_or_missing_reviewed_status"] != "block_not_silently_drop" or
        policy["queue_membership"] != "all_main_confirmed_af_with_unadjudicated_status"):
        raise ValueError("Action status vocabulary differs from the final-v2 merge contract")
    if not 0 < c["weight_tolerance"] <= 1e-6:
        raise ValueError("Invalid conservation tolerance")
    return c


def literal(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def id_expression(column: str, prefix: str) -> str:
    """SQL expression: whole-string match before stripping URL, never substring salvage."""
    if prefix not in {"W", "A", "I"}:
        raise ValueError(prefix)
    s = f"trim(CAST({column} AS VARCHAR))"
    return (f"CASE WHEN regexp_full_match({s}, '(https?://openalex.org/)?{prefix}[0-9]+') "
            f"THEN regexp_extract({s}, '{prefix}[0-9]+', 0) ELSE NULL END")


def normalize_id(value: str | None, prefix: str) -> str | None:
    if prefix not in {"W", "A", "I"}:
        raise ValueError(prefix)
    if value is None or not re.fullmatch(rf"(?:https?://openalex\.org/)?{prefix}[0-9]+", value.strip()):
        return None
    return value.strip().rsplit("/", 1)[-1]


def checked_date(value: str | None, year: int) -> tuple[date | None, str]:
    if value is None or not value.strip():
        return None, "missing"
    value = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None, "invalid"
    try:
        result = date.fromisoformat(value)
    except ValueError:
        return None, "invalid"
    return (result, "valid") if result.year == year else (None, "year_conflict")


def input_paths(c: dict) -> dict[str, list[Path]]:
    result = {}
    for role, relative in c["inputs"].items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"Unsafe input path: {relative}")
        paths = sorted(ROOT.glob(relative)) if "*" in relative else [ROOT / relative]
        if not paths:
            raise FileNotFoundError(relative)
        for p in paths:
            if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(ROOT):
                raise ValueError(f"Expected in-project regular input: {p}")
        result[role] = paths
    protocol = Path(c["protocol_path"])
    if not protocol.is_file() or protocol.is_symlink():
        raise FileNotFoundError(f"Protocol source missing: {protocol}")
    result["protocol"] = [protocol]
    return result


def inventory(sources: dict[str, list[Path]], *, full: bool) -> list[dict]:
    import pyarrow.parquet as pq
    records = []
    for role, paths in sources.items():
        for path in paths:
            before = path.stat()
            rec = {"role": role, "path": str(path), "size_bytes": before.st_size,
                   "mtime_ns": before.st_mtime_ns}
            if path.suffix == ".parquet":
                pf = pq.ParquetFile(path)
                missing = REQUIRED[role] - set(pf.schema_arrow.names)
                if missing:
                    raise ValueError(f"Missing fields {sorted(missing)} in {path}")
                rec.update(rows=pf.metadata.num_rows, schema=str(pf.schema_arrow))
            if full:
                rec["sha256"] = sha256(path)
            if (before.st_size, before.st_mtime_ns) != (path.stat().st_size, path.stat().st_mtime_ns):
                raise ValueError(f"Input changed while hashing: {path}")
            records.append(rec)
    return records


def upstream(sources: dict, inv: list[dict], *, full: bool) -> dict:
    prep = read_json(sources["master_summary"][0])
    lock = read_json(sources["final_lock"][0])
    final = sources["final_csv"][0]
    digest = sha256(final)
    if digest != prep["sources"]["final_csv"]["sha256"] or digest != lock["outputs"][final.name]["sha256"]:
        raise ValueError("Final CSV differs from upstream preparation / final-v2 lock")
    if sha256(sources["final_lock"][0]) != prep["sources"]["final_lock"]["sha256"]:
        raise ValueError("Final-v2 lock changed since master preparation")
    master = next(x for x in inv if x["role"] == "master")
    if master["rows"] != prep["counts"]["master_records"]:
        raise ValueError("Upstream master row count changed")
    if full and master["sha256"] != prep["outputs"]["works_analysis_master"]["sha256"]:
        raise ValueError("Upstream master content changed")
    return prep


def assert_unchanged(inv: list[dict]) -> None:
    for rec in inv:
        p = Path(rec["path"])
        if (p.stat().st_size, p.stat().st_mtime_ns) != (rec["size_bytes"], rec["mtime_ns"]):
            raise ValueError(f"Input changed during run: {p}")


def output_dir(path: Path, *, existing: bool = False) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink() or not path.resolve().is_relative_to(MODULE) or path.resolve() == MODULE:
        raise ValueError("Output must be a non-symlink subdirectory of nhb_revision_v1")
    if existing and not path.is_dir():
        raise FileNotFoundError(path)
    if not existing and path.exists():
        raise FileExistsError(f"Output exists; choose a new --output-dir: {path}")
    return path


def connect(threads: int = 2, memory_gib: int = 4, database: str = ":memory:", spill: Path | None = None):
    import duckdb
    if not 1 <= threads <= 16 or not 1 <= memory_gib <= 32:
        raise ValueError("threads 1..16; memory-gib 1..32")
    con = duckdb.connect(database)
    con.execute(f"SET threads={threads}")
    con.execute(f"SET memory_limit={literal(str(memory_gib) + 'GB')}")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET autoinstall_known_extensions=false")
    if spill is not None:
        con.execute(f"SET temp_directory={literal(spill)}")
        con.execute("SET max_temp_directory_size='8GB'")
    return con


def environment() -> dict:
    import duckdb
    import pyarrow
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "duckdb": duckdb.__version__, "pyarrow": pyarrow.__version__}


def scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]
