from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
from collections import Counter
import os, csv, json, html, hashlib, math
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
for n in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + n)
INK, MUTED, GRID, BLUE = ('#11151C', '#53647D', '#E8EDF3', '#193F85')
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
MARK = {'L': 'o', 'M': 's', 'H': '^'}
LABEL = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
INC = ['L', 'LM', 'UM', 'H']
NAMES = ['Low income', 'Lower-middle income', 'Upper-middle income', 'High income']
NC = [2, 12, 20, 34]
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': INK})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
A, B, R, COUNTRIES, DETAIL = [read(n) for n in ['S30a_d_coverage.csv', 'S30e_income_benchmark_summary.csv', 'S30e_income_benchmark_replicates.csv', 'country_order_and_groups.csv', 'coverage_country_institution_group_year.csv']]
assert len(A) == 72 and len(B) == 4
assert Counter((r['income_group'] for r in COUNTRIES)) == dict(zip(INC, NC))
assert {r['country'] for r in COUNTRIES if r['income_group'] == 'L'} == {'ET', 'UG'}
assert sum((int(r['baseline_institutions']) for r in A if int(r['year']) == 2025)) == 48010
for r in A:
    rr = [t for t in DETAIL if all((t[k] == r[k] for k in ['income_group', 'institution_group', 'year']))]
    assert len(rr) == int(r['countries'])
    assert sum((int(t['baseline_institutions']) for t in rr)) == int(r['baseline_institutions'])
    assert sum((int(t['AF_institutions']) for t in rr)) == int(r['AF_institutions'])
    assert abs(math.fsum((float(t['coverage_pct']) for t in rr)) / len(rr) - float(r['equal_country_coverage_pct'])) < 1e-10
for r in B:
    assert abs(float(r['observed_gap_change_pp']) - float(r['expected_gap_change_pp']) - float(r['observed_minus_expected_pp'])) < 1e-10
    draws = [t for t in R if t['income_group'] == r['income_group']]
    assert len(draws) == 5000
    lo, hi = np.quantile([float(t['centered_gap_change_pp']) for t in draws], [0.025, 0.975])
    assert abs(lo - float(r['centered_reference_low_pp'])) < 1e-10 and abs(hi - float(r['centered_reference_high_pp'])) < 1e-10
    assert abs(float(r['unshifted_reference_low_pp']) - float(r['expected_gap_change_pp']) - lo) < 1e-10
fig = plt.figure(figsize=(7.2, 7.0), facecolor='white')
positions = [[0.1, 0.735, 0.37, 0.215], [0.59, 0.735, 0.37, 0.215], [0.1, 0.425, 0.37, 0.215], [0.59, 0.425, 0.37, 0.215]]
axes = [fig.add_axes(pos) for pos in positions]
for ax, inc, name, n in zip(axes, INC, NAMES, NC):
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
    last = {}
    for g in ['L', 'M', 'H']:
        rr = sorted([r for r in A if r['income_group'] == inc and r['institution_group'] == g], key=lambda r: int(r['year']))
        x = [int(r['year']) for r in rr]
        y = [float(r['equal_country_coverage_pct']) for r in rr]
        ax.plot(x, y, color=COL[g], marker=MARK[g], ms=3.2, lw=1.35)
        last[g] = y[-1]
    ordered = sorted(last, key=last.get)
    label_y = {}
    previous = -10
    for g in ordered:
        label_y[g] = max(last[g], previous + 3.1)
        previous = label_y[g]
    if label_y[ordered[-1]] > 48:
        shift = label_y[ordered[-1]] - 48
        label_y = {g: y - shift for g, y in label_y.items()}
    for g in ordered:
        if abs(label_y[g] - last[g]) > 0.15:
            ax.plot([2025, 2025.16], [last[g], label_y[g]], color=COL[g], lw=0.6)
        ax.text(2025.21, label_y[g], f'{last[g]:.1f}', color=COL[g], fontsize=7.2, va='center')
    ax.set_xlim(2019.85, 2025.85)
    ax.set_ylim(0, 50)
    ax.set_xticks(range(2020, 2026))
    ax.set_yticks([0, 10, 20, 30, 40, 50])
    ax.grid(axis='y', color=GRID, lw=0.55)
    ax.set_xlabel('Publication year')
    ax.legend(handles=[Line2D([], [], ls='none', label=f'{name} (n = {n})')], loc='upper center', bbox_to_anchor=(0.5, -0.14 if ax in axes[:2] else -0.26), frameon=False, fontsize=7.7, handlelength=0, handletextpad=0)
axes[0].set_xlabel('')
axes[1].set_xlabel('')
axes[0].set_ylabel('Cumulative AF coverage (%)')
axes[2].set_ylabel('Cumulative AF coverage (%)')
fig.legend(handles=[Line2D([], [], color=COL[g], marker=MARK[g], ms=3.5, lw=1.3, label=LABEL[g]) for g in ['L', 'M', 'H']], loc='center', bbox_to_anchor=(0.53, 0.315), ncol=3, frameon=False, fontsize=7.6, handlelength=1.7, columnspacing=2.2)
e = fig.add_axes([0.27, 0.085, 0.66, 0.18])
e.spines[['top', 'right', 'left']].set_visible(False)
e.tick_params(length=3, width=0.6)
e.set_axisbelow(True)
e.grid(axis='x', color=GRID, lw=0.55)
for i, inc in enumerate(INC):
    r = next((r for r in B if r['income_group'] == inc))
    v, lo, hi = [float(r[k]) for k in ['observed_minus_expected_pp', 'centered_reference_low_pp', 'centered_reference_high_pp']]
    e.plot([lo, hi], [i, i], color='#A5B6CD', lw=3.5, solid_capstyle='butt', zorder=1)
    e.plot(v, i, 'o', ms=4.5, color=BLUE, zorder=3)
    e.annotate(f'{v:+.2f}', (v, i), xytext=(0, 7), textcoords='offset points', ha='center', va='bottom', fontsize=7.2, color=BLUE)
e.axvline(0, color='#8C9BB1', ls='--', lw=0.8)
e.set_yticks(range(4), NAMES)
e.tick_params(axis='y', length=0, pad=8)
e.set_ylim(3.55, -0.55)
e.set_xlim(-6.5, 8)
e.set_xticks([-6, -3, 0, 3, 6])
e.set_xlabel('Observed − expected annual gap change (pp)', labelpad=7)
e.legend(handles=[Line2D([], [], color=BLUE, marker='o', ms=4.5, ls='none', label='Observed − expected'), Line2D([], [], color='#A5B6CD', lw=3.5, label='95% reference range')], loc='upper center', bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False, fontsize=7.4, handlelength=1.5, columnspacing=2)
for x, y, label in [(0.025, 0.972, 'a'), (0.515, 0.972, 'b'), (0.025, 0.662, 'c'), (0.515, 0.662, 'd'), (0.025, 0.28, 'e')]:
    fig.text(x, y, label, fontsize=11, fontweight='bold')
fig.canvas.draw()
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S7.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S7_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S7_preview.png', dpi=180)
caption = 'Supplementary Fig. S7 | Institutional AF coverage by national income. a–d, Cumulative coverage in 2020–2025 by World Bank FY2020 income group, averaged equally across countries. Within-country institutional groups use 2015–2019 output; all 48,010 baseline institutions remain in the denominators. Labels show 2025 coverage and n denotes countries. The low-income group contains only Ethiopia and Uganda. e, Observed minus expected change in the annual Higher–Lower coverage gap from 2021 to 2025. Bars show zero-centred 95% conditional reference ranges from 5,000 AF-label allocations; points show observed residuals. These ranges are not confidence intervals around the points. Negative values indicate less gap widening than expected. Panel e uses annual coverage; a–d use cumulative coverage.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'old_figure': 'S30', 'new_figure': 'S7', 'coverage_points': 72, 'coverage_means_and_counts_recomputed_from_country_records': True, 'income_countries': dict(zip(INC, NC)), 'low_income_countries': ['ET', 'UG'], 'baseline_institutions': 48010, 'allocation_replicates_per_income_group': 5000, 'all_four_reference_ranges_recomputed_from_saved_replicates': True, 'residual_identities_passed': True, 'new_simulations_run': False, 'source_data_unchanged': True, 'endpoint_label_positions_adjusted_only': True, 'png_dpi': 600}, indent=2))
(P / 'README.txt').write_text('New S7 corresponds to current S30. Four cumulative-coverage panels use identical 0–50% limits. Insets removed; all endpoints unchanged, endpoint labels separated where needed. Income names appear below each plot; institutional-group legend below a–d. Panel e reference bars remain centred around zero rather than around observed residuals. All 72 coverage points and counts checked against country-level records; 95% reference ranges checked against all 5,000 saved allocations per income group. No new simulations or model fitting.\n\nRebuild: python code/build_s7.py (numpy, matplotlib required).\n')
root = '/historical-workspace/.codex/visualizations/2026/11/10/01a1c5e5-0c05-72a1-a396-bb7eff1839b0/income_group_analysis_20261110/'
sub = {'S30a_d_coverage.csv': 'S30_updated_Figure2_style/source_data/', 'S30e_income_benchmark_summary.csv': 'S30_updated_Figure2_style/source_data/', 'S30e_income_benchmark_replicates.csv': 'Supplementary_S30_final/source_data/', 'country_order_and_groups.csv': 'Supplementary_S30_final/source_data/', 'coverage_country_institution_group_year.csv': 'tables/'}
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'source': root + sub[p.name] + p.name} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig S7</title><style>body{font:16px Arial;max-width:1050px;margin:35px auto;line-height:1.6;padding:0 24px;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S7_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S7.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S7_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
print(P / 'Review.html')
