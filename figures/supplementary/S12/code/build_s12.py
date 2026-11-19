from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.2, 'ytick.labelsize': 8, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C'})
S = P / 'source_data/strict_main_pairings.csv'
with S.open() as f:
    raw = list(csv.DictReader(f))
R = [r for r in raw if r['setting'] == 'standardized' and r['corpus'] in ['AF', 'reference']]
assert len(R) == 32
for cp in ['AF', 'reference']:
    rr = [r for r in R if r['corpus'] == cp]
    for k in ['observed_share', 'expected_share']:
        assert abs(sum((float(r[k]) for r in rr)) - 1) < 1e-10
    assert abs(sum((float(r['observed_minus_expected_pp']) for r in rr))) < 1e-09
    for r in rr:
        assert abs(100 * (float(r['observed_share']) - float(r['expected_share'])) - float(r['observed_minus_expected_pp'])) < 1e-10
        for share, credit in [('observed_share', 'observed_credit'), ('expected_share', 'expected_credit')]:
            assert abs(float(r[share]) * float(r['sum_weights']) - float(r[credit])) < 1e-08
G = ['higher', 'middle', 'lower', 'outside']
LAB = ['High', 'Middle', 'Low', 'Outside']

def mat(cp, key):
    return np.array([[float(next((r for r in R if r['corpus'] == cp and r['first_group'] == g and (r['last_group'] == h)))[key]) for h in G] for g in G])
M = [mat('AF', 'expected_share') * 100, mat('reference', 'expected_share') * 100, mat('reference', 'observed_minus_expected_pp')]
blue = LinearSegmentedColormap.from_list('credit', ['#F7FAFD', '#A5BDDD', '#193F85'])
div = LinearSegmentedColormap.from_list('deviation', ['#17165E', '#F7F7F7', '#E62216'])
fig = plt.figure(figsize=(7.2, 3.35), facecolor='white')
axes = []
ims = []
limit = max((abs(float(r['observed_minus_expected_pp'])) for r in R))
for i, x in enumerate([0.1, 0.4, 0.7]):
    ax = fig.add_axes([x, 0.39, 0.25, 0.54])
    axes.append(ax)
    im = ax.imshow(M[i], cmap=blue if i < 2 else div, vmin=0 if i < 2 else -limit, vmax=100 if i < 2 else limit)
    ims.append(im)
    ax.set_xticks(range(4), LAB)
    ax.set_yticks(range(4), LAB if i == 0 else [''] * 4)
    ax.tick_params(length=0, pad=5)
    ax.set_xticks(np.arange(-0.5, 4, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 4, 1), minor=True)
    ax.grid(which='minor', color='white', lw=0.7)
    ax.tick_params(which='minor', length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    for j in range(4):
        for k in range(4):
            v = M[i][j, k]
            txt = (f'{v:.1f}' if v >= 0.1 else '<0.1' if v > 0 else '0') if i < 2 else '0.00' if abs(v) < 0.005 else f'{v:+.2f}'
            ax.text(k, j, txt, ha='center', va='center', fontsize=7.4, color='white' if (v > 60 if i < 2 else abs(v) > 0.65 * limit) else '#11151C')
axes[0].set_ylabel('First-author national output group', labelpad=8)
fig.text(0.525, 0.29, 'Last-author national output group', ha='center', fontsize=8)
cb1 = fig.colorbar(ims[0], cax=fig.add_axes([0.15, 0.16, 0.45, 0.027]), orientation='horizontal', ticks=[0, 25, 50, 75, 100])
cb1.outline.set_visible(False)
cb1.ax.tick_params(length=2, width=0.5, pad=3, labelsize=7)
cb1.set_label('Expected pairing credit (%)', labelpad=6)
cb2 = fig.colorbar(ims[2], cax=fig.add_axes([0.7, 0.16, 0.25, 0.027]), orientation='horizontal', ticks=[-2, 0, 2])
cb2.outline.set_visible(False)
cb2.ax.tick_params(length=2, width=0.5, pad=3, labelsize=7)
cb2.set_label('Observed − expected (pp)', labelpad=6)
for x, t in [(0.025, 'a'), (0.365, 'b'), (0.665, 'c')]:
    fig.text(x, 0.96, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S12.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S12_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S12_preview.png', dpi=180)
caption = 'Supplementary Fig. S12 | Team-composition expectations for first–last authorship. Expected pairing shares for AF (a) and composition-standardized non-AF studies (b), and observed-minus-expected shares for non-AF studies (c). Expectations select two distinct authors uniformly within each study’s team. Rows denote first-author and columns last-author national output groups, fixed using 2015–2019 publications; Outside denotes countries outside the fixed groups. Analyses use 5,087 AF and 332,760 non-AF studies on common support. Shares are percentages; deviations are percentage points. Within-group pairings may span countries. Observed shares and AF deviations are shown in Fig. 4.'
(P / 'caption.txt').write_text(caption + '\n')
with (P / 'plotted_values.csv').open('w') as f:
    w = csv.writer(f)
    w.writerow(['panel', 'corpus', 'first_group', 'last_group', 'value', 'unit'])
    for i, (cp, key) in enumerate([('AF', 'expected_share'), ('reference', 'expected_share'), ('reference', 'observed_minus_expected_pp')]):
        for j, g in enumerate(G):
            for k, h in enumerate(G):
                w.writerow(['abc'[i], cp, LAB[j], LAB[k], M[i][j, k], 'percent' if i < 2 else 'percentage_points'])
(P / 'validation.json').write_text(json.dumps({'old_panels': ['S20b', 'S20e', 'S20f'], 'new_figure': 'S12', 'plotted_cells': 48, 'standardized_pairing_rows_checked': 32, 'observed_and_expected_share_sums_equal_one': True, 'deviations_sum_to_zero': True, 'deviations_recomputed_from_shares': True, 'share_times_weight_equals_credit': True, 'group_direction': 'rows first author; columns last author', 'source_data_unchanged': True, 'team_selection_or_bootstrap_rerun': False, 'verification_scope': 'Aggregate pairing identities and normalization verified from exported tables; no independent reconstruction from author records.'}, indent=2))
(P / 'README.txt').write_text('S12 retains old S20b,e,f; other old S20 panels duplicate main Fig4. AF and non-AF expected shares use identical 0–100% colors; non-AF deviation colors use symmetric limits matched to maximum absolute deviation across AF and non-AF. All 48 cells retained, national High/Middle/Low/Outside naming. Values below 0.1% labelled <0.1; full precision retained in plotted_values.csv. No panel titles, horizontal color bars below. Aggregate normalization and credit identities verified; team-level expectations not rerun. Rebuild: python code/build_s12.py (numpy, matplotlib).\n')
(P / 'provenance.json').write_text(json.dumps({'source': '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F4/tables/strict_main_pairings.csv', 'sha256': hashlib.sha256(S.read_bytes()).hexdigest()}, indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S12</title><style>body{font:16px Arial;max-width:1100px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S12_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S12.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S12_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_values.csv">Plotted values</a></p>')
