"""Assemble the plotting handoff using frozen aggregate CSVs, without refitting analyses."""
from pathlib import Path
import csv
import hashlib
import json
import math
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parent
OLD = Path('/historical-workspace/Desktop/Findings_figures/past_version_figures/figure1_plan2_final_v1/tables')
OUT = ROOT / 'source_data'
OUT.mkdir(exist_ok=True)

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))

def write(name, rows):
    assert rows, name
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

manifest = {'version': '2026-10-25_v2', 'description': 'Frozen aggregate plotting tables, not a raw database or validation sample.', 'copied': [], 'derived': {}, 'checks': {}}

for source_root, names in [
    (OLD, [
        'concentration.csv', 'concentration_endpoint_sensitivity.csv',
        'monthly_diffusion.csv', 'annual_diffusion_counts.csv',
        'country_first_observed.csv', 'first_observed_stage_map_source.csv',
        'annual_country_credits.csv', 'annual_source_coverage.csv',
        'normalization_country_selection.csv', 'fixed_ten_composition.csv',
    ]),
    (CURRENT, [
        'matching_summary.csv', 'matching_endpoint_changes.csv',
        'matching_stratum_support.csv', 'Finding1_dynamic_results_source.csv',
        'country_normalization.csv', 'subfield_year_handoff.csv',
        'subfield_period_handoff.csv', 'subfield_period_top5_other_handoff.csv',
        'subfield_year_top5_other_handoff.csv',
    ])
]:
    for name in names:
        source = source_root / name
        destination = OUT / name
        shutil.copy2(source, destination)
        manifest['copied'].append({'file': name, 'original_path': str(source), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})

selection = sorted(read(OUT / 'normalization_country_selection.csv'), key=lambda x: int(x['baseline_rank']))
top10 = selection[:10]
expected = ['US', 'CN', 'JP', 'DE', 'GB', 'IN', 'FR', 'KR', 'IT', 'CA']
assert [x['country_code'] for x in top10] == expected
normalization = read(OUT / 'country_normalization.csv')
lookup = {(int(x['year']), x['country_code']): x for x in normalization}
names = {'US': 'United States', 'CN': 'China', 'JP': 'Japan', 'DE': 'Germany', 'GB': 'United Kingdom', 'IN': 'India', 'FR': 'France', 'KR': 'South Korea', 'IT': 'Italy', 'CA': 'Canada'}
endpoints = []
for selected in top10:
    for year in [2021, 2025]:
        code = selected['country_code']
        row = lookup[(year, code)]
        value = float(row['R'])
        assert math.isfinite(value) and value > 0
        endpoints.append({
            'baseline_rank': selected['baseline_rank'], 'country_code': code,
            'country_name': names[code], 'year': year,
            'R': row['R'], 'AF_credit': row['AF_credit'],
            'eligible_credit': row['ALL_credit'], 'AF_share': row['AF_share'],
            'eligible_share': row['ALL_share'], 'log2_R': math.log2(value),
            'selection_rule': 'Top ten by 2015-2019 eligible fractional country credit',
        })
write('figure1d_top10_endpoints.csv', endpoints)
manifest['derived']['figure1d_top10_endpoints.csv'] = 'Join baseline ranks 1-10 to raw annual R for 2021 and 2025; no field-composition weighting or confidence intervals.'

# Supplementary heatmap: baseline top 20 + Other, recomputed from pooled credits.
top20_codes = [x['country_code'] for x in selection[:20]]
heatmap = []
for year in range(2021, 2026):
    year_rows = [x for x in normalization if int(x['year']) == year]
    total_a = sum(float(x['AF_credit']) for x in year_rows)
    total_t = sum(float(x['ALL_credit']) for x in year_rows)
    for rank, code in enumerate(top20_codes + ['Other'], 1):
        if code == 'Other':
            pool = [x for x in year_rows if x['country_code'] not in top20_codes]
        else:
            pool = [lookup[(year, code)]]
        a = sum(float(x['AF_credit']) for x in pool)
        t = sum(float(x['ALL_credit']) for x in pool)
        r = (a / total_a) / (t / total_t) if t > 0 else None
        heatmap.append({'baseline_display_order': rank, 'country_code': code, 'year': year,
                        'AF_credit': a, 'eligible_credit': t, 'AF_share': a / total_a,
                        'eligible_share': t / total_t, 'R': r,
                        'n_pooled_countries': len(pool),
                        'value_status': 'undefined' if r is None else ('zero' if r == 0 else 'positive')})
write('supplementary_S5_top20_other_R.csv', heatmap)
manifest['derived']['supplementary_S5_top20_other_R.csv'] = 'Baseline top 20 plus Other pooled from remaining country credits; denominator is full eligible corpus, not screen-negative non-AF.'

# ED2a: normalize actual country credits to attributed output, dropping Unknown.
fixed = read(OUT / 'fixed_ten_composition.csv')
composition = []
fixed_codes = []
for year in range(2021, 2026):
    rows = [x for x in fixed if int(x['year']) == year and x['country_code'] not in ['Other', 'Unknown']]
    codes = [x['country_code'] for x in rows]
    if not fixed_codes:
        fixed_codes = codes
    assert codes == fixed_codes and len(codes) == 10
    known_values = {int(x['known_AF_studies']) for x in rows}
    assert len(known_values) == 1
    known = known_values.pop()
    other = known - sum(float(x['credit']) for x in rows)
    assert other >= 0
    for order, row in enumerate(rows, 1):
        credit = float(row['credit'])
        composition.append({'year': year, 'display_order': order, 'country_code': row['country_code'],
                            'fractional_credit': credit, 'known_AF_studies': known,
                            'share_of_attributed_AF': credit / known,
                            'percent_of_attributed_AF': 100 * credit / known})
    composition.append({'year': year, 'display_order': 11, 'country_code': 'Other',
                        'fractional_credit': other, 'known_AF_studies': known,
                        'share_of_attributed_AF': other / known,
                        'percent_of_attributed_AF': 100 * other / known})
    assert abs(sum(x['share_of_attributed_AF'] for x in composition if x['year'] == year) - 1) < 1e-12
write('ed2a_attributed_composition.csv', composition)
manifest['derived']['ed2a_attributed_composition.csv'] = 'Fixed-ten credit / known_AF_studies; Other = attributed credit minus fixed-ten credit. Unknown excluded from the denominator. Original fraction column deliberately not used.'

raw_endpoints = [x for x in read(OUT / 'concentration_endpoint_sensitivity.csv')
                 if x['estimand'] == 'AF_minus_C_Gini_endpoint_change' and int(x['start']) in [2021, 2022] and int(x['end']) == 2025]
assert len(raw_endpoints) == 2
write('raw_gap_endpoint_summary.csv', raw_endpoints)
manifest['derived']['raw_gap_endpoint_summary.csv'] = 'Select pre-existing raw endpoint bootstrap summaries for 2021/2022 to 2025; no subtraction of marginal interval bounds.'

concentration = read(OUT / 'concentration.csv')
raw = {int(x['year']): float(x['delta_gini']) for x in concentration}
early_fraction = (raw[2021] - raw[2022]) / (raw[2021] - raw[2025])
assert abs(early_fraction - 0.6589099102) < 1e-6
assert len(endpoints) == 20 and len(heatmap) == 105 and len(composition) == 55
assert abs(float(next(x for x in raw_endpoints if x['start'] == '2021')['point']) - (raw[2025] - raw[2021])) < 1e-12
manifest['checks'] = {
    'top10_countries': expected, 'top10_endpoint_rows': len(endpoints),
    'all_top10_endpoint_R_positive': True,
    'ED2_fixed_ten': fixed_codes, 'ED2_each_year_shares_sum_to_one': True,
    'S5_rows': len(heatmap), 'raw_narrowing_fraction_in_2021_2022': early_fraction,
    'raw_endpoint_summary_matches_annual_difference': True,
}
for name in manifest['derived']:
    manifest['derived'][name] = {'definition': manifest['derived'][name],
                                'sha256': hashlib.sha256((OUT / name).read_bytes()).hexdigest()}
(ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

zip_path = ROOT.parent / 'Finding1_修改说明与绘图底表_v2.zip'
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(ROOT.rglob('*')):
        if path.is_file():
            archive.write(path, arcname=str(Path(ROOT.name) / path.relative_to(ROOT)))
with zipfile.ZipFile(zip_path) as archive:
    assert archive.testzip() is None
print(json.dumps({'status': 'PASS', 'bundle': str(zip_path), 'bytes': zip_path.stat().st_size,
                  'csv_files': len(list(OUT.glob('*.csv'))), 'checks': manifest['checks']}, ensure_ascii=False, indent=2))
