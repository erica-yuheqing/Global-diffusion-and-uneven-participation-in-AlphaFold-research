from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Rebuild Figure 5 from audited numerical sources; no analytical re-estimation.

Run --prepare once to copy the source data from the existing review package.
Subsequent runs use only the portable CSVs in this figure package.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib import font_manager
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'source_data'
OUT = ROOT / 'figures'
QA = ROOT / 'validation'
ORIGINAL = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/Scientific_Influence_review_v2.0')
GROUPS = ['L', 'M', 'H']
NAMES = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
COLORS = {'L': '#5798D2', 'M': '#298F79', 'H': '#193F83'}
MARKERS = {'L': 'o', 'M': 's', 'H': '^'}
INK = '#151A22'
MUTED = '#4D607A'
GRID = '#E5EBF3'
AXIS = '#9AAAC1'
PANEL_TITLE_SIZE = 9.3

def prepare():
    files = {'journal_estimates.csv': 'source_data/panels/Fig6_a/coordinates.csv', 'citation_estimates.csv': 'source_data/panels/Fig6_b/coordinates.csv', 'journal_institutions.csv': 'source_data/panels/ED_SI1_b/coordinates.csv', 'citation_institutions.csv': 'source_data/panels/ED_SI2_b/coordinates.csv', 'coverage_2024.csv': 'tables/coverage_summary_2024.csv', 'coverage_country_group_2024.csv': 'tables/coverage_country_group_2024.csv'}
    provenance = []
    for name, rel in files.items():
        f = ORIGINAL / rel
        shutil.copy2(f, SRC / name)
        provenance.append({'source': str(f), 'copy': f'source_data/{name}', 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()})
    (QA / 'source_provenance.json').write_text(json.dumps(provenance, indent=2))

def style_axes(ax, xlim, ticks, ylim):
    ax.set(xlim=xlim, xticks=ticks, ylim=ylim)
    for side in ['top', 'right', 'left']:
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color(AXIS)
    ax.spines['bottom'].set_linewidth(0.65)
    ax.tick_params(axis='x', colors=MUTED, length=2.6, width=0.6, pad=4)
    ax.tick_params(axis='y', left=False, labelleft=False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color=GRID, linewidth=0.45)

def group_labels(ax, positions):
    for g, y in zip(GROUPS, positions):
        ax.text(-0.055, y, NAMES[g], transform=ax.get_yaxis_transform(), va='center', ha='right', color=COLORS[g], fontsize=8.3, clip_on=False)

def main():
    args = argparse.ArgumentParser()
    args.add_argument('--prepare', action='store_true')
    opts = args.parse_args()
    for directory in [SRC, OUT, QA]:
        directory.mkdir(exist_ok=True, parents=True)
    if opts.prepare:
        prepare()
    for f in ['Arial.ttf', 'Arial Bold.ttf']:
        p = Path('/System/Library/Fonts/Supplemental') / f
        if p.exists():
            release_addfont(str(p))
    plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.2, 'ytick.labelsize': 8, 'text.color': INK, 'axes.labelcolor': INK, 'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none', 'savefig.facecolor': 'white'})
    fig = plt.figure(figsize=(180 / 25.4, 176 / 25.4), facecolor='white')
    values, distribution_summaries = ([], [])
    groups_y = [2, 1, 0]
    configs = [('a', 'journal', 'journal_position', 'Journal percentile', 0.71, 0.917), ('b', 'citation', 'percentile_12m', '12-month citation percentile', 0.435, 0.642)]
    expected_means = {'journal': [6.84, 9.08, 8.61], 'citation': [4.19, 5.6, 8.36]}
    expected_n = {'journal': [121, 576, 5202], 'citation': [45, 269, 3735]}
    fig.text(0.305, 0.971, 'Mean difference (95% interval)', fontsize=7.8, ha='center', va='center', color=MUTED)
    fig.text(0.75, 0.971, 'Distribution across institutions', fontsize=7.8, ha='center', va='center', color=MUTED)
    for letter, outcome, metric, title, y0, title_y in configs:
        est = pd.read_csv(SRC / f'{outcome}_estimates.csv')
        est = est.loc[est.metric.eq(metric)].set_index('group')
        inst = pd.read_csv(SRC / f'{outcome}_institutions.csv')
        mean_ax = fig.add_axes([0.155, y0, 0.3, 0.16997])
        dist_ax = fig.add_axes([0.535, y0, 0.43, 0.16997])
        style_axes(mean_ax, (-0.5, 12.5), [0, 4, 8, 12], (-0.5, 2.5))
        style_axes(dist_ax, (-85, 85), [-80, -40, 0, 40, 80], (-0.5, 2.5))
        group_labels(mean_ax, groups_y)
        for ax in [mean_ax, dist_ax]:
            ax.axvline(0, color='#788CA9', ls=(0, (3, 3)), lw=0.7, zorder=1)
            for yy in [0.5, 1.5]:
                ax.axhline(yy, color=GRID, lw=0.45, zorder=0)
        for j, (g, yy) in enumerate(zip(GROUPS, groups_y)):
            row = est.loc[g]
            observed = inst.loc[inst.group.eq(g), f'delta_{metric}'].dropna().to_numpy()
            assert len(observed) == expected_n[outcome][j]
            assert np.isclose(observed.mean(), row.estimate, atol=1e-10)
            assert f'{row.estimate:.2f}' == f'{expected_means[outcome][j]:.2f}'
            mean_ax.errorbar(row.estimate, yy, xerr=[[row.estimate - row.lower], [row.upper - row.estimate]], color=COLORS[g], marker=MARKERS[g], markersize=5.1, elinewidth=1.1, capsize=2.3, capthick=0.9, zorder=4)
            mean_ax.annotate(f'+{row.estimate:.2f}', (row.estimate, yy), xytext=(0, 8), textcoords='offset points', ha='center', va='bottom', fontsize=8.1)
            body = dist_ax.violinplot(observed, positions=[yy], orientation='horizontal', widths=0.69, points=180, showmeans=False, showmedians=False, showextrema=False)['bodies'][0]
            body.set_facecolor(COLORS[g])
            body.set_edgecolor(COLORS[g])
            body.set_alpha(0.26)
            body.set_linewidth(0.7)
            q25, median, q75 = np.quantile(observed, [0.25, 0.5, 0.75])
            dist_ax.plot([q25, q75], [yy, yy], color=COLORS[g], lw=2.1, solid_capstyle='round', zorder=4)
            dist_ax.plot(median, yy, 'o', mfc='white', mec=COLORS[g], mew=0.85, ms=4.2, zorder=5)
            dist_ax.text(0.99, yy - 0.29, f'n = {len(observed):,}', transform=dist_ax.get_yaxis_transform(), ha='right', va='center', fontsize=7.1, color=MUTED)
            values.append({'panel': letter, 'group': g, 'metric': metric, 'estimate': row.estimate, 'lower': row.lower, 'upper': row.upper, 'n_institutions': len(observed)})
            distribution_summaries.append({'outcome': outcome, 'group': g, 'n': len(observed), 'q25': q25, 'median': median, 'q75': q75, 'min': float(observed.min()), 'max': float(observed.max())})
        fig.text(0.035, title_y, letter, fontsize=11, fontweight='bold', va='center')
        fig.text(0.56, title_y, title, fontsize=PANEL_TITLE_SIZE, ha='center', va='center')
    fig.text(0.56, 0.377, 'AF - non-AF (percentile points)', fontsize=8.1, ha='center')
    fig.add_artist(Line2D([0.155, 0.965], [0.348, 0.348], transform=fig.transFigure, color='#D9E2EE', linewidth=0.65))
    cov = pd.read_csv(SRC / 'coverage_2024.csv').set_index('group')
    country_cov = pd.read_csv(SRC / 'coverage_country_group_2024.csv')
    assert country_cov.country.nunique() == 68
    assert len(country_cov) == 204
    assert country_cov.baseline_denominator.sum() == 48010
    assert not country_cov.duplicated(['country', 'group']).any()
    text_artists, coverage_details, gap_values = ([], [], [])
    targets = {'venue_lower': [0.58, 3.09, 23.41], 'citation_lower': [0.13, 0.89, 9.36]}
    fig.text(0.035, 0.316, 'c', fontsize=11, fontweight='bold', va='center')
    fig.text(0.155, 0.316, 'Confirmed institutional coverage (%)', fontsize=PANEL_TITLE_SIZE, va='center')
    legend_handles = [Line2D([0], [0], marker='o', linestyle='none', markersize=3, markerfacecolor='none', markeredgecolor='#9AAAC1', markeredgewidth=0.65, label='Country'), Line2D([0], [0], marker='o', linestyle='none', markersize=4.5, markerfacecolor=MUTED, markeredgecolor='white', markeredgewidth=0.5, label='Mean')]
    fig.legend(handles=legend_handles, loc='center right', bbox_to_anchor=(0.97, 0.316), ncol=2, frameon=False, fontsize=7.0, handletextpad=0.35, columnspacing=1.25, borderaxespad=0)
    fig.add_artist(Rectangle((0.07, 0.196875), 0.9, 0.053125, transform=fig.transFigure, facecolor='#F4F7FC', edgecolor='none', zorder=0))
    columns = [('venue_lower', 0.155, 0.318, 0.515, 'Journal ≥75th percentile'), ('citation_lower', 0.585, 0.318, 0.945, 'Citation ≥90th percentile')]
    for col_index, (metric, xpos, width, val_x, label) in enumerate(columns):
        ax = fig.add_axes([xpos, 0.08, width, 0.17])
        style_axes(ax, (-2, 70), [0, 20, 40, 60], (-0.6, 2.6))
        ax.patch.set_alpha(0)
        if col_index == 0:
            group_labels(ax, groups_y)
        for yy in [0.5, 1.5]:
            ax.axhline(yy, color=GRID, lw=0.45, zorder=0)
        fig.text(xpos + width / 2, 0.272, label, fontsize=7.8, ha='center', va='center')
        fig.text(val_x, 0.272, 'Mean', fontsize=7.0, color=MUTED, ha='center', va='center')
        for j, (g, yy) in enumerate(zip(GROUPS, groups_y)):
            frame = country_cov.loc[country_cov.group.eq(g)].sort_values('country')
            xs = frame[metric].to_numpy()
            value = float(cov.loc[g, metric])
            assert len(xs) == 68
            assert np.isclose(xs.mean(), value, atol=1e-12)
            assert f'{value:.2f}' == f'{targets[metric][j]:.2f}'
            placed = []
            jitter = np.zeros(len(xs))
            candidates = [0] + [sign * k * 0.075 for k in range(1, 6) for sign in (1, -1)]
            for index in np.argsort(xs, kind='stable'):
                x = xs[index]
                for dy in candidates:
                    if all((((x - px) / 1.15) ** 2 + ((dy - py) / 0.075) ** 2 >= 1.0 for px, py in placed)):
                        jitter[index] = dy
                        break
                else:
                    scores = [min((((x - px) / 1.15) ** 2 + ((dy - py) / 0.075) ** 2 for px, py in placed)) for dy in candidates]
                    jitter[index] = candidates[int(np.argmax(scores))]
                placed.append((x, jitter[index]))
            ax.scatter(xs, yy + jitter, s=6, facecolors='none', edgecolors=COLORS[g], linewidths=0.4, alpha=0.38, zorder=2)
            ax.scatter([value], [yy], s=34, marker=MARKERS[g], c=COLORS[g], edgecolors='white', linewidths=0.7, zorder=4)
            val_y = 0.08 + (yy + 0.6) / 3.2 * 0.17
            text_artists.append(fig.text(val_x, val_y, f'{value:.2f}', fontsize=8.4, ha='center', va='center', color=INK))
            values.append({'panel': 'c', 'group': g, 'metric': metric, 'estimate': value, 'unit': 'percent', 'denominator': 'all baseline institutions in country-group cells', 'weighting': 'equal countries', 'window': '2020-2024'})
            coverage_details.append({'metric': metric, 'group': g, 'n_countries': len(xs), 'mean': value, 'min': float(xs.min()), 'max': float(xs.max()), 'n_zero_countries': int((xs == 0).sum())})
        gap = float(cov.loc['H', metric] - cov.loc['L', metric])
        gap_values.append({'metric': metric, 'higher_minus_lower_pp': gap})
    fig.text(0.5575, 0.025, 'Institutions with ≥1 qualifying AF study (%)', fontsize=8.1, ha='center')
    (QA / 'country_coverage_summaries.json').write_text(json.dumps(coverage_details, indent=2))
    (QA / 'coverage_gaps.json').write_text(json.dumps(gap_values, indent=2))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = [t.get_window_extent(renderer) for t in text_artists]
    overlaps = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes)) if boxes[i].overlaps(boxes[j])]
    assert not overlaps, overlaps
    page = fig.bbox
    outside = [t.get_text() for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text() and (t.get_window_extent(renderer).x0 < 0 or t.get_window_extent(renderer).x1 > page.x1 or t.get_window_extent(renderer).y0 < 0 or (t.get_window_extent(renderer).y1 > page.y1))]
    assert not outside, outside
    base = OUT / 'Figure5_shared_labels'
    fig.savefig(base.with_suffix('.pdf'))
    fig.savefig(base.with_suffix('.svg'))
    fig.savefig(OUT / 'Figure5_shared_labels_600dpi.png', dpi=600)
    fig.savefig(OUT / 'Figure5_shared_labels_preview.png', dpi=180)
    (QA / 'plotted_values.json').write_text(json.dumps(values, indent=2))
    (QA / 'distribution_summaries.json').write_text(json.dumps(distribution_summaries, indent=2))
    (QA / 'verification.json').write_text(json.dumps({'all_mean_estimates_match_original': True, 'institution_counts_match_original': True, 'all_six_coverage_values_match_manuscript': True, 'distribution_means_match_group_estimates': True, 'coverage_labels_overlap': overlaps, 'text_outside_page': outside, 'no_new_inference_or_reestimated_intervals': True, 'coverage_is_confirmed_only': True, 'coverage_displayed_as_exact_percentages': True, 'coverage_layout': 'country distributions and country-equal means in two threshold columns', 'highlight': 'Lower group row; visual emphasis only', 'page_width_mm': 180, 'page_height_mm': 176, 'country_coverage_means_match_original': True, 'countries_per_group': 68, 'baseline_population': 48010, 'additional_information': 'observed country variation; descriptive gaps retained in caption', 'a_b_subpanel_headers': 'shared once at top', 'country_dots': 'all retained, lighter styling'}, indent=2))
    plt.close(fig)
    print('Exported Figure5_shared_labels: PDF, editable SVG, 600-dpi PNG and preview.')
if __name__ == '__main__':
    main()
