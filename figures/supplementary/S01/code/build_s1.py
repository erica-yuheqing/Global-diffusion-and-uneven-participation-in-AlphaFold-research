from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
BLUE, INK, MUTED, LINE = ('#173873', '#11151C', '#53647D', '#CBD5E2')

def read(file):
    with (P / 'source_data' / file).open() as f:
        return {r['node']: int(r['n']) for r in csv.DictReader(f)}
A, B, C = (read('S1' + p + '.csv') for p in 'abc')
assert A['Eligible foundations'] - A['Original approved links'] == 2
assert A['Original approved links'] - A['Revision approved links'] == 15
assert B['Additional retrieval leads'] - B['Additional eligible candidates'] == 61
assert B['Earlier decisive supplementary reviews'] + B['Remaining supplementary review'] == 765
assert B['Remaining supplementary review'] - B['A/B submitted'] == 30
assert sum((C[k] for k in ['Supplementary accepted use', 'Supplementary non-use', 'Supplementary platform', 'Supplementary uncertain'])) == 765
assert C['Supplementary accepted use'] - 1 == C['Initial added net AF'] + C['Latest added net AF']
assert C['Old main AF'] + C['Initial added net AF'] + C['Latest added net AF'] == C['Final main AF']
fig = plt.figure(figsize=(7.2, 6.7), facecolor='white')
ax = fig.add_axes([0, 0, 1, 1])
ax.set(xlim=(0, 1), ylim=(0, 1))
ax.axis('off')

def t(x, y, s, fs=8, weight='normal', color=INK, ha='left', va='center'):
    return ax.text(x, y, s, fontsize=fs, fontweight=weight, color=color, ha=ha, va=va)

def rule(x1, x2, y):
    ax.plot([x1, x2], [y, y], color=LINE, lw=0.65)

def arrow(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>', mutation_scale=7, lw=0.75, color=MUTED))

def box(x, y, w, h, label, n, unit, final=False):
    ax.add_patch(Rectangle((x, y), w, h, facecolor='#F5F8FC' if final else 'white', edgecolor=BLUE if final else LINE, lw=0.9 if final else 0.65))
    t(x + w / 2, y + h * 0.8, label, 7.5, 'bold', ha='center')
    t(x + w / 2, y + h * 0.49, f'{n:,}', 14, 'bold', BLUE, ha='center')
    t(x + w / 2, y + h * 0.19, unit, 7, color=MUTED, ha='center')
t(0.025, 0.972, 'a', 11, 'bold')
labels = [('Raw corpus', A['Raw corpus'], '2015–2025 records'), ('Eligible records', A['Eligible foundations'], 'Articles, reviews, preprints'), ('Original linkage', A['Original approved links'], 'Study units'), ('Revised linkage', A['Revision approved links'], 'Study units'), ('Analysis corpus', A['Main eligible corpus'], '2020–2025 studies')]
xs = [0.045, 0.238, 0.431, 0.624, 0.817]
w = 0.174
for i, (label, n, u) in enumerate(labels):
    box(xs[i], 0.785, w, 0.145, label, n, u, i == 4)
    if i < 4:
        arrow(xs[i] + w, 0.856, xs[i + 1] - 0.003, 0.856)
t(0.525, 0.755, '2 original + 15 additional duplicate records removed', 7, color=MUTED, ha='center')
rule(0.045, 0.99, 0.717)
t(0.025, 0.682, 'b', 11, 'bold')
t(0.555, 0.682, 'c', 11, 'bold')
box(0.07, 0.528, 0.425, 0.112, 'Additional leads', B['Additional retrieval leads'], 'Work records')
arrow(0.2825, 0.528, 0.2825, 0.487)
t(0.309, 0.505, '61 outside eligible types', 7, color=MUTED)
box(0.07, 0.371, 0.425, 0.112, 'Eligible for review', B['Additional eligible candidates'], 'Work records')
arrow(0.2825, 0.371, 0.2825, 0.348)
ax.plot([0.17, 0.39], [0.348, 0.348], color=MUTED, lw=0.75)
arrow(0.17, 0.348, 0.17, 0.322)
arrow(0.39, 0.348, 0.39, 0.322)
box(0.07, 0.217, 0.2, 0.101, 'Earlier reviews', B['Earlier decisive supplementary reviews'], 'Decisions available')
box(0.295, 0.217, 0.2, 0.101, 'Remaining', B['Remaining supplementary review'], '28 insufficient; 2 too long')
arrow(0.395, 0.217, 0.395, 0.189)
box(0.295, 0.079, 0.2, 0.106, 'A/B submissions', B['A/B submitted'], 'Per model')
t(0.07, 0.149, '154 full-text packets', 7.5, color=MUTED)
t(0.07, 0.12, '402 abstract packets', 7.5, color=MUTED)
t(0.07, 0.091, '516 routed C reviews', 7.5, color=MUTED)
t(0.595, 0.619, 'Disposition', 7.5, 'bold', MUTED)
t(0.958, 0.619, 'Works', 7.5, 'bold', MUTED, ha='right')
rule(0.59, 0.965, 0.596)
for y, label, key in [(0.566, 'AF use accepted', 'Supplementary accepted use'), (0.519, 'Non-use accepted', 'Supplementary non-use'), (0.472, 'Platform paper excluded', 'Supplementary platform'), (0.425, 'Unresolved', 'Supplementary uncertain')]:
    t(0.595, y, label, 8)
    t(0.958, y, f'{C[key]:,}', 10, 'bold', BLUE, ha='right')
rule(0.59, 0.965, 0.397)
t(0.78, 0.365, '74 positive works → 73 additional studies', 8, 'bold', BLUE, ha='center')
t(0.78, 0.335, 'One duplicate removed through version linkage', 7, color=MUTED, ha='center')
t(0.78, 0.267, '16,341 + 70 + 3', 13, 'bold', BLUE, ha='center')
arrow(0.78, 0.243, 0.78, 0.211)
box(0.59, 0.079, 0.375, 0.128, 'Final AF sample', C['Final main AF'], '2020–2025 studies', True)
fig.savefig(P / 'figures/Supplementary_Fig_S1.pdf')
fig.savefig(P / 'figures/Supplementary_Fig_S1.svg')
fig.savefig(P / 'figures/Supplementary_Fig_S1_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S1_preview.png', dpi=160)
(P / 'validation.json').write_text(json.dumps({'source_counts_unchanged': True, 'count_reconciliations': 'passed', 'png_dpi': 600, 'pdf': 'vector with embedded TrueType fonts'}, indent=2))
print(P / 'figures/Supplementary_Fig_S1_preview.png')
