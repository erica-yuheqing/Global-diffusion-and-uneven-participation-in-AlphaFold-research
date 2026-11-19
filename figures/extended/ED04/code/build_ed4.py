from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Recreate the supplied ED4 layout with explicit within-country tier wording.

Historical source-file numbering is ED3; this is current Extended Data Fig. 4.
No sample definitions or data values are changed.
"""
from pathlib import Path
import os, sys, json, hashlib
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'validation/mpl')
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from matplotlib.font_manager import fontManager
from matplotlib.text import Text
from PIL import Image
for name in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + name)
INK, SLATE, MUTED = ('#11151C', '#475B78', '#647187')
NAVY, BAR, RULE, ARROW = ('#173F82', '#7C99BF', '#CAD6E7', '#8998AE')
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'text.color': INK, 'axes.labelcolor': INK, 'axes.linewidth': 0.6, 'xtick.color': MUTED, 'ytick.color': INK, 'xtick.labelsize': 7.2, 'ytick.labelsize': 7.2, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'figure.facecolor': 'white', 'savefig.facecolor': 'white'})
flow = pd.read_csv(P / 'source_data/ED3_a.csv')
annual = pd.read_csv(P / 'source_data/ED3_b.csv')
assert flow.institutions.tolist() == [52098, 50371, 50271, 48010]
assert annual.new_institutions.tolist() == [16, 562, 1636, 1551, 1231, 1373]
assert all((flow.institutions.iloc[i] - flow.excluded_to_next.iloc[i] == flow.institutions.iloc[i + 1] for i in range(3)))
assert annual.new_institutions.cumsum().tolist() == annual.cumulative_institutions.tolist()
fig = plt.figure(figsize=(183 / 25.4, 126.05 / 25.4))
fig.text(0.035, 0.942, 'a', fontsize=11, fontweight='bold', va='center')
fig.text(0.585, 0.942, 'b', fontsize=11, fontweight='bold', va='center')
labels = ['Baseline institutions', 'Unique baseline country', 'Valid within-country output tertiles', 'Main sample · 68 countries']
ys = [0.872, 0.6515, 0.431, 0.214]
for i, (n, label, y) in enumerate(zip(flow.institutions, labels, ys)):
    fig.text(0.09, y, f'{n:,}', fontsize=20.5 if i == 3 else 16.5, fontweight='bold', color=NAVY if i == 3 else SLATE, ha='left', va='center')
    fig.text(0.09, y - 0.055, label, fontsize=8.0, ha='left', va='center')
    line_y = y - 0.094
    fig.add_artist(Line2D([0.09, 0.336], [line_y, line_y], transform=fig.transFigure, lw=0.9 if i < 3 else 1.2, color=RULE if i < 3 else NAVY))
    if i < 3:
        end_y = line_y - 0.077
        mid_y = line_y - 0.043
        fig.add_artist(FancyArrowPatch((0.115, line_y), (0.115, end_y), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=7, linewidth=1.0, color=ARROW, shrinkA=0, shrinkB=0))
        fig.add_artist(FancyArrowPatch((0.115, mid_y), (0.355, mid_y), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=7, linewidth=1.0, color=ARROW, shrinkA=0, shrinkB=0))
        fig.text(0.375, mid_y + 0.013, f'{int(flow.excluded_to_next.iloc[i]):,}', fontsize=9.5, fontweight='bold', color=MUTED, va='center')
        reasons = ['Unknown / multiple\nbaseline countries', 'Collapsed / empty tertiles\n42 countries', 'Group below 20\n111 countries']
        fig.text(0.375, mid_y - 0.013, reasons[i], fontsize=7.2, color=MUTED, va='top', linespacing=1.35)
ax = fig.add_axes([0.665, 0.17, 0.305, 0.68])
ax.set_axisbelow(True)
bars = ax.bar(annual.year, annual.new_institutions, width=0.6, color=[NAVY if year == 2022 else BAR for year in annual.year], linewidth=0)
for bar, year, n in zip(bars, annual.year, annual.new_institutions):
    ax.text(bar.get_x() + bar.get_width() / 2, n + 29, f'{n:,}', ha='center', va='bottom', fontsize=7.2, color=NAVY if year == 2022 else '#30435F', fontweight='bold' if year == 2022 else 'normal')
ax.set_ylim(0, 1800)
ax.set_xlim(2019.4, 2025.6)
ax.set_xticks(annual.year)
ax.set_yticks([0, 500, 1000, 1500])
ax.yaxis.grid(True, color='#E6EDF4', lw=0.6)
ax.tick_params(axis='y', length=0, pad=7)
ax.tick_params(axis='x', length=3, width=0.6, pad=5)
for side in ['top', 'left', 'right']:
    ax.spines[side].set_visible(False)
ax.spines['bottom'].set_color('#8EA1BF')
ax.set_ylabel('Date-resolved institutions', fontsize=8.0, labelpad=9)
ax.set_xlabel('First observed publication year', fontsize=8.0, labelpad=10)
fig.canvas.draw()
r = fig.canvas.get_renderer()
outside = []
for t in fig.findobj(Text):
    if not t.get_visible() or not t.get_text().strip():
        continue
    b = t.get_window_extent(r)
    if b.x0 < 0 or b.y0 < 0 or b.x1 > fig.bbox.width or (b.y1 > fig.bbox.height):
        outside.append(t.get_text())
assert not outside, outside
name = 'Extended_Data_Fig4_optimized'
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'{name}.{ext}')
png = P / 'figures' / f'{name}_600dpi.png'
fig.savefig(png, dpi=600)
with Image.open(png) as im:
    im.convert('RGB').save(png, dpi=(600, 600))
    im.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(P / 'figures' / f'{name}_preview.png')
plt.close(fig)
original_dir = Path('/historical-workspace/Desktop/Results_methods_response_20261102/data/F2/source_data')
checks = {}
for f in sorted((P / 'source_data').glob('*.csv')):
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    original = original_dir / f.name
    checks[f.name] = {'sha256': digest, 'identical_to_original': digest == json.loads((P / 'provenance/source_hashes.json').read_text())[f.name]}
    assert checks[f.name]['identical_to_original']
(P / 'validation/checks.json').write_text(json.dumps({'source_files': checks, 'flow_counts': flow.institutions.tolist(), 'annual_counts': annual.new_institutions.tolist(), 'flow_reconciles': True, 'text_outside_canvas': outside, 'original_figure': 'Extended Data Figures_1103.docx, current ED4', 'historical_source_number': 'ED3', 'display_label_change': {'from': 'Valid domestic tertiles', 'to': 'Valid within-country output tertiles'}, 'country_exclusion_annotations': {'collapsed_or_empty_tertiles': 42, 'any_tertile_below_20': 111}, 'annotation_source': 'Supplied DOCX embedded ED4 image', 'matplotlib_version': matplotlib.__version__}, indent=2))
print('ED4 exported; all source data unchanged and flow counts reconciled.')
