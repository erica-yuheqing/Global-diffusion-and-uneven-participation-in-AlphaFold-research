"""Full annual provider universe -> category percentiles -> one source/year.

This is a derived SJR position, never an official CiteScore percentile.
"""
from collections import defaultdict
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from import_scimago import parse, match_sources, frozen_inputs
from collect import HERE, require, sha

ROOT = HERE.parents[2]
RANKING = ROOT / "ranking"


def category_positions(records, categories):
    eligible = records[records.provider_type.eq("journal") & records.sjr.notna() & ~records.csv_quote_warning]
    cols = ["scimago_source_id", "metric_year", "sjr"]
    long = categories.merge(eligible[cols], on=["scimago_source_id", "metric_year"], validate="many_to_one")
    long = long[~long.category.str.strip().isin(["", "-", "NA", "N/A"])].copy()
    require(not long[["scimago_source_id", "metric_year", "category"]].duplicated().any(), "Duplicate journal/category")
    groups = long.groupby(["metric_year", "category"])
    long["category_journals"] = groups.sjr.transform("size")
    long["ascending_midrank"] = groups.sjr.rank(method="average", ascending=True)
    long["sjr_category_percentile"] = np.where(long.category_journals.gt(1),
        100 * (long.ascending_midrank - 1) / (long.category_journals - 1), np.nan)
    aggregate = long.groupby(["scimago_source_id", "metric_year"]).agg(
        journal_position=("sjr_category_percentile", "mean"),
        best_category_position=("sjr_category_percentile", "max"),
        usable_categories=("sjr_category_percentile", "count"),
        category_count=("category", "size"),
        mean_official_category_Q1=("category_quartile", lambda x: np.mean(x.dropna().eq("Q1")) if len(x.dropna()) else np.nan)).reset_index()
    all_positions = records[["scimago_source_id", "metric_year", "provider_type", "sjr", "best_quartile", "csv_quote_warning"]].merge(
        aggregate, on=["scimago_source_id", "metric_year"], how="left", validate="one_to_one")
    all_positions["official_best_Q1"] = np.where(all_positions.best_quartile.notna(), all_positions.best_quartile.eq("Q1").astype(float), np.nan)
    return long, all_positions


def annual_bridge(metadata, records, positions, year):
    # The preliminary importer required both current and annual journal types.
    # Here the annual provider type is authoritative for historical eligibility.
    bridge = match_sources(metadata, records, year)
    bridge = bridge.merge(positions.drop(columns=["sjr", "best_quartile"]), on=["scimago_source_id", "metric_year"], how="left", validate="many_to_one")
    valid = (bridge.scimago_source_id.notna() & bridge.provider_type.eq("journal") &
             bridge.sjr.notna() & bridge.csv_quote_warning.eq(False) & bridge.journal_position.notna())
    bridge["position_available"] = valid
    bridge["position_status"] = bridge.match_status
    bridge.loc[valid, "position_status"] = "annual_journal_position_available"
    for col in ["journal_position", "best_category_position", "official_best_Q1", "mean_official_category_Q1"]:
        bridge.loc[~valid, col] = np.nan
    require(bridge.source_id.is_unique, "Source/year bridge expanded")
    return bridge


def build_annual(d):
    metadata, needs, _, pins = frozen_inputs()
    records_all, category_all, provider_positions, bridges, audits, issues = [], [], [], [], [], []
    hashes = set()
    for year in range(2015, 2026):
        path = RANKING / f"scimagojr {year}.csv"
        records, categories, invalid, header = parse(path, year)
        digest = sha(path)
        require(digest not in hashes, "Annual files are identical")
        hashes.add(digest); pins[str(path)] = digest
        # '-' is a declared missing placeholder, not a failed ISSN checksum.
        invalid = invalid.copy()
        missing = invalid.issue.eq("invalid_issn") & invalid.raw_value.str.strip().isin(["-", "NA", "N/A"])
        invalid.loc[missing, "issue"] = "missing_issn_placeholder"
        invalid["metric_year"] = year
        long, pos = category_positions(records, categories)
        bridge = annual_bridge(metadata, records, pos, year)
        selected = needs[needs.year.eq(year)].merge(bridge[["source_id", "position_available"]], on="source_id", how="left", validate="one_to_one")
        audits.append(dict(year=year, provider_rows=len(records), journal_rows=int(records.provider_type.eq("journal").sum()),
            sjr_present_rows=int(records.sjr.notna().sum()), category_rows=len(categories), category_rank_rows=len(long),
            quote_warning_rows=int(records.csv_quote_warning.sum()), invalid_issn_tokens=int(invalid.issue.eq("invalid_issn").sum()),
            missing_issn_placeholders=int(missing.sum()), required_source_years=len(selected),
            source_years_with_position=int(selected.position_available.sum()),
            ambiguous_source_ids=int(bridge.match_status.eq("ambiguous_provider_ids_quarantined").sum()),
            csv_columns=len(header), raw_sha256=digest))
        (d / "raw").mkdir(exist_ok=True)
        shutil.copyfile(path, d / "raw" / f"scimago_{year}.csv")
        require(sha(d / "raw" / f"scimago_{year}.csv") == digest, "Annual copy differs")
        records_all.append(records); category_all.append(long); provider_positions.append(pos); bridges.append(bridge); issues.append(invalid)
        print(f"Annual journal positions: {year}; provider records {len(records):,}", flush=True)
    pd.concat(records_all, ignore_index=True).to_parquet(d / "data/provider_records.parquet", index=False)
    pd.concat(category_all, ignore_index=True).to_parquet(d / "data/category_positions.parquet", index=False)
    pd.concat(provider_positions, ignore_index=True).to_parquet(d / "data/provider_journal_positions.parquet", index=False)
    joined = pd.concat(bridges, ignore_index=True)
    require(not joined[["source_id", "metric_year"]].duplicated().any(), "Combined source-year duplicates")
    joined.to_parquet(d / "data/journal_year_position.parquet", index=False)
    pd.concat(issues, ignore_index=True).to_csv(d / "tables/format_issn_review.csv", index=False)
    pd.DataFrame(audits).to_csv(d / "tables/annual_import_audit.csv", index=False)
    joined[~joined.position_available].to_parquet(d / "data/unavailable_source_years.parquet", index=False)
    return pins
