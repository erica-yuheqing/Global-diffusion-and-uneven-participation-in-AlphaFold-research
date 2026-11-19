from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Join verified AF milestones to the original ED2, preserving monthly/map data."""
from pathlib import Path
import os, sys, re, json, xml.etree.ElementTree as ET
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch/mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import patches, colors
from matplotlib.path import Path as MPath
from matplotlib.font_manager import fontManager
from matplotlib.text import Text
from PIL import Image
for font in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + font)
INK, MUTED, GRID = ('#11151C', '#657183', '#E9EEF4')
NAVY, MID, LIGHT, DATA = ('#173873', '#6685BE', '#BBCDED', '#173873')
BAR_BLUE = '#6685BE'
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.2, 'ytick.labelsize': 7.2, 'axes.linewidth': 0.6, 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'figure.facecolor': 'white', 'savefig.facecolor': 'white'})

def rgba(c, a):
    return colors.to_rgba(c, a)

def read(name):
    return pd.read_csv(P / 'source_data' / name, keep_default_na=False)

def num(date):
    return mdates.date2num(pd.Timestamp(date))
START, END = (pd.Timestamp('2018-01-01'), pd.Timestamp('2025-12-31'))
PHASES = [('2020-01-01', '2021-07-01', NAVY, 'Pre-AF2'), ('2021-07-01', '2024-05-01', MID, 'AF2'), ('2024-05-01', '2026-01-01', LIGHT, 'AF3')]
BOUNDARIES = ['2021-07-01', '2024-05-01']
events = read('milestones.csv')
cumulative, monthly = (read('monthly_cumulative.csv'), read('monthly_new.csv'))
stages = read('first_observed_stages.csv')
assert len(events) == 9 and len(stages) == 143
assert len(cumulative) == len(monthly) == 72
assert cumulative[['month', 'new_countries', 'cumulative_countries']].equals(monthly[['month', 'new_countries', 'cumulative_countries']])
fig = plt.figure(figsize=(183 / 25.4, 224 / 25.4))
for x, y, letter in [(0.025, 0.986, 'a'), (0.025, 0.386, 'b'), (0.025, 0.21, 'c')]:
    fig.text(x, y, letter, fontsize=11, fontweight='bold', va='top')
ns = {'s': 'http://www.w3.org/2000/svg'}
root = ET.parse(P / 'assets/original_ED2.svg').getroot()
old_map = root.find('.//s:g[@id="axes_1"]', ns)
collection = old_map.find('s:g[@id="PatchCollection_1"]', ns)
assert collection is not None and len(collection) == 280
clip_id = next(iter(collection)).attrib['clip-path'][5:-1]
clip = root.find(f'.//s:clipPath[@id="{clip_id}"]/s:rect', ns)
clip = {k: float(v) for k, v in clip.attrib.items()}

def fill(style):
    return re.search('(?:^|;)\\s*fill:\\s*([^;]+)', style).group(1).strip()

def parse_polygon(d):
    tokens = re.findall('[MLZmlz]|[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][-+]?\\d+)?', d)
    assert not re.search('[ACHQSTVachqstv]', d)
    vertices, codes, i, first = ([], [], 0, None)
    while i < len(tokens):
        command = tokens[i]
        i += 1
        if command in ['z', 'Z']:
            vertices.append(first)
            codes.append(MPath.CLOSEPOLY)
        else:
            assert command in ['M', 'L']
            pair = [float(tokens[i]), float(tokens[i + 1])]
            i += 2
            if command == 'M':
                first = pair
            vertices.append(pair)
            codes.append(MPath.MOVETO if command == 'M' else MPath.LINETO)
    return MPath(vertices, codes)
ma = fig.add_axes([0.045, 0.68, 0.92, 0.295])
polygons, markers = ([], [])
for path in collection:
    d, face = (path.attrib['d'], fill(path.attrib['style']))
    ma.add_patch(patches.PathPatch(parse_polygon(d), facecolor=face, edgecolor='white', linewidth=0.2))
    polygons.append({'d': d, 'fill': face})
for group in old_map:
    if group.attrib.get('id', '').startswith('PathCollection'):
        for use in group.findall('.//s:use', ns):
            x, y, face = (float(use.attrib['x']), float(use.attrib['y']), fill(use.attrib['style']))
            ma.scatter(x, y, s=6, c=face, edgecolor='#666A70', linewidth=0.25, zorder=3)
            markers.append({'x': x, 'y': y, 'fill': face})
assert len(markers) == 12
ma.set(xlim=(clip['x'], clip['x'] + clip['width']), ylim=(clip['y'] + clip['height'], clip['y']))
ma.set_aspect('equal')
ma.axis('off')
legend = [patches.Patch(facecolor=c, label=s) for c, s in [(NAVY, 'Pre-AF2'), (MID, 'AF2'), (LIGHT, 'AF3'), ('#E4E4E4', 'Not observed'), ('#F8F8F8', 'Outside code registry')]]
legend[-1].set_edgecolor('#BBBBBB')
legend[-1].set_linewidth(0.4)
fig.legend(handles=legend, loc='center', bbox_to_anchor=(0.53, 0.657), ncol=5, frameon=False, fontsize=6.5, handlelength=1.1, handletextpad=0.6, columnspacing=1.2)
fig.text(0.025, 0.628, 'Milestones', fontsize=8, va='center')
timeline = fig.add_axes([0.165, 0.42, 0.795, 0.19])
timeline.set(xlim=(START, END), ylim=(-0.25, 3.98))
timeline.set_yticks([3, 2, 1, 0], ['Method', 'Database', 'Code / weights', 'Recognition'])
timeline.tick_params(axis='y', length=0, pad=7, labelsize=6.7, labelcolor=MUTED)
timeline.xaxis.set_major_locator(mdates.YearLocator())
timeline.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
timeline.tick_params(axis='x', top=True, labeltop=True, bottom=False, labelbottom=False, length=2, width=0.5, pad=3)
for spine in timeline.spines.values():
    spine.set_visible(False)
for y in [3, 2, 1, 0]:
    timeline.hlines(y, START, END, color='#DCE4ED', linewidth=0.6)
for date in pd.date_range('2018-01-01', '2025-01-01', freq='YS'):
    timeline.axvline(date, color=GRID, lw=0.4, alpha=0.7, zorder=0)
for date in BOUNDARIES:
    timeline.axvline(pd.Timestamp(date), color='#8D9AB0', linewidth=0.65, linestyle=(0, (3, 3)), alpha=0.75, zorder=0)
lane_y = {'Method': 3, 'Database': 2, 'Code / weights': 1, 'Recognition': 0}
lane_colors = {'Method': NAVY, 'Database': '#466994', 'Code / weights': '#6685A7', 'Recognition': '#99A9BF'}
lane_marks = {'Method': 'o', 'Database': 's', 'Code / weights': 'D', 'Recognition': 'o'}
event_bounds = []
for row in events.itertuples():
    date, y, col = (pd.Timestamp(row.month), lane_y[row.lane], lane_colors[row.lane])
    timeline.scatter(date, y, s=20, marker=lane_marks[row.lane], facecolor='white' if row.lane == 'Recognition' else rgba(col, 0.9), edgecolor=col, linewidth=0.65, zorder=4)
    label = date.strftime('%b %Y') + '\n' + row.label
    if row.detail:
        label += '\n' + row.detail
    t = timeline.text(date, y + 0.17, label, ha='center', va='bottom', fontsize=6.3, color=MUTED if row.lane == 'Recognition' else INK, linespacing=1.13, zorder=5, bbox=dict(facecolor='white', edgecolor='none', pad=0.35, alpha=0.92))
    event_bounds.append((row.id, row.lane, t))

def dates_background(ax):
    for left, right, col, name in PHASES:
        ax.axvspan(pd.Timestamp(left), pd.Timestamp(right), color=rgba(col, 0.014), zorder=0)
    ax.axvspan(START, pd.Timestamp('2020-01-01'), color='#F8FAFC', zorder=0)
    ax.axvline(pd.Timestamp('2020-01-01'), color='#CAD3DF', lw=0.5, ls=(0, (2, 3)))
    for date in BOUNDARIES:
        ax.axvline(pd.Timestamp(date), color='#A5B2C4', linewidth=0.65, linestyle=(0, (3, 3)), alpha=0.8)
    ax.set_xlim(START, END)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.spines['bottom'].set_color('#9CAABF')
    ax.tick_params(length=2.5, width=0.55, pad=3)
    ax.set_axisbelow(True)
    ax.grid(axis='y', color=GRID, lw=0.4, alpha=0.65)
b = fig.add_axes([0.165, 0.23, 0.795, 0.15])
c = fig.add_axes([0.165, 0.09, 0.795, 0.105])
for ax in [b, c]:
    dates_background(ax)
b.step(pd.to_datetime(cumulative.month), cumulative.cumulative_countries, where='post', color=DATA, linewidth=1.35)
c.bar(pd.to_datetime(monthly.month), monthly.new_countries, width=24, color=rgba(BAR_BLUE, 0.88), edgecolor='none')
b.set(ylim=(0, 165), yticks=[0, 50, 100, 150], ylabel='Cumulative countries / regions')
c.set(ylim=(0, 12), yticks=[0, 5, 10], ylabel='Monthly new', xlabel='Publication month')
b.tick_params(labelbottom=False)
b.text(pd.Timestamp('2019-01-01'), 80, 'Monthly series\nstarts in 2020', ha='center', va='center', fontsize=6.6, color=MUTED, linespacing=1.3)
for date, value in [('2021-06-01', 14), ('2024-04-01', 123), ('2025-12-01', 143)]:
    observed = int(cumulative.loc[cumulative.month.eq(date), 'cumulative_countries'].iloc[0])
    assert observed == value
    b.annotate(str(value), (pd.Timestamp(date), value), xytext=(-3 if value == 143 else 0, 5), textcoords='offset points', ha='right' if value == 143 else 'center', color=DATA, fontsize=7.4)
fig.canvas.draw()
renderer, outside, skip = (fig.canvas.get_renderer(), [], set())
for ax in fig.axes:
    for axis in [ax.xaxis, ax.yaxis]:
        lo, hi = sorted(axis.get_view_interval())
        for tick in axis.get_major_ticks():
            if not ax.axison or not lo - 1e-07 <= tick.get_loc() <= hi + 1e-07:
                skip.update([id(tick.label1), id(tick.label2)])
for text in fig.findobj(Text):
    if id(text) in skip or not text.get_visible() or (not text.get_text().strip()):
        continue
    box = text.get_window_extent(renderer)
    if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > fig.bbox.width + 0.5 or (box.y1 > fig.bbox.height + 0.5):
        outside.append(text.get_text())
assert not outside, outside
overlap = []
for i, (name, lane, text) in enumerate(event_bounds):
    one = text.get_window_extent(renderer)
    for name2, lane2, text2 in event_bounds[i + 1:]:
        if one.overlaps(text2.get_window_extent(renderer)):
            overlap.append([name, name2])
assert not overlap, overlap
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / ('Figure2_diffusion_clean_blue.' + ext))
png = P / 'figures/Figure2_diffusion_clean_blue_600dpi.png'
fig.savefig(png, dpi=600)
with Image.open(png) as source:
    source.convert('RGB').save(png, dpi=(600, 600))
    source.resize((1600, round(source.height * 1600 / source.width)), Image.Resampling.LANCZOS).save(P / 'figures/Figure2_diffusion_clean_blue_preview.png')
(P / 'validation/map_vector_layer.json').write_text(json.dumps({'clip': clip, 'polygons': polygons, 'markers': markers}, separators=(',', ':')) + '\n')
(P / 'validation/style_and_layout.json').write_text(json.dumps({'size_mm': [183, 224], 'original_abc_letters_preserved': True, 'milestones': len(events), 'milestone_resolution': 'month', 'common_time_axis': ['2018-01-01', '2025-12-31'], 'monthly_data_window_unchanged': ['2020-01-01', '2025-12-01'], 'pre2020_statistical_series': 'blank, never zero-filled', 'original_map_polygon_paths': len(polygons), 'original_map_point_markers': len(markers), 'phase_boundaries_unchanged': BOUNDARIES, 'event_label_overlaps': overlap, 'outside_canvas_text': outside, 'new_empirical_estimates': False, 'context_is_not_causal_attribution': True, 'b_curve_color': DATA, 'c_bar_color': BAR_BLUE, 'c_bar_alpha': 0.88, 'phase_background_alpha': 0.014, 'pre2020_background': '#F8FAFC', 'change_scope': 'b,c colour, contrast and grid only; a and timeline unchanged'}, indent=2) + '\n')
plt.close(fig)
print('Saved integrated ED2: original map and 72 monthly records; 9 verified contextual milestones.')
