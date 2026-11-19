from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, hashlib, html, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
A = read('ED_use_transitions_a.csv')
B = read('Figure3_c.csv')
T = read('Fig3c_use_transitions.csv')
U = read('Fig3d_author_groups.csv')
for r in A:
    t = next((t for t in T if t['cohort'] == 'All' and t['size_group'] == 'All' and (t['activity'] == r['activity'])))
    for k in ['N', 'n00', 'n01', 'n10', 'n11']:
        assert int(r[k]) == int(t[k])
    n = int(r['N'])
    assert sum((int(r[k]) for k in ['n00', 'n01', 'n10', 'n11'])) == n
    for key, count in [('newly_established_pct', 'n01'), ('not_reestablished_pct', 'n10')]:
        assert abs(float(r[key]) - 100 * int(r[count]) / n) < 1e-10
    assert abs(float(r['changed_pct']) - 100 * (int(r['n01']) + int(r['n10'])) / n) < 1e-10
    assert abs(float(r['net_change_pp']) - 100 * (int(r['n01']) - int(r['n10'])) / n) < 1e-10
for r in B:
    t = next((t for t in U if t['cohort'] == 'All' and t['size_group'] == 'All' and (t['author_group'] == r['author_group'])))
    for k in ['n', 'N', 'repeat_N']:
        assert int(t[k]) == int(r[k])
    assert abs(float(r['percent']) - 100 * int(r['n']) / int(r['N'])) < 1e-10
assert sum((int(r['n']) for r in B)) == 1312 and 2137 - 1312 == 825
fig = plt.figure(figsize=(7.2, 5.25), facecolor='white')
a = fig.add_axes([0.3, 0.6, 0.58, 0.32])
b = fig.add_axes([0.3, 0.13, 0.58, 0.28])
for ax in [a, b]:
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.tick_params(axis='y', length=0, pad=9)
    ax.tick_params(axis='x', length=3, width=0.6)
light = '#9CB6DA'
dark = '#193F85'
labels = ['Precomputed structures', 'Prediction runs', 'Method/tool development', 'Evaluation/validation']
for i, r in enumerate(A):
    l = float(r['not_reestablished_pct'])
    v = float(r['newly_established_pct'])
    a.barh(i, -l, height=0.45, color=light, zorder=3)
    a.barh(i, v, height=0.45, color=dark, zorder=3)
    a.text(-l - 0.45, i, str(r['n10']), ha='right', va='center', fontsize=7.8, color='#53647D')
    a.text(v + 0.45, i, str(r['n01']), ha='left', va='center', fontsize=7.8, color=dark)
    a.text(1.04, i, f"{int(r['N']):,}", transform=a.get_yaxis_transform(), va='center', ha='left', fontsize=7.6, color='#53647D')
a.text(1.04, 1.09, 'Paired n', transform=a.transAxes, ha='left', fontsize=7.6, color='#53647D')
a.axvline(0, color='#8C9BB1', lw=0.8)
a.set_xlim(-17, 17)
a.set_ylim(3.55, -0.55)
a.set_yticks(range(4), labels)
a.set_xticks([-15, -10, -5, 0, 5, 10, 15], ['15', '10', '5', '0', '5', '10', '15'])
a.set_xlabel('Institutions with changed activity evidence (%)', labelpad=7)
a.legend(handles=[Patch(color=light, label='Not re-established'), Patch(color=dark, label='Newly established')], loc='upper center', bbox_to_anchor=(0.5, -0.3), frameon=False, ncol=2, fontsize=7.5, handlelength=1.2, columnspacing=2)
blabels = ['Initial authors only', 'Initial + other authors', 'No initial-author overlap']
colors = ['#9CB6DA', '#6689BD', dark]
for i, (r, col) in enumerate(zip(B, colors)):
    v = float(r['percent'])
    b.barh(i, v, height=0.48, color=col, zorder=3)
    b.text(v + 1.2, i, f"{v:.1f}% ({int(r['n']):,})", ha='left', va='center', fontsize=8, color=dark)
b.set_xlim(0, 100)
b.set_ylim(2.6, -0.6)
b.set_yticks(range(3), blabels)
b.set_xticks([0, 25, 50, 75, 100])
b.set_xlabel('Institutions with assessable author overlap (%)', labelpad=7)
fig.text(0.035, 0.95, 'a', fontsize=11, fontweight='bold')
fig.text(0.035, 0.445, 'b', fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S8.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S8_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S8_preview.png', dpi=180)
caption = 'Supplementary Fig. S8 | Activity evidence and author continuity. a, Changes in activity evidence between institutions’ initial and first subsequent AF studies. Bars show the shares of assessable paired institutions; labels give counts and paired n gives the denominator for each activity. Activities overlap and are recorded at the study level, not attributed to individual institutions. Evidence not re-established at follow-up does not imply confirmed non-use; independent activity-label validation remains incomplete. b, Institution-affiliated author overlap among 1,312 assessable institutions out of 2,137 confirmed repeaters; 825 remain unclassified. Initial authors only does not require every initial author to return. Author overlap does not establish knowledge transfer or team replacement.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'old_figures': ['S10a', 'S13'], 'new_figure': 'S8', 'activity_transition_counts_match_upstream_summary': True, 'activity_four_cell_totals_and_all_percentages_recomputed': True, 'author_counts_match_upstream_summary': True, 'author_count_total': 1312, 'confirmed_repeaters': 2137, 'unclassified': 825, 'author_percentages_recomputed': True, 'verification_scope': 'Exported plotting data checked against upstream aggregate tables; no reclassification or institution-level reconstruction performed.', 'source_data_unchanged': True, 'png_dpi': 600}, indent=2))
(P / 'README.txt').write_text('S8 combines old S10a and S13. The redundant development transition matrix (old S10b) is retained numerically, not plotted. Source CSV files are unchanged. All activity and author counts checked against upstream aggregate tables; percentages recalculated from counts. This is an aggregate consistency check, not independent validation of activity labels or a rerun of author mapping. Rebuild with python code/build_s8.py (matplotlib required).\n')
S = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding3_v7_review_v1')
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'source': str(S / ('source_inputs/tables' if p.name.startswith('Fig3') else 'source_data') / p.name)} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S8</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S8_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S8.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S8_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
