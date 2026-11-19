from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import csv, json, os, hashlib, html, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle, FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import fontManager
for f in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + f)
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
BLUE, INK, MUTED, LINE = ('#173873', '#11151C', '#53647D', '#CBD5E2')

def read(name):
    with (P / 'source_data' / name).open() as f:
        return list(csv.DictReader(f))
a, b, c = [read('S2' + s + '.csv') for s in 'abc']
total = sum((int(r['n']) for r in a))
resolved = sum((int(r['n']) for r in a if r['reference_status'] == 'resolved'))
unresolved = total - resolved
mat = np.array([[next((int(r['n']) for r in b if r['reference'] == ref and r['prediction'] == pred)) for pred in ['yes', 'no', 'uncertain/missing']] for ref in ['yes', 'no']])
assert total == 150 and resolved == 122 and (unresolved == 28)
assert mat.sum() == resolved and mat.tolist() == [[103, 0, 0], [2, 15, 2]]
assert sum((int(r['n']) for r in a if r['reference_route'] == 'ab_exact_agreement')) == 41
assert sum((int(r['n']) for r in a if r['reference_route'] == 'human_adjudication')) == 109
fig = plt.figure(figsize=(7.2, 3.65), facecolor='white')
canvas = fig.add_axes([0, 0, 1, 1])
canvas.set(xlim=(0, 1), ylim=(0, 1))
canvas.axis('off')

def text(x, y, s, fs=8, weight='normal', color=INK, ha='center'):
    return canvas.text(x, y, s, ha=ha, va='center', fontsize=fs, fontweight=weight, color=color)

def arrow(x1, y1, x2, y2):
    canvas.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>', mutation_scale=8, lw=0.8, color=MUTED))

def box(x, y, w, h, n, label, highlight=False):
    canvas.add_patch(Rectangle((x, y), w, h, facecolor='#F5F8FC' if highlight else 'white', edgecolor=BLUE if highlight else LINE, lw=0.8))
    text(x + w / 2, y + h * 0.63, f'{n:,}', 20, 'bold', BLUE)
    text(x + w / 2, y + h * 0.24, label, 8.3)
text(0.025, 0.94, 'a', 11, 'bold', ha='left')
text(0.505, 0.94, 'b', 11, 'bold', ha='left')
box(0.15, 0.64, 0.22, 0.2, total, 'Candidate works')
arrow(0.26, 0.64, 0.26, 0.564)
canvas.plot([0.14, 0.38], [0.56, 0.56], color=MUTED, lw=0.8)
arrow(0.14, 0.56, 0.14, 0.49)
arrow(0.38, 0.56, 0.38, 0.49)
box(0.04, 0.28, 0.2, 0.2, resolved, 'Resolved', True)
box(0.28, 0.28, 0.2, 0.2, unresolved, 'Unresolved')
text(0.14, 0.212, 'Used in panel b', 7.5, color=MUTED)
text(0.38, 0.205, '24 insufficient evidence\n4 uncertain judgements', 7.3, color=MUTED)
ax = fig.add_axes([0.645, 0.285, 0.325, 0.485])
cmap = LinearSegmentedColormap.from_list('existing_blue', ['#F2F5F9', BLUE])
ax.imshow(mat, cmap=cmap, vmin=0, vmax=103, aspect='auto', interpolation='nearest')
for i in range(2):
    for j in range(3):
        ax.text(j, i, str(mat[i, j]), ha='center', va='center', fontsize=11, color='white' if mat[i, j] > 50 else INK)
ax.set_xticks(range(3), ['AF use', 'Non-use', 'Unknown'])
ax.set_yticks(range(2), ['AF use', 'Non-use'])
ax.set_xlabel('Production label', labelpad=10)
ax.set_ylabel('Human label', labelpad=8)
ax.tick_params(length=0, pad=7, labelsize=8)
ax.set_xticks(np.arange(-0.5, 3, 1), minor=True)
ax.set_yticks(np.arange(-0.5, 2, 1), minor=True)
ax.grid(which='minor', color='white', linewidth=1.5)
ax.tick_params(which='minor', length=0)
for spine in ax.spines.values():
    spine.set_visible(False)
text(0.8075, 0.825, '122 resolved works', 7.5, color=MUTED)
fig.canvas.draw()
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S2.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S2_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S2_preview.png', dpi=180)
caption = 'Supplementary Fig. S2 | Pilot annotation and production-label agreement. a, Human review of 150 deliberately selected candidate works yielded 122 resolved labels and 28 unresolved cases. The human reference combined 41 exact agreements and 109 adjudications across two annotation workbooks. b, Production labels compared with resolved human labels; cells show work counts. Precision was 98.10% (103/105) and recall 100% (103/103). Unknown predictions remain separate from non-use. This selected pilot was not an independent held-out validation and does not assess retrieval completeness.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'total': total, 'resolved': resolved, 'unresolved': unresolved, 'matrix': mat.tolist(), 'precision': 103 / 105, 'recall': 1.0, 'counts_reconciled': True, 'source_data_unchanged': True, 'png_dpi': 600}, indent=2))
(P / 'provenance.json').write_text(json.dumps([{'file': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'source': '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F1/source_data/' + f.name} for f in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'README.txt').write_text('S2 revision\n\nPanel c removed; human unresolved counts incorporated in a. All original source CSVs retained unchanged. Panel b contains the complete 2x3 matrix, including unknown production labels. Annotation-route counts and pilot interpretation are in the caption.\n\nRebuild with Python, numpy and matplotlib: python code/build_s2.py\n')
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig S2</title><style>body{font:16px Arial;max-width:1100px;margin:35px auto;line-height:1.6;padding:0 24px;color:#18212d}img{width:100%}a{color:#173873}</style><img src="figures/Supplementary_Fig_S2_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S2.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S2_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
print(P / 'Review.html')
