from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import csv, json, os, html, hashlib, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.2, 'ytick.labelsize': 7.3, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
E = read('T_SI3_estimates.csv')
W = read('outcome_weighting.csv')
COM = read('T_SI6_common_composition.csv')
G = ['L', 'M', 'H']
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
A = [('journal_full2025', 'journal_position', 'Journal · Institution'), ('journal_full2025_country_equal', 'journal_position', 'Journal · Country'), ('journal_full2025_paper_equal', 'journal_position', 'Journal · Study'), ('journal_institution_year', 'journal_position', 'Journal · Institution-year'), ('citation_max', 'percentile_12m', 'Citation · Institution'), ('citation_max_country_equal', 'percentile_12m', 'Citation · Country'), ('citation_max_paper_equal', 'percentile_12m', 'Citation · Study'), ('citation_institution_year', 'percentile_12m', 'Citation · Institution-year')]
B = [(o + s, 'journal_position' if o == 'journal' else 'percentile_12m', label + ' · ' + tag) for o, label in [('journal', 'Journal'), ('citation', 'Citation')] for s, tag in [('_min5', '≥5 references'), ('_pub_quarter', 'Quarter'), ('_month', 'Month')]]
C = [('citation_max', 'percentile_12m', 'Maximum'), ('common', 'percentile_12m', 'Common')]
selected = []

def get(s, m, g):
    rows = [r for r in E + W if r['sample_id'] == s and r['metric'] == m and (r['group'] == g)]
    assert len(rows) == 1
    r = rows[0]
    v = float(r['estimate'])
    lo = float(r['lower'])
    hi = float(r['upper'])
    assert abs(float(r['AF_mean']) - float(r['REF_mean']) - v) < 1e-09
    assert lo <= v <= hi
    return r
for panel, rows in [('a', A), ('b', B), ('c', C)]:
    for s, m, label in rows:
        for g in G:
            selected.append(dict(panel=panel, label=label, **get(s, m, g)))
for r in COM:
    assert abs(float(r['AF_mean']) - float(r['REF_mean']) - float(r['difference'])) < 1e-10
fig = plt.figure(figsize=(7.2, 7.6), facecolor='white')
a = fig.add_axes([0.25, 0.5, 0.27, 0.42])
b = fig.add_axes([0.72, 0.5, 0.25, 0.42])
c = fig.add_axes([0.25, 0.13, 0.27, 0.22])
d = fig.add_axes([0.72, 0.13, 0.25, 0.22])
handles = [Line2D([], [], color=COL[g], marker='o', ls='none', ms=3.5, label=NAM[g]) for g in G]
for ax, rows, panel in [(a, A, 'a'), (b, B, 'b'), (c, C, 'c')]:
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.axvline(0, color='#8C9BB1', ls='--', lw=0.8)
    ax.tick_params(axis='y', length=0, pad=7)
    ax.tick_params(axis='x', length=3, width=0.6)
    all_lo = []
    all_hi = []
    for i, (s, m, label) in enumerate(rows):
        for g, off in zip(G, [-0.19, 0, 0.19]):
            r = get(s, m, g)
            v, lo, hi = [float(r[k]) for k in ['estimate', 'lower', 'upper']]
            all_lo.append(lo)
            all_hi.append(hi)
            ax.errorbar(v, i + off, xerr=[[v - lo], [hi - v]], fmt='o', color=COL[g], ms=3.3, lw=0.9, capsize=1.5)
    ax.set_ylim(len(rows) - 0.6, -0.6)
    ax.set_yticks(range(len(rows)), [r[2] for r in rows])
    ax.set_xlabel('AF − non-AF (percentile points)', labelpad=8)
    low = min(0, min(all_lo))
    high = max(all_hi)
    pad = (high - low) * 0.07
    ax.set_xlim(low - pad, high + pad)
    if ax in [a, b]:
        split = 3.5 if ax == a else 2.5
        ax.axhline(split, color='#DDE3EA', lw=0.65)
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.15 if ax in [a, b] else -0.28), frameon=False, ncol=3, fontsize=6.8, handlelength=0.7, columnspacing=0.7)
d.spines[['top', 'right', 'left']].set_visible(False)
d.set_axisbelow(True)
d.grid(axis='x', color='#E8EDF3', lw=0.55)
d.tick_params(axis='y', length=0, pad=7)
d.tick_params(axis='x', length=3, width=0.6)
labels = []
for i, (out, g) in enumerate([(out, g) for out in ['journal', 'citation'] for g in G]):
    r = next((r for r in COM if r['outcome'] == out and r['group'] == g))
    af, ref = (float(r['AF_mean']), float(r['REF_mean']))
    d.plot([ref, af], [i, i], color=COL[g], lw=1)
    d.plot(af, i, 'o', color=COL[g], ms=3.8)
    d.plot(ref, i, 's', mfc='white', mec=COL[g], ms=3.8)
    labels.append(('Journal' if out == 'journal' else 'Citation') + ' · ' + NAM[g])
d.axhline(2.5, color='#DDE3EA', lw=0.65)
d.set_yticks(range(6), labels)
d.set_ylim(5.65, -0.65)
d.set_xlim(0, 100)
d.set_xticks([0, 25, 50, 75, 100])
d.set_xlabel('Common-composition percentile', labelpad=8)
d.legend(handles=[Line2D([], [], marker='o', color='#53647D', ls='none', label='AF'), Line2D([], [], marker='s', mfc='white', mec='#53647D', ls='none', label='non-AF')], loc='upper center', bbox_to_anchor=(0.5, -0.28), frameon=False, ncol=2, fontsize=7, handlelength=0.9, columnspacing=1.2)
for x, y, t in [(0.025, 0.955, 'a'), (0.565, 0.955, 'b'), (0.025, 0.39, 'c'), (0.565, 0.39, 'd')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S14.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S14_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S14_preview.png', dpi=180)
caption = 'Supplementary Fig. S14 | Weighting, matching and outcome-sample sensitivity. a, AF–non-AF differences under equal institution, country, study and institution-year weighting. b, Comparisons requiring ≥5 non-AF references per cell or matching publication time by quarter or month. c, Citation differences in the maximum and common 2020–2024 outcome samples. d, Absolute outcomes after standardizing institutional groups to a common composition target; point estimates only. Colours identify within-country baseline output groups. Whiskers in a–c show conditional 95% intervals from 5,000 shared-study reweightings. Matching rules can change sample support; sample sizes are retained in the accompanying data. Journal year-window comparisons appear in Extended Data Fig. 9d.'
(P / 'caption.txt').write_text(caption + '\n')
fields = ['panel', 'label', 'sample_id', 'group', 'metric', 'estimate', 'lower', 'upper', 'n_institutions', 'n_af_works', 'weighting', 'publication_window']
with (P / 'plotted_estimates.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(selected)
(P / 'validation.json').write_text(json.dumps({'old_figure': 'S24', 'new_figure': 'S14', 'interval_estimates': len(selected), 'absolute_outcome_pairs': len(COM), 'point_estimates_AF_minus_reference_identities_passed': True, 'unique_sample_metric_group_selection_checked': True, 'all_intervals_contain_point_estimates_and_fit_axes': True, 'intervals_retained_from_original_exports': True, 'bootstrap_recomputed': False, 'source_files_unchanged': True, 'verification_scope': 'Export selection and point-estimate arithmetic verified; matching, weighting models and shared-study intervals not independently rerun.'}, indent=2))
(P / 'README.txt').write_text('New S14 retains old S24a,b,d and the citation maximum/common comparison from c. Journal window/common comparisons already in ED9d are omitted from the plot; the complete original estimate table is retained unchanged. a institution/country/study/institution-year weights; b minimum references and quarter/month matching; c 2020–2024 maximum vs common citation sample; d common composition point estimates. Group colors standardized. Original conditional intervals retained; selection uniqueness and AF-minus-reference identities checked. Sample sizes/weights in plotted_estimates.csv. No model or bootstrap rerun. Rebuild: python code/build_s14.py (matplotlib).\n')
EBASE = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': EBASE + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S14</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S14_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S14.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S14_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_estimates.csv">Estimates and sample sizes</a></p>')
