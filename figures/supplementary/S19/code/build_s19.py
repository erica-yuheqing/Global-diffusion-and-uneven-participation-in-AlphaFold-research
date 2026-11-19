from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import csv, json, os, html, hashlib, zipfile, math
from collections import Counter
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.4, 'ytick.labelsize': 7.4, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
R = read('absolute_network_outcomes.csv')
F = [r for r in read('Fig6_own_connectivity_coordinates.csv') if r['coordinate_type'] == 'institution']
assert len(R) == len(F) == 9934
key = lambda r: (r['outcome'], r['institution_id'])
FR = {key(r): r for r in F}
assert len(FR) == len(F)
assert len(set((key(r) for r in R))) == len(R)
assert set(FR) == {key(r) for r in R}
expected = {('journal', 'L'): 121, ('journal', 'M'): 574, ('journal', 'H'): 5195, ('citation', 'L'): 45, ('citation', 'M'): 269, ('citation', 'H'): 3730}
assert Counter(((r['outcome'], r['group']) for r in R)) == expected
for r in R:
    t = FR[key(r)]
    assert r['group'] == t['group'] and r['country'] == t['country']
    for c in ['x', 'AF_mean', 'REF_mean']:
        assert abs(float(r[c]) - float(t[c])) < 1e-10
    assert abs(float(r['AF_mean']) - float(r['REF_mean']) - float(r['D_i'])) < 1e-09
    assert abs(float(r['D_i']) - float(t['y'])) < 1e-09
    assert 0 <= float(r['AF_mean']) <= 100 and 0 <= float(r['REF_mean']) <= 100 and (0 <= float(r['x']) < 9.5)
G = ['L', 'M', 'H']
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
AF = '#E62216'
REF = '#173873'
fig = plt.figure(figsize=(7.2, 6.4), facecolor='white')
axes = []
for i, g in enumerate(G):
    for j, out in enumerate(['journal', 'citation']):
        ax = fig.add_axes([0.12 + j * 0.48, [0.7, 0.42, 0.14][i], 0.35, 0.23])
        axes.append(ax)
        rr = [r for r in R if r['group'] == g and r['outcome'] == out]
        x = [float(r['x']) for r in rr]
        alpha = {'L': 0.7, 'M': 0.42, 'H': 0.15}[g]
        size = {'L': 10, 'M': 7, 'H': 4.5}[g]
        ax.scatter(x, [float(r['REF_mean']) for r in rr], marker='x', s=size * 0.8, color=REF, alpha=alpha, linewidths=0.45, zorder=2)
        ax.scatter(x, [float(r['AF_mean']) for r in rr], marker='o', s=size, facecolors='none', edgecolors=AF, alpha=alpha, linewidths=0.45, zorder=3)
        ax.spines[['top', 'right']].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(color='#E8EDF3', lw=0.5)
        ax.tick_params(length=3, width=0.6)
        ax.set_xlim(-0.15, 9.5)
        ax.set_ylim(-2, 102)
        ax.set_xticks([0, 3, 6, 9])
        ax.set_yticks([0, 50, 100])
        if i < 2:
            ax.set_xticklabels([])
        if j:
            ax.set_yticklabels([])
        else:
            ax.set_ylabel(NAM[g] + ' institutions\nMean percentile', labelpad=9)
        ax.text(0.97, 0.05, f'n = {len(rr):,}', transform=ax.transAxes, ha='right', va='bottom', fontsize=7.4, color='#53647D', bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.8, 'pad': 1})
        fig.text(0.025 + j * 0.51, [0.95, 0.67, 0.39][i], 'abcdef'[i * 2 + j], fontsize=11, fontweight='bold')
fig.text(0.295, 0.967, 'Journal percentile', ha='center', fontsize=9)
fig.text(0.775, 0.967, '12-month citation percentile', ha='center', fontsize=9)
fig.text(0.535, 0.075, 'Baseline ln(1 + degree)', ha='center', fontsize=8)
fig.legend(handles=[Line2D([], [], marker='o', mfc='none', mec=AF, ls='none', ms=4.5, label='AF'), Line2D([], [], marker='x', color=REF, ls='none', ms=4.5, label='non-AF')], loc='center', bbox_to_anchor=(0.535, 0.03), frameon=False, ncol=2, fontsize=8, handlelength=1, columnspacing=2)
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S19.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S19_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S19_preview.png', dpi=180)
caption = 'Supplementary Fig. S19 | Absolute publication outcomes and prior institutional connectivity. Institution-level mean journal percentiles (a,c,e) and 12-month citation percentiles (b,d,f) for AF studies and their matched non-AF references, plotted against 2015–2019 collaboration degree. Rows show Lower, Middle and Higher within-country baseline output groups. Each institution contributes one AF point and one reference point at the same connectivity value; n denotes institutions. Samples match the own-connectivity analyses in Fig. 6a. Axes are shared; point opacity decreases in larger samples to limit overplotting. These absolute outcomes complement the within-institution AF–non-AF differences in Fig. 6.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'new_figure': 'S19', 'origin': 'Absolute outcome scatter previously removed from ED10', 'institution_outcome_records': len(R), 'plotted_points': 2 * len(R), 'samples': {o: {g: expected[o, g] for g in G} for o in ['journal', 'citation']}, 'exact_institution_ID_sets_match_Fig6_own_connectivity': True, 'x_AF_mean_REF_mean_match_Fig6_export': True, 'AF_minus_REF_matches_Fig6_differences': True, 'all_points_plotted_without_subsampling_or_jitter': True, 'percentiles_within_0_100': True, 'source_files_unchanged': True, 'models_or_matching_rerun': False}, indent=2))
(P / 'README.txt').write_text('Additional S19 restores absolute-outcome scatter previously removed from ED10, separate from the six-panel S18. Each institution/outcome appears twice: AF mean and matched reference mean. Exact institution IDs, connectivity and means cross-checked against original Fig6 own-connectivity export (upstream identifier Fig7a). 9,934 institution/outcome records, 19,868 points. Journal counts L/M/H=121/574/5195; citation=45/269/3730. Common axes, no jitter, no sampling, group-dependent opacity. Two shared outcome-column headings only; no individual subplot titles. One shared legend below all panels. All points and text remain vector in PDF/SVG. No model fitting or rematching. Rebuild: python code/build_s19.py (matplotlib).\n')
EB = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/source_data/panels/'
source = {'absolute_network_outcomes.csv': EB + 'ED_SI4_b/coordinates.csv', 'Fig6_own_connectivity_coordinates.csv': EB + 'Fig7_a/coordinates.csv'}
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': source[p.name], 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S19</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S19_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S19.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S19_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
