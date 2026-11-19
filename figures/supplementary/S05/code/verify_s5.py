from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
from collections import defaultdict
import csv, math, json
P = Path('/historical-workspace/.codex/visualizations/2026/11/11/01a1c9af-2c9a-7102-8d89-1bb32abfbfca/Supplementary_figures_revision_20261118/S5')
root = Path('/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F2/tables')

def read(p):
    with Path(p).open() as f:
        return list(csv.DictReader(f))
original = read('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding2_v7_final_v1/inputs/ready/S8_alternative_trajectories.csv')
check = {}
for filename in ['S8_c.csv', 'S8_d.csv']:
    for r in read(P / 'source_data' / filename):
        rr = next((z for z in original if all((r[k] == z[k] for k in ['metric', 'sample', 'alternative_group', 'year']))))
        for key in ['C', 'coverage_pct']:
            assert abs(float(r[key]) - float(rr[key])) < 1e-12
        for key in ['countries', 'fixed_institutions']:
            assert int(r[key]) == int(rr[key])
check['all_36_alternative_trajectory_points_match_upstream'] = True
inst = read(root / 'new_continuous_institution_design.csv')
assert len(inst) == 48010 and len({r['institution_id'] for r in inst}) == 48010 and (len({r['country'] for r in inst}) == 68)
check['institution_design_48010_unique_institutions_68_countries'] = True
bins = defaultdict(list)
support = defaultdict(list)
for r in inst:
    bins[r['country'], int(r['bin'])].append(int(r['y']))
    support[r['country']].append(float(r['percentile']))
for r in read(P / 'source_data/new_continuous_bin_summary.csv'):
    k = int(r['bin'])
    records = [v for (country, b), v in bins.items() if b == k]
    assert len(records) == int(r['effective_countries'])
    assert sum(map(len, records)) == int(r['fixed_N'])
    assert sum((sum(v) for v in records)) == int(r['AF_N'])
    assert abs(math.fsum((sum(v) / len(v) for v in records)) / len(records) - float(r['coverage'])) < 1e-12
check['all_10_observed_bin_points_recomputed_from_institution_records'] = True
pred = defaultdict(list)
for r in read(root / 'new_continuous_country_predictions.csv'):
    pred[round(float(r['percentile']), 12)].append(float(r['predicted_coverage']))
for r in read(P / 'source_data/S10_d.csv'):
    x = float(r['percentile'])
    vals = pred[round(x, 12)]
    assert len(vals) == 68
    assert abs(math.fsum(vals) / 68 - float(r['predicted_coverage'])) < 1e-12
    n = sum((min(v) - 1e-12 <= x <= max(v) + 1e-12 for v in support.values()))
    assert n == int(r['countries_with_observed_percentile_support'])
    assert (n < 68) == (r['any_country_extrapolation'].lower() == 'true')
check['all_201_standardized_points_recomputed_from_68_country_predictions'] = True
check['all_201_support_and_extrapolation_flags_verified_against_institution_records'] = True
check['scope'] = 'Existing trajectory exports, institution design records, country-specific prediction records and plotting transformations checked. Original AF detection and model fitting not rerun.'
(P / 'Detailed_verification.json').write_text(json.dumps(check, indent=2))
print(json.dumps(check, indent=2))
