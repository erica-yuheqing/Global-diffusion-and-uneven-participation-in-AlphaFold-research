from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
variants = ['strict_main', 'strict_international', 'full_institution', 'unique_role_country_candidate_pool', 'support_ref_1', 'support_ref_10', 'support_ref_20']
labels = ['Primary (≥5 non-AF/cell)', 'Stricter international criterion', 'Complete institution mapping', 'Single-country first/last authors', '≥1 non-AF/cell', '≥10 non-AF/cell', '≥20 non-AF/cell']
T = {v: read(v + '_delta.csv') for v in variants}
B = [r for r in read('strict_main_benchmark_change.csv') if r['setting'] == 'standardized' and r['level'] == 'group']
selected = []
for v in variants:
    for role in ['first', 'last']:
        r = next((r for r in T[v] if r['setting'] == 'standardized' and r['benchmark'] == 'author' and (r['role'] == role) and (r['entity_id'] == 'group:lower')))
        assert abs(float(r['R_AF']) - float(r['R_reference']) - float(r['delta'])) < 1e-10
        assert float(r['ci_low']) <= float(r['delta']) <= float(r['ci_high']) and int(r['valid_replicates']) >= 1900
        selected.append(r)
for r in B:
    z = {bench: next((t for t in T['strict_main'] if t['setting'] == 'standardized' and t['benchmark'] == bench and (t['role'] == r['role']) and (t['entity_id'] == r['entity_id']))) for bench in ['country', 'author']}
    assert abs(float(z['author']['delta']) - float(z['country']['delta']) - float(r['C'])) < 1e-10
    assert abs(float(r['author_delta']) - float(r['country_delta']) - float(r['C'])) < 1e-10
    assert int(r['valid_replicates']) >= 1900
assert all((-0.37 < float(r['ci_low']) <= float(r['ci_high']) < 0.16 for r in selected))
fig = plt.figure(figsize=(7.2, 6.0), facecolor='white')
a = fig.add_axes([0.3, 0.65, 0.64, 0.27])
b = fig.add_axes([0.34, 0.16, 0.25, 0.31])
c = fig.add_axes([0.7, 0.16, 0.25, 0.31])
col = '#193F85'
for ax in [a, b, c]:
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.tick_params(axis='x', length=3, width=0.6)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.axvline(0, ls='--', color='#8C9BB1', lw=0.8)
for i, g in enumerate(['higher', 'middle', 'lower', 'outside']):
    for role, marker, off in [('first', 'o', -0.12), ('last', '^', 0.12)]:
        r = next((r for r in B if r['entity_id'] == 'group:' + g and r['role'] == role))
        v, lo, hi = [float(r[k]) for k in ['C', 'ci_low', 'ci_high']]
        a.errorbar(v, i + off, xerr=[[v - lo], [hi - v]], fmt=marker, ms=4.8, mfc=col if role == 'first' else 'white', mec=col, ecolor=col, lw=1, capsize=2)
        if g == 'lower':
            a.annotate(f'{v:+.3f}', (v, i + off), xytext=(0, 8 if role == 'first' else -13), textcoords='offset points', ha='center', fontsize=7.5, color=col)
a.axhspan(1.62, 2.38, color='#F6F3FA', zorder=0)
a.set_yticks(range(4), ['High', 'Middle', 'Low', 'Outside'])
a.set_ylim(3.55, -0.55)
a.set_xlim(-0.035, 0.29)
a.set_xticks([0, 0.1, 0.2])
a.set_xlabel('Paired benchmark change (C)', labelpad=7)
a.legend(handles=[Line2D([], [], marker='o', color=col, ls='none', ms=4.8, label='First author'), Line2D([], [], marker='^', mfc='white', mec=col, ls='none', ms=4.8, label='Last author')], loc='upper center', bbox_to_anchor=(0.5, -0.29), frameon=False, ncol=2, fontsize=7.5, handlelength=1, columnspacing=2)
for ax, role in [(b, 'first'), (c, 'last')]:
    for i, vn in enumerate(variants):
        r = next((t for t in selected if t['analysis_id'] == vn and t['role'] == role))
        v, lo, hi = [float(r[k]) for k in ['delta', 'ci_low', 'ci_high']]
        ax.errorbar(v, i, xerr=[[v - lo], [hi - v]], fmt='o', ms=4.5, mfc=col if i == 0 else 'white', mec=col, ecolor=col, lw=1, capsize=2)
    ax.axhspan(-0.4, 0.4, color='#F6F3FA', zorder=0)
    ax.set_ylim(6.65, -0.65)
    ax.set_xlim(-0.37, 0.16)
    ax.set_xticks([-0.3, -0.15, 0, 0.15])
    ax.set_yticks(range(7), labels if ax == b else [''] * 7)
    ax.set_xlabel('Low-group ' + role + ' authorship (ΔRR)', labelpad=8)
fig.legend(handles=[Line2D([], [], marker='o', color=col, ls='none', ms=4.5, label='Primary'), Line2D([], [], marker='o', mfc='white', mec=col, ls='none', ms=4.5, label='Sensitivity analysis')], loc='center', bbox_to_anchor=(0.64, 0.052), frameon=False, ncol=2, fontsize=7.5, handlelength=1, columnspacing=2)
for x, y, t in [(0.035, 0.955, 'a'), (0.035, 0.5, 'b'), (0.64, 0.5, 'c')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S10.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S10_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S10_preview.png', dpi=180)
caption = 'Supplementary Fig. S10 | Authorship benchmarks and eligibility sensitivity. a, Paired change in the AF–non-AF representation contrast when replacing fractional country output with team-author credit: C = ΔRR(team) − ΔRR(output). Positive values indicate an upward shift in the contrast. National groups use 2015–2019 output; Outside comprises countries outside these groups. b,c, Low-group first- and last-author ΔRR under the team-author benchmark across eligibility and support criteria. Each variant rebuilds common support and target weights; the primary analysis requires ≥5 non-AF studies per cell. Whiskers show conditional 95% whole-study bootstrap intervals (2,000 replicates); dashed lines mark zero. Sensitivity analyses are not independent replications.'
(P / 'caption.txt').write_text(caption + '\n')
with (P / 'plotted_values.csv').open('w') as f:
    fields = ['analysis_id', 'role', 'entity_id', 'delta', 'ci_low', 'ci_high', 'n_studies_AF', 'n_studies_reference']
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(selected)
(P / 'validation.json').write_text(json.dumps({'new_figure': 'S10', 'old_panels': ['S21a', 'S18a', 'S18b'], 'benchmark_changes': len(B), 'sensitivity_estimates': len(selected), 'RR_AF_minus_RR_reference_identities_passed': True, 'paired_benchmark_change_identities_passed': True, 'all_intervals_retained_from_original_paired_or_variant_bootstrap': True, 'intervals_recomputed': False, 'models_or_bootstrap_rerun': False, 'source_csv_unchanged': True, 'verification_scope': 'Point-estimate identities and export selection checked; original bootstrap intervals retained, not independently reconstructed.'}, indent=2))
(P / 'README.txt').write_text('S10 combines old S21a and S18a,b. Uses standardized strict-main group paired changes and seven standardized author-benchmark Low-group sensitivity estimates per role. All original confidence intervals retained; no subtraction of marginal interval endpoints. Point estimates checked against RR identities and paired benchmark differences. No bootstrap rerun. Input internal group codes higher/lower are displayed as national High/Low. Complete cohort counts remain in plotted_values.csv and source tables. Rebuild: python code/build_s10.py (matplotlib).\n')
E = '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F4/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': E + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S10</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S10_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S10.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S10_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_values.csv">Sensitivity estimates and cohort counts</a></p>')
