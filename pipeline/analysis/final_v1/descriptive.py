#!/usr/bin/env python3
"""Generate the pre-specified descriptive summaries for the final AF database."""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import (
    CONFIG_PATH,
    OUT_DIR,
    atomic_write_json,
    load_config,
    load_json,
    require_regular_file,
    sha256_file,
)


MASTER = OUT_DIR / "works_analysis_master.parquet"
REVIEWED = OUT_DIR / "reviewed_candidates.parquet"
VALIDATION = OUT_DIR / "validation_report.json"
RESULTS = OUT_DIR / "descriptive_results.json"
LABELS_CSV = OUT_DIR / "final_label_distribution.csv"
USE_CSV = OUT_DIR / "af_use_distribution.csv"
ADOPTION_CSV = OUT_DIR / "adoption_distribution.csv"
ANNUAL_CSV = OUT_DIR / "annual_af_use_adoption.csv"
DOMAIN_CSV = OUT_DIR / "domain_af_use_adoption.csv"
SENSITIVITY_CSV = OUT_DIR / "sensitivity_bounds.csv"
EVIDENCE_CSV = OUT_DIR / "evidence_distribution.csv"
OUTPUTS = (
    LABELS_CSV,
    USE_CSV,
    ADOPTION_CSV,
    ANNUAL_CSV,
    DOMAIN_CSV,
    SENSITIVITY_CSV,
    EVIDENCE_CSV,
    RESULTS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def refuse_existing(force: bool) -> None:
    existing = [path for path in OUTPUTS if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "Derived outputs already exist; pass --force explicitly: "
            + ", ".join(str(path) for path in existing)
        )


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def wilson_interval(successes: float, total: float, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return math.nan, math.nan
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half_width = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    ) / denominator
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def label_distribution(frame: pd.DataFrame, column: str, scopes: dict[str, pd.Series]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope_name, mask in scopes.items():
        subset = frame.loc[mask]
        counts = subset[column].fillna("<missing>").value_counts(dropna=False)
        denominator = len(subset)
        for value, count in counts.items():
            rows.append(
                {
                    "scope": scope_name,
                    "variable": column,
                    "value": value,
                    "n": int(count),
                    "denominator": int(denominator),
                    "percent": 100.0 * count / denominator if denominator else math.nan,
                }
            )
    return pd.DataFrame(rows)


def sensitivity_rows(frame: pd.DataFrame, scopes: dict[str, pd.Series]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope_name, mask in scopes.items():
        subset = frame.loc[mask]
        for variable in ("af_use_label", "adoption_eligible"):
            counts = subset[variable].value_counts()
            yes = int(counts.get("yes", 0))
            no = int(counts.get("no", 0))
            uncertain = int(counts.get("uncertain", 0))
            total = yes + no + uncertain
            resolved = yes + no
            ci_low, ci_high = wilson_interval(yes, resolved)
            rows.append(
                {
                    "scope": scope_name,
                    "variable": variable,
                    "yes": yes,
                    "no": no,
                    "uncertain": uncertain,
                    "total": total,
                    "resolved_n": resolved,
                    "resolved_yes_percent": 100.0 * yes / resolved if resolved else math.nan,
                    "resolved_yes_ci95_low_percent": 100.0 * ci_low,
                    "resolved_yes_ci95_high_percent": 100.0 * ci_high,
                    "conservative_lower_percent": 100.0 * yes / total if total else math.nan,
                    "expansive_upper_percent": 100.0 * (yes + uncertain) / total if total else math.nan,
                }
            )
    return pd.DataFrame(rows)


def annual_summary(frame: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    subset = frame.loc[
        frame["publication_year"].between(start_year, end_year, inclusive="both")
        & frame["analytical_document_type_eligible"].fillna(False)
    ].copy()
    rows: list[dict[str, object]] = []
    for year, group in subset.groupby("publication_year", dropna=False):
        row: dict[str, object] = {"publication_year": int(year), "candidate_records": int(len(group))}
        for prefix, variable in (("use", "af_use_label"), ("adoption", "adoption_eligible")):
            counts = group[variable].value_counts()
            yes = int(counts.get("yes", 0))
            no = int(counts.get("no", 0))
            uncertain = int(counts.get("uncertain", 0))
            resolved = yes + no
            ci_low, ci_high = wilson_interval(yes, resolved)
            row.update(
                {
                    f"{prefix}_yes": yes,
                    f"{prefix}_no": no,
                    f"{prefix}_uncertain": uncertain,
                    f"{prefix}_resolved_n": resolved,
                    f"{prefix}_resolved_yes_percent": 100.0 * yes / resolved if resolved else math.nan,
                    f"{prefix}_resolved_ci95_low_percent": 100.0 * ci_low,
                    f"{prefix}_resolved_ci95_high_percent": 100.0 * ci_high,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("publication_year")


def domain_summary(frame: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    subset = frame.loc[
        frame["publication_year"].between(start_year, end_year, inclusive="both")
        & frame["analytical_document_type_eligible"].fillna(False)
    ].copy()
    subset["domain_label"] = subset["domain_labels"].fillna("Unassigned").str.split("|")
    exploded = subset.explode("domain_label", ignore_index=True)
    exploded["domain_label"] = exploded["domain_label"].fillna("Unassigned").replace("", "Unassigned")
    exploded["domain_weight"] = exploded["domain_count"].where(exploded["domain_count"] > 0, 1)
    exploded["domain_weight"] = 1.0 / exploded["domain_weight"]
    rows: list[dict[str, object]] = []
    for domain, group in exploded.groupby("domain_label", dropna=False):
        row: dict[str, object] = {
            "domain_label": domain,
            "unique_candidate_records": int(group["work_id"].nunique()),
            "fractional_candidate_records": float(group["domain_weight"].sum()),
        }
        for prefix, variable in (("use", "af_use_label"), ("adoption", "adoption_eligible")):
            weighted = group.groupby(variable, dropna=False)["domain_weight"].sum()
            yes = float(weighted.get("yes", 0.0))
            no = float(weighted.get("no", 0.0))
            uncertain = float(weighted.get("uncertain", 0.0))
            resolved = yes + no
            row.update(
                {
                    f"{prefix}_yes_fractional": yes,
                    f"{prefix}_no_fractional": no,
                    f"{prefix}_uncertain_fractional": uncertain,
                    f"{prefix}_resolved_yes_percent": 100.0 * yes / resolved if resolved else math.nan,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["fractional_candidate_records", "domain_label"], ascending=[False, True]
    )


def main() -> None:
    args = parse_args()
    config = load_config()
    require_regular_file(MASTER, "analysis master")
    require_regular_file(REVIEWED, "reviewed candidates")
    require_regular_file(VALIDATION, "validation report")
    validation = load_json(VALIDATION)
    if not validation.get("ready_for_descriptive_analysis"):
        raise ValueError("Validation report contains blockers; descriptive analysis is not permitted")
    refuse_existing(args.force)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    reviewed = pd.read_parquet(REVIEWED)
    start_year = int(config["main_period"]["start_year"])
    end_year = int(config["main_period"]["end_year"])
    scopes = {
        "all_reviewed_candidates": pd.Series(True, index=reviewed.index),
        "main_period_eligible_documents": (
            reviewed["publication_year"].between(start_year, end_year, inclusive="both")
            & reviewed["analytical_document_type_eligible"].fillna(False)
        ),
    }

    labels = label_distribution(reviewed, "primary_label", scopes)
    use = label_distribution(reviewed, "af_use_label", scopes)
    adoption = label_distribution(reviewed, "adoption_eligible", scopes)
    evidence = pd.concat(
        [
            label_distribution(reviewed, "evidence_tier", scopes),
            label_distribution(reviewed, "evidence_level", scopes),
            label_distribution(reviewed, "relevance_level", scopes),
        ],
        ignore_index=True,
    )
    sensitivity = sensitivity_rows(reviewed, scopes)
    annual = annual_summary(reviewed, start_year, end_year)
    domain = domain_summary(reviewed, start_year, end_year)

    for frame, path in (
        (labels, LABELS_CSV),
        (use, USE_CSV),
        (adoption, ADOPTION_CSV),
        (annual, ANNUAL_CSV),
        (domain, DOMAIN_CSV),
        (sensitivity, SENSITIVITY_CSV),
        (evidence, EVIDENCE_CSV),
    ):
        atomic_write_csv(frame, path)

    manifest = {
        "schema_version": "af-final-descriptive-results-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reproducibility": {
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "config_path": str(CONFIG_PATH),
            "config_sha256": sha256_file(CONFIG_PATH),
        },
        "analysis_period": {"start_year": start_year, "end_year": end_year},
        "guardrails": {
            "uncertain_recoded_as_no": False,
            "screen_negative_treated_as_confirmed_non_use": False,
            "domain_counting": "fractional within work",
            "action_disagreement_included_in_action_analysis": False,
        },
        "source_files": {
            "reviewed_candidates": {"path": str(REVIEWED), "sha256": sha256_file(REVIEWED)},
            "validation_report": {"path": str(VALIDATION), "sha256": sha256_file(VALIDATION)},
        },
        "outputs": {
            path.name: {"path": str(path), "sha256": sha256_file(path)}
            for path in OUTPUTS
            if path != RESULTS
        },
        "headline_all_reviewed": json.loads(
            sensitivity.loc[
                sensitivity["scope"].eq("all_reviewed_candidates")
            ].to_json(orient="records")
        ),
    }
    atomic_write_json(RESULTS, manifest, force=args.force)
    print(f"Reviewed candidates:    {len(reviewed):,}")
    print(f"Main-period candidates: {int(scopes['main_period_eligible_documents'].sum()):,}")
    print(f"Descriptive manifest:   {RESULTS}")


if __name__ == "__main__":
    main()
