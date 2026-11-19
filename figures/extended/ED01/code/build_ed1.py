from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Render saved network associations. No model fitting or bootstrap reruns."""
from pathlib import Path
import os, sys, json, hashlib
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch/mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, patches
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.font_manager import fontManager
from PIL import Image
for name in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + name)
INK, MUTED, GRID = ('#11151C', '#657183', '#E9EEF4')
GROUPS = ['L', 'M', 'H']
LABEL = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
COL = {'L': '#7A9DBF', 'M': '#4D8D7B', 'H': '#173873'}
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
    for ext in ['pdf', 'svg']:
        fig.savefig(P / 'figures' / f'{name}.{ext}')
    png = P / 'figures' / f'{name}_600dpi.png'
    fig.savefig(png, dpi=600)
    with Image.open(png) as im:
        im.convert('RGB').save(png, dpi=(600, 600))
        im.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(P / 'figures' / f'{name}_preview.png')
    plt.close(fig)
    return outside
from matplotlib.patches import FancyArrowPatch
NAVY, RED, RULE, CONNECTOR = ('#173873', '#D7505D', '#CBD5E2', '#8B97A9')
ed = read('ED1_original')
supp = read('supplementary_retrieval_original')
scope = read('corpus_scope_original')

def value(frame, field, key):
    rows = frame[frame[field].eq(key)]
    assert len(rows) == 1, (field, key)
    return int(rows.n.iloc[0])
v = {'corpus': value(ed, 'step', 'Corpus'), 'initial_candidates': value(ed, 'step', 'Initial candidates'), 'additional_leads': value(supp, 'node', 'Additional retrieval leads'), 'additional_eligible': value(supp, 'node', 'Additional eligible candidates'), 'AF_studies': value(ed, 'step', 'AF-use cohort'), 'main_eligible': value(scope, 'node', 'Main eligible corpus') if 'node' in scope else value(scope, 'stage', 'Main eligible corpus')}
assert v == {'corpus': 6046663, 'initial_candidates': 29127, 'additional_leads': 826, 'additional_eligible': 765, 'AF_studies': 16414, 'main_eligible': 2714594}
fig = plt.figure(figsize=(183 / 25.4, 150 / 25.4))
texts = []

def txt(x, y, s, size=8, color=INK, weight='normal', **kwargs):
    texts.append(s)
    return fig.text(x, y, s, fontsize=size, color=color, fontweight=weight, **kwargs)

def rule(x0, x1, y, color=RULE, lw=0.7):
    fig.add_artist(Line2D([x0, x1], [y, y], transform=fig.transFigure, color=color, lw=lw, zorder=1))

def segment(x0, y0, x1, y1, color=CONNECTOR, lw=0.75):
    fig.add_artist(Line2D([x0, x1], [y0, y1], transform=fig.transFigure, color=color, lw=lw, zorder=1))

def arrow(x0, y0, x1, y1):
    fig.add_artist(FancyArrowPatch((x0, y0), (x1, y1), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=6.5, linewidth=0.75, color=CONNECTOR, shrinkA=0, shrinkB=0, zorder=2))
txt(0.08, 0.946, 'OpenAlex life-science corpus', 9.6, weight='bold')
txt(0.08, 0.882, f"{v['corpus']:,}", 22, NAVY, weight='bold')
txt(0.08, 0.848, 'publication records', 8.2, MUTED)
txt(0.665, 0.91, '2015–2025 · 22 subfields', 8.0, NAVY)
txt(0.665, 0.875, 'Eligible analysis corpus · 2020–2025', 7.2, MUTED)
txt(0.665, 0.843, f"{v['main_eligible']:,} studies", 11, NAVY, weight='bold')
rule(0.08, 0.92, 0.825, color=NAVY, lw=0.8)
segment(0.5, 0.825, 0.5, 0.795)
segment(0.27, 0.795, 0.73, 0.795)
arrow(0.27, 0.795, 0.27, 0.754)
arrow(0.73, 0.795, 0.73, 0.754)
rule(0.08, 0.46, 0.754)
rule(0.54, 0.92, 0.754)
txt(0.08, 0.718, 'Initial retrieval', 9.0, weight='bold')
txt(0.08, 0.665, f"{v['initial_candidates']:,}", 18.5, NAVY, weight='bold')
txt(0.08, 0.638, 'candidate work records', 8.0, MUTED)
txt(0.08, 0.6, 'Keywords and citations:', 8.0)
txt(0.08, 0.576, 'AF2 / Multimer / AFDB / AF3', 8.0)
txt(0.54, 0.718, 'Supplementary retrieval', 9.0, weight='bold')
txt(0.54, 0.665, f"{v['additional_leads']:,}", 18.5, NAVY, weight='bold')
txt(0.54, 0.638, 'additional work-record leads', 8.0, MUTED)
txt(0.54, 0.6, f"{v['additional_eligible']:,} eligible candidate works", 8.0, weight='bold')
txt(0.54, 0.576, 'Expanded terms and AF1 citations', 8.0)
rule(0.08, 0.46, 0.547)
rule(0.54, 0.92, 0.547)
segment(0.27, 0.547, 0.27, 0.518)
segment(0.73, 0.547, 0.73, 0.518)
segment(0.27, 0.518, 0.73, 0.518)
arrow(0.5, 0.518, 0.5, 0.475)
rule(0.08, 0.92, 0.475)
segment(0.08, 0.475, 0.08, 0.249, color=NAVY, lw=1.25)
txt(0.105, 0.447, 'Evidence assessment', 9.0, NAVY, weight='bold')
txt(0.105, 0.414, 'Evidence of the study’s own AF use', 11.0, weight='bold')
txt(0.105, 0.366, 'Abstract and full-text evidence', 8.1)
txt(0.105, 0.339, 'Model-assisted review', 8.1)
txt(0.105, 0.312, 'Targeted human adjudication', 8.0)
segment(0.595, 0.395, 0.595, 0.265, color=RULE, lw=0.6)
txt(0.62, 0.373, 'Insufficient on their own', 7.8, weight='bold')
txt(0.62, 0.347, 'Citations, background or', 7.5, MUTED)
txt(0.62, 0.324, 'future plans', 7.5, MUTED)
txt(0.62, 0.292, 'Unresolved evidence', 7.8, weight='bold')
txt(0.62, 0.267, 'Recorded as unknown', 7.5, MUTED)
rule(0.08, 0.92, 0.249)
arrow(0.5, 0.249, 0.5, 0.208)
rule(0.08, 0.92, 0.208, color=NAVY, lw=0.8)
txt(0.08, 0.18, 'Confirmed AF-use studies', 9.0, weight='bold')
txt(0.08, 0.106, f"{v['AF_studies']:,}", 25, RED, weight='bold')
txt(0.33, 0.126, '2020–2025', 9.0, NAVY)
txt(0.33, 0.101, 'After study consolidation', 8.0, MUTED)
rule(0.08, 0.92, 0.072, color=NAVY, lw=0.8)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
items = [t for t in fig.texts if t.get_visible() and t.get_text().strip()]
overlaps = []
for i, a in enumerate(items):
    ba = a.get_window_extent(renderer)
    for b in items[i + 1:]:
        bb = b.get_window_extent(renderer)
        dx = min(ba.x1, bb.x1) - max(ba.x0, bb.x0)
        dy = min(ba.y1, bb.y1) - max(ba.y0, bb.y0)
        if dx > 0.5 and dy > 0.5:
            overlaps.append([a.get_text(), b.get_text()])
assert not overlaps, overlaps
export(fig, 'ED1_identification_concise')
(P / 'source_data/displayed_information.json').write_text(json.dumps({'counts': v, 'rendered_text': texts, 'corpus_years': '2015–2025', 'cohort_years': '2020–2025', 'eligible_primary_subfields': 22, 'retrieval_paths_are_parallel': True, 'no_counts_added_or_subtracted_across_records_and_studies': True}, indent=2, ensure_ascii=False) + '\n')
(P / 'validation/style_and_layout.json').write_text(json.dumps({'size_mm': [183, 150], 'font': release_font_family(), 'rounded_boxes': False, 'filled_boxes': False, 'gradients': False, 'shadows': False, 'outcome_accent': RED, 'structure_color': NAVY, 'all_original_counts_preserved': True, 'review_rule_details_in_caption': True, 'main_eligible_scope_location': 'source-context band, outside the screening outcome', 'A_B_and_routed_C_review': 'preserved in caption; abbreviated in figure', 'text_overlaps': overlaps}, indent=2) + '\n')
print('ED1 redesigned: all 6 counts, date ranges, retrieval routes and evidence rules retained.')
