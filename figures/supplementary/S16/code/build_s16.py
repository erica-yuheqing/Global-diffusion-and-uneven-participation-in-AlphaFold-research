from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile, math
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
ENT = read('entry_opportunity_summary.csv')
COV = read('coverage_summary.csv')
DETAIL = read('coverage_country_group_2024.csv') + read('coverage_country_group_2025.csv')
G = ['L', 'M', 'H']
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
MARK = {'L': 'o', 'M': 's', 'H': '^'}
annual = [r for r in E if r['sample_id'].startswith('journal_annual_') and r['metric'] == 'journal_position' or (r['sample_id'].startswith('citation_annual_') and r['metric'] == 'percentile_12m')]
for r in annual:
    if not r['estimate']:
        assert int(r['n_institutions']) == 0
        continue
    assert abs(float(r['AF_mean']) - float(r['REF_mean']) - float(r['estimate'])) < 1e-09
    if int(r['n_institutions']) < 10:
        assert not r['lower'] and (not r['upper'])
    else:
        assert float(r['lower']) <= float(r['estimate']) <= float(r['upper'])
for r in COV:
    rr = [t for t in DETAIL if t['publication_end_year'] == r['publication_end_year'] and t['group'] == r['group']]
    assert len(rr) == 68
    for ev in ['af', 'venue']:
        for end, status in [('lower', 'confirmed'), ('upper', 'possible')]:
            for t in rr:
                assert abs(100 * float(t[ev + '_' + status + '_n']) / int(t['baseline_denominator']) - float(t[ev + '_' + end])) < 1e-09
            assert abs(math.fsum((float(t[ev + '_' + end]) for t in rr)) / 68 - float(r[ev + '_' + end])) < 1e-10
for r in ENT:
    n = int(r['institutions'])
    for ev in ['venue', 'citation']:
        lo, hi = (float(r[ev + '_confirmed']), float(r[ev + '_possible']))
        assert 0 <= lo <= hi <= 1
        for v in [lo, hi]:
            assert abs(v * n - round(v * n)) < 1e-09
for g in G:
    assert len({r['institutions'] for r in ENT if r['group'] == g}) == 1
fig = plt.figure(figsize=(7.2, 6.6), facecolor='white')
a = fig.add_axes([0.12, 0.63, 0.34, 0.28])
b = fig.add_axes([0.62, 0.63, 0.34, 0.28])
c = fig.add_axes([0.25, 0.18, 0.25, 0.29])
d = fig.add_axes([0.72, 0.18, 0.25, 0.29])
for ax in [a, b, c, d]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
for ax, out in [(a, 'journal'), (b, 'citation')]:
    vals = []
    for g, off in zip(G, [-0.07, 0, 0.07]):
        rr = sorted([r for r in annual if r['group'] == g and r['sample_id'].startswith(out + '_annual_')], key=lambda r: r['sample_id'])
        x = [int(r['sample_id'][-4:]) + off for r in rr]
        y = [float(r['estimate']) if r['estimate'] else float('nan') for r in rr]
        ax.plot(x, y, color=COL[g], lw=1.05)
        for xx, r in zip(x, rr):
            if not r['estimate']:
                continue
            v = float(r['estimate'])
            small = int(r['n_institutions']) < 10
            ax.plot(xx, v, MARK[g], color=COL[g], mfc='white' if small else COL[g], ms=4.2)
            if not small:
                lo, hi = (float(r['lower']), float(r['upper']))
                ax.errorbar(xx, v, yerr=[[v - lo], [hi - v]], fmt='none', color=COL[g], lw=0.85, capsize=1.8)
                vals.extend([lo, hi])
            vals.append(v)
    ax.axhline(0, color='#8C9BB1', ls='--', lw=0.8)
    ax.grid(axis='y', color='#E8EDF3', lw=0.55)
    ax.set_xticks(range(2020, 2026 if out == 'journal' else 2025))
    ax.set_xlim(2019.75, 2025.25 if out == 'journal' else 2024.25)
    lo = min(0, min(vals))
    hi = max(vals)
    pad = (hi - lo) * 0.12
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlabel('Publication year', labelpad=7)
    ax.set_ylabel(('Journal' if out == 'journal' else '12-month citation') + ' difference\n(percentile points)', labelpad=7)
    ax.legend(handles=[Line2D([], [], color=COL[g], marker=MARK[g], lw=1, ms=3.5, label=NAM[g]) for g in G] + [Line2D([], [], color='#53647D', marker='o', mfc='white', ls='none', ms=3.5, label='n < 10')], loc='upper center', bbox_to_anchor=(0.5, -0.24), frameon=False, ncol=4, fontsize=7, handlelength=1, columnspacing=1)
CS = [('venue', 12, 'Journal · 12 months'), ('venue', 24, 'Journal · 24 months'), ('citation', 12, 'Citation · 12 months'), ('citation', 24, 'Citation · 24 months')]
DS = [('af', 2024, 'AF · 2020–24'), ('af', 2025, 'AF · 2020–25'), ('venue', 2024, 'Journal · 2020–24'), ('venue', 2025, 'Journal · 2020–25')]
for ax, spec in [(c, CS), (d, DS)]:
    ax.spines['left'].set_visible(False)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.tick_params(axis='y', length=0, pad=8)
    for i, (ev, period, label) in enumerate(spec):
        for g, off in zip(G, [-0.2, 0, 0.2]):
            if ax == c:
                r = next((r for r in ENT if r['group'] == g and int(r['followup_months']) == period))
                lo, hi = (100 * float(r[ev + '_confirmed']), 100 * float(r[ev + '_possible']))
            else:
                r = next((r for r in COV if r['group'] == g and int(r['publication_end_year']) == period))
                lo, hi = (float(r[ev + '_lower']), float(r[ev + '_upper']))
            ax.plot([lo, hi], [i + off, i + off], color=COL[g], lw=1, ls=':')
            ax.plot(lo, i + off, 'o', color=COL[g], ms=3.5)
            ax.plot(hi, i + off, 'o', mfc='white', mec=COL[g], ms=3.5)
    ax.set_yticks(range(4), [r[2] for r in spec])
    ax.set_ylim(3.6, -0.6)
    ax.axhline(1.5, color='#DDE3EA', lw=0.65)
    ax.set_xlim(0, 100 if ax == c else 50)
    ax.set_xticks([0, 25, 50, 75, 100] if ax == c else [0, 10, 20, 30, 40, 50])
    ax.set_xlabel('Entrant coverage (%)' if ax == c else 'Baseline-population coverage (%)', labelpad=8)
    groupkey = ax.legend(handles=[Line2D([], [], color=COL[g], lw=1.2, label=NAM[g]) for g in G], loc='upper center', bbox_to_anchor=(0.5, -0.26), frameon=False, ncol=3, fontsize=6.8, handlelength=0.8, columnspacing=0.8)
    ax.add_artist(groupkey)
    ax.legend(handles=[Line2D([], [], marker='o', color='#53647D', ls='none', ms=3.5, label='Confirmed'), Line2D([], [], marker='o', mfc='white', mec='#53647D', ls='none', ms=3.5, label='Possible')], loc='upper center', bbox_to_anchor=(0.5, -0.38), frameon=False, ncol=2, fontsize=6.8, handlelength=0.8, columnspacing=1.4)
for x, y, t in [(0.025, 0.95, 'a'), (0.54, 0.95, 'b'), (0.025, 0.51, 'c'), (0.565, 0.51, 'd')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S16.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S16_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S16_preview.png', dpi=180)
caption = 'Supplementary Fig. S16 | Annual publication outcomes and qualifying-study coverage. a,b, Annual AF–non-AF differences in journal and 12-month citation percentiles. Whiskers show conditional 95% intervals from 5,000 shared-study reweightings; open points denote fewer than ten institutions. Unavailable estimates remain missing; points are slightly offset horizontally. c, Qualifying-study coverage after 12 and 24 months in the same mature entrant cohort (Lower, n = 48; Middle, 190; Higher, 2,489). d, Equal-country mean AF and qualifying-journal coverage in the fixed baseline population. Qualifying thresholds are journal ≥75th and citation ≥90th percentile. Filled/open endpoints in c,d show confirmed/possible recorded-status bounds, not confidence intervals or bounds on all unobserved AF use. Colours identify within-country baseline output groups.'
(P / 'caption.txt').write_text(caption + '\n')
with (P / 'annual_plotted_estimates.csv').open('w') as f:
    fields = ['sample_id', 'group', 'metric', 'estimate', 'lower', 'upper', 'n_institutions', 'n_af_works']
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(annual)
(P / 'validation.json').write_text(json.dumps({'new_figure': 'S16', 'old_panels': ['S26a', 'S26b', 'S26e', 'S26f'], 'annual_rows_including_missing': len(annual), 'annual_AF_minus_reference_identities_checked': True, 'small_n_points_have_no_intervals': True, 'missing_values_preserved': True, 'coverage_means_recomputed_from_68_country_rows_per_group_year': True, 'country_event_counts_and_rates_checked': True, 'entrant_proportions_convert_to_integer_counts': True, 'same_entrant_counts_at_both_windows': True, 'bootstrap_intervals_recomputed': False, 'verification_scope': 'Annual point identities and country-level coverage aggregation verified; entrant fractions checked arithmetically against fixed counts, not reconstructed from event histories. No bootstrap or underlying classification rerun.'}, indent=2))
(P / 'README.txt').write_text('S16 retains old S26a,b,e,f. Old c,d first-year/study-count distributions omitted under the concise plan. Annual intervals retained unchanged; n<10 remains point only, zero-institution rows missing. No 2025 immature citation result added. Coverage plots replace overlapping curves with separate rows and recorded-status endpoints. Fixed-population coverage recomputed as equal-country means from country-group counts; entrant proportions checked against fixed cohort counts. The recorded possible endpoint is not a confidence interval or an exhaustive upper bound on AF use. No model or bootstrap rerun. Rebuild: python code/build_s16.py (matplotlib).\n')
EB = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': EB + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S16</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S16_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S16.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S16_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
