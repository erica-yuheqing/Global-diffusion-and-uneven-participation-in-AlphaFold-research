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
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 7.7, 'xtick.labelsize': 7.2, 'ytick.labelsize': 7.2, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
R = {o: read('network_results_' + o + '.csv') for o in ['journal', 'citation']}
AD = {o: read('network_adjusted_group_contrasts_' + o + '.csv') for o in R}
G = ['L', 'M', 'H']
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
SPEC = [(['degree_own', 'strength_own', 'strength_own_fixed_base', 'strength_own_fixed_alt'], ['Degree', 'Fractional strength', 'Common · degree', 'Common · strength']), (['degree_own', 'rolling_own', 'rolling_own_fixed_base', 'rolling_own_fixed_alt'], ['2015–19 baseline', '3-year lagged', 'Common · baseline', 'Common · lagged']), (['degree_own', 'expanded_own', 'observed_covered_network_own', 'expanded_own_fixed_base', 'expanded_own_fixed_alt'], ['Baseline boundary', 'Expanded boundary', 'Roster-covered', 'Common · baseline', 'Common · expanded']), (['degree_own', 'network_no_large_own', 'outcomes_no_large_own', 'both_no_large_own'], ['Primary', 'Exclude large teams · network', 'Exclude large teams · outcomes', 'Exclude large teams · both']), (['degree_partner', 'partial_any', 'partial80', 'partner_max'], ['Complete partners · mean', 'Scored partners · mean', 'Coverage ≥80% · mean', 'Complete partners · maximum']), (['M1', 'M1_without_high_leverage'], ['Adjusted', 'Exclude high leverage'])]

def get(o, s, g, adjusted=False):
    metric = 'journal_position' if o == 'journal' else 'percentile_12m'
    rr = [r for r in (AD[o] if adjusted else R[o]) if r['sample_id'] == s and r['group'] == g and (r['metric'] == metric) and (r['coefficient'] == ('log_degree_slope' if adjusted else 'slope'))]
    assert len(rr) == 1
    return rr[0]
selected = []
counts_checked = 0
for j, (names, labels) in enumerate(SPEC):
    for s, label in zip(names, labels):
        for o in R:
            for g in G:
                r = get(o, s, g, j == 5)
                selected.append(dict(panel='abcdef'[j], label=label, **r))
                if r['estimate']:
                    assert math.isfinite(float(r['estimate']))
                    if r['lower'] and r['upper']:
                        assert float(r['lower']) <= float(r['estimate']) <= float(r['upper'])
                    else:
                        assert int(float(r['n_institutions'])) < 10
                else:
                    assert r['status'] == 'not_estimable' and (not r['lower']) and (not r['upper'])
for prefix in ['strength_own', 'rolling_own', 'expanded_own']:
    for o in R:
        for g in G:
            x, y = (get(o, prefix + '_fixed_base', g), get(o, prefix + '_fixed_alt', g))
            for k in ['n_institutions', 'n_AF_unique', 'n_links']:
                assert x[k] == y[k]
            counts_checked += 1
for o, n in [('journal', 5), ('citation', 2)]:
    assert int(get(o, 'M1_without_high_leverage', 'L', True)['n_institutions']) == n
fig = plt.figure(figsize=(7.2, 9.4), facecolor='white')
axes = []
for i, (names, labels) in enumerate(SPEC):
    x = 0.26 if i % 2 == 0 else 0.73
    y = [0.76, 0.44, 0.12][i // 2]
    ax = fig.add_axes([x, y, 0.24, 0.2])
    axes.append(ax)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.axvline(0, color='#8C9BB1', ls='--', lw=0.8)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.tick_params(axis='x', length=3, width=0.6)
    ends = []
    missing = []
    for j, s in enumerate(names):
        for g, goff in zip(G, [-0.25, 0, 0.25]):
            for o, ooff, m in [('journal', -0.065, 'o'), ('citation', 0.065, 'D')]:
                r = get(o, s, g, i == 5)
                yy = j + goff + ooff
                if not r['estimate']:
                    missing.append((yy, g))
                    continue
                v = float(r['estimate'])
                ends.append(v)
                ax.plot(v, yy, m, color=COL[g], mfc=COL[g] if o == 'journal' else 'white', ms=3.1, mew=0.8)
                if r['lower'] and r['upper']:
                    lo, hi = (float(r['lower']), float(r['upper']))
                    ends.extend([lo, hi])
                    ax.errorbar(v, yy, xerr=[[v - lo], [hi - v]], fmt='none', color=COL[g], lw=0.8, capsize=1.5)
    lo = min(0, min(ends))
    hi = max(0, max(ends))
    pad = (hi - lo) * 0.08
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(len(names) - 0.45, -0.55)
    ax.set_yticks(range(len(names)), labels)
    for yy, g in missing:
        ax.text(0.03, yy, 'NE', transform=ax.get_yaxis_transform(), color=COL[g], va='center', ha='left', fontsize=7)
    if i in [0, 1, 2, 3]:
        xlabel = 'Own-network slope\n(per unit ln(1 + measure))'
    elif i == 4:
        xlabel = 'Partner-connectivity slope\n(per 10 percentile points)'
    else:
        xlabel = 'Adjusted own-connectivity slope\n(per unit ln(1 + degree))'
    ax.set_xlabel(xlabel, labelpad=7)
    if i in [0, 1, 2]:
        ax.axhline(1.5 if i < 2 else 2.5, color='#DDE3EA', lw=0.6)
    lg = ax.legend(handles=[Line2D([], [], color=COL[g], lw=1.3, label=NAM[g]) for g in G], loc='upper center', bbox_to_anchor=(0.5, -0.34), frameon=False, ncol=3, fontsize=6.8, handlelength=0.8, columnspacing=0.8)
    ax.add_artist(lg)
    ax.legend(handles=[Line2D([], [], color='#53647D', marker='o', ls='none', ms=3.3, label='Journal'), Line2D([], [], mec='#53647D', mfc='white', marker='D', ls='none', ms=3.3, label='Citation')], loc='upper center', bbox_to_anchor=(0.5, -0.45), frameon=False, ncol=2, fontsize=6.8, handlelength=0.8, columnspacing=1)
    fig.text(0.025 if i % 2 == 0 else 0.565, y + 0.225, 'abcdef'[i], fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S18.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S18_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S18_preview.png', dpi=180)
caption = 'Supplementary Fig. S18 | Network sensitivity checks. Own-network slopes under alternative measures (a), historical windows (b), boundaries (c) and large-team exclusions (d). Common denotes fixed-intersection comparisons; large teams have >20 institutions in the full observed roster. e, Partner scores using complete or partially scored partner sets. f, Adjusted own-connectivity slopes before and after high-leverage exclusions. Outcomes are institutional AF–non-AF percentile differences. Colours identify within-country baseline output groups; filled circles/open diamonds denote journal/12-month citation outcomes. Whiskers show conditional 95% intervals from 5,000 shared-study reweightings with networks fixed. NE marks the inestimable Lower-group partner-maximum citation model. High-leverage exclusions retain only five/two Lower institutions for journal/citation outcomes, shown without intervals. Slopes are per unit ln(1 + network measure) in a–d, per ten partner-percentile points in e and per unit ln(1 + degree) in f.'
(P / 'caption.txt').write_text(caption + '\n')
fields = ['panel', 'label', 'outcome', 'sample_id', 'group', 'model_id', 'coefficient', 'estimate', 'lower', 'upper', 'n_institutions', 'n_AF_unique', 'n_links', 'status', 'unit', 'scale']
with (P / 'plotted_estimates.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(selected)
(P / 'validation.json').write_text(json.dumps({'old_figure': 'S28', 'new_figure': 'S18', 'selected_rows': len(selected), 'defined_point_estimates': sum((bool(r['estimate']) for r in selected)), 'inestimable_rows': [(r['sample_id'], r['group'], r['outcome']) for r in selected if not r['estimate']], 'fixed_intersection_count_comparisons': counts_checked, 'fixed_intersection_counts_equal_for_institutions_studies_links': True, 'lower_high_leverage_retained': {'journal': 5, 'citation': 2}, 'intervals_retained_from_original_results': True, 'bootstrap_or_networks_recomputed': False, 'source_files_unchanged': True, 'verification_scope': 'Unique model/metric/group selection, interval arithmetic, missing statuses and fixed-intersection aggregate counts verified. Identical record IDs, network construction and bootstrap not independently rerun.'}, indent=2))
(P / 'README.txt').write_text('S18 revises old S28 with six network sensitivity panels. a–d unadjusted own-network slopes; e unadjusted partner scores; f adjusted group-specific own slopes from group contrasts, not the pooled raw model coefficient. All original estimates/intervals retained. Fixed-intersection institution/study/link counts checked equal for strength, lagged and expanded boundary comparisons; record identities not independently reconstructed. Partner-maximum Lower citation is NE, never zero. High-leverage Lower n=5/2 have points without intervals. No model/network/bootstrap rerun. Absolute outcome scatter removed from earlier ED10 is not reintroduced under the concise figure plan. Rebuild: python code/build_s18.py (matplotlib).\n')
EB = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/tables/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': EB + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S18</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S18_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S18.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S18_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_estimates.csv">Estimates and sample sizes</a></p>')
