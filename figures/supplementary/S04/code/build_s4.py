from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile
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
BLUE, RED, INK, MUTED, GRID = ('#173873', '#E62216', '#11151C', '#53647D', '#E8EDF3')
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': INK})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
A, B, C = (read('S6b.csv'), read('S6c.csv'), read('S6d.csv'))
specs = ['count_only', 'count_composition', 'count_composition_known_country']
labels = ['Count only', 'Count + composition', '+ Known-country restriction']
colors = ['#173873', '#6685BE', '#8FAAD3']
marks = ['o', 's', 'D']
styles = ['-', '--', ':']
for r in A:
    assert int(r['replicates']) == 2000
    assert float(r['lower']) <= float(r['point']) <= float(r['upper'])
    assert abs(float(r['AF_gini']) - float(r['matched_non_AF_mean']) - float(r['point'])) < 1e-12
for r in B:
    vals = {int(t['year']): float(t['point']) for t in A if t['spec'] == r['spec']}
    assert abs(vals[int(r['end'])] - vals[int(r['start'])] - float(r['point'])) < 1e-12
for r in C:
    assert int(r['assigned_n']) + int(r['unknown_n']) == int(r['n'])
    assert abs(int(r['assigned_n']) / int(r['n']) - float(r['coverage'])) < 1e-12
fig = plt.figure(figsize=(7.2, 5.7), facecolor='white')
a = fig.add_axes([0.12, 0.64, 0.83, 0.29])
b = fig.add_axes([0.25, 0.19, 0.34, 0.29])
c = fig.add_axes([0.72, 0.19, 0.25, 0.29])
for ax in [a, b, c]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
for i, s in enumerate(specs):
    rr = sorted([r for r in A if r['spec'] == s], key=lambda r: int(r['year']))
    x = np.array([int(r['year']) for r in rr])
    v = np.array([float(r['point']) for r in rr])
    lo = np.array([float(r['lower']) for r in rr])
    hi = np.array([float(r['upper']) for r in rr])
    a.plot(x, v, marker=marks[i], markersize=3.8, lw=1.3, ls=styles[i], color=colors[i], label=labels[i], zorder=5 - i)
    a.fill_between(x, lo, hi, color=colors[i], alpha=0.1, lw=0, zorder=0)
a.set_xlim(2020.85, 2025.15)
a.set_xticks(range(2021, 2026))
a.set_ylim(0, 0.045)
a.set_yticks([0, 0.01, 0.02, 0.03, 0.04])
a.set_ylabel('AF − matched non-AF Gini')
a.set_xlabel('Publication year')
a.grid(axis='y', lw=0.55, color=GRID)
a.legend(loc='upper center', bbox_to_anchor=(0.5, -0.26), ncol=3, frameon=False, fontsize=7.4, handlelength=2, columnspacing=1.7)
for i, s in enumerate(specs):
    for start, dy, filled in [(2021, -0.12, True), (2022, 0.12, False)]:
        r = next((r for r in B if r['spec'] == s and int(r['start']) == start))
        v, lo, hi = (float(r[k]) for k in ['point', 'lower', 'upper'])
        b.errorbar(v, i + dy, xerr=[[v - lo], [hi - v]], fmt='o' if filled else 'D', ms=4, mfc=colors[i] if filled else 'white', mec=colors[i], mew=0.85, ecolor=colors[i], elinewidth=1, capsize=2, zorder=3)
b.set_yticks(range(3), ['Count only', 'Count +\ncomposition', '+ Known-country\nrestriction'])
b.set_ylim(2.5, -0.5)
b.set_xlim(-0.016, 0.016)
b.set_xticks([-0.01, 0, 0.01])
b.axvline(0, color='#8C9BB1', ls='--', lw=0.7)
b.grid(axis='x', color=GRID, lw=0.55)
b.tick_params(axis='y', length=0, pad=8)
b.set_xlabel('Change in matched Gini gap\n(2025 − start year)', labelpad=8)
b.legend(handles=[Line2D([], [], marker='o', ms=4, color=MUTED, ls='none', label='2021–2025'), Line2D([], [], marker='D', ms=4, mfc='white', color=MUTED, ls='none', label='2022–2025')], loc='upper center', bbox_to_anchor=(0.5, -0.37), ncol=2, frameon=False, fontsize=7.3, handletextpad=0.5, columnspacing=1.1)
for g, color, mark in [('AF', RED, 'o'), ('C', BLUE, 's')]:
    rr = sorted([r for r in C if r['group'] == g], key=lambda r: int(r['year']))
    c.plot([int(r['year']) for r in rr], [float(r['coverage']) * 100 for r in rr], color=color, marker=mark, lw=1.25, ms=3.3, label='AF' if g == 'AF' else 'non-AF')
c.set_xlim(2019.8, 2025.2)
c.set_xticks([2020, 2022, 2024])
c.set_ylim(0, 103)
c.set_yticks([0, 25, 50, 75, 100])
c.set_ylabel('Studies with country information (%)', labelpad=5)
c.set_xlabel('Publication year')
c.grid(axis='y', color=GRID, lw=0.55)
c.legend(loc='upper center', bbox_to_anchor=(0.5, -0.37), ncol=2, frameon=False, fontsize=7.3, handlelength=1.4, columnspacing=1.1)
for x, y, label in [(0.025, 0.96, 'a'), (0.025, 0.515, 'b'), (0.645, 0.515, 'c')]:
    fig.text(x, y, label, fontsize=11, fontweight='bold')
fig.canvas.draw()
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S4.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S4_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S4_preview.png', dpi=180)
caption = 'Supplementary Fig. S4 | Sensitivity of national concentration comparisons. a, AF–non-AF Gini gaps after matching study counts alone, adding subfield and document-type composition, or further restricting to studies with known country information. b, Changes in matched gaps from 2021 or 2022 to 2025; negative values indicate narrowing. Shading in a and whiskers in b show central 95% ranges across 2,000 non-AF matching draws with AF output held fixed, rather than full confidence intervals. c, Studies with identifiable country information as a percentage of each corpus. Non-AF denotes screen-negative reference studies.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'old_figure': 'S6', 'new_figure': 'S4', 'annual_gap_identity_passed': True, 'endpoint_changes_reconciled': True, 'geographic_counts_reconciled': True, 'source_data_unchanged': True, 'matching_draws': 2000, 'png_dpi': 600}, indent=2))
(P / 'provenance.json').write_text(json.dumps([{'file': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'source': '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F1/source_data/' + f.name} for f in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'README.txt').write_text('New S4 corresponds to old S6. Old S6b,c,d become a,b,c. Old S6a is retained numerically and is not plotted. Main Fig1 caption reference to the full-scale S6a series must be removed or updated when manuscript citations are synchronized. All source estimates and ranges retained unchanged. Matching ranges condition on fixed AF output.\n\nRebuild: python code/build_s4.py (numpy and matplotlib required).\n')
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig S4</title><style>body{font:16px Arial;max-width:1100px;margin:35px auto;line-height:1.6;padding:0 24px;color:#18212d}img{width:100%}a{color:#173873}</style><img src="figures/Supplementary_Fig_S4_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S4.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S4_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
print(P / 'Review.html')
