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
from matplotlib.patches import Patch
from matplotlib.font_manager import fontManager
for n in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + n)
INK, MUTED, GRID, BLUE = ('#11151C', '#53647D', '#E8EDF3', '#173873')
PURPLE = ['#482064', '#9271AD', '#B79ACB']
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.3, 'ytick.labelsize': 7.5, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': INK})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
TOP = [read('S9_' + s + '.csv') for s in 'bcd']
D, E, F = (read('S10_a.csv'), read('S10_b.csv'), read('S10_c.csv'))
ALL = read('S9_a.csv')
for rows, context in zip(TOP, ['High', 'Middle', 'Low']):
    assert len(rows) == 5 and {r['context'] for r in rows} == {context}
    for r in rows:
        assert int(r['draws']) == 5000
        assert float(r['reference_low_pp']) < float(r['analytic_expected_G_pp']) < float(r['reference_high_pp'])
for r in D + F:
    assert int(r['draws']) == 5000
    assert abs(float(r['actual_delta_G']) - float(r['expected_delta_G']) - float(r['excess'])) < 1e-11
    assert abs(float(r['reference_low']) - float(r['expected_delta_G']) - float(r['centered_low'])) < 1e-11
for r in ALL:
    match = next((t for t in E if t['weighting'] == 'equal_country' and t['year'] == r['year']))
    assert abs(float(r['observed_G_pp']) - float(match['G_pp'])) < 1e-11
main = next((r for r in D if r['setting'] == 'main'))
for field in ['actual_delta_G', 'expected_delta_G', 'excess']:
    assert abs(float(main[field]) - float(next((r for r in F if r['variant'] == 'main'))[field])) < 1e-11
equal = {int(r['year']): float(r['G_pp']) for r in E if r['weighting'] == 'equal_country'}
assert abs(equal[2025] - equal[2021] - float(main['actual_delta_G'])) < 1e-11
assert {r['setting']: int(r['countries']) for r in D} == {'main': 68, 'N10': 91, 'N30': 57}
fig = plt.figure(figsize=(7.2, 6.25), facecolor='white')
tops = [fig.add_axes([x, 0.675, 0.25, 0.265]) for x in [0.085, 0.405, 0.725]]
d = fig.add_axes([0.14, 0.205, 0.205, 0.25])
e = fig.add_axes([0.445, 0.205, 0.21, 0.25])
f = fig.add_axes([0.795, 0.205, 0.18, 0.25])
for ax in tops + [d, e, f]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
for i, (ax, rows, color, context, n) in enumerate(zip(tops, TOP, PURPLE, ['High', 'Middle', 'Low'], [23, 22, 23])):
    rows = sorted(rows, key=lambda r: int(r['year']))
    x = np.array([int(r['year']) for r in rows])
    v = np.array([float(r['observed_G_pp']) for r in rows])
    ref = np.array([float(r['analytic_expected_G_pp']) for r in rows])
    lo = np.array([float(r['reference_low_pp']) for r in rows])
    hi = np.array([float(r['reference_high_pp']) for r in rows])
    ax.fill_between(x, lo, hi, color=color, alpha=0.18, lw=0)
    ax.plot(x, v, color=color, marker='o', ms=3, lw=1.4)
    ax.plot(x, ref, color=color, ls='--', lw=1.3)
    ax.set_xlim(2020.85, 2025.15)
    ax.set_ylim(0, 36)
    ax.set_xticks(range(2021, 2026))
    ax.set_yticks([0, 10, 20, 30])
    ax.set_xlabel('Publication year')
    ax.grid(axis='y', color=GRID, lw=0.55)
    if i == 0:
        ax.set_ylabel('Annual coverage gap (pp)')
    ax.legend(handles=[Line2D([], [], color=color, lw=2, label=f'{context} (n = {n})')], loc='upper center', bbox_to_anchor=(0.5, -0.29), frameon=False, fontsize=7.5, handlelength=1.3)
fig.legend(handles=[Line2D([], [], color=MUTED, marker='o', ms=3, lw=1.3, label='Observed'), Line2D([], [], color=MUTED, lw=1.3, ls='--', label='Expected'), Patch(facecolor=MUTED, alpha=0.18, edgecolor='none', label='95% reference range')], loc='center', bbox_to_anchor=(0.53, 0.537), ncol=3, frameon=False, fontsize=7.4, handlelength=1.6, columnspacing=1.7)

def paired(ax, rows, labels):
    for i, r in enumerate(rows):
        v, ref = (float(r['actual_delta_G']), float(r['expected_delta_G']))
        ax.plot([v, ref], [i, i], color='#A8B4C5', lw=1, zorder=1)
        ax.plot(v, i, marker='o', ms=4, color=BLUE, zorder=3)
        ax.plot(ref, i, marker='D', ms=4, mfc='white', mec=BLUE, mew=0.9, zorder=3)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_ylim(2.55, -0.55)
    ax.set_xlim(17, 26)
    ax.set_xticks([18, 22, 26])
    ax.grid(axis='x', color=GRID, lw=0.55)
    ax.tick_params(axis='y', length=0, pad=7)
    ax.set_xlabel('2021–2025 gap change (pp)', labelpad=8)
paired(d, [next((r for r in D if r['setting'] == key)) for key in ['N10', 'main', 'N30']], ['≥10\n91 countries', '≥20\n68 countries', '≥30\n57 countries'])
for i, key in enumerate(['main', 'document_type', 'team_size']):
    row = next((r for r in F if r['variant'] == key))
    residual = float(row['actual_delta_G']) - float(row['expected_delta_G'])
    assert abs(residual - float(row['excess'])) < 1e-11
    f.plot(residual, i, marker='o', ms=4.5, color=BLUE, zorder=3)
    f.annotate(f'{residual:+.2f}', (residual, i), xytext=(0, 8), textcoords='offset points', ha='center', va='bottom', fontsize=7.5, color=BLUE)
f.set_yticks(range(3), ['Primary', '+ Document\ntype', '+ Team-size\nstrata'])
f.set_ylim(2.55, -0.55)
f.set_xlim(-4, 0.45)
f.set_xticks([-4, -2, 0])
f.axvline(0, color='#8C9BB1', lw=0.8, ls='--')
f.grid(axis='x', color=GRID, lw=0.55)
f.tick_params(axis='y', length=0, pad=7)
f.set_xlabel('Observed − expected\ngap change (pp)', labelpad=8)
for w, color, marker, label in [('equal_country', BLUE, 'o', 'Equal country'), ('pooled_institution', '#6685BE', 's', 'Pooled institutions')]:
    rr = sorted([r for r in E if r['weighting'] == w], key=lambda r: int(r['year']))
    e.plot([int(r['year']) for r in rr], [float(r['G_pp']) for r in rr], color=color, marker=marker, ms=3, lw=1.3, label=label)
e.set_xlim(2020.8, 2025.2)
e.set_ylim(0, 30)
e.set_xticks([2021, 2023, 2025])
e.set_yticks([0, 10, 20, 30])
e.set_xlabel('Publication year')
e.set_ylabel('Annual coverage gap (pp)', labelpad=5)
e.grid(axis='y', color=GRID, lw=0.55)
e.legend(loc='upper center', bbox_to_anchor=(0.5, -0.39), frameon=False, fontsize=7.3, handlelength=1.5)
handles = [Line2D([], [], marker='o', ms=4, color=BLUE, ls='none', label='Observed'), Line2D([], [], marker='D', ms=4, color=BLUE, mfc='white', ls='none', label='Expected')]
for ax in [d]:
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.39), frameon=False, fontsize=7.3, handlelength=1.1, handletextpad=0.5)
for x, y, label in [(0.025, 0.966, 'a'), (0.345, 0.966, 'b'), (0.665, 0.966, 'c'), (0.025, 0.49, 'd'), (0.37, 0.49, 'e'), (0.695, 0.49, 'f')]:
    fig.text(x, y, label, fontsize=11, fontweight='bold')
fig.canvas.draw()
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S6.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S6_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S6_preview.png', dpi=180)
caption = 'Supplementary Fig. S6 | Reference checks for institutional coverage disparities. a–c, Annual coverage gaps between Higher and Lower institutional groups within High-, Middle- and Low-output countries, respectively, averaged equally across countries. Solid and dashed lines show observed and expected gaps; shading shows central 95% conditional ranges from 5,000 AF-label allocations. d, Observed and expected gap changes under minimum within-country group sizes of 10, 20 or 30 institutions. e, Annual gaps under equal-country and pooled-institution weighting. f, Observed minus expected gap changes under the primary reference and additional document-type or fixed team-size strata; negative values indicate less widening than expected. Filled circles and open diamonds in d show observed and expected values. Points in d,f are shown without intervals. All gaps are in percentage points (pp); reference ranges are not effect confidence intervals. Groups use 2015–2019 records.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'current_panels': ['S8b', 'S8c', 'S8d', 'S9a', 'S9b', 'S9c'], 'upstream_exports': ['S9_b', 'S9_c', 'S9_d', 'S10_a', 'S10_b', 'S10_c'], 'conditional_allocations': 5000, 'threshold_countries': {'10': 91, '20': 68, '30': 57}, 'national_group_countries': {'High': 23, 'Middle': 22, 'Low': 23}, 'source_data_unchanged': True, 'gap_and_residual_identities_passed': True, 'primary_specifications_match': True, 'equal_country_gap_matches_annual_reference_file': True, 'png_dpi': 600, 'simulation_rerun': False, 'panel_f': 'Observed minus expected change; -3.00, -2.75, -2.86 pp; no intervals'}, indent=2))
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'source': '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F2/source_data/' + p.name} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'README.txt').write_text('New S6 combines current manuscript S8b–d and S9a–c. Upstream export numbering differs: S9_b–d and S10_a–c. Conditional reference ranges appear only in a–c. d retains observed and analytic expected points without intervals. f shows their signed difference with a zero reference line and numerical labels; no intervals are added. The global annual S9_a source is retained for consistency checks but not plotted because main Fig2 includes it. No simulation or model re-fitting.\n\nRebuild: python code/build_s6.py (numpy, matplotlib required).\n')
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig S6</title><style>body{font:16px Arial;max-width:1150px;margin:35px auto;line-height:1.6;padding:0 24px;color:#18212d}img{width:100%}a{color:#173873}</style><img src="figures/Supplementary_Fig_S6_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S6.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S6_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
print(P / 'Review.html')
