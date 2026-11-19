from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import argparse, csv, json, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.colors import to_rgba
from matplotlib import font_manager
from PIL import Image
P = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Regenerate Figure 3 from the supplied analysis estimates.')
parser.add_argument('--output-dir', type=Path, default=P / 'figures')
args = parser.parse_args()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
for name in ['Arial.ttf', 'Arial Bold.ttf']:
    font = Path('/System/Library/Fonts/Supplemental') / name
    if font.exists():
        release_addfont(str(font))
AF = '#D5281D'
REF = '#131460'
INK = '#18212B'
MUTED = '#58697C'
GRID = '#E5EBF1'
BAND = '#F7F4FA'
GP = {'higher': '#4A2368', 'middle': '#9470AE', 'lower': '#C4AFD6', 'outside': '#A4ADBB'}
COUNTRY_LABELS = {'higher': 'High', 'middle': 'Middle', 'lower': 'Low', 'outside': 'Outside'}
DEEP = GP['higher']
GROUPS = ['higher', 'middle', 'lower']
ROLES = ['first', 'last']
BENCHMARKS = ['country', 'author']
CORPORA = [('AF', AF, 'o'), ('reference', REF, 's')]
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 7, 'axes.labelsize': 7.5, 'axes.labelcolor': INK, 'xtick.labelsize': 6.7, 'ytick.labelsize': 6.7, 'text.color': INK, 'xtick.color': MUTED, 'ytick.color': MUTED, 'axes.edgecolor': MUTED, 'axes.linewidth': 0.55, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'savefig.facecolor': 'white', 'axes.unicode_minus': True})
available_fonts = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams['font.family'] = next((f for f in [release_font_family(), 'Liberation Sans', 'DejaVu Sans'] if f in available_fonts))
names = ['strict_main_R.csv', 'strict_main_delta.csv', 'strict_main_benchmark_change.csv']

def read(name):
    with (P / 'source_data' / name).open() as f:
        return list(csv.DictReader(f))

def selected(name):
    return [r for r in read(name) if r['level'] == 'group' and r['setting'] == 'standardized']

def write_csv(name, rows):
    target = OUT / 'source_data'
    target.mkdir(exist_ok=True)
    fields = list(dict.fromkeys((k for r in rows for k in r)))
    with (target / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
RR = {(r['entity_id'], r['role'], r['benchmark'], r['corpus']): r for r in selected(names[0])}
DD = {(r['entity_id'], r['role'], r['benchmark']): r for r in selected(names[1])}
CC = {(r['entity_id'], r['role']): r for r in selected(names[2])}

def axes(fig, bounds):
    ax = fig.add_axes(bounds)
    for side in ['top', 'right']:
        ax.spines[side].set_visible(False)
    ax.tick_params(length=2.5, width=0.55, pad=3)
    return ax

def letter(fig, label, x, y):
    fig.text(x, y, label, fontsize=10, weight='bold', va='top')

def corpus_legend(fig, xy=(0.98, 0.99), loc='upper right'):
    fig.legend(handles=[Rectangle((0, 0), 1, 1, facecolor=to_rgba(c, 0.3), edgecolor=to_rgba(c, 0.75), lw=0.5, label='AF' if cp == 'AF' else 'non-AF') for cp, c, m in CORPORA], loc=loc, bbox_to_anchor=xy, frameon=False, ncol=2, handlelength=1.3, handletextpad=0.5, columnspacing=1.5, fontsize=7)

def save(fig, name, records):
    fig.canvas.draw()
    from matplotlib.text import Text
    renderer = fig.canvas.get_renderer()
    for obj in fig.findobj(match=Text):
        if not obj.get_visible() or not obj.get_text().strip():
            continue
        if obj in [lab for ax in fig.axes for lab in ax.get_xticklabels() + ax.get_yticklabels()]:
            continue
        bbox = obj.get_window_extent(renderer)
        assert bbox.x0 >= -1 and bbox.y0 >= -1 and (bbox.x1 <= fig.bbox.width + 1) and (bbox.y1 <= fig.bbox.height + 1), obj.get_text()
    out = OUT / name
    fig.savefig(out.with_suffix('.pdf'), metadata={'Title': name.replace('_', ' ')})
    fig.savefig(out.with_suffix('.svg'))
    fig.savefig(str(out) + '_600dpi.png', dpi=600)
    with Image.open(str(out) + '_600dpi.png') as im:
        im.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(str(out) + '_preview.png')
    plt.close(fig)
    (OUT / (name + '_values.json')).write_text(json.dumps(records, indent=2) + '\n')
    return {'output_directory': str(OUT), 'plotted_records': len(records)}

def main_figure():
    fig = plt.figure(figsize=(183 / 25.4, 174 / 25.4))
    data = []
    lefts = [0.165, 0.445, 0.725]
    width = 0.225
    fig.add_artist(Rectangle((lefts[2] - 0.012, 0.112), width + 0.024, 0.805, transform=fig.transFigure, facecolor=BAND, edgecolor='none', zorder=-10))
    for x in [0.417, 0.697]:
        for lower, upper in [(0.6, 0.917), (0.112, 0.467)]:
            fig.add_artist(Line2D([x, x], [lower, upper], transform=fig.transFigure, color=GRID, lw=0.65, zorder=-9))
    corpus_legend(fig, (0.555, 0.538), loc='center')
    letter(fig, 'a', 0.028, 0.975)
    for j, g in enumerate(GROUPS):
        cx = lefts[j] + width / 2
        fig.text(cx, 0.943, COUNTRY_LABELS[g], ha='center', va='top', fontsize=8, weight='bold' if g == 'lower' else 'normal')
        fig.add_artist(Line2D([cx - 0.03, cx + 0.03], [0.921, 0.921], transform=fig.transFigure, color=GP[g], lw=2.8))
        ax = axes(fig, [lefts[j], 0.619, width, 0.273])
        ax.set_facecolor('none')
        ax.spines['left'].set_visible(False)
        ax.axvline(1, color=MUTED, lw=0.65, ls=(0, (3, 3)), zorder=4)
        ax.axhline(1.875, color=GRID, lw=0.65, zorder=0)
        for bm, ys in [('country', [3.55, 2.65]), ('author', [1.1, 0.2])]:
            for role, y in zip(ROLES, ys):
                for cp, col, mark in CORPORA:
                    r = RR['group:' + g, role, bm, cp]
                    v, lo, hi = [float(r[k]) for k in ['R', 'ci_low', 'ci_high']]
                    dy = 0.16 if cp == 'AF' else -0.16
                    ax.barh(y + dy, v, left=0, height=0.245, facecolor=to_rgba(col, 0.3), edgecolor=to_rgba(col, 0.75), linewidth=0.5, zorder=1)
                    ax.errorbar(v, y + dy, xerr=[[v - lo], [hi - v]], fmt='none', ecolor=col, capsize=1.8, elinewidth=0.9, capthick=0.7, zorder=5)
                    data.append(dict(panel='a', group=g, role=role, benchmark=bm, corpus=cp, RR=v, ci_low=lo, ci_high=hi))
        ax.set(xlim=(0, 1.2), ylim=(-0.45, 4.2), xticks=[0, 0.5, 1], yticks=[3.55, 2.65, 1.1, 0.2], yticklabels=['First', 'Last', 'First', 'Last'])
        ax.tick_params(axis='y', length=0, pad=7, labelleft=j == 0)
        if j == 0:
            for y, txt in [(3.1, 'Country\noutput'), (0.65, 'Team-author\ncredit')]:
                ax.text(-0.49, y, txt, transform=ax.get_yaxis_transform(), ha='center', va='center', fontsize=6.9, color=MUTED)
    fig.text(0.555, 0.567, 'Representation ratio (RR; 1 = proportional)', ha='center', fontsize=7.5)
    fig.add_artist(Line2D([0.145, 0.96], [0.51, 0.51], transform=fig.transFigure, color=GRID, lw=0.7))
    letter(fig, 'b', 0.028, 0.491)
    fig.legend(handles=[Line2D([0], [0], marker='o', ls='-', color=DEEP, ms=4, lw=1.3, label='First authorship'), Line2D([0], [0], marker='^', ls=(0, (4, 2)), color=DEEP, mfc='white', ms=4.3, lw=1.3, label='Last authorship')], loc='lower center', bbox_to_anchor=(0.555, 0.012), ncol=2, frameon=False, fontsize=7, handlelength=2.3, handletextpad=0.6, columnspacing=2)
    for j, g in enumerate(GROUPS):
        ax = axes(fig, [lefts[j], 0.158, width, 0.298])
        ax.set_facecolor('none')
        ax.axhline(0, color=MUTED, lw=0.65, ls=(0, (3, 3)), zorder=0)
        for role, mark, offset, style in [('first', 'o', -0.055, '-'), ('last', '^', 0.055, (0, (4, 2)))]:
            xs = [offset, 1 + offset]
            vals = [float(DD['group:' + g, role, bm]['delta']) for bm in BENCHMARKS]
            ax.plot(xs, vals, color=GP[g], lw=1.8 if g == 'lower' else 1.4, ls=style, zorder=2)
            for x, bm, v in zip(xs, BENCHMARKS, vals):
                r = DD['group:' + g, role, bm]
                lo, hi = [float(r[k]) for k in ['ci_low', 'ci_high']]
                ax.errorbar(x, v, yerr=[[v - lo], [hi - v]], fmt=mark, mfc=GP[g] if role == 'first' else 'white', mec=DEEP, mew=0.8, ms=4.4, ecolor=DEEP, elinewidth=0.8, capsize=1.7, capthick=0.7, zorder=3)
                above = role == 'last' if g == 'lower' else role == 'first'
                label_y = hi + 0.019 if above else lo - 0.02
                ax.text(x, label_y, f'{v:+.3f}'.replace('-', '−'), ha='center', va='bottom' if above else 'top', fontsize=6.5, weight='bold' if g == 'lower' else 'normal')
                data.append(dict(panel='b', group=g, role=role, benchmark=bm, delta_RR=v, ci_low=lo, ci_high=hi))
        ax.set(xlim=(-0.32, 1.32), ylim=(-0.43, 0.16), yticks=[-0.4, -0.2, 0], xticks=[0, 1], xticklabels=['Country\noutput', 'Team-author\ncredit'])
        ax.tick_params(axis='x', length=0, pad=6, colors=INK, labelsize=6.6)
        if j > 0:
            ax.spines['left'].set_visible(False)
            ax.tick_params(axis='y', left=False, labelleft=False)
        else:
            ax.set_ylabel('AF–non-AF difference (ΔRR)', labelpad=8)
    fig.text(0.555, 0.064, 'Participation benchmark', ha='center', fontsize=7.5)
    expected = json.loads((P / 'validation/Figure3_RR_values.json').read_text())
    assert data == expected, 'Plotted values differ from the approved source data'
    assert len(data) == 36
    write_csv('Source_Data_Figure_3_plotted.csv', data)
    shares = []
    changes = []
    for g in GROUPS:
        k = 'group:' + g
        rc = RR[k, 'first', 'country', 'AF']
        ra = RR[k, 'first', 'author', 'AF']
        rl = RR[k, 'last', 'country', 'AF']
        shares.append(dict(group=g, country_output_pct=100 * float(rc['participation_credit']) / float(rc['participation_total']), team_author_pct=100 * float(ra['participation_credit']) / float(ra['participation_total']), first_author_pct=100 * float(rc['role_credit']) / float(rc['role_total']), last_author_pct=100 * float(rl['role_credit']) / float(rl['role_total'])))
        for role in ROLES:
            r = CC[k, role]
            changes.append(dict(group=g, role=role, paired_change=float(r['C']), ci_low=float(r['ci_low']), ci_high=float(r['ci_high'])))
            assert np.isclose(float(r['C']), float(DD[k, role, 'author']['delta']) - float(DD[k, role, 'country']['delta']), atol=1e-12)
    write_csv('Source_Data_Figure_3_credit_shares.csv', shares)
    write_csv('Paired_benchmark_changes_for_Table_S8b.csv', changes)
    return save(fig, 'Figure3_RR', data)
if __name__ == '__main__':
    print(json.dumps(main_figure(), indent=2))
