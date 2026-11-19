from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Validate every displayed numeric series and all frozen input hashes."""
from pathlib import Path
import csv, json, math, hashlib
import numpy as np
P = Path(__file__).resolve().parents[1]
style = json.loads((P / 'validation/style_and_layout.json').read_text())
for name, sha in style['source_csv_hashes'].items():
    assert hashlib.sha256((P / 'source_data' / name).read_bytes()).hexdigest() == sha, name
read = lambda name: list(csv.DictReader((P / 'source_data' / name).open(newline='')))
A = read('Fig2a_cumulative.csv')
B = sorted(read('Fig2b_ratio.csv'), key=lambda r: int(r['year']))
D = read('entry_activities.csv')
E = {r['group']: r for r in read('repeat_reference.csv') if r['variant'] == 'primary_entry_conditioned'}
G = read('Fig2d_benchmark_summary.csv')[0]
F = {r['group']: r for r in read('Fig2e_growth_components.csv') if r['context'] == 'All'}
T = sorted(read('annual_gap_reference.csv'), key=lambda r: int(r['year']))
draws = np.array([float(r['delta_G_pp']) for r in read('Fig2d_benchmark_draws.csv')])
assert len(draws) == 5000
records = json.loads((P / 'validation/plotted_values.json').read_text())
assert len(records) == 21
for r in records:
    if r['panel'] in ['a', 'a_inset']:
        q = sorted([v for v in A if v['group'] == r['group']], key=lambda v: int(v['year']))
        assert r['x'] == [int(v['year']) for v in q]
        assert np.allclose(r['y'], [float(v['coverage_pct']) for v in q], rtol=0, atol=1e-12)
    elif r['panel'] == 'b':
        assert r['year'] == [int(v['year']) for v in B]
        assert r['ratio'] == [float(v['R']) for v in B] and r['gap'] == [float(v['G_pp']) for v in B]
    elif r['panel'] == 'b_annual_reference':
        assert r['year'] == [int(v['year']) for v in T]
        assert np.allclose(r['observed_gap_pp'], [float(v['observed_G_pp']) for v in T], rtol=0, atol=1e-12)
        for a, b in [('expected_gap_pp', 'analytic_expected_G_pp'), ('reference_low_pp', 'reference_low_pp'), ('reference_high_pp', 'reference_high_pp')]:
            assert r[a] == [float(v[b]) for v in T]
        assert all((lo <= mu <= hi for lo, mu, hi in zip(r['reference_low_pp'], r['expected_gap_pp'], r['reference_high_pp'])))
        assert math.isclose(r['expected_gap_pp'][-1] - r['expected_gap_pp'][0], float(G['expected_delta_G']), abs_tol=1e-12)
    elif r['panel'] == 'c_activity':
        v = next((v for v in D if v['group'] == r['group'] and int(v['activity_order']) == r['activity_order']))
        assert r['supported_pct'] == float(v['supported_pct'])
        assert math.isclose(r['supported_pct'], 100 * int(v['Y']) / int(v['D']), abs_tol=1e-10)
    elif r['panel'] == 'd_repeat':
        v = E[r['group']]
        for a, b in [('observed_pct', 'observed_pct'), ('reference_pct', 'expected_pct'), ('reference_low', 'reference_lower_pct'), ('reference_high', 'reference_upper_pct'), ('including_unresolved_pct', 'registered_possible_upper_pct')]:
            assert r[a] == float(v[b])
assert {r['panel'] for r in records} == {'a', 'a_inset', 'b', 'b_annual_reference', 'c_activity', 'd_repeat'}
for r in json.loads((P / 'validation/repeat_values.json').read_text()):
    v = E[r['group']]
    assert r['N'] == int(v['N']) and r['confirmed'] == int(v['confirmed'])
    assert r['observed_minus_expected_pp'] == float(v['observed_minus_expected_pp'])
assert math.isclose(float(F['H']['observed_growth_pp']) - float(F['L']['observed_growth_pp']), float(G['actual_delta_G']), abs_tol=1e-12)
assert math.isclose(float(F['H']['analytic_expected_growth_pp']) - float(F['L']['analytic_expected_growth_pp']), float(G['expected_delta_G']), abs_tol=1e-12)
assert math.isclose(float(F['H']['r_pp']) - float(F['L']['r_pp']), float(G['excess']), abs_tol=1e-12)
print('Eight frozen source hashes, 21 plotted records, annual reference ranges and endpoint gap identities verified; 5,000 allocations retained.')
