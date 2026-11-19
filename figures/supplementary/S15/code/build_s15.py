from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, hashlib, html, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.3, 'ytick.labelsize': 7.5, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})
with (P / 'source_data/T_SI3_estimates.csv').open() as f:
    E = list(csv.DictReader(f))
G = ['L', 'M', 'H']
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
selected = []

def get(s, m, g):
    rows = [r for r in E if r['sample_id'] == s and r['metric'] == m and (r['group'] == g)]
    assert len(rows) == 1
    r = rows[0]
    assert abs(float(r['AF_mean']) - float(r['REF_mean']) - float(r['estimate'])) < 1e-09
    assert float(r['lower']) <= float(r['estimate']) <= float(r['upper'])
    return r
A = [('journal_full2025', 'high_journal75', 'Mean category ≥75th'), ('journal_full2025', 'high_journal90', 'Mean category ≥90th'), ('journal_official_Q1', 'official_best_Q1', 'Best-category Q1')]
B = [('citation_max', 'high_citation90', '≥90th percentile'), ('citation_max', 'high_citation95', '≥95th percentile')]
C = [('journal_full2025', 'journal_position', 'All journals'), ('journal_exclude_multidisciplinary', 'journal_position', 'Exclude multidisciplinary')]
fig = plt.figure(figsize=(7.2, 5.6), facecolor='white')
a = fig.add_axes([0.27, 0.64, 0.25, 0.29])
b = fig.add_axes([0.72, 0.64, 0.25, 0.29])
c = fig.add_axes([0.27, 0.18, 0.25, 0.29])
d = fig.add_axes([0.72, 0.18, 0.25, 0.29])
handles = [Line2D([], [], color=COL[g], marker='o', ls='none', ms=3.7, label=NAM[g]) for g in G]
for ax, spec, panel in [(a, A, 'a'), (b, B, 'b'), (c, C, 'c')]:
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.axvline(0, color='#8C9BB1', ls='--', lw=0.8)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.tick_params(axis='x', length=3, width=0.6)
    ends = []
    for i, (s, m, label) in enumerate(spec):
        for g, off in zip(G, [-0.18, 0, 0.18]):
            r = get(s, m, g)
            selected.append(dict(panel=panel, label=label, **r))
            v, lo, hi = [float(r[k]) for k in ['estimate', 'lower', 'upper']]
            ends.extend([lo, hi])
            ax.errorbar(v, i + off, xerr=[[v - lo], [hi - v]], fmt='o', color=COL[g], ms=3.7, lw=0.95, capsize=1.8)
    ax.set_ylim(len(spec) - 0.55, -0.55)
    ax.set_yticks(range(len(spec)), [r[2] for r in spec])
    lo = min(0, min(ends))
    hi = max(ends)
    pad = (hi - lo) * 0.08
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_xlabel('AF − non-AF\n(' + ('percentile points' if ax == c else 'percentage points') + ')', labelpad=8)
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.39), frameon=False, ncol=3, fontsize=6.8, handlelength=0.7, columnspacing=0.65)
d.spines[['top', 'right', 'left']].set_visible(False)
d.set_axisbelow(True)
d.grid(axis='x', color='#E8EDF3', lw=0.55)
d.axvline(0, color='#8C9BB1', ls='--', lw=0.8)
d.tick_params(axis='y', length=0, pad=8)
d.tick_params(axis='x', length=3, width=0.6)
ends = []
for i, g in enumerate(G):
    pair = [get('paired_12_24', m, g) for m in ['percentile_12m', 'percentile_24m']]
    for key in ['n_institutions', 'n_af_works', 'n_affiliation_links']:
        assert pair[0][key] == pair[1][key]
    for r, off, mark in zip(pair, [-0.1, 0.1], ['o', 'D']):
        selected.append(dict(panel='d', label=r['metric'], **r))
        v, lo, hi = [float(r[k]) for k in ['estimate', 'lower', 'upper']]
        ends.extend([lo, hi])
        d.errorbar(v, i + off, xerr=[[v - lo], [hi - v]], fmt=mark, color=COL[g], mfc=COL[g] if mark == 'o' else 'white', ms=4.4, lw=1, capsize=2)
d.set_yticks(range(3), [f'{NAM[g]} (n = ' + get('paired_12_24', 'percentile_12m', g)['n_institutions'] + ')' for g in G])
d.set_ylim(2.5, -0.5)
d.set_xlim(min(0, min(ends)) - 0.5, max(ends) + 0.6)
d.set_xlabel('AF − non-AF\n(percentile points)', labelpad=8)
d.legend(handles=[Line2D([], [], marker='o', color='#53647D', ls='none', label='12 months'), Line2D([], [], marker='D', mfc='white', mec='#53647D', ls='none', label='24 months')], loc='upper center', bbox_to_anchor=(0.5, -0.39), frameon=False, ncol=2, fontsize=7, handlelength=0.8, columnspacing=1)
max_shift = 0
for s in ['citation_reference_min50', 'citation_reference_min200']:
    for g in G:
        for m in ['high_citation90', 'high_citation95']:
            max_shift = max(max_shift, abs(float(get(s, m, g)['estimate']) - float(get('citation_max', m, g)['estimate'])))
assert max_shift < 0.03
for x, y, t in [(0.025, 0.96, 'a'), (0.565, 0.96, 'b'), (0.025, 0.5, 'c'), (0.565, 0.5, 'd')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S15.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S15_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S15_preview.png', dpi=180)
caption = 'Supplementary Fig. S15 | Outcome measurement and citation-window sensitivity. a, AF–non-AF differences in high-journal shares using mean-category percentile thresholds or supplier-reported best-category Q1. b, Differences in shares reaching the 90th or 95th citation percentile. Requiring ≥50 or ≥200 reference studies per percentile cell changed these estimates by <0.03 percentage points (accompanying data). c, Journal-percentile differences with and without multidisciplinary journals. d, Twelve- and twenty-four-month citation differences using identical AF studies and jointly assessable reference support; n denotes institutions. Colours identify within-country baseline output groups. Whiskers show conditional 95% intervals from 5,000 shared-study reweightings; dashed lines mark zero. Panels a,b report percentage points; c,d report percentile points.'
(P / 'caption.txt').write_text(caption + '\n')
fields = ['panel', 'label', 'sample_id', 'group', 'metric', 'estimate', 'lower', 'upper', 'n_institutions', 'n_af_works', 'n_control_works', 'n_affiliation_links', 'publication_window']
with (P / 'plotted_estimates.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(selected)
(P / 'validation.json').write_text(json.dumps({'new_figure': 'S15', 'old_panels': ['S25a–c', 'S29c'], 'plotted_estimates': len(selected), 'estimate_identities_checked': True, 'paired_window_institution_study_and_link_counts_equal': True, 'maximum_threshold_share_shift_pp_for_reference_min50_min200': max_shift, 'original_bootstrap_intervals_preserved': True, 'bootstrap_recomputed': False, 'source_csv_unchanged': True, 'verification_scope': 'Aggregate estimates, counts and selected export rows verified; underlying percentile construction, matching and bootstrap not rerun.'}, indent=2))
(P / 'README.txt').write_text('S15 combines old S25a–c and S29c. Original S29a,b duplicate ED9 and Fig5 and are omitted. Redundant citation minimum-reference threshold rows retained numerically rather than plotted. National vs institutional naming preserved: these panels use institutional Lower/Middle/Higher. Binary threshold-share differences use percentage points, percentile outcomes use percentile points. Original intervals retained, point identities checked. Paired-window sample counts checked equal; source construction defines jointly assessable comparisons. No model/bootstrap rerun. Rebuild: python code/build_s15.py (matplotlib).\n')
EBASE = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': EBASE + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S15</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S15_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S15.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S15_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_estimates.csv">Estimates and sample sizes</a></p>')
