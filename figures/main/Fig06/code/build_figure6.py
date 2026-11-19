from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Render saved network associations. No model fitting or bootstrap reruns."""
from pathlib import Path
import os, sys, json, hashlib
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'validation/mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, patches
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.transforms import Bbox
from matplotlib.font_manager import fontManager
from PIL import Image
for name in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + name)
INK, MUTED, GRID = ('#11151C', '#526278', '#E6EDF4')
GROUPS = ['L', 'M', 'H']
LABEL = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
COL = {'L': '#5B96C9', 'M': '#2F8B75', 'H': '#173F82'}
MARK = {'L': 'o', 'M': 's', 'H': '^'}
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'axes.linewidth': 0.6, 'xtick.labelsize': 7.2, 'ytick.labelsize': 8, 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': INK, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'figure.facecolor': 'white', 'savefig.facecolor': 'white'})

def read(name):
    return pd.read_csv(P / 'source_data' / f'{name}.csv', float_precision='round_trip')

def rgba(c, a):
    return colors.to_rgba(c, a)

def legend(fig, y=0.977):
    fig.legend(handles=[Line2D([], [], color=COL[g], lw=1.6, label=LABEL[g]) for g in GROUPS], loc='center', bbox_to_anchor=(0.55, y), ncol=3, frameon=False, fontsize=7.3, handlelength=1.1, handletextpad=0.6, columnspacing=1.7)

def export(fig, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    outside = []
    skip_ids = set()
    for ax in fig.axes:
        for axis in [ax.xaxis, ax.yaxis]:
            lo, hi = sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks():
                if not lo - 1e-07 <= tick.get_loc() <= hi + 1e-07:
                    skip_ids.update([id(tick.label1), id(tick.label2)])
    for text in fig.findobj(Text):
        if id(text) in skip_ids or not text.get_visible() or (not text.get_text().strip()):
            continue
        if text.axes is not None:
            skip = False
            for axis in [text.axes.xaxis, text.axes.yaxis]:
                lo, hi = sorted(axis.get_view_interval())
                for t in axis.get_major_ticks():
                    if text in [t.label1, t.label2] and (not lo <= t.get_loc() <= hi):
                        skip = True
            if skip:
                continue
        b = text.get_window_extent(renderer)
        if b.x0 < -0.5 or b.y0 < -0.5 or b.x1 > fig.bbox.width + 0.5 or (b.y1 > fig.bbox.height + 0.5):
            outside.append(text.get_text())
    assert not outside, outside
    output_box = Bbox.from_bounds(0, 0, 183 / 25.4, 183.5 / 25.4)
    for text in fig.findobj(Text):
        if id(text) in skip_ids or not text.get_visible() or (not text.get_text().strip()):
            continue
        assert text.get_window_extent(renderer).y1 <= 183.5 / 190 * fig.bbox.height + 0.5, text.get_text()
    for ext in ['pdf', 'svg']:
        fig.savefig(P / 'figures' / f'{name}.{ext}', bbox_inches=output_box)
    png = P / 'figures' / f'{name}_600dpi.png'
    fig.savefig(png, dpi=600, bbox_inches=output_box)
    with Image.open(png) as im:
        im.convert('RGB').save(png, dpi=(600, 600))
        im.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(P / 'figures' / f'{name}_preview.png')
    plt.close(fig)
    return outside
tables = {o: read('network_results_' + o) for o in ['journal', 'citation']}
coords = {k: read(name) for k, name in [('own', 'own_connectivity_coordinates'), ('partner', 'partner_centrality_coordinates')]}
fig = plt.figure(figsize=(183 / 25.4, 190 / 25.4))
FRAME_LEFT, FRAME_RIGHT, DIVIDER = (0.06, 0.985, 0.543)
PANEL_CENTERS = [0.313, 0.773]
fig.text(FRAME_LEFT, 0.947, 'a', fontsize=11, fontweight='bold', va='top')
fig.text(0.55, 0.947, 'b', fontsize=11, fontweight='bold', va='top')
fig.text(PANEL_CENTERS[0], 0.945, 'Own connectivity', ha='center', va='top', fontsize=9.0)
fig.text(PANEL_CENTERS[1], 0.945, 'Partner connectivity', ha='center', va='top', fontsize=9.0)
col_x = [0.11, 0.326, 0.57, 0.786]
width = 0.19
axes_height = 0.145
row_y = [0.665, 0.397, 0.129]
data_axes = []
for i, title in enumerate(['Journal percentile', '12-month citation'] * 2):
    fig.text(col_x[i] + width / 2, 0.909, title, ha='center', fontsize=7.8)
fig.text(0.027, 0.485, 'AF − non-AF (percentile points)', rotation=90, ha='center', va='center', fontsize=7.5)
registry, curve_records, scatter_checks = ([], [], [])
for row_id, g in enumerate(GROUPS):
    y0 = row_y[row_id]
    fig.add_artist(patches.Rectangle((FRAME_LEFT, y0 - 0.033), FRAME_RIGHT - FRAME_LEFT, 0.256, transform=fig.transFigure, facecolor='none', edgecolor='#D2DDE8', linewidth=0.65, zorder=0))
    fig.add_artist(Line2D([FRAME_LEFT, FRAME_LEFT], [y0 - 0.033, y0 + 0.223], transform=fig.transFigure, color=COL[g], lw=1.9, zorder=1))
    fig.add_artist(Line2D([DIVIDER, DIVIDER], [y0 - 0.021, y0 + 0.212], transform=fig.transFigure, color='#A5B5C9', lw=0.9, zorder=0))
    fig.text(col_x[0], y0 + 0.201, LABEL[g], fontsize=8.9, fontweight='bold', color=COL[g], va='bottom')
    for kind, kind_col in [('own', 0), ('partner', 2)]:
        source = coords[kind]
        observed = source[source.group.eq(g) & source.coordinate_type.eq('institution')]
        xmin, xmax = (float(observed.x.min()), float(observed.x.max()))
        pad = (xmax - xmin) * 0.04
        xlim = (xmin - pad, xmax + pad)
        ticks = ({'L': [0, 1, 2, 3], 'M': [1, 3, 5], 'H': [3, 6, 9]} if kind == 'own' else {'L': [50, 75, 100], 'M': [60, 80, 100], 'H': [25, 50, 75, 100]})[g]
        for outcome, outcome_col, metric in [('journal', 0, 'journal_position'), ('citation', 1, 'percentile_12m')]:
            col = kind_col + outcome_col
            z = source[source.group.eq(g) & source.outcome.eq(outcome) & source.coordinate_type.eq('institution')]
            t = tables[outcome]
            model = t[t.sample_id.eq('degree_' + kind) & t.group.eq(g) & t.metric.eq(metric)]
            slope = model[model.coefficient.eq('slope')].iloc[0]
            intercept = float(model[model.coefficient.eq('intercept')].estimate.iloc[0])
            v, lo, hi = map(float, [slope.estimate, slope.lower, slope.upper])
            assert len(z) == int(slope.n_institutions) and z.y.between(-85, 85).all()
            assert z.x.between(*xlim).all()
            ax = fig.add_axes([col_x[col], y0, width, axes_height])
            data_axes.append((row_id, col, ax))
            ax.spines[['top', 'right']].set_visible(False)
            for name in ['left', 'bottom']:
                ax.spines[name].set_color('#8D9FB3')
            ax.tick_params(axis='both', length=2.1, width=0.5, labelsize=6.8, pad=2.7)
            ax.set(xlim=xlim, xticks=ticks, ylim=(-85, 85), yticks=[-75, 0, 75])
            if col != 0:
                ax.tick_params(axis='y', labelleft=False)
            ax.axhline(0, c='#8B9BAF', ls=(0, (3, 3)), lw=0.7, zorder=1)
            tint = np.array(colors.to_rgb(COL[g]))
            strength = {'L': 0.78, 'M': 0.6, 'H': 0.38}[g]
            tint = 1 - (1 - tint) * strength
            ax.scatter(z.x, z.y, s={'L': 7.2, 'M': 3.8, 'H': 2.0}[g], marker='o', color=tint, alpha=1, edgecolors='none', zorder=2)
            scale = 10 if kind == 'partner' else 1
            xs = np.sort(z.x.unique())
            cuts = np.flatnonzero(np.diff(xs) > max((xs[-1] - xs[0]) * 0.15, 1e-09)) + 1
            for segment_id, segment in enumerate(np.split(xs, cuts)):
                if len(segment) < 2:
                    continue
                xx = np.linspace(segment[0], segment[-1], 100)
                yy = intercept + v * xx / scale
                ax.plot(xx, yy, c=COL[g], lw=1.6, zorder=4)
                for x, y in zip(xx, yy):
                    curve_records.append({'predictor': kind, 'outcome': outcome, 'group': g, 'segment': segment_id, 'x': float(x), 'y': float(y), 'intercept': intercept, 'saved_slope': v, 'x_scale': scale})
            old = source[source.group.eq(g) & source.outcome.eq(outcome) & source.coordinate_type.eq('conditional_M0_curve')]
            if len(old):
                assert np.allclose(old.y, intercept + v * old.x / scale, atol=1e-12, rtol=1e-12)
            fig.text(col_x[col], y0 + 0.174, f'β = {v:+.2f}', color=INK, fontsize=7.2, fontweight='bold', va='bottom')
            fig.text(col_x[col] + width, y0 + 0.174, f'n = {len(z):,}', ha='right', color=MUTED, fontsize=6.4, va='bottom')
            fig.text(col_x[col], y0 + 0.153, f'95% [{lo:+.2f}, {hi:+.2f}]', color=MUTED, fontsize=6.4, va='bottom')
            registry.append({'panel': 'a' if kind == 'own' else 'b', 'predictor': kind, 'outcome': outcome, 'group': g, 'estimate': v, 'lower': lo, 'upper': hi, 'n_institutions': len(z), 'unit': slope.unit, 'interval_type': slope.interval_type})
            scatter_checks.append({'predictor': kind, 'outcome': outcome, 'group': g, 'n_points': len(z), 'xlim': list(xlim), 'all_points_displayed': True, 'shared_y_limits': [-85, 85]})
fig.text(PANEL_CENTERS[0], 0.066, 'ln(1 + degree)', ha='center', fontsize=8.4)
fig.text(PANEL_CENTERS[1], 0.066, 'Partners’ mean degree percentile', ha='center', fontsize=8.4)
fig.text(PANEL_CENTERS[0], 0.039, 'β per unit', ha='center', color=MUTED, fontsize=8.0)
fig.text(PANEL_CENTERS[1], 0.039, 'β per 10 percentile points', ha='center', color=MUTED, fontsize=8.0)
assert registry == json.loads((P / 'validation/original_plotted_values.json').read_text())
assert scatter_checks == json.loads((P / 'validation/original_scatter_checks.json').read_text())
for row_id, col, ax in data_axes:
    assert np.isclose(ax.get_position().x0, col_x[col])
    assert np.isclose(ax.get_position().y0, row_y[row_id])
    assert np.isclose(ax.get_position().width, width)
    assert np.isclose(ax.get_position().height, axes_height)
outside = export(fig, 'Figure6_readability')
(P / 'validation/plotted_values.json').write_text(json.dumps(registry, indent=2) + '\n')
(P / 'validation/scatter_checks.json').write_text(json.dumps(scatter_checks, indent=2) + '\n')
pd.DataFrame(curve_records).to_csv(P / 'validation/rendered_fit_coordinates.csv', index=False, float_format='%.17g')
(P / 'validation/style_and_layout.json').write_text(json.dumps({'size_mm': [183, 183.5], 'canvas_size_mm': [183, 190], 'top_margin_trim_mm': 6.5, 'group_frames': True, 'frame_edge': '#D2DDE8', 'frame_linewidth_pt': 0.65, 'group_color_left_accent_pt': 1.9, 'frame_background': 'white', 'central_divider_color': '#A5B5C9', 'central_divider_linewidth_pt': 0.9, 'bottom_axis_title_size_pt': 8.4, 'slope_unit_size_pt': 8.0, 'range_note_on_figure': False, 'group_frame_vertical_gap_mm': 2.28, 'group_definition_visible': 'caption only; group row labels retained', 'row_y': row_y, 'column_x': col_x, 'column_width': width, 'axes_height': axes_height, 'panel_centers': PANEL_CENTERS, 'frame_left': FRAME_LEFT, 'frame_right': FRAME_RIGHT, 'groups_in_separate_rows': True, 'panels': {'a': 'own connectivity', 'b': 'partner connectivity'}, 'group_colors': COL, 'scatter_tint_strength': {'L': 0.78, 'M': 0.6, 'H': 0.38}, 'scatter_sizes_pt_squared': {'L': 7.2, 'M': 3.8, 'H': 2.0}, 'fit_line_width_pt': 1.6, 'slopes_in_neutral_bold_text': True, 'slope_units_directly_labelled': True, 'group_identity_directly_labelled_in_each_row': True, 'scatter_tints_are_opaque_to_prevent_overlap_darkening': True, 'all_12_slopes_and_intervals_on_their_corresponding_scatter': True, 'n_is_institutions_not_studies': True, 'common_y_limits': [-85, 85], 'x_support_shared_across_outcomes_within_group_and_predictor': True, 'x_scales_differ_across_groups': True, 'original_slopes_intervals_counts_exact_match': True, 'scatter_checks_exact_match': True, 'outside_canvas_text': outside, 'source_hashes': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (P / 'source_data').glob('*.csv')}, 'new_models_fitted': False, 'new_bootstrap_draws': 0}, indent=2) + '\n')
print('Saved three framed output groups, 12 scatter panels with original slopes, intervals and institution counts.')
