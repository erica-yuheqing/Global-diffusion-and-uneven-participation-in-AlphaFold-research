from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Redraw frozen concentration estimates; no fitting or re-estimation of intervals."""
from pathlib import Path
import os, sys, json, hashlib
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch/mpl')
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import fontManager
from matplotlib.text import Text
from matplotlib.colors import to_rgba
from PIL import Image
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
AF = '#D5281D'
BLUE = '#12145F'
MATCHED = '#6A87B8'
INK = '#15171C'
MUTED = '#626A78'
GRID = '#E9EDF2'
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.2, 'ytick.labelsize': 7.2, 'axes.linewidth': 0.65, 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'figure.facecolor': 'white', 'savefig.facecolor': 'white'})

def read(n):
    return pd.read_csv(P / 'source_data' / n, float_precision='round_trip')
a = read('Figure1a.csv').sort_values('year')
r = read('Figure1b_raw.csv').sort_values('year')
m = read('Figure1b_matched.csv').sort_values('year')
rawall = read('concentration_endpoint_sensitivity.csv')
matchall = read('matching_endpoint_changes.csv')
raw = rawall[(rawall.start == 2021) & (rawall.end == 2025) & rawall.estimand.eq('AF_minus_C_Gini_endpoint_change')].iloc[0]
matched = matchall[(matchall.start == 2021) & (matchall.end == 2025) & matchall.spec.eq('count_composition')].iloc[0]
assert np.allclose(a.af_gini - a.comparator_gini, r.delta_gini, atol=1e-14, rtol=0)
assert np.allclose(m.AF_gini - m.matched_non_AF_mean, m.point, atol=1e-14, rtol=0)
assert np.isclose(raw.point, r.delta_gini.iloc[-1] - r.delta_gini.iloc[0], rtol=0, atol=1e-14)
assert np.isclose(matched.point, m.point.iloc[-1] - m.point.iloc[0], rtol=0, atol=1e-14)
assert a.country_count.eq(227).all() and m.replicates.eq(2000).all()
early = float((r.delta_gini.iloc[0] - r.delta_gini.iloc[1]) / (r.delta_gini.iloc[0] - r.delta_gini.iloc[-1]))
fig = plt.figure(figsize=(183 / 25.4, 137 / 25.4))
registry = []
ax = fig.add_axes([0.095, 0.395, 0.375, 0.465])
bx = fig.add_axes([0.605, 0.395, 0.375, 0.465])
fig.text(0.025, 0.977, 'a', fontsize=11, fontweight='bold', va='top')
fig.text(0.535, 0.977, 'b', fontsize=11, fontweight='bold', va='top')
for axis in [ax, bx]:
    axis.spines[['top', 'right']].set_visible(False)
    for s in ['left', 'bottom']:
        axis.spines[s].set_color('#6F7785')
    axis.set_axisbelow(True)
    axis.grid(axis='y', color=GRID, lw=0.5)
    axis.tick_params(length=2.8, width=0.6, pad=3)
    axis.set(xlim=(2020.8, 2025.2), xticks=range(2021, 2026), xlabel='Publication year')
    axis.xaxis.labelpad = 6
for prefix, col, mark, fillalpha, label in [('af', AF, 'o', 0.1, 'AF'), ('comparator', BLUE, 's', 0.075, 'non-AF')]:
    ax.fill_between(a.year, a[prefix + '_lower'], a[prefix + '_upper'], color=col, alpha=fillalpha, lw=0)
    line, = ax.plot(a.year, a[prefix + '_gini'], color=col, lw=1.5, marker=mark, ms=4.5, mec=col, mfc=col, mew=0.6, label=label, zorder=3)
    assert np.array_equal(line.get_ydata(), a[prefix + '_gini'])
    for row in a.itertuples():
        registry.append({'panel': 'a', 'series': label, 'year': row.year, 'point': getattr(row, prefix + '_gini'), 'lower': getattr(row, prefix + '_lower'), 'upper': getattr(row, prefix + '_upper')})
    for idx, ha, dx in [(0, 'left', 2), (-1, 'right', -2)]:
        row = a.iloc[idx]
        v = float(row[prefix + '_gini'])
        ax.annotate(f'{v:.4f}', (row.year, v), xytext=(dx, 7 if prefix == 'af' else -13), textcoords='offset points', ha=ha, color=col, fontsize=7.6)
ax.set(ylim=(0.89, 0.96), yticks=[0.9, 0.92, 0.94, 0.96], ylabel='Output Gini')
ax.legend(frameon=False, loc='lower center', bbox_to_anchor=(0.5, 1.09), ncol=2, fontsize=8, handlelength=2, handletextpad=0.6, columnspacing=1.8)
bx.fill_between(r.year, r.delta_lower, r.delta_upper, color=BLUE, alpha=0.075, lw=0)
rawline, = bx.plot(r.year, r.delta_gini, color=BLUE, lw=1.5, marker='D', ms=4.2, mfc=BLUE, mec=BLUE, mew=0.55, zorder=4)
errs = np.array([m.point - m.lower, m.upper - m.point])
matchedlines = bx.errorbar(m.year, m.point, yerr=errs, color=MATCHED, lw=1.3, ls=(0, (3, 2)), marker='o', ms=4.4, mfc='white', mec=MATCHED, mew=0.8, capsize=2.4, capthick=0.7, elinewidth=0.85, zorder=3)
assert np.array_equal(rawline.get_ydata(), r.delta_gini)
assert np.array_equal(matchedlines.lines[0].get_ydata(), m.point)
segments = matchedlines.lines[2][0].get_segments()
assert np.allclose([s[0, 1] for s in segments], m.lower, atol=1e-14, rtol=0)
assert np.allclose([s[1, 1] for s in segments], m.upper, atol=1e-14, rtol=0)
bx.axhline(0, color='#9AA1AC', lw=0.7, ls=(0, (4, 3)), zorder=1)
bx.set(ylim=(-0.003, 0.058), yticks=[0, 0.01, 0.02, 0.03, 0.04, 0.05], ylabel='Gini gap (AF − non-AF)')
bx.legend(handles=[Line2D([], [], color=BLUE, lw=1.5, marker='D', ms=4, mfc=BLUE, label='Raw'), Line2D([], [], color=MATCHED, lw=1.3, ls='--', marker='o', ms=4, mfc='white', label='Matched')], frameon=False, loc='lower center', bbox_to_anchor=(0.5, 1.09), ncol=2, fontsize=8, columnspacing=1.7, handletextpad=0.6)
for frame, col, key in [(r, BLUE, 'delta_gini'), (m, MATCHED, 'point')]:
    for idx, ha, dx in [(0, 'left', 2), (-1, 'right', -2)]:
        row = frame.iloc[idx]
        v = float(row[key])
        dy = 7 if key == 'delta_gini' else -14
        bx.annotate(f'{v:.4f}', (row.year, v), xytext=(dx, dy), textcoords='offset points', ha=ha, color=col, fontsize=7.5)
    for row in frame.itertuples():
        registry.append({'panel': 'b', 'series': 'Raw' if key == 'delta_gini' else 'Matched', 'year': row.year, 'point': getattr(row, key), 'lower': getattr(row, 'delta_lower' if key == 'delta_gini' else 'lower'), 'upper': getattr(row, 'delta_upper' if key == 'delta_gini' else 'upper')})
bx.plot([2021, 2021, 2022, 2022], [0.0523, 0.0532, 0.0532, 0.0523], color='#8E96A6', lw=0.7, clip_on=False)
bx.text(2020.91, 0.0551, f'{early:.0%} of net raw narrowing', fontsize=6.7, color=MUTED, ha='left')
fig.add_artist(Line2D([0.095, 0.98], [0.315, 0.315], transform=fig.transFigure, color='#DFE3E9', lw=0.65))
fig.text(0.025, 0.29, 'c', fontsize=11, fontweight='bold', va='top')
cx = fig.add_axes([0.345, 0.112, 0.365, 0.155])
cx.set(xlim=(-0.026, 0.016), ylim=(0, 2), xticks=[-0.02, -0.01, 0, 0.01], yticks=[])
cx.spines[['top', 'right', 'left']].set_visible(False)
cx.spines['bottom'].set_color('#7C8491')
cx.set_axisbelow(True)
cx.grid(axis='x', color=GRID, lw=0.5)
cx.axvline(0, color='#929BA9', lw=0.75, ls=(0, (4, 3)))
cx.tick_params(axis='x', length=2.7, width=0.6, pad=3)
cx.set_xlabel('Change in Gini gap, 2025 − 2021', labelpad=6)
for y, q, col, mark, label, kind in [(1.5, raw, BLUE, 'D', 'Raw gap', '95% bootstrap interval'), (0.5, matched, MATCHED, 'o', 'Matched gap', '95% matched range')]:
    cx.errorbar([q.point], [y], xerr=[[q.point - q.lower], [q.upper - q.point]], color=col, marker=mark, ms=4.8, mfc=col if mark == 'D' else 'white', mec=col, mew=0.8, lw=1.4, capsize=3, capthick=0.9, zorder=3)
    yfig = 0.112 + 0.155 * y / 2
    fig.text(0.105, yfig + 0.006, label, fontsize=8.0, va='center', fontweight='bold', color=INK)
    fig.text(0.105, yfig - 0.02, kind, fontsize=6.5, va='center', color=MUTED)
    fig.text(0.755, yfig + 0.006, f'{q.point:+.4f}', fontsize=8.4, fontweight='bold', color=col, va='center')
    fig.text(0.755, yfig - 0.02, f'[{q.lower:+.4f}, {q.upper:+.4f}]', fontsize=6.8, color=MUTED, va='center')
    registry.append({'panel': 'c', 'series': label, 'start': 2021, 'end': 2025, 'point': q.point, 'lower': q.lower, 'upper': q.upper, 'interval_type': q.get('interval_type', 'conditional_95pct_whole_study_bootstrap_1000')})
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
outside = []
skip = set()
for aa in fig.axes:
    for axis in [aa.xaxis, aa.yaxis]:
        lo, hi = sorted(axis.get_view_interval())
        for tick in axis.get_major_ticks():
            if not aa.axison or not lo - 1e-07 <= tick.get_loc() <= hi + 1e-07:
                skip.update([id(tick.label1), id(tick.label2)])
for t in fig.findobj(Text):
    if id(t) in skip or not t.get_visible() or (not t.get_text().strip()):
        continue
    b = t.get_window_extent(renderer)
    if b.x0 < -0.5 or b.y0 < -0.5 or b.x1 > fig.bbox.width + 0.5 or (b.y1 > fig.bbox.height + 0.5):
        outside.append(t.get_text())
assert not outside, outside
for ext in ['pdf', 'svg']:
    fig.savefig(P / f'figures/Figure1_concentration_refined.{ext}')
png = P / 'figures/Figure1_concentration_refined_600dpi.png'
fig.savefig(png, dpi=600)
with Image.open(png) as im:
    im.convert('RGB').save(png, dpi=(600, 600))
    im.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(P / 'figures/Figure1_concentration_refined_preview.png')
(P / 'validation/plotted_values.json').write_text(json.dumps(registry, indent=2) + '\n')
(P / 'validation/style_and_checks.json').write_text(json.dumps({'palette': {'AF': AF, 'non_AF_and_raw_gap': BLUE, 'matched_gap': MATCHED}, 'size_mm': [183, 137], 'raw_early_narrowing_fraction': early, 'fixed_country_count': 227, 'source_numeric_changes': False, 'new_panel_c_uses_frozen_paired_endpoint_summaries': True, 'marginal_interval_endpoints_not_subtracted': True, 'matched_ranges_are_not_AF_minus_nonAF_confidence_intervals': True, 'no_smoothing_or_trend_test': True, 'outside_canvas_text': outside, 'source_hashes': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (P / 'source_data').glob('*.csv')}}, indent=2) + '\n')
print('Validated 20 annual estimates, 2 paired endpoint changes, and all saved uncertainty limits.')
