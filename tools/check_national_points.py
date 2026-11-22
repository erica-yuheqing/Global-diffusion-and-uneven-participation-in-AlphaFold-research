"""Calculate national concentration or check the manuscript's frozen annual estimates."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def concentration(credits):
    values = np.sort(np.asarray(credits, dtype=float))
    n = len(values)
    total = values.sum()
    if not n or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Credits must be finite, non-negative numbers.")
    if not np.isfinite(total) or total <= 0:
        raise ValueError("Each year must have positive, finite total credit.")
    shares = values / total
    return {
        "af_gini": float(np.sum((2 * np.arange(1, n + 1) - n - 1) * values) / (n * total)),
        "af_hhi": float((shares * shares).sum()),
        "af_top5": float(shares[-5:].sum()),
        "af_top10": float(shares[-10:].sum()),
    }


def country_year_results(path):
    data = pd.read_csv(path, usecols=["year", "country_code", "af_credit"],
                       dtype={"country_code": str}, keep_default_na=False)
    data["country_code"] = data["country_code"].str.strip()
    if data.empty or data["country_code"].eq("").any():
        raise ValueError("Supply at least one row and a country code on every row.")
    years = pd.to_numeric(data["year"], errors="raise")
    if not years.between(1, 9999).all() or (years % 1 != 0).any():
        raise ValueError("Supply a whole calendar year on every row.")
    data["year"] = years.astype(int)
    if data.duplicated(["year", "country_code"]).any():
        raise ValueError("Supply one row per country and year.")
    countries = set(data["country_code"])
    rows = []
    for year, group in data.groupby("year", sort=True):
        if set(group["country_code"]) != countries:
            raise ValueError("Use the same country roster in every year.")
        rows.append({"year": int(year), "countries": len(countries),
                     **concentration(group["af_credit"])})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--credits-csv", type=Path, help="Use your own country-year credit table.")
    group.add_argument("--analysis-root", type=Path,
                       default=Path(__file__).resolve().parents[1] / "analysis_archives")
    args = parser.parse_args()
    if args.credits_csv is not None:
        print(json.dumps(country_year_results(args.credits_csv), indent=2, allow_nan=False))
        return

    tables = args.analysis_root / "01_national/tables"
    data = pd.read_csv(tables / "Table_S4_country_year_R_first_observation.csv", keep_default_na=False)
    reference = pd.read_csv(tables / "raw_annual_Gini.csv")
    results = []
    for row in reference.itertuples():
        credits = data.loc[data.year == row.year, "af_credit"]
        if len(credits) != 227:
            raise ValueError(f"Expected 227 country rows for {row.year}.")
        estimates = concentration(credits)
        actual = np.array(list(estimates.values()))
        expected = [getattr(row, name) for name in estimates]
        np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)
        results.append({"year": int(row.year), "af_gini": estimates["af_gini"],
                        "max_abs_error": float(max(abs(actual - expected)))})
    print(json.dumps({"status": "passed", "rows": results,
                      "reference_gini_and_intervals_recomputed": False}, indent=2))


if __name__ == "__main__":
    main()
