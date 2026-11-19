from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, csv, json, html, hashlib, zipfile
P = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(P / 'scratch')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import fontManager
for n in ['Arial.ttf', 'Arial Bold.ttf']:
    release_addfont('/System/Library/Fonts/Supplemental/' + n)
BLUE, RED, GRAY, INK, MUTED, GRID = ('#173873', '#E62216', '#B9C2CE', '#11151C', '#53647D', '#E8EDF3')
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'axes.edgecolor': '#9BAABE', 'axes.linewidth': 0.6, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': INK})

def read(n):
    with (P / 'source_data' / n).open() as f:
        return list(csv.DictReader(f))
A, B, D = (read('S3a.csv'), read('S3b.csv'), read('S4b.csv'))
years = [int(r['publication_year']) for r in A]
counts = [int(r['confirmed_af']) for r in A]
groups = sorted([r['display_group'] for r in B if r['display_group'] != 'Other'], key=lambda g: -next((int(r['AF']) for r in B if r['display_group'] == g))) + ['Other']
lookup = {r['display_group']: r for r in B}
af = np.array([float(lookup[g]['AF_share']) * 100 for g in groups])
eligible = np.array([float(lookup[g]['eligible_share']) * 100 for g in groups])
rates = np.array([[next((float(r['AF_rate']) * 100 for r in D if r['display_group'] == g and int(r['year']) == y)) for y in years] for g in groups])
assert sum(counts) == sum((int(r['AF']) for r in B)) == 16414
assert sum((int(r['eligible']) for r in B)) == 2714594
assert abs(af.sum() - 100) < 1e-08 and abs(eligible.sum() - 100) < 1e-08
for y, n in zip(years, counts):
    assert sum((int(r['AF']) for r in D if int(r['year']) == y)) == n
for g in groups:
    assert sum((int(r['AF']) for r in D if r['display_group'] == g)) == int(lookup[g]['AF'])
    assert sum((int(r['eligible']) for r in D if r['display_group'] == g)) == int(lookup[g]['eligible'])
fig = plt.figure(figsize=(7.2, 5.9), facecolor='white')
a = fig.add_axes([0.09, 0.62, 0.32, 0.32])
b = fig.add_axes([0.66, 0.62, 0.31, 0.32])
c = fig.add_axes([0.21, 0.18, 0.74, 0.295])
for ax in [a, b]:
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)
a.bar(years, counts, width=0.65, color=BLUE, zorder=3)
a.set_ylim(0, 6500)
a.set_xticks(years, [str(y) for y in years])
a.set_yticks([0, 2000, 4000, 6000], ['0', '2,000', '4,000', '6,000'])
a.set_ylabel('Confirmed AF studies')
a.set_xlabel('Publication year')
a.grid(axis='y', color=GRID, lw=0.6)
for y, n in zip(years, counts):
    a.text(y, n + 140, f'{n:,}', ha='center', va='bottom', fontsize=7.5, color=BLUE)
yy = np.arange(len(groups))
b.barh(yy - 0.16, af, height=0.28, color=RED, label='AF')
b.barh(yy + 0.16, eligible, height=0.28, color=GRAY, label='Eligible corpus')
b.set_yticks(yy, groups)
b.invert_yaxis()
b.set_xlim(0, 78)
b.set_xticks([0, 20, 40, 60])
b.set_xlabel('Share of studies (%)')
b.grid(axis='x', color=GRID, lw=0.6)
for i, (x1, x2) in enumerate(zip(af, eligible)):
    b.text(x1 + 1, i - 0.16, f'{x1:.1f}', va='center', fontsize=7, color=RED)
    b.text(x2 + 1, i + 0.16, f'{x2:.1f}', va='center', fontsize=7, color=MUTED)
b.tick_params(axis='y', length=0, pad=7)
b.legend(loc='upper center', bbox_to_anchor=(0.47, -0.25), ncol=2, frameon=False, fontsize=7.3, handlelength=1.1, columnspacing=1.2)
cmap = LinearSegmentedColormap.from_list('existing_blue', ['#F3F6FA', '#B8CBE3', BLUE])
im = c.imshow(rates, cmap=cmap, vmin=0, vmax=2, aspect='auto', interpolation='nearest')
c.set_xticks(range(6), years)
c.set_yticks(range(6), groups)
c.tick_params(length=0, pad=7)
c.set_xlabel('Publication year', labelpad=8)
c.set_xticks(np.arange(-0.5, 6, 1), minor=True)
c.set_yticks(np.arange(-0.5, 6, 1), minor=True)
c.grid(which='minor', color='white', lw=1.2)
c.tick_params(which='minor', length=0)
for sp in c.spines.values():
    sp.set_visible(False)
for i in range(6):
    for j in range(6):
        v = rates[i, j]
        label = '0' if v == 0 else '<0.01' if v < 0.01 else f'{v:.2f}'
        c.text(j, i, label, ha='center', va='center', fontsize=8, color='white' if v >= 1.3 else INK)
cbax = fig.add_axes([0.395, 0.06, 0.37, 0.013])
cb = fig.colorbar(im, cax=cbax, orientation='horizontal', ticks=[0, 0.5, 1, 1.5, 2])
cb.outline.set_visible(False)
cb.ax.tick_params(length=2, labelsize=7)
cb.set_label('AF studies within each subfield (%)', fontsize=8, labelpad=5)
for x, y, s in [(0.025, 0.955, 'a'), (0.475, 0.955, 'b'), (0.025, 0.495, 'c')]:
    fig.text(x, y, s, fontsize=11, fontweight='bold')
fig.canvas.draw()
for ext in ['pdf', 'svg']:
    fig.savefig(P / 'figures' / f'Supplementary_Fig_S3.{ext}')
fig.savefig(P / 'figures/Supplementary_Fig_S3_600dpi.png', dpi=600)
fig.savefig(P / 'figures/Supplementary_Fig_S3_preview.png', dpi=180)
caption = 'Supplementary Fig. S3 | Growth and subfield distribution of AF research. a, Annual confirmed AF-study counts. b, Subfield shares of AF studies (n = 16,414) and the eligible corpus (n = 2,714,594), pooled over 2020–2025. c, AF studies as a percentage of eligible studies within each subfield and year. The five largest AF subfields by total study count are fixed across panels; Other pools the remaining subfields. The eligible corpus includes AF studies. The 2020 AF sample contains 11 studies.'
(P / 'caption.txt').write_text(caption + '\n')
(P / 'validation.json').write_text(json.dumps({'AF_total': sum(counts), 'eligible_total': sum((int(r['eligible']) for r in B)), 'annual_and_subfield_counts_reconciled': True, 'source_data_unchanged': True, 'yearly_subfield_composition': 'S4a retained numerically; not plotted', 'png_dpi': 600}, indent=2))
(P / 'provenance.json').write_text(json.dumps([{'file': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'source': '/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F1/source_data/' + f.name} for f in sorted((P / 'source_data').glob('*.csv'))], indent=2))
(P / 'README.txt').write_text('Merged S3 and S4\n\nOld S3a -> a; old S3b -> b; old S4b -> c. Old S4a retained unchanged as numerical data. All source counts and denominators unchanged. Heatmap values are percentages; positive values below 0.01% are labelled <0.01. No uncertainty intervals are implied.\n\nRebuild: python code/build_s3.py (numpy and matplotlib required).\n')
(P / 'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Supplementary Fig S3</title><style>body{font:16px Arial;max-width:1100px;margin:35px auto;line-height:1.6;padding:0 24px;color:#18212d}img{width:100%}a{color:#173873}</style><img src="figures/Supplementary_Fig_S3_preview.png"><p>' + html.escape(caption) + '</p><p><a href="figures/Supplementary_Fig_S3.pdf">Vector PDF</a> · <a href="figures/Supplementary_Fig_S3_600dpi.png">600 dpi PNG</a> · <a href="caption.txt">Caption</a></p>')
print(P / 'Review.html')
