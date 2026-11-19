#!/usr/bin/env python3
"""Render publication-ready descriptive figures from saved analysis tables."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from common import OUT_DIR, PROJECT_ROOT, atomic_write_json, load_json, require_regular_file, sha256_file


FIGURE_DIR = PROJECT_ROOT / "outputs" / "figures" / "final_v1"
LABELS_CSV = OUT_DIR / "af_use_distribution.csv"
ANNUAL_CSV = OUT_DIR / "annual_af_use_adoption.csv"
UNCERTAIN_JSON = OUT_DIR / "uncertain_use_summary.json"
LABEL_FIGURE = FIGURE_DIR / "final_af_use_composition.pdf"
ANNUAL_FIGURE = FIGURE_DIR / "annual_af_use_adoption.pdf"
UNCERTAIN_FIGURE = FIGURE_DIR / "uncertainty_evidence_profile.pdf"
MANIFEST = FIGURE_DIR / "figures_manifest.json"
OUTPUTS = (LABEL_FIGURE, ANNUAL_FIGURE, UNCERTAIN_FIGURE, MANIFEST)
COLORS = {"yes": "#0072B2", "no": "#D55E00", "uncertain": "#999999"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def refuse_existing(force: bool) -> None:
    existing = [path for path in OUTPUTS if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "Figure outputs already exist; pass --force explicitly: "
            + ", ".join(str(path) for path in existing)
        )


def save_figure(figure: plt.Figure, path: Path) -> None:
    temporary = path.with_suffix(".part.pdf")
    figure.savefig(temporary, bbox_inches="tight", metadata={"Creator": "analysis/final_v1/figures.py"})
    plt.close(figure)
    temporary.replace(path)


def composition_figure(frame: pd.DataFrame) -> None:
    subset = frame.loc[frame["scope"].eq("all_reviewed_candidates")].set_index("value")
    order = ["yes", "no", "uncertain"]
    values = [int(subset.loc[value, "n"]) for value in order]
    figure, axis = plt.subplots(figsize=(6.4, 4.2), constrained_layout=True)
    bars = axis.bar(order, values, color=[COLORS[value] for value in order])
    axis.set_ylabel("Number of reviewed candidate works")
    axis.set_xlabel("Final AF-use status")
    axis.spines[["top", "right"]].set_visible(False)
    axis.bar_label(bars, labels=[f"{value:,}" for value in values], padding=3)
    save_figure(figure, LABEL_FIGURE)


def annual_figure(frame: pd.DataFrame) -> None:
    figure, axis = plt.subplots(figsize=(7.2, 4.5), constrained_layout=True)
    axis.plot(
        frame["publication_year"],
        frame["use_resolved_yes_percent"],
        marker="o",
        color="#0072B2",
        label="Confirmed AF use among resolved records",
    )
    axis.fill_between(
        frame["publication_year"],
        frame["use_resolved_ci95_low_percent"],
        frame["use_resolved_ci95_high_percent"],
        color="#0072B2",
        alpha=0.16,
        linewidth=0,
    )
    axis.plot(
        frame["publication_year"],
        frame["adoption_resolved_yes_percent"],
        marker="s",
        color="#009E73",
        label="Confirmed adoption among resolved records",
    )
    axis.set_xlabel("Publication year")
    axis.set_ylabel("Percent")
    axis.set_ylim(0, 100)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False)
    save_figure(figure, ANNUAL_FIGURE)


def uncertainty_figure(summary: dict[str, object]) -> None:
    evidence = summary["distributions"]["evidence_tier"]
    frame = pd.DataFrame(evidence).sort_values("count")
    figure, axis = plt.subplots(figsize=(7.0, 4.2), constrained_layout=True)
    bars = axis.barh(frame["value"], frame["count"], color="#CC79A7")
    axis.set_xlabel("Works with uncertain AF-use status")
    axis.set_ylabel("Available evidence tier")
    axis.spines[["top", "right"]].set_visible(False)
    axis.bar_label(bars, labels=[f"{int(value):,}" for value in frame["count"]], padding=3)
    save_figure(figure, UNCERTAIN_FIGURE)


def main() -> None:
    args = parse_args()
    for path, label in (
        (LABELS_CSV, "AF-use distribution"),
        (ANNUAL_CSV, "annual distribution"),
        (UNCERTAIN_JSON, "uncertain-use summary"),
    ):
        require_regular_file(path, label)
    refuse_existing(args.force)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    composition_figure(pd.read_csv(LABELS_CSV))
    annual_figure(pd.read_csv(ANNUAL_CSV))
    uncertainty_figure(load_json(UNCERTAIN_JSON))
    manifest = {
        "schema_version": "af-final-figures-manifest-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "sources": {
            str(path): sha256_file(path) for path in (LABELS_CSV, ANNUAL_CSV, UNCERTAIN_JSON)
        },
        "figures": {
            path.name: {"path": str(path), "sha256": sha256_file(path)}
            for path in (LABEL_FIGURE, ANNUAL_FIGURE, UNCERTAIN_FIGURE)
        },
        "format": "vector PDF",
        "palette": "colorblind-safe Okabe-Ito-derived colors",
    }
    atomic_write_json(MANIFEST, manifest, force=args.force)
    print(f"Figures written to:     {FIGURE_DIR}")


if __name__ == "__main__":
    main()
