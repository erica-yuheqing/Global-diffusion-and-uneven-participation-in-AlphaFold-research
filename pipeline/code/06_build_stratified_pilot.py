#!/usr/bin/env python3
"""Build a reproducible AlphaFold stratified pilot from the local manifest.

The primary allocation is by AF usage level. Each usage quota is distributed
across publication-year bands, then records are selected by a stable SHA-256
ordering derived from the user-supplied random seed and OpenAlex work ID.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fulltext_pipeline.common import DEFAULT_DB_PATH


DEFAULT_QUOTAS = {
    "citation_only": 60,
    "direct_use": 35,
    "mention_only": 25,
    "database_or_resource_use": 15,
    "benchmark_or_method_discussion": 15,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DB_PATH.parent.parent / "pilot" / "pilot_150.csv",
    )
    parser.add_argument("--seed", type=int, default=20260818)
    parser.add_argument(
        "--quota",
        action="append",
        metavar="USAGE=N",
        help="Override one default usage quota; may be repeated",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print allocations without writing CSV or metadata",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output and its companion metadata file",
    )
    return parser.parse_args()


def parse_quotas(overrides: list[str] | None) -> dict[str, int]:
    quotas = dict(DEFAULT_QUOTAS)
    for value in overrides or []:
        if "=" not in value:
            raise ValueError(f"Invalid --quota {value!r}; expected USAGE=N")
        usage, raw_count = value.split("=", 1)
        usage = usage.strip()
        if usage not in quotas:
            raise ValueError(f"Unknown usage level {usage!r}; choose from {sorted(quotas)}")
        count = int(raw_count)
        if count < 0:
            raise ValueError("Quotas must be non-negative")
        quotas[usage] = count
    if sum(quotas.values()) < 1:
        raise ValueError("At least one quota must be positive")
    return quotas


def year_band(year: int | None) -> str:
    if year is None:
        return "unknown"
    if year <= 2021:
        return "through_2021"
    if year >= 2025:
        return "2025_plus"
    return str(year)


def stable_hash(seed: int, work_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{work_id}".encode()).hexdigest()


def fingerprint(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def allocate_year_bands(counts: dict[str, int], quota: int) -> dict[str, int]:
    """Hamilton-style proportional allocation with one record per band when possible."""
    nonempty = {band: count for band, count in counts.items() if count > 0}
    population = sum(nonempty.values())
    if quota > population:
        raise ValueError(f"Quota {quota} exceeds stratum population {population}")
    if quota == 0:
        return {band: 0 for band in nonempty}

    raw = {band: quota * count / population for band, count in nonempty.items()}
    allocation = {
        band: min(count, int(raw[band])) for band, count in nonempty.items()
    }

    if quota >= len(nonempty):
        for band in nonempty:
            allocation[band] = max(1, allocation[band])
    else:
        allocation = {band: 0 for band in nonempty}
        for band in sorted(nonempty, key=lambda item: (-raw[item], item))[:quota]:
            allocation[band] = 1

    while sum(allocation.values()) > quota:
        candidates = [band for band, value in allocation.items() if value > 1]
        if not candidates:
            raise RuntimeError("Could not reduce year-band allocation to requested quota")
        band = max(candidates, key=lambda item: (allocation[item] - raw[item], item))
        allocation[band] -= 1

    while sum(allocation.values()) < quota:
        candidates = [
            band for band, value in allocation.items() if value < nonempty[band]
        ]
        if not candidates:
            raise RuntimeError("Could not fill year-band allocation to requested quota")
        band = max(candidates, key=lambda item: (raw[item] - allocation[item], item))
        allocation[band] += 1

    return allocation


def load_population(db_path: Path) -> list[dict[str, Any]]:
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT work_id, doi, title, publication_year, work_type,
                   af_usage_level, domain_labels, fetch_status, parse_status
            FROM works
            WHERE in_current_corpus=1
            ORDER BY work_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def build_sample(
    population: list[dict[str, Any]], quotas: dict[str, int], seed: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_usage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in population:
        usage = row.get("af_usage_level")
        if usage in quotas:
            enriched = dict(row)
            enriched["year_band"] = year_band(row.get("publication_year"))
            enriched["selection_hash"] = stable_hash(seed, row["work_id"])
            by_usage[usage].append(enriched)

    selected: list[dict[str, Any]] = []
    allocation_metadata: dict[str, Any] = {}
    for usage, quota in quotas.items():
        rows = by_usage.get(usage, [])
        if quota > len(rows):
            raise ValueError(
                f"Quota for {usage} is {quota}, but only {len(rows)} records are available"
            )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["year_band"]].append(row)
        band_counts = {band: len(items) for band, items in grouped.items()}
        band_allocations = allocate_year_bands(band_counts, quota)
        allocation_metadata[usage] = {
            "population": len(rows),
            "selected": quota,
            "year_band_population": dict(sorted(band_counts.items())),
            "year_band_selected": dict(sorted(band_allocations.items())),
        }
        for band, band_quota in band_allocations.items():
            candidates = sorted(grouped[band], key=lambda row: row["selection_hash"])
            for row in candidates[:band_quota]:
                record = dict(row)
                record["usage_population_n"] = len(rows)
                record["usage_selected_n"] = quota
                record["year_band_population_n"] = band_counts[band]
                record["year_band_selected_n"] = band_quota
                probability = band_quota / band_counts[band]
                record["inclusion_probability"] = probability
                record["sampling_weight"] = 1.0 / probability
                selected.append(record)

    selected.sort(key=lambda row: row["selection_hash"])
    for index, row in enumerate(selected, start=1):
        row["pilot_order"] = index
        row["sampling_seed"] = seed

    metadata = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sampling_seed": seed,
        "population_n": len(population),
        "selected_n": len(selected),
        "requested_quotas": quotas,
        "allocation": allocation_metadata,
        "corpus_work_id_sha256": fingerprint([row["work_id"] for row in population]),
        "pilot_work_id_sha256": fingerprint([row["work_id"] for row in selected]),
        "note": "Pilot weights are for diagnostics; do not mix this development sample with locked validation.",
    }
    return selected, metadata


def print_summary(selected: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    print(f"Population: {metadata['population_n']:,}")
    print(f"Selected:   {metadata['selected_n']:,}")
    print(f"Seed:       {metadata['sampling_seed']}")
    print(f"Corpus SHA-256: {metadata['corpus_work_id_sha256']}")
    print(f"Pilot SHA-256:  {metadata['pilot_work_id_sha256']}")
    print("\nAF usage allocation")
    usage_counts = Counter(row["af_usage_level"] for row in selected)
    for usage in DEFAULT_QUOTAS:
        population_n = metadata["allocation"][usage]["population"]
        print(f"{usage:32s} {usage_counts[usage]:>4,} / {population_n:>6,}")
    print("\nYear-band allocation within usage")
    for usage in DEFAULT_QUOTAS:
        counts = metadata["allocation"][usage]["year_band_selected"]
        rendered = ", ".join(f"{band}={count}" for band, count in counts.items())
        print(f"{usage:32s} {rendered}")


def write_outputs(
    output: Path,
    selected: list[dict[str, Any]],
    metadata: dict[str, Any],
    overwrite: bool,
) -> None:
    metadata_path = output.with_suffix(".meta.json")
    if not overwrite:
        existing = [path for path in (output, metadata_path) if path.exists()]
        if existing:
            raise FileExistsError(
                "Refusing to replace existing output; use --overwrite: "
                + ", ".join(str(path) for path in existing)
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pilot_order",
        "work_id",
        "af_usage_level",
        "publication_year",
        "year_band",
        "work_type",
        "doi",
        "title",
        "domain_labels",
        "fetch_status",
        "parse_status",
        "sampling_seed",
        "selection_hash",
        "usage_population_n",
        "usage_selected_n",
        "year_band_population_n",
        "year_band_selected_n",
        "inclusion_probability",
        "sampling_weight",
    ]
    temporary_csv = output.with_suffix(output.suffix + ".part")
    with temporary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selected)
    temporary_csv.replace(output)

    temporary_metadata = metadata_path.with_suffix(metadata_path.suffix + ".part")
    temporary_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_metadata.replace(metadata_path)
    print(f"\nPilot CSV written to {output}")
    print(f"Sampling metadata written to {metadata_path}")


def main() -> None:
    args = parse_args()
    quotas = parse_quotas(args.quota)
    population = load_population(args.db)
    selected, metadata = build_sample(population, quotas, args.seed)
    print_summary(selected, metadata)
    if args.dry_run:
        print("\nDry run: no files written")
        return
    write_outputs(args.output, selected, metadata, args.overwrite)


if __name__ == "__main__":
    main()
