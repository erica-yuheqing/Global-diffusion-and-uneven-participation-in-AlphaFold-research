from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile
from collections import Counter
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.3, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': '#11151C', 'xtick.color': '#53647D'})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
F = read('T_SI1_global_flow.csv')
T = read('T_SI1.csv')
K = read('T_SI1_country_group.csv')
MISS = read('T_SI1_overlapping_missingness.csv')
J = read('journal_institutions.csv')
CIT = read('citation_institutions.csv')
G = ['L', 'M', 'H']
NAM = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
COL = {'L': '#569BD8', 'M': '#21937F', 'H': '#193F85'}
BASE = {'L': 17602, 'M': 14720, 'H': 15688}
tables = {'journal': J, 'citation': CIT}
stats = []
for key, rows in tables.items():
    for g in G:
        rr = [r for r in rows if r['group'] == g]
        n = len(rr)
        single = sum((int(r['n_AF_works']) == 1 for r in rr))
        window = '2020_2025' if key == 'journal' else '2020_2024'
        t = next((t for t in T if t['window'] == window and t['sample_id'] == key + '_matched' and (t['group'] == g)))
        assert n == int(t['n_institutions'])
        assert len(set((r['institution_id'] for r in rr))) == n
        assert abs(100 * n / BASE[g] - float(t['retention_percent'])) < 1e-10
        stats.append({'outcome': key, 'group': g, 'n': n, 'coverage_pct': 100 * n / BASE[g], 'single_n': single, 'single_pct': 100 * single / n})
for g in G:
    rr = [r for r in K if r['group'] == g and r['window'] == '2020_2025']
    assert sum((int(r['baseline_institutions']) for r in rr)) == BASE[g]
    for key, count in [('journal', 'journal_matched_institutions'), ('citation', 'citation_matched_institutions')]:
        assert sum((int(r[count]) for r in rr)) == next((r['n'] for r in stats if r['outcome'] == key and r['group'] == g))
REAS = ['journal_missing', 'no_journal_reference', 'citation_quality_or_rank_missing', 'no_citation_reference', 'citation_immature_2025']
RL = ['Journal outcome unavailable', 'No journal reference', 'Citation outcome unavailable', 'No citation reference', '2025 citation window incomplete']
M = []
for reason in REAS:
    row = []
    for g in G:
        r = next((r for r in MISS if r['window'] == '2020_2025' and r['group'] == g and (r['reason'] == reason)))
        assert abs(100 * int(r['AF_links']) / int(r['denominator_AF_links']) - float(r['percent'])) < 1e-10
        row.append(float(r['percent']))
    M.append(row)
fig = plt.figure(figsize=(7.2, 6.2), facecolor='white')
a = fig.add_axes([0.04, 0.64, 0.52, 0.28])
a.axis('off')
xs = [0, 0.45, 0.65, 0.8, 0.95]
heads = ['Sample', 'Studies', 'Lower', 'Middle', 'Higher']
for x, h in zip(xs, heads):
    a.text(x, 0.97, h, ha='left' if x == 0 else 'center', va='center', fontsize=7.5, color=COL.get({'Lower': 'L', 'Middle': 'M', 'Higher': 'H'}.get(h, ''), '#53647D'))
a.plot([0, 1], [0.85, 0.85], color='#AAB7C8', lw=0.6)
coh = [('AF (2020–25)', 'AF_2020_2025', None, '2020_2025'), ('Journal (2020–25)', 'journal_primary', 'journal_matched', '2020_2025'), ('Citation (2020–24)', 'citation_primary', 'citation_matched', '2020_2024'), ('Common (2020–24)', 'common_2020_2024', 'common', '2020_2024')]
for i, (label, stage, sample, window) in enumerate(coh):
    y = 0.72 - i * 0.2
    values = [int(next((r for r in F if r['stage'] == stage))['count'])]
    for g in G:
        values.append(int(next((r for r in T if r['window'] == window and r['sample_id'] == (sample or 'AF_participants') and (r['group'] == g)))['n_institutions']))
    a.text(0, y, label, ha='left', va='center', fontsize=7.2)
    for x, v in zip(xs[1:], values):
        a.text(x, y, f'{v:,}', ha='center', va='center', fontsize=7.5)
    a.plot([0, 1], [y - 0.09, y - 0.09], color='#E8EDF3', lw=0.6)
a.set_xlim(-0.01, 1.02)
a.set_ylim(-0.05, 1.05)
b = fig.add_axes([0.7, 0.64, 0.26, 0.28])
d = fig.add_axes([0.7, 0.18, 0.26, 0.29])
for ax in [b, d]:
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E8EDF3', lw=0.55)
    ax.tick_params(axis='y', length=0, pad=7)
    ax.tick_params(axis='x', length=3, width=0.6)
    ax.set_yticks(range(3), [NAM[g] for g in G])
    ax.set_ylim(2.5, -0.5)
    for i, g in enumerate(G):
        for key, off, m in [('journal', -0.1, 'o'), ('citation', 0.1, 'D')]:
            r = next((r for r in stats if r['outcome'] == key and r['group'] == g))
            v = r['coverage_pct' if ax == b else 'single_pct']
            ax.plot(v, i + off, marker=m, color=COL[g], mfc=COL[g] if key == 'journal' else 'white', ms=4.8, ls='none')
    ax.legend(handles=[Line2D([], [], marker='o', color='#53647D', ls='none', label='Journal'), Line2D([], [], marker='D', mfc='white', mec='#53647D', ls='none', label='Citation')], loc='upper center', bbox_to_anchor=(0.5, -0.28), frameon=False, ncol=2, fontsize=7.3, handlelength=1, columnspacing=1)
b.set_xlim(-1, 36)
b.set_xticks([0, 10, 20, 30])
b.set_xlabel('Baseline institutions covered (%)', labelpad=8)
d.set_xlim(0, 100)
d.set_xticks([0, 25, 50, 75, 100])
d.set_xlabel('Institutions with one AF study (%)', labelpad=8)
c = fig.add_axes([0.3, 0.18, 0.25, 0.29])
cmap = LinearSegmentedColormap.from_list('missing', ['#F7FAFD', '#A5BDDD', '#193F85'])
im = c.imshow(M, cmap=cmap, vmin=0, vmax=100, aspect='auto')
c.set_xticks(range(3), ['Lower', 'Middle', 'Higher'])
c.set_yticks(range(5), RL)
c.tick_params(length=0, pad=7, labelsize=7.3)
for s in c.spines.values():
    s.set_visible(False)
c.set_xticks(np.arange(-0.5, 3, 1), minor=True)
c.set_yticks(np.arange(-0.5, 5, 1), minor=True)
c.grid(which='minor', color='white', lw=0.8)
c.tick_params(which='minor', length=0)
for i in range(5):
    for j in range(3):
        c.text(j, i, f'{M[i][j]:.1f}', ha='center', va='center', fontsize=7.5, color='white' if M[i][j] > 65 else '#11151C')
cb = fig.colorbar(im, cax=fig.add_axes([0.3, 0.095, 0.25, 0.015]), orientation='horizontal', ticks=[0, 50, 100])
cb.outline.set_visible(False)
cb.ax.tick_params(length=2, width=0.5, labelsize=7)
cb.set_label('AF study–institution links (%)', fontsize=7.5, labelpad=5)
for x, y, t in [(0.025, 0.955, 'a'), (0.61, 0.955, 'b'), (0.025, 0.51, 'c'), (0.61, 0.51, 'd')]:
    fig.text(x, y, t, fontsize=11, fontweight='bold')
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S13.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S13_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S13_preview.png', dpi=180)
caption = 'Supplementary Fig. S13 | Publication-outcome sample support. a, AF studies and institutions in the journal (2020–2025), 12-month citation (2020–2024) and common 2020–2024 outcome samples with matched non-AF references. Study counts cover the full eligible population; institution counts show classified baseline groups. These are parallel samples, not successive exclusions. b, Outcome-sample coverage of fixed baseline institutions (Lower, 17,602; Middle, 14,720; Higher, 15,688). c, Unavailable outcomes or references among 2020–2025 AF study–institution links; reasons overlap and cannot be added. d, Institutions with exactly one eligible AF study, as a percentage of each outcome sample. Colours identify within-country baseline institutional groups; filled circles denote journal and open diamonds citation samples.'
(P / 'caption.txt').write_text(caption + '\n')
with (P / 'plotted_sample_summary.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=list(stats[0]))
    w.writeheader()
    w.writerows(stats)
(P / 'validation.json').write_text(json.dumps({'old_figure': 'S22', 'new_figure': 'S13', 'institution_sample_counts_recomputed': True, 'sample_counts_cross_checked_with_country_group_tables': True, 'coverage_percentages_recomputed': True, 'single_AF_percentages_recomputed_from_institution_n_AF_works': True, 'missingness_percentages_recomputed_from_link_counts': True, 'baseline_denominators': BASE, 'journal_counts': [r['n'] for r in stats if r['outcome'] == 'journal'], 'citation_counts': [r['n'] for r in stats if r['outcome'] == 'citation'], 'global_study_counts': 'Retained from original global-flow table; no study-level reconstruction.', 'common_sample': 'Retained from original matched common-sample summary, not inferred from institution-set overlap.', 'models_rerun': False, 'source_csv_unchanged': True}, indent=2))
(P / 'README.txt').write_text('New S13 revises old S22. Four panels retain parallel sample counts, population coverage, overlapping outcome/reference missingness and outcome-specific single-study institutions. Missingness panel omits network-only reasons already covered by ED10. Journal cohort 2020–2025; citations and common cohort 2020–2024. Counts and single-study shares recomputed from outcome-specific institution CSVs; coverage checked against group and country summaries. Common sample is the matched-record intersection, not the intersection of institution IDs alone. Global study and common counts retained from original summaries. No raw corpus rebuild or model rerun. Rebuild: python code/build_s13.py (numpy, matplotlib).\n')
E = '/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0/tables/'
FBASE = '/historical-workspace/.codex/visualizations/2026/11/11/01a1c9af-2c9a-7102-8d89-1bb32abfbfca/Figure5_compact_dots_20261114/source_data/'
(P / 'provenance.json').write_text(json.dumps([{'file': p.name, 'source': (FBASE if p.name.endswith('_institutions.csv') else E) + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig. S13</title><style>body{font:16px Arial;max-width:1050px;margin:32px auto;padding:0 24px;line-height:1.6;color:#18212d}img{width:100%}a{color:#193f85}</style><img src="figures/Supplementary_Fig_S13_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S13.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S13_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a> · <a href="plotted_sample_summary.csv">Sample summary</a></p>')
