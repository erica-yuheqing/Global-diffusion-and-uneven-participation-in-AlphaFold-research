#!/usr/bin/env python3
"""Write LaTeX tabular fragments from the saved final-v1 descriptive outputs."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import OUT_DIR, PROJECT_ROOT, atomic_write_json, load_json, require_regular_file, sha256_file


TABLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "final_v1"
LABELS_CSV = OUT_DIR / "final_label_distribution.csv"
USE_CSV = OUT_DIR / "af_use_distribution.csv"
ADOPTION_CSV = OUT_DIR / "adoption_distribution.csv"
SENSITIVITY_CSV = OUT_DIR / "sensitivity_bounds.csv"
UNCERTAIN_JSON = OUT_DIR / "uncertain_use_summary.json"
LABELS_TEX = TABLE_DIR / "final_label_distribution.tex"
USE_ADOPTION_TEX = TABLE_DIR / "af_use_and_adoption.tex"
SENSITIVITY_TEX = TABLE_DIR / "sensitivity_bounds.tex"
UNCERTAIN_TEX = TABLE_DIR / "uncertain_use_reasons.tex"
MANIFEST = TABLE_DIR / "tables_manifest.json"
OUTPUTS = (LABELS_TEX, USE_ADOPTION_TEX, SENSITIVITY_TEX, UNCERTAIN_TEX, MANIFEST)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def refuse_existing(force: bool) -> None:
    existing = [path for path in OUTPUTS if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "Table outputs already exist; pass --force explicitly: "
            + ", ".join(str(path) for path in existing)
        )


def write_latex(frame: pd.DataFrame, path: Path, *, column_format: str | None = None) -> None:
    text = frame.to_latex(
        index=False,
        escape=True,
        column_format=column_format,
        float_format=lambda value: f"{value:.1f}",
        na_rep="--",
    )
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    args = parse_args()
    for path, label in (
        (LABELS_CSV, "final-label distribution"),
        (USE_CSV, "AF-use distribution"),
        (ADOPTION_CSV, "adoption distribution"),
        (SENSITIVITY_CSV, "sensitivity bounds"),
        (UNCERTAIN_JSON, "uncertain-use summary"),
    ):
        require_regular_file(path, label)
    refuse_existing(args.force)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    labels = pd.read_csv(LABELS_CSV)
    labels = labels.loc[labels["scope"].eq("all_reviewed_candidates"), ["value", "n", "percent"]]
    labels.columns = ["Final label", "n", "Percent"]
    write_latex(labels, LABELS_TEX, column_format="lrr")

    use = pd.read_csv(USE_CSV)
    adoption = pd.read_csv(ADOPTION_CSV)
    combined = pd.concat([use, adoption], ignore_index=True)
    combined = combined.loc[
        combined["scope"].eq("all_reviewed_candidates"),
        ["variable", "value", "n", "percent"],
    ]
    combined["variable"] = combined["variable"].map(
        {"af_use_label": "AF use", "adoption_eligible": "Adoption"}
    )
    combined.columns = ["Outcome", "Status", "n", "Percent"]
    write_latex(combined, USE_ADOPTION_TEX, column_format="llrr")

    sensitivity = pd.read_csv(SENSITIVITY_CSV)
    sensitivity = sensitivity.loc[
        :,
        [
            "scope",
            "variable",
            "resolved_yes_percent",
            "resolved_yes_ci95_low_percent",
            "resolved_yes_ci95_high_percent",
            "conservative_lower_percent",
            "expansive_upper_percent",
        ],
    ]
    sensitivity.columns = [
        "Scope",
        "Outcome",
        "Resolved percent",
        "CI low",
        "CI high",
        "Lower bound",
        "Upper bound",
    ]
    write_latex(sensitivity, SENSITIVITY_TEX, column_format="llrrrrr")

    uncertain_summary = load_json(UNCERTAIN_JSON)
    uncertain = pd.DataFrame(uncertain_summary["distributions"]["evidence_tier"])
    uncertain = uncertain.loc[:, ["value", "count", "percent"]]
    uncertain.columns = ["Evidence tier", "n", "Percent"]
    write_latex(uncertain, UNCERTAIN_TEX, column_format="lrr")

    manifest = {
        "schema_version": "af-final-tables-manifest-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "sources": {
            str(path): sha256_file(path)
            for path in (LABELS_CSV, USE_CSV, ADOPTION_CSV, SENSITIVITY_CSV, UNCERTAIN_JSON)
        },
        "tables": {
            path.name: {"path": str(path), "sha256": sha256_file(path)}
            for path in (LABELS_TEX, USE_ADOPTION_TEX, SENSITIVITY_TEX, UNCERTAIN_TEX)
        },
        "note": "Files contain tabular fragments only; captions and labels belong in the manuscript.",
    }
    atomic_write_json(MANIFEST, manifest, force=args.force)
    print(f"Tables written to:      {TABLE_DIR}")


if __name__ == "__main__":
    main()
