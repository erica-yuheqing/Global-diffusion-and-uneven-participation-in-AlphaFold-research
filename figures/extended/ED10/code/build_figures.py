from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import argparse, json, hashlib, shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'source_data'
OUT = ROOT / 'figures'
QA = ROOT / 'validation'
ORIGINAL = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0')
G = ['L', 'M', 'H']
N = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
C = {'L': '#5798D2', 'M': '#298F79', 'H': '#193F83'}
MK = {'L': 'o', 'M': 's', 'H': '^'}
INK = '#151A22'
MUTED = '#4D607A'
GRID = '#E5EBF3'
AXIS = '#9AAAC1'
AF = '#D5281D'
REF = '#131460'
for p in [SRC, OUT, QA, ROOT / 'captions', ROOT / 'text']:
    p.mkdir(parents=True, exist_ok=True)

def prepare():
    mapping = {'journal_ecdf.csv': 'source_data/panels/ED_SI1_a/coordinates.csv', 'citation_ecdf.csv': 'source_data/panels/ED_SI2_a/coordinates.csv', 'historical_estimates.csv': 'source_data/panels/ED_SI1_c/coordinates.csv', 'sample_estimates.csv': 'source_data/panels/ED_SI1_d/coordinates.csv', 'selection_records.csv': 'source_data/panels/ED_SI4_a/coordinates.csv', 'own_models.csv': 'source_data/panels/ED_SI4_c/coordinates.csv', 'network_models.csv': 'tables/T_SI9_network_models.csv', 'partner_status.csv': 'tables/T_SI8_partner_degree.csv', 'absolute_network_outcomes.csv': 'source_data/panels/ED_SI4_b/coordinates.csv'}
    provenance = []
    for name, rel in mapping.items():
        f = ORIGINAL / rel
        d = pd.read_csv(f)
        if name == 'selection_records.csv':
            d = d[['institution_id', 'group', 'log_degree', 'stage']]
        if name == 'own_models.csv':
            d = d[d.model_id.isin(['M0', 'M1', 'M1_partner_sample', 'M2'])]
        if name == 'network_models.csv':
            d = d[(d.model_id == 'M2') & (d.coefficient == 'partner_per10')]
        d.to_csv(SRC / name, index=False)
        provenance.append(dict(source=str(f), destination=name, source_sha256=hashlib.sha256(f.read_bytes()).hexdigest(), rows=len(d)))
    (QA / 'source_provenance.json').write_text(json.dumps(provenance, indent=2))

def setup():
    for f in ['Arial.ttf', 'Arial Bold.ttf']:
        p = Path('/System/Library/Fonts/Supplemental') / f
        if p.exists():
            release_addfont(str(p))
    plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'axes.titlesize': 8.7, 'xtick.labelsize': 7, 'ytick.labelsize': 7.5, 'text.color': INK, 'axes.labelcolor': INK, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'savefig.facecolor': 'white'})

def axes(ax, xlim=None, xticks=None, ylim=None, ygrid=False):
    for s in ['top', 'right']:
        ax.spines[s].set_visible(False)
    for s in ['left', 'bottom']:
        ax.spines[s].set_color(AXIS)
        ax.spines[s].set_linewidth(0.6)
    ax.tick_params(colors=MUTED, width=0.6, length=2.5)
    ax.set_axisbelow(True)
    ax.grid(axis='both' if ygrid else 'x', color=GRID, lw=0.45)
    if xlim:
        ax.set_xlim(xlim)
    if xticks is not None:
        ax.set_xticks(xticks)
    if ylim:
        ax.set_ylim(ylim)

def rows(ax):
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.set_yticks([2, 1, 0], [N[g] for g in G])
    for t, g in zip(ax.get_yticklabels(), G):
        t.set_color(C[g])
    ax.axhspan(1.55, 2.45, color='#F5F8FC', zorder=-2)

def err(ax, r, y, g, marker=None, open_=False, ms=4.6):
    ax.errorbar(r['estimate'], y, xerr=[[r['estimate'] - r['lower']], [r['upper'] - r['estimate']]], fmt=marker or MK[g], color=C[g], mfc='white' if open_ else C[g], mec=C[g], ms=ms, lw=1, capsize=2, capthick=0.7, zorder=3)

def save(fig, name):
    fig.savefig(OUT / (name + '.pdf'), dpi=600)
    fig.savefig(OUT / (name + '.svg'))
    fig.savefig(OUT / (name + '_600dpi.png'), dpi=600)
    fig.savefig(OUT / (name + '_preview.png'), dpi=170)
    plt.close(fig)

def ed9():
    fig = plt.figure(figsize=(183 / 25.4, 161 / 25.4))
    group_handles = [Line2D([], [], color=C[g], lw=2, label=N[g]) for g in G]
    series_handles = [Line2D([], [], color=MUTED, lw=1.2, ls=s, label=l) for s, l in [('-', 'AF'), ('--', 'non-AF')]]
    stats = []
    for letter, which, left, title in [('a', 'journal', 0.115, 'Journal percentile'), ('b', 'citation', 0.615, '12-month citation percentile')]:
        ax = fig.add_axes([left, 0.61, 0.345, 0.305])
        axes(ax, (0, 100), [0, 25, 50, 75, 100], (0, 1), True)
        d = pd.read_csv(SRC / (which + '_ecdf.csv'))
        for g in G:
            for s, ls in [('AF', '-'), ('REF', '--')]:
                z = d[(d.group == g) & (d.series == s)].sort_values('x')
                assert len(z) > 0 and np.isclose(z.y.iloc[-1], 1)
                ax.step(np.r_[0, z.x, 100], np.r_[0, z.y, 1], where='post', color=C[g], ls=ls, lw=1.15)
                stats.append(dict(panel=letter, group=g, series=s, n=len(z)))
        ax.set_xlabel('Institution mean percentile')
        ax.set_yticks([0, 0.5, 1])
        ax.set_title(title, pad=9)
        if which == 'journal':
            ax.set_ylabel('Cumulative share of institutions')
        else:
            ax.set_yticklabels([])
        fig.text(left - 0.085, 0.945, letter, fontsize=12, fontweight='bold')
    fig.legend(handles=group_handles + series_handles, loc='center', bbox_to_anchor=(0.54, 0.515), ncol=5, frameon=False, fontsize=7, handlelength=1.8, columnspacing=1.8)
    ax = fig.add_axes([0.115, 0.145, 0.345, 0.275])
    axes(ax, (-1, 25), [0, 8, 16, 24], (-0.85, 2.5))
    rows(ax)
    ax.axvline(0, color=AXIS, lw=0.8, ls=(0, (3, 3)))
    ax.set_title('Historical reference', pad=12)
    d = pd.read_csv(SRC / 'historical_estimates.csv')
    for y, g in zip([2, 1, 0], G):
        r = d[d.group == g].iloc[0]
        err(ax, r, y, g)
        ax.annotate(f'+{r.estimate:.2f}', (r.estimate, y), xytext=(0, 9), textcoords='offset points', ha='center', fontsize=8, fontweight='bold')
        ax.text(24.7, y - 0.27, f'n = {int(r.n_institutions):,}', ha='right', fontsize=6.7, color=MUTED)
    ax.set_xlabel('AF - historical reference\n(journal percentile points)')
    fig.text(0.03, 0.455, 'c', fontsize=12, fontweight='bold')
    ax = fig.add_axes([0.615, 0.145, 0.345, 0.275])
    axes(ax, (-0.5, 12.5), [0, 4, 8, 12], (-0.85, 2.5))
    rows(ax)
    ax.axvline(0, color=AXIS, lw=0.8, ls=(0, (3, 3)))
    ax.set_title('Year window and sample', pad=12)
    d = pd.read_csv(SRC / 'sample_estimates.csv')
    samples = [('journal_max2024', '2020–24 · available', 'o', True, 0.2), ('common', '2020–24 · shared', 'D', True, 0), ('journal_full2025', '2020–25 · available', 'o', False, -0.2)]
    for y, g in zip([2, 1, 0], G):
        for sample, label, marker, op, off in samples:
            r = d[(d.group == g) & (d.sample_id == sample)].iloc[0]
            err(ax, r, y + off, g, marker, op, 4.2)
            if sample == 'journal_full2025':
                ax.annotate(f'+{r.estimate:.2f}', (r.estimate, y + off), xytext=(0, -13), textcoords='offset points', ha='center', fontsize=7.2, fontweight='bold')
    ax.set_xlabel('AF - non-AF\n(journal percentile points)')
    fig.text(0.53, 0.455, 'd', fontsize=12, fontweight='bold')
    handles = [Line2D([], [], color=MUTED, marker=m, mfc='white' if op else MUTED, ls='none', ms=4, label=l.replace(' · ', '\n')) for s, l, m, op, off in samples]
    fig.legend(handles=handles, bbox_to_anchor=(0.7875, 0.034), loc='center', ncol=3, frameon=False, fontsize=6.6, handlelength=0.8, handletextpad=0.45, columnspacing=1.4)
    save(fig, 'Extended_Data_Fig9')
    (QA / 'ed9_ecdf_counts.json').write_text(json.dumps(stats, indent=2))

def ed10():
    fig = plt.figure(figsize=(183 / 25.4, 224 / 25.4))
    group_handles = [Line2D([], [], color=C[g], marker=MK[g], lw=1, label=N[g], ms=4) for g in G]
    fig.text(0.025, 0.952, 'a', fontsize=12, fontweight='bold')
    stages = ['B2', 'AF participant', 'Journal matched', 'Citation matched', 'Journal own network', 'Citation own network']
    labels = ['Baseline', 'AF participants', 'Journal matched', 'Citation matched', 'Journal network', 'Citation network']
    d = pd.read_csv(SRC / 'selection_records.csv')
    summary = []
    for j, g in enumerate(G):
        left = 0.255 + j * 0.24
        fig.add_artist(Rectangle((left - 0.012, 0.745), 0.22, 0.22, transform=fig.transFigure, fill=False, edgecolor='#CBD5E2', linewidth=0.65, zorder=0))
        ax = fig.add_axes([left, 0.775, 0.15, 0.155])
        axes(ax, (0, 8), [0, 4, 8], (5.6, -0.6))
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='y', length=0, pad=10)
        ax.set_yticks(range(6), labels if j == 0 else [''] * 6)
        ax.set_title(N[g], fontsize=8, color=C[g], pad=14)
        ax.text(1.3, 1.025, 'n', transform=ax.transAxes, ha='right', fontsize=6.5, color=MUTED)
        for i, stage in enumerate(stages):
            z = d[(d.stage == stage) & (d.group == g)].log_degree.dropna()
            q = z.quantile([0.25, 0.5, 0.75])
            ax.plot([q.iloc[0], q.iloc[2]], [i, i], c=C[g], lw=1.1)
            ax.plot(q.iloc[1], i, marker=MK[g], c=C[g], ms=3.7)
            ax.text(1.3, i, f'{len(z):,}', transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=6.7)
            summary.append(dict(stage=stage, group=g, n=len(z), q25=q.iloc[0], median=q.iloc[1], q75=q.iloc[2]))
    fig.text(0.57, 0.72, 'Baseline ln(1 + degree)', ha='center', fontsize=7.5)
    fig.text(0.025, 0.693, 'b', fontsize=12, fontweight='bold')
    fig.text(0.5, 0.693, 'Own connectivity', fontsize=9, ha='center')
    joint_records = []
    partner = pd.read_csv(SRC / 'network_models.csv')
    models = ['M0', 'M1', 'M1_partner_sample', 'M2']
    ys = [3.3, 2.3, 0.9, -0.1]
    d = pd.read_csv(SRC / 'own_models.csv')
    for outcome, left, title in [('journal', 0.265, 'Journal percentile'), ('citation', 0.655, '12-month citation percentile')]:
        ax = fig.add_axes([left, 0.445, 0.3, 0.215])
        axes(ax, (-4, 8), [-4, 0, 4, 8], (-0.65, 3.85))
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='y', length=0)
        ax.axvline(0, color=AXIS, lw=0.8, ls=(0, (3, 3)))
        ax.axhline(1.6, c=AXIS, lw=0.6)
        ax.set_yticks(ys, ['Unadjusted', 'Adjusted', 'Adjusted\n(partner sample)', '+ Partners'] if outcome == 'journal' else [''] * 4)
        for y, m in zip(ys, models):
            for j, g in enumerate(G):
                r = d[(d.outcome == outcome) & (d.model_id == m) & (d.group == g)].iloc[0]
                err(ax, r, y + (1 - j) * 0.16, g, ms=3.4)
                joint_records.append(dict(panel='b', outcome=outcome, group=g, estimate=r.estimate, lower=r.lower, upper=r.upper, n_institutions=int(r.n_institutions), model=m))
        ax.set_title(title, pad=8)
    fig.text(0.61, 0.416, 'Slope per ln(1 + degree)', ha='center', fontsize=7.3)
    fig.legend(handles=group_handles, loc='center', bbox_to_anchor=(0.61, 0.391), ncol=3, frameon=False, fontsize=7, handlelength=1.8, columnspacing=1.8)
    fig.text(0.025, 0.351, 'c', fontsize=12, fontweight='bold')
    fig.text(0.5, 0.351, 'Partner connectivity (pooled)', fontsize=9, ha='center')
    for outcome, left, title in [('journal', 0.265, 'Journal percentile'), ('citation', 0.655, '12-month citation percentile')]:
        ax = fig.add_axes([left, 0.261, 0.3, 0.055])
        axes(ax, (0, 2.5), [0, 1, 2], (-0.65, 0.65))
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='y', length=0)
        ax.set_yticks([0], ['Pooled'] if outcome == 'journal' else [''])
        ax.axvline(0, color=AXIS, lw=0.8, ls=(0, (3, 3)))
        r = partner[partner.outcome == outcome].iloc[0]
        ax.errorbar(r.estimate, 0, xerr=[[r.estimate - r.lower], [r.upper - r.estimate]], fmt='o', c=MUTED, ms=4.4, lw=1.1, capsize=2)
        ax.annotate(f'{r.estimate:+.2f}', (r.estimate, 0), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=7.2, fontweight='bold')
        ax.annotate(f'n = {int(r.n_institutions):,}', (r.estimate, 0), xytext=(0, -13), textcoords='offset points', ha='center', fontsize=6.7, color=MUTED)
        ax.set_title(title, pad=5, fontsize=8)
        joint_records.append(dict(panel='c', outcome=outcome, group='pooled', estimate=r.estimate, lower=r.lower, upper=r.upper, n_institutions=int(r.n_institutions), model='M2'))
    fig.text(0.61, 0.224, 'Slope per 10 partner-percentile points', ha='center', fontsize=7.5)
    (QA / 'network_plotted_values.json').write_text(json.dumps(joint_records, indent=2))
    fig.text(0.025, 0.182, 'd', fontsize=12, fontweight='bold')
    fig.text(0.56, 0.182, 'Partner-information coverage', fontsize=9, ha='center')
    ax = fig.add_axes([0.215, 0.084, 0.64, 0.083])
    axes(ax, (0, 100), [0, 25, 50, 75, 100], (-0.5, 2.5))
    rows(ax)
    d = pd.read_csv(SRC / 'partner_status.csv')
    counts = d.groupby(['group', 'status']).AF_links.sum().unstack(fill_value=0).reindex(G)
    statuses = [('valid_observed_roster_all_partners_scored', 'Partners scored', '#364D85'), ('observed_author_affiliations_incomplete', 'Incomplete mapping', '#BDCADF'), ('outside_boundary', 'Outside boundary', '#8D9BB1'), ('single_institution', 'Single institution', '#E7ECF4'), ('focal_not_in_roster', 'Focal absent', '#54647A')]
    left = np.zeros(3)
    totals = counts.sum(axis=1).to_numpy()
    coverage = []
    for status, label, col in statuses:
        vals = 100 * counts[status].to_numpy() / totals
        ax.barh([2, 1, 0], vals, left=left, color=col, height=0.54, edgecolor='white', linewidth=0.3)
        if status == 'valid_observed_roster_all_partners_scored':
            for y, v in zip([2, 1, 0], vals):
                ax.text(v / 2, y, f'{v:.1f}%', ha='center', va='center', fontsize=7, color='white', fontweight='bold')
        for g, n, v in zip(G, counts[status], vals):
            coverage.append(dict(group=g, status=status, n=int(n), percent=v))
        left += vals
    for y, n in zip([2, 1, 0], totals):
        ax.text(1.025, y, f'n = {int(n):,}', transform=ax.get_yaxis_transform(), fontsize=6.7, color=MUTED, va='center')
    ax.set_xlabel('AF study–institution links (%)', fontsize=7.5)
    fig.legend(handles=[Patch(facecolor=c, label=l) for s, l, c in statuses], loc='center', bbox_to_anchor=(0.53, 0.018), ncol=5, frameon=False, fontsize=6.0, handlelength=1.0, handletextpad=0.45, columnspacing=1.2)
    for y in [0.709, 0.373, 0.207]:
        fig.add_artist(Line2D([0.1, 0.96], [y, y], transform=fig.transFigure, color='#D5DAE1', lw=0.55))
    save(fig, 'Extended_Data_Fig10')
    pd.DataFrame(summary).to_csv(QA / 'selection_summary.csv', index=False)
    pd.DataFrame(coverage).to_csv(QA / 'partner_coverage.csv', index=False)

def absolute_companion():
    fig = plt.figure(figsize=(183 / 25.4, 157 / 25.4))
    d = pd.read_csv(SRC / 'absolute_network_outcomes.csv')
    for j, o in enumerate(['journal', 'citation']):
        for i, g in enumerate(G):
            ax = fig.add_axes([0.14 + j * 0.46, 0.69 - i * 0.26, 0.355, 0.19])
            axes(ax, (0, 10), [0, 3, 6, 9], (-3, 103), True)
            z = d[(d.outcome == o) & (d.group == g)]
            ax.scatter(z.x, z.REF_mean, s=4 if g == 'H' else 9, marker='x', color=REF, alpha=0.22 if g == 'H' else 0.48, linewidths=0.4, rasterized=True)
            ax.scatter(z.x, z.AF_mean, s=4 if g == 'H' else 9, facecolors='none', edgecolors=AF, alpha=0.2 if g == 'H' else 0.6, linewidths=0.4, rasterized=True)
            ax.set_yticks([0, 50, 100])
            ax.text(0.97, 0.06, f'n = {len(z):,}', transform=ax.transAxes, ha='right', fontsize=6.7, color=MUTED)
            if j == 0:
                ax.set_ylabel('Percentile')
                ax.text(-0.23, 0.5, N[g], transform=ax.transAxes, rotation=90, ha='center', va='center', color=C[g], fontsize=8.5, fontweight='bold')
            if i == 0:
                ax.set_title('Journal percentile' if j == 0 else '12-month citation percentile', pad=9)
            if i == 2:
                ax.set_xlabel('Baseline ln(1 + degree)')
    fig.legend(handles=[Line2D([], [], marker='o', ls='none', mfc='white', mec=AF, label='AF', ms=4), Line2D([], [], marker='x', ls='none', color=REF, label='non-AF', ms=4)], loc='upper center', bbox_to_anchor=(0.55, 0.985), ncol=2, frameon=False)
    save(fig, 'Supplementary_network_absolute_outcomes')
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--prepare', action='store_true')
    args = p.parse_args()
    if args.prepare:
        prepare()
    setup()
    ed9()
    ed10()
    print('Rendered ED9 and ED10 with panel-local legends below.')
