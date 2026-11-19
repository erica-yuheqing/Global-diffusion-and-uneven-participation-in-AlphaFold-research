from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib
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
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': INK})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
A, B, C, D = (read('S8_c.csv'), read('S8_d.csv'), read('S10_d.csv'), read('new_continuous_bin_summary.csv'))
group_sizes = []
for rows, metric in [(A, 'authors'), (B, 'partners')]:
    assert len(rows) == 18 and {r['sample'] for r in rows} == {'common_valid'}
    assert {r['metric'] for r in rows} == {metric}
    assert {int(r['countries']) for r in rows} == {67}
    assert all((abs(100 * float(r['C']) - float(r['coverage_pct'])) < 1e-10 for r in rows))
    n = sum((int(next((r['fixed_institutions'] for r in rows if r['alternative_group'] == g))) for g in ['L', 'M', 'H']))
    assert n == 47910
    group_sizes.append({g: int(next((r['fixed_institutions'] for r in rows if r['alternative_group'] == g))) for g in ['L', 'M', 'H']})
assert len(C) == 201 and {int(r['countries']) for r in C} == {68} and ({int(r['institutions']) for r in C} == {48010})
assert all((not r['lower'] and (not r['upper']) for r in C))
assert sum((int(r['fixed_N']) for r in D)) == 48010
fig = plt.figure(figsize=(7.2, 5.8), facecolor='white')
a = fig.add_axes([0.1, 0.62, 0.37, 0.32])
b = fig.add_axes([0.59, 0.62, 0.37, 0.32])
c = fig.add_axes([0.16, 0.17, 0.75, 0.31])
for ax in [a, b, c]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
    ax.grid(axis='y', color=GRID, lw=0.55)
for ax, rows in [(a, A), (b, B)]:
    for g in ['L', 'M', 'H']:
        rr = sorted([r for r in rows if r['alternative_group'] == g], key=lambda r: int(r['year']))
        x = [int(r['year']) for r in rr]
        y = [float(r['coverage_pct']) for r in rr]
        ax.plot(x, y, color=COL[g], marker=MARK[g], ms=3.3, lw=1.35, label=LABEL[g])
        ax.annotate(f'{y[-1]:.1f}', xy=(x[-1], y[-1]), xytext=(5, 0), textcoords='offset points', fontsize=7.2, color=COL[g], va='center')
    ax.set_xlim(2019.85, 2025.65)
    ax.set_ylim(0, 42)
    ax.set_xticks(range(2020, 2026))
    ax.set_yticks([0, 10, 20, 30, 40])
    ax.set_xlabel('Publication year')
a.set_ylabel('Cumulative AF coverage (%)')
b.set_ylabel('Cumulative AF coverage (%)')
fig.legend(handles=[Line2D([], [], color=COL[g], marker=MARK[g], lw=1.3, ms=3.5, label=LABEL[g]) for g in ['L', 'M', 'H']], loc='center', bbox_to_anchor=(0.53, 0.535), frameon=False, ncol=3, fontsize=7.6, handlelength=1.6, columnspacing=2)
C = sorted(C, key=lambda r: float(r['percentile']))
x = np.array([float(r['percentile']) * 100 for r in C])
y = np.array([float(r['predicted_coverage']) * 100 for r in C])
extra = np.array([r['any_country_extrapolation'].lower() == 'true' for r in C])
segment_extra = extra[:-1] | extra[1:]
starts = np.r_[0, np.flatnonzero(segment_extra[1:] != segment_extra[:-1]) + 1]
ends = np.r_[starts[1:], len(x) - 1]
for start, end in zip(starts, ends):
    c.plot(x[start:end + 1], y[start:end + 1], color=BLUE, lw=1.5, ls='--' if segment_extra[start] else '-', zorder=2)
c.scatter([float(r['percentile']) * 100 for r in D], [float(r['coverage']) * 100 for r in D], s=24, facecolors='white', edgecolors=MUTED, linewidths=0.9, zorder=3)
c.set_xlim(0, 100)
c.set_ylim(0, 90)
c.set_xticks([0, 20, 40, 60, 80, 100])
c.set_yticks([0, 20, 40, 60, 80])
c.set_ylabel('Cumulative AF coverage in 2025 (%)')
c.set_xlabel('Within-country baseline publication percentile', labelpad=7)
c.legend(handles=[Line2D([], [], color=BLUE, lw=1.5, label='Standardized'), Line2D([], [], color=BLUE, lw=1.5, ls='--', label='Extrapolated segment'), Line2D([], [], color=MUTED, marker='o', mfc='white', ms=4, ls='none', label='Observed bins')], loc='upper center', bbox_to_anchor=(0.5, -0.3), ncol=3, frameon=False, fontsize=7.4, handlelength=1.8, columnspacing=1.6)
for xx, yy, label in [(0.025, 0.965, 'a'), (0.515, 0.965, 'b'), (0.025, 0.505, 'c')]:
    fig.text(xx, yy, label, fontsize=11, fontweight='bold')
fig.canvas.draw()
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S5.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S5_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S5_preview.png', dpi=180)
caption = 'Supplementary Fig. S5 | Institutional coverage under alternative classifications and continuous publication rank. a,b, Cumulative AF coverage using within-country groups defined by baseline linked-author counts (a) or institutional-partner counts (b). Both analyses retain the same 47,910 institutions in 67 countries, with metric-specific group assignments fixed across 2020–2025. c, Coverage by within-country publication percentile in 2025 across 48,010 institutions in 68 countries. The curve is a country-adjusted spline standardized equally across countries; dashed segments extend beyond at least one country’s observed rank range. Open circles show equally weighted country means within rank bins, containing 44–68 countries. All baseline measures use 2015–2019 records. Estimates are descriptive; no confidence intervals are shown.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'current_manuscript_panels': ['S7c', 'S7d', 'S9d'], 'upstream_export_names': ['S8_c.csv', 'S8_d.csv', 'S10_d.csv'], 'common_sample': {'institutions': 47910, 'countries': 67, 'group_counts_by_metric': group_sizes}, 'continuous_rank_sample': {'institutions': 48010, 'countries': 68}, 'observed_bin_countries_range': [min((int(r['effective_countries']) for r in D)), max((int(r['effective_countries']) for r in D))], 'predictions_refitted': False, 'source_data_unchanged': True, 'rank_axis': 'original fractions multiplied by 100', 'png_dpi': 600}, indent=2))
source_root = '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F2/'
(P / 'provenance.json').write_text(json.dumps([{'file': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'source': source_root + ('tables/' if f.name.startswith('new_') else 'source_data/') + f.name} for f in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'README.txt').write_text('New S5 combines current manuscript S7c,d and S9d. Upstream exports use different numbering: S8_c.csv, S8_d.csv, S10_d.csv. No model re-fitting or classifications recalculated. Top panels use the common sample of 47,910 institutions/67 countries; continuous rank uses 48,010/68. Dashed curve segments flag extrapolation in any country. Observed rank-bin means may have different country composition; they are not estimates of the identical standardized target.\n\nRebuild: python code/build_s5.py (numpy and matplotlib required).\n')
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig S5</title><style>body{font:16px Arial;max-width:1100px;margin:35px auto;line-height:1.6;padding:0 24px;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S5_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S5.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S5_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
print(P / 'Review.html')
