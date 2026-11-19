from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile
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
E = read('T_SI3_estimates.csv')
H = read('history_support.csv')
G = ['L', 'M', 'H']
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
MK = {'L': 'o', 'M': 's', 'H': '^'}
Q = [r for r in E if r['sample_id'] in ['history_min1', 'history_min3', 'history_min5', 'history_min10'] and r['metric'] == 'journal_position']
assert len(Q) == 12
for r in Q:
    if int(r['n_institutions']) == 0:
        assert not r['estimate'] and (not r['lower']) and (not r['upper'])
        continue
    assert abs(float(r['AF_mean']) - float(r['REF_mean']) - float(r['estimate'])) < 1e-09
    if int(r['n_institutions']) < 10:
        assert not r['lower'] and (not r['upper'])
    else:
        assert float(r['lower']) <= float(r['estimate']) <= float(r['upper'])
for g in G:
    ns = [int(next((r for r in Q if r['group'] == g and r['sample_id'] == 'history_min' + str(m)))['n_institutions']) for m in [1, 3, 5, 10]]
    assert all((ns[i] >= ns[i + 1] for i in range(3)))
assert [int(next((r for r in Q if r['group'] == 'L' and r['sample_id'] == 'history_min' + str(m)))['n_institutions']) for m in [1, 3, 5, 10]] == [23, 7, 1, 0]
observed = [r for r in H if r['history_status'] == 'observed_support']
assert all((float(r['median_history_papers']) > 0 for r in observed))
fig = plt.figure(figsize=(7.2, 3.8), facecolor='white')
a = fig.add_axes([0.12, 0.3, 0.31, 0.59])
b = fig.add_axes([0.61, 0.3, 0.25, 0.59])
nax = fig.add_axes([0.9, 0.3, 0.065, 0.59])
nax.axis('off')
for ax in [a, b]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
for g in G:
    rr = sorted([r for r in observed if r['group'] == g], key=lambda r: int(r['year']))
    a.plot([int(r['year']) for r in rr], [float(r['median_history_papers']) for r in rr], color=COL[g], marker=MK[g], lw=1.2, ms=4)
a.set_yscale('log')
a.set_yticks([1, 3, 10, 30, 100, 300], ['1', '3', '10', '30', '100', '300'])
a.set_ylim(1, 450)
a.set_xticks(range(2020, 2025))
a.set_xlim(2019.8, 2024.2)
a.grid(axis='y', color='#E8EDF3', lw=0.55)
a.set_xlabel('AF publication year', labelpad=8)
a.set_ylabel('Median comparable historical studies\n(log scale)', labelpad=8)
a.legend(handles=[Line2D([], [], color=COL[g], marker=MK[g], ms=3.5, lw=1, label=NAM[g]) for g in G], loc='upper center', bbox_to_anchor=(0.5, -0.3), frameon=False, ncol=3, fontsize=7, handlelength=1, columnspacing=1)
for i, m in enumerate([1, 3, 5, 10]):
    for g, off in zip(G, [-0.19, 0, 0.19]):
        r = next((r for r in Q if r['group'] == g and r['sample_id'] == 'history_min' + str(m)))
        n = int(r['n_institutions'])
        nax.text(0.5, i + off, f'{n:,}', color=COL[g], ha='center', va='center', fontsize=7.2)
        if n == 0:
            continue
        v = float(r['estimate'])
        b.plot(v, i + off, MK[g], color=COL[g], mfc='white' if n < 10 else COL[g], ms=4.2)
        if n >= 10:
            lo, hi = (float(r['lower']), float(r['upper']))
            b.errorbar(v, i + off, xerr=[[v - lo], [hi - v]], fmt='none', color=COL[g], lw=1, capsize=2)
b.axvline(0, color='#8C9BB1', ls='--', lw=0.8)
b.spines['left'].set_visible(False)
b.grid(axis='x', color='#E8EDF3', lw=0.55)
b.set_xlim(-12, 24)
b.set_xticks([-10, 0, 10, 20])
b.set_yticks(range(4), ['History ≥1', 'History ≥3', 'History ≥5', 'History ≥10'])
b.tick_params(axis='y', length=0, pad=8)
b.set_ylim(3.6, -0.6)
nax.set_ylim(3.6, -0.6)
nax.set_xlim(0, 1)
nax.text(0.5, 1.06, 'n', transform=nax.transAxes, ha='center', fontsize=8, color='#53647D')
b.set_xlabel('AF − historical reference\n(journal percentile points)', labelpad=8)
b.legend(handles=[Line2D([], [], color=COL[g], marker=MK[g], ms=3.5, ls='none', label=NAM[g]) for g in G] + [Line2D([], [], marker='o', mfc='white', mec='#53647D', ms=3.5, ls='none', label='n < 10')], loc='upper center', bbox_to_anchor=(0.6, -0.3), frameon=False, ncol=4, fontsize=6.8, handlelength=0.7, columnspacing=0.8)
fig.text(0.025, 0.95, 'a', fontsize=11, fontweight='bold')
fig.text(0.51, 0.95, 'b', fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S17.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S17_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S17_preview.png', dpi=180)
caption = 'Supplementary Fig. S17 | Historical comparison support. a, Median numbers of same-institution, subfield and document-type studies in 2015–2019, across AF study–institution links with observed historical support; the vertical scale is logarithmic. b, AF-minus-historical-reference journal-percentile differences under increasing minimum historical-study requirements, starting from the common 2020–2024 outcome sample. Whiskers show conditional 95% intervals from 5,000 shared-study reweightings. Open points have fewer than ten institutions and no interval; n denotes retained institutions. The Lower group retains 23, 7, 1 and 0 institutions; no estimate is plotted at zero support. Colours identify within-country baseline output groups. These historical comparisons differ from the contemporaneous matched non-AF comparisons.'
(P / 'caption.txt').write_text(caption + '\n')
with (P / 'plotted_estimates.csv').open('w') as f:
    fields = ['sample_id', 'group', 'estimate', 'lower', 'upper', 'n_institutions', 'n_af_works']
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(Q)
(P / 'validation.json').write_text(json.dumps({'new_figure': 'S17', 'old_panels': ['S27c', 'S27d'], 'historical_support_points': len(observed), 'threshold_rows': 12, 'point_estimate_identities_checked': True, 'lower_retained_counts': [23, 7, 1, 0], 'sample_counts_monotonically_decrease_with_threshold': True, 'zero_support_estimate_missing': True, 'small_n_intervals_absent': True, 'historical_support_medians_positive_for_log_scale': True, 'original_bootstrap_intervals_preserved': True, 'bootstrap_recomputed': False, 'source_files_unchanged': True, 'caption_correction': 'AF-minus-historical reference, not contemporaneous non-AF. Verified against outcomes.py and build_comparisons.py.', 'verification_scope': 'Aggregate selection, counts and arithmetic checked; historical medians retained from source summary, not independently reconstructed from study records.'}, indent=2))
(P / 'README.txt').write_text('New S17 retains old S27c,d. Old S27a,b omitted under concise plan. Caption corrects comparison identity: historical 2015–2019 same-institution/subfield/document-type references, not contemporaneous non-AF. Verified in original build_comparisons.py lines 50–53 and outcomes.py lines 39–40. a uses exported positive-support medians, not recomputed from raw records. b count/point identities checked; original intervals retained. Lower n=23/7/1/0; n<10 open points without intervals, n=0 no point. Complete source summaries include no-history records. No model/bootstrap rerun. Rebuild: python code/build_s17.py (matplotlib).\n')
EB = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': EB + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S17</title><style>body{font:16px Arial;max-width:1100px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S17_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S17.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S17_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_estimates.csv">Estimates and sample sizes</a></p>')
