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
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.4, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
A = [r for r in read('S31_authorship_AF_minus_reference.csv') if r['income_group'] in ['H', 'UM', 'LM', 'L']]
B = read('S31_benchmark_shift_C.csv')
R = read('authorship_representation.csv')
SH = read('authorship_credit_shares.csv')
assert len(A) == 32
SAMPLE = read('income_group_sample_summary.csv')
assert sum((int(r['countries_in_original_68']) for r in SAMPLE)) == 68
assert sum((int(r['countries_in_227_unit_roster']) for r in SAMPLE)) == 213
assert next((r for r in SAMPLE if r['income_group'] == 'L'))['original_68_country_codes'] == 'ET,UG'
for r in A:
    vals = {}
    for corpus in ['AF', 'reference']:
        t = next((t for t in R if all((t[k] == r[k] for k in ['scope', 'income_group', 'benchmark', 'role'])) and t['corpus'] == corpus))
        s = next((t for t in SH if all((t[k] == r[k] for k in ['scope', 'income_group'])) and t['corpus'] == corpus))
        ratio = float(s[r['role'] + '_author_pct']) / float(s['country_participation_pct' if r['benchmark'] == 'country' else 'author_participation_pct'])
        assert abs(float(t['R']) - ratio) < 1e-10
        vals[corpus] = float(t['R'])
        assert abs(vals[corpus] - float(r['R_' + corpus])) < 1e-10
    assert abs(vals['AF'] - vals['reference'] - float(r['delta_R'])) < 1e-10
    assert float(r['ci_low']) <= float(r['delta_R']) <= float(r['ci_high']) and int(r['valid_replicates']) == 2000
for r in B:
    z = {bench: next((t for t in A if all((t[k] == r[k] for k in ['scope', 'income_group', 'role'])) and t['benchmark'] == bench)) for bench in ['country', 'author']}
    assert abs(float(z['author']['delta_R']) - float(z['country']['delta_R']) - float(r['C'])) < 1e-10
scopes = list(dict.fromkeys((r['scope'] for r in A)))
assert len(scopes) == 2
print('Scopes:', scopes)
fig = plt.figure(figsize=(7.2, 5.6), facecolor='white')
positions = [[0.27, 0.64, 0.29, 0.29], [0.66, 0.64, 0.29, 0.29], [0.27, 0.19, 0.29, 0.29], [0.66, 0.19, 0.29, 0.29]]
G = ['H', 'UM', 'LM', 'L']
names = ['High income', 'Upper-middle', 'Lower-middle', 'Low income']
col = {'country': '#193F85', 'author': '#569BD8'}
axes = []
for ix, pos in enumerate(positions):
    ax = fig.add_axes(pos)
    axes.append(ax)
    scope = scopes[ix // 2]
    role = ['first', 'last'][ix % 2]
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=9)
    ax.tick_params(axis='x', length=3, width=0.6)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.axvline(0, color='#8C9BB1', lw=0.8, ls='--')
    for i, g in enumerate(G):
        for bench, off, marker in [('country', -0.12, 'o'), ('author', 0.12, 'D')]:
            r = next((r for r in A if r['scope'] == scope and r['role'] == role and (r['income_group'] == g) and (r['benchmark'] == bench)))
            v, lo, hi = [float(r[k]) for k in ['delta_R', 'ci_low', 'ci_high']]
            assert -0.6 < lo <= hi < 0.6
            ax.errorbar(v, i + off, xerr=[[v - lo], [hi - v]], fmt=marker, ms=4.5, mfc=col[bench] if bench == 'country' else 'white', mec=col[bench], ecolor=col[bench], capsize=2, lw=1.05)
    ax.axhspan(2.6, 3.4, color='#F5F8FC', zorder=0)
    ax.set_ylim(3.55, -0.55)
    ax.set_xlim(-0.6, 0.6)
    ax.set_xticks([-0.5, -0.25, 0, 0.25, 0.5])
    ax.set_yticks(range(4), names if ix % 2 == 0 else [''] * 4)
    ax.set_xlabel(('First' if role == 'first' else 'Last') + ' authorship (ΔRR)', labelpad=8)
    ax.legend(handles=[Line2D([], [], marker='o', color=col['country'], ls='none', ms=4.5, label='Country output'), Line2D([], [], marker='D', mfc='white', mec=col['author'], color=col['author'], ls='none', ms=4.5, label='Team authors')], loc='upper center', bbox_to_anchor=(0.5, -0.26), frameon=False, ncol=2, fontsize=6.8, handlelength=0.8, columnspacing=0.9)
for x, y, t in [(0.035, 0.96, 'a'), (0.6, 0.96, 'b'), (0.035, 0.51, 'c'), (0.6, 0.51, 'd')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S11.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S11_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S11_preview.png', dpi=180)
caption = 'Supplementary Fig. S11 | Authorship representation by national income. AF–non-AF differences in first- and last-author representation (ΔRR) within the original 68-country scope (a,b) and across 213 income-classified countries and regions (c,d), using fractional country-output and team-author benchmarks. Income groups follow World Bank FY2020 classifications; the original-scope low-income group contains only Ethiopia and Uganda. All panels use the same 5,087 AF and 332,760 non-AF studies and publication-year, subfield and document-type weights. Outside-scope credit remains in global denominators. Whiskers show conditional 95% intervals from 2,000 shared whole-study bootstrap replicates; dashed lines mark zero.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'old_figure': 'S31', 'new_figure': 'S11', 'plotted_estimates': 32, 'RR_values_recomputed_from_pooled_credit_shares': True, 'AF_minus_reference_identities_passed': True, 'paired_benchmark_change_identities_passed': True, 'scopes': scopes, 'all_intervals_fully_within_axes': True, 'source_files_unchanged': True, 'bootstrap_intervals_recomputed': False, 'verification_scope': 'Aggregate point estimates reconstructed from pooled credit-share tables; saved original bootstrap intervals preserved, not independently recalculated.'}, indent=2))
(P / 'README.txt').write_text('Revised old S31: four compact panels, common axes, no panel titles, legends below each panel. ΔRR replaces ΔR. Both geographic scopes use the same study sample and standardization; scopes change income-group attribution, not study eligibility. All 32 point estimates checked against pooled credit shares and saved RR values. Original conditional bootstrap intervals retained. Paired C table included numerically without adding redundant panels. Rebuild: python code/build_s11.py (matplotlib).\n')
E = '/historical-workspace/.codex/visualizations/2026/11/10/01a1c5e5-0c05-72a1-a396-bb7eff1839b0/income_group_analysis_20261110/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': E + ('S31_updated_style/source_data/' if p.name.startswith('S31') else 'tables/') + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S11</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S11_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S11.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S11_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
