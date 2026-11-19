from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
from collections import defaultdict
import csv, json, math
P = Path('/historical-workspace/.codex/visualizations/2026/11/11/01a1c9af-2c9a-7102-8d89-1bb32abfbfca/Supplementary_figures_revision_20261118/S6')
ROOT = Path('/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F2')
UP = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding2_v7_final_v1/inputs/ready')

def read(p):
    with Path(p).open() as f:
        return list(csv.DictReader(f))
check = {}
original = read(UP / 'S9_annual_benchmark_gaps.csv')
for filename in ['S9_b.csv', 'S9_c.csv', 'S9_d.csv']:
    for r in read(P / 'source_data' / filename):
        t = next((z for z in original if all((r[k] == z[k] for k in ['context', 'year']))))
        for k in ['observed_G_pp', 'analytic_expected_G_pp', 'reference_low_pp', 'reference_high_pp']:
            assert abs(float(r[k]) - float(t[k])) < 1e-10
check['15_annual_country_group_points_and_reference_ranges_match_upstream'] = True
for filename, upstream, keys in [('S10_a.csv', 'S10a_historical_thresholds.csv', ['variant', 'setting', 'context']), ('S10_c.csv', 'S10c_historical_benchmark_specs.csv', ['variant', 'setting', 'context'])]:
    original = read(UP / upstream)
    for r in read(P / 'source_data' / filename):
        t = next((z for z in original if all((r[k] == z[k] for k in keys))))
        for k in ['actual_delta_G', 'expected_delta_G', 'excess']:
            assert abs(float(r[k]) - float(t[k])) < 1e-10
check['all_threshold_and_stratification_estimates_match_upstream'] = True
annual = read(ROOT / 'tables/new_weighting_annual.csv')
for r in read(P / 'source_data/S10_b.csv'):
    vals = {z['group']: float(z['coverage_pct']) for z in annual if z['weighting'] == r['weighting'] and z['year'] == r['year']}
    assert abs(vals['H'] - vals['L'] - float(r['G_pp'])) < 1e-10
check['10_weighting_gap_points_recomputed_from_group_coverage'] = True
inst = read(ROOT / 'tables/institution_baseline_and_first_participation.csv')
lookup = {r['institution_id']: r for r in inst}
active = defaultdict(set)
with (ROOT / 'tables/new_institution_year_pool_counts.csv').open() as f:
    for r in csv.DictReader(f):
        if int(r['pool_AF']) > 0:
            active[int(r['year'])].add(r['institution_id'])

def calc(threshold, year, context=None):
    den = defaultdict(int)
    num = defaultdict(int)
    for iid, r in lookup.items():
        if r['eligible_' + str(threshold)].lower() != 'true' or r['group'] not in ['H', 'L']:
            continue
        if context is not None and r['context'] != context:
            continue
        k = (r['country'], r['group'])
        den[k] += 1
        num[k] += int(iid in active[year])
    countries = {country for country, g in den}
    rates = {g: math.fsum((num[country, g] / den[country, g] for country in countries)) / len(countries) * 100 for g in ['H', 'L']}
    return (rates['H'] - rates['L'], len(countries))
for file, context, count in [('S9_b.csv', 'High', 23), ('S9_c.csv', 'Middle', 22), ('S9_d.csv', 'Low', 23)]:
    for r in read(P / 'source_data' / file):
        v, n = calc(20, int(r['year']), context)
        assert n == count
        assert abs(v - float(r['observed_G_pp'])) < 1e-10, (context, r['year'], v, r['observed_G_pp'])
check['15_observed_country_group_gaps_recomputed_from_institution_year_records'] = True
for r in read(P / 'source_data/S10_a.csv'):
    threshold = {'N10': 10, 'main': 20, 'N30': 30}[r['setting']]
    if threshold == 10:
        assert len({r['country'] for r in lookup.values() if r['eligible_10'].lower() == 'true'}) == 91
        continue
    v2021, n = calc(threshold, 2021)
    v2025, _ = calc(threshold, 2025)
    assert n == int(r['countries']) and abs(v2025 - v2021 - float(r['actual_delta_G'])) < 1e-10
check['N20_and_N30_observed_gap_changes_recomputed_from_institution_records'] = True
check['N10_country_count_verified_against_registry'] = 91
check['N10_verification_limit'] = 'N10 estimates match historical upstream exports. The available institution-year pool table covers only 68 countries, so the 91-country N10 observed result cannot be independently reconstructed from this table; absent-country rows were not treated as zero.'
check['scope'] = 'Observed rates reconstructed; existing conditional reference results checked against upstream files. Allocation simulations not rerun.'
(P / 'Detailed_verification.json').write_text(json.dumps(check, indent=2))
print(json.dumps(check, indent=2))
