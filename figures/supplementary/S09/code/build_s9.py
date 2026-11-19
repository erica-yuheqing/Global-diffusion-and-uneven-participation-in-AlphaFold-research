from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
from collections import Counter
import os, csv, json, html, hashlib, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.2, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
I, S, D, W, Q = [read(n) for n in ['institution_opportunities.csv', 'reference_summary.csv', 'reference_draws.csv', 'S4_common_windows.csv', 'institution_reference_predictions.csv']]
G = ['L', 'M', 'H']
C = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85', 'All': '#53647D'}
N = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher', 'All': 'All'}
counts = {'L': 176, 'M': 630, 'H': 3903, 'All': 4955}
assert len(I) == 4955
for g in G:
    rr = [r for r in I if r['size_group'] == g]
    assert len(rr) == counts[g]
    assert np.median([int(r['opportunities']) for r in rr]) == {'L': 2, 'M': 7, 'H': 53}[g]
for r in S:
    g = r['group']
    qq = [t for t in Q if t['variant'] == r['variant'] and (g == 'All' or t['size_group'] == g)]
    assert len(qq) == int(r['N'])
    assert sum((t['observed_repeat'] == 'True' for t in qq)) == int(r['confirmed'])
    assert abs(np.mean([float(t['expected_repeat']) for t in qq]) * 100 - float(r['expected_pct'])) < 1e-09
    assert abs(float(r['observed_pct']) - float(r['expected_pct']) - float(r['observed_minus_expected_pp'])) < 1e-09
    dd = [float(t[g]) for t in D if t['variant'] == r['variant']]
    assert len(dd) == int(r['replicates'])
    lo, hi = np.quantile(dd, [0.025, 0.975])
    assert abs(lo - float(r['reference_lower_pct'])) < 1e-09 and abs(hi - float(r['reference_upper_pct'])) < 1e-09
ww = [r for r in W if r['cohort'] == 'All' and r['size_group'] in G + ['All']]
assert len(ww) == 12
for r in ww:
    n, c, u, k = [int(r[t]) for t in ['N', 'C', 'U', 'known_no_event']]
    assert c + u + k == n
    if int(r['months']) == 12:
        ss = next((t for t in S if t['variant'] == 'primary_entry_conditioned' and t['group'] == r['size_group']))
        assert n == int(ss['N']) and c == int(ss['confirmed'])
        assert abs(100 * (c + u) / n - float(ss['registered_possible_upper_pct'])) < 1e-09
fig = plt.figure(figsize=(7.2, 6.25), facecolor='white')
a = fig.add_axes([0.11, 0.62, 0.35, 0.3])
b = fig.add_axes([0.61, 0.62, 0.35, 0.3])
c = fig.add_axes([0.14, 0.17, 0.32, 0.28])
d = fig.add_axes([0.61, 0.17, 0.35, 0.28])
for ax in [a, b, c, d]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='y', color='#E8EDF3', lw=0.55)
    ax.tick_params(length=3, width=0.6)
for g in G:
    x = np.sort([int(r['opportunities']) for r in I if r['size_group'] == g])
    a.step(x, np.arange(1, len(x) + 1) / len(x), where='post', color=C[g], lw=1.4)
a.set_xscale('symlog', linthresh=1)
a.set_xlim(0, max((int(r['opportunities']) for r in I)) * 1.1)
a.set_ylim(0, 1)
a.set_xticks([0, 1, 10, 100, 1000], ['0', '1', '10', '100', '1,000'])
a.set_yticks([0, 0.5, 1])
a.set_xlabel('Studies within 12 months of entry')
a.set_ylabel('Cumulative share of institutions')
handles = [Line2D([], [], color=C[g], lw=1.5, label=N[g]) for g in G]
a.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.24), ncol=3, frameon=False, fontsize=7, handlelength=1.2, columnspacing=0.9)
variants = ['primary_entry_conditioned', 'coarser_no_country_set', 'relaxed_entry_studies_only']
for g in G:
    vals = [float(next((r for r in S if r['variant'] == v and r['group'] == g))['observed_minus_expected_pp']) for v in variants]
    b.plot(range(3), vals, color=C[g], marker='o', ms=4, lw=1.25)
b.axhline(0, color='#8C9BB1', lw=0.8, ls='--')
b.set_xticks(range(3), ['Primary', 'Coarser', 'Relaxed'])
b.set_xlim(-0.25, 2.25)
b.set_ylim(-3, 6.5)
b.set_yticks([-2, 0, 2, 4, 6])
b.set_ylabel('Observed − expected repeat publication (pp)')
b.set_xlabel('Allocation specification')
b.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.24), ncol=3, frameon=False, fontsize=7, handlelength=1.2, columnspacing=0.9)
for i, g in enumerate(G):
    r = next((r for r in S if r['variant'] == 'next_complete_calendar_year' and r['group'] == g))
    obs, exp, lo, hi = [float(r[k]) for k in ['observed_pct', 'expected_pct', 'reference_lower_pct', 'reference_upper_pct']]
    c.plot([obs, exp], [i, i], color=C[g], lw=1)
    c.errorbar(exp, i, xerr=[[exp - lo], [hi - exp]], fmt='D', mfc='white', mec=C[g], ecolor=C[g], ms=4.5, capsize=2, lw=1)
    c.plot(obs, i, 'o', color=C[g], ms=4.5)
c.set_yticks(range(3), [N[g] for g in G])
c.set_ylim(2.55, -0.55)
c.set_xlim(0, 60)
c.set_xticks([0, 20, 40, 60])
c.set_xlabel('Repeat publication in next calendar year (%)')
c.grid(False)
c.grid(axis='x', color='#E8EDF3', lw=0.55)
c.legend(handles=[Line2D([], [], marker='o', color='#53647D', ls='none', label='Observed'), Line2D([], [], marker='D', mfc='white', mec='#53647D', ls='none', label='Expected')], loc='upper center', bbox_to_anchor=(0.5, -0.24), frameon=False, ncol=2, fontsize=7.2, handlelength=1.2, columnspacing=1.3)
for j, g in enumerate(['All'] + G):
    rr = sorted([r for r in ww if r['size_group'] == g], key=lambda r: int(r['months']))
    x = np.array([int(r['months']) for r in rr], float) + [-0.18, -0.06, 0.06, 0.18][j]
    y = [100 * int(r['C']) / int(r['N']) for r in rr]
    upper = [100 * (int(r['C']) + int(r['U'])) / int(r['N']) for r in rr]
    d.plot(x, y, color=C[g], marker='o', ms=3.4, lw=1.2)
    for xx, yy, up in zip(x, y, upper):
        d.plot([xx, xx], [yy, up], color=C[g], lw=0.9, ls=':')
        d.plot(xx, up, 'o', mfc='white', mec=C[g], ms=3.2, mew=0.8)
    d.text(x[-1] + 0.3, y[-1], f'{y[-1]:.1f}', color=C[g], va='center', fontsize=7)
d.set_xlim(2, 14)
d.set_ylim(0, 65)
d.set_xticks([3, 6, 12])
d.set_yticks([0, 20, 40, 60])
d.set_xlabel('Months since first AF publication')
d.set_ylabel('Confirmed repeat publication (%)')
d.legend(handles=[Line2D([], [], color=C[g], marker='o', ms=3, lw=1, label=N[g]) for g in ['All'] + G], loc='upper center', bbox_to_anchor=(0.5, -0.24), ncol=4, frameon=False, fontsize=7, handlelength=0.8, columnspacing=0.8)
for x, y, t in [(0.025, 0.955, 'a'), (0.515, 0.955, 'b'), (0.025, 0.485, 'c'), (0.515, 0.485, 'd')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S9.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S9_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S9_preview.png', dpi=180)
caption = 'Supplementary Fig. S9 | Repeat publication and follow-up opportunities. The fixed complete-12-month cohort contains 4,955 institutions: Lower, 176; Middle, 630; Higher, 3,903; and unclassified, 246. a, Distributions of distinct studies published within 12 months of entry (medians: 2, 7 and 53 for Lower, Middle and Higher); the horizontal scale is linear near zero and logarithmic above one. b, Observed minus expected repeat AF publication under primary entry constraints, coarser strata omitting country sets, and relaxed constraints fixing entry AF studies only. c, Observed and expected repeat AF publication in the next complete calendar year. Whiskers are 95% conditional allocation ranges, not confidence intervals. d, Confirmed repeat publication at 3, 6 and 12 months in the same cohort. Open circles additionally include registered unresolved potential follow-ups; dotted extensions are not confidence intervals or bounds on all unobserved AF use. All includes unclassified institutions. Institutional groups use baseline within-country output.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'new_figure': 'S9', 'old_panels': ['S11b', 'S11c', 'S11d', 'S12a–d'], 'institution_records': len(I), 'group_counts': counts, 'opportunity_medians_verified': True, 'all_20_reference_summary_rows_rebuilt_from_institution_predictions': True, 'all_reference_ranges_recomputed_from_saved_allocations': True, 'all_12_window_rows_count_identities_checked': True, '12_month_counts_cross_checked_against_reference_summary': True, 'classification_or_model_rerun': False, 'source_data_unchanged': True}, indent=2))
(P / 'README.txt').write_text('Merged old S11b–d and S12. Old S11a record-state plot omitted; underlying records remain in institution_opportunities.csv. All four old S12 panels combined in d. Institutional counts, opportunity medians and all reference summaries verified from institution-level exported records/predictions. Allocation ranges recomputed from saved draws; no new model fitting, allocation simulation or AF-label validation. Rebuild: python code/build_s9.py (numpy and matplotlib).\n')
E = '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/Entry_reference/tables/'
F = '/historical-workspace/Desktop/Findings_figures/Findings/v7/finding3_v7_review_v1/source_inputs/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': (F if p.name == 'S4_common_windows.csv' else E) + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S9</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S9_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S9.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S9_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
