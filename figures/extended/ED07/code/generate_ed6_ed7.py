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
    fig.legend(handles=[Line2D([0], [0], color=c, marker=m, ls='none', ms=4, label='AF' if cp == 'AF' else 'non-AF') for cp, c, m in CORPORA], loc=loc, bbox_to_anchor=xy, frameon=False, ncol=2, handletextpad=0.4, columnspacing=1.5, fontsize=7)

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

def ed6():
    flow = read('strict_annual_flow.csv')
    team = read('team_size.csv')
    gr = read('strict_group_annual_retention.csv')
    fig = plt.figure(figsize=(183 / 25.4, 166 / 25.4))
    corpus_legend(fig, (0.975, 0.997))
    data = []
    letter(fig, 'a', 0.025, 0.94)
    letter(fig, 'b', 0.535, 0.94)
    ax = axes(fig, [0.115, 0.602, 0.355, 0.299])
    for cp, col, mark in CORPORA:
        rr = sorted([r for r in flow if r['corpus'] == cp], key=lambda r: int(r['year']))
        xs = [int(r['year']) for r in rr]
        ys = [float(r['international_pct']) for r in rr]
        ax.plot(xs, ys, color=col, marker=mark, ms=3.7, lw=1.2)
        for r in rr:
            data.append(dict(panel='a', corpus=cp, year=int(r['year']), international_pct=float(r['international_pct']), country_known=int(r['country_known'])))
        ax.text(2025, ys[-1] + (1.0 if cp == 'AF' else -1.6), f'{ys[-1]:.2f}', color=col, ha='right', va='bottom' if cp == 'AF' else 'top', fontsize=7, weight='bold')
    af = next((float(r['international_pct']) for r in flow if r['corpus'] == 'AF' and r['year'] == '2025'))
    ref = next((float(r['international_pct']) for r in flow if r['corpus'] == 'reference' and r['year'] == '2025'))
    ax.plot([2025.23, 2025.36, 2025.36, 2025.23], [ref, ref, af, af], color=MUTED, lw=0.6, clip_on=False)
    ax.text(2025.18, (af + ref) / 2, f'+{af - ref:.2f} pp', ha='right', va='center', fontsize=6.8)
    ax.set(xlim=(2019.8, 2025.6), ylim=(22, 42), xticks=range(2020, 2026), yticks=[24, 28, 32, 36, 40], ylabel='International studies (%)', xlabel='Publication year')
    for i, scope in enumerate(['country_known', 'international']):
        ax = axes(fig, [0.62, 0.772 - i * 0.17, 0.34, 0.126])
        for cp, col, mark in CORPORA:
            rr = sorted([r for r in team if r['corpus'] == ('AF' if cp == 'AF' else 'non-AF') and r['scope'] == scope], key=lambda r: int(r['year']))
            xs = np.array([int(r['year']) for r in rr]) + (-0.075 if cp == 'AF' else 0.075)
            ys = np.array([float(r['median']) for r in rr])
            lo = np.array([float(r['q25']) for r in rr])
            hi = np.array([float(r['q75']) for r in rr])
            ax.errorbar(xs, ys, yerr=[ys - lo, hi - ys], fmt=mark + '-', color=col, ms=3, lw=0.9, elinewidth=0.65, capsize=1.5, capthick=0.6)
            for r in rr:
                data.append(dict(panel='b', scope=scope, corpus=cp, year=int(r['year']), median=float(r['median']), q25=float(r['q25']), q75=float(r['q75']), n=int(r['n_assessable'])))
        ax.text(0.02, 0.97, 'Country-known' if i == 0 else 'International', transform=ax.transAxes, va='top', fontsize=6.7, color=MUTED)
        ax.set(xlim=(2019.7, 2025.3), ylim=(0, 17), xticks=range(2020, 2026), yticks=[2, 8, 14])
        if i == 0:
            ax.tick_params(axis='x', labelbottom=False)
        else:
            ax.set_xlabel('Publication year')
    fig.text(0.557, 0.748, 'Observed authors', rotation=90, ha='center', va='center', fontsize=7.5)
    fig.add_artist(Line2D([0.09, 0.96], [0.535, 0.535], transform=fig.transFigure, color=GRID, lw=0.7))
    letter(fig, 'c', 0.025, 0.493)
    fig.text(0.113, 0.49, 'Study selection', fontsize=8, va='top')
    stages = [('International', 'international_historical'), ('Role-eligible', 'common_roles_strict'), ('Author-complete', 'strict_complete'), ('Common support', 'strict_supported')]
    columns = [0.315, 0.455]
    yrows = [0.39, 0.305, 0.22, 0.135]
    for x, (cp, col, mark) in zip(columns, CORPORA):
        fig.text(x, 0.446, 'AF' if cp == 'AF' else 'non-AF', ha='center', color=col, fontsize=7.4, weight='bold')
        counts = [sum((int(r[field]) for r in flow if r['corpus'] == cp)) for lab, field in stages]
        assert counts[-1] == (5087 if cp == 'AF' else 332760)
        for idx, ((lab, field), count, y) in enumerate(zip(stages, counts, yrows)):
            fig.text(x, y, f'{count:,}', ha='center', va='center', fontsize=8, weight='bold' if idx == 3 else 'normal', color=col)
            if idx < 3:
                fig.add_artist(Line2D([x, x], [y - 0.017, yrows[idx + 1] + 0.022], transform=fig.transFigure, color=col, lw=0.6))
                fig.text(x + 0.018, (y + yrows[idx + 1]) / 2, f'{100 * counts[idx + 1] / count:.1f}%', ha='left', va='center', fontsize=6.2, color=MUTED, bbox=dict(facecolor='white', edgecolor='none', pad=0.3))
            data.append(dict(panel='c', corpus=cp, stage=lab, n=count))
    for (lab, _), y in zip(stages, yrows):
        fig.text(0.113, y, lab, fontsize=7, va='center')
    letter(fig, 'd', 0.535, 0.493)
    fig.text(0.62, 0.49, 'Author-complete retention', fontsize=8, va='top')
    ax = axes(fig, [0.674, 0.135, 0.286, 0.293])
    for i, g in enumerate(['higher', 'middle', 'lower', 'outside']):
        yy = 3 - i
        vals = []
        for cp, col, mark in CORPORA:
            rr = [r for r in gr if r['corpus'] == cp and r['national_group'] == g]
            den = sum((int(r['international_group_n']) for r in rr))
            num = sum((int(r['strict_complete_n']) for r in rr))
            val = 100 * num / den
            vals.append(val)
            ax.plot(val, yy, marker=mark, ms=4, color=col, zorder=3)
            ax.text(val, yy + (0.16 if cp == 'AF' else -0.16), f'{val:.1f}', ha='center', va='bottom' if cp == 'AF' else 'top', fontsize=6.7, color=col)
            data.append(dict(panel='d', group=g, corpus=cp, complete=num, international=den, retention_pct=val))
        ax.plot(vals, [yy, yy], color='#A4ADBB', lw=0.8, zorder=1)
        ax.plot([-0.045, -0.045], [yy - 0.25, yy + 0.25], transform=ax.get_yaxis_transform(), color=GP[g], lw=2.2, clip_on=False)
    ax.set(xlim=(72, 86), ylim=(-0.6, 3.6), xticks=[75, 80, 85], yticks=[3, 2, 1, 0], yticklabels=['High', 'Middle', 'Low', 'Outside'], xlabel='Retention (%)')
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=10)
    write_csv('Source_Data_ED6.csv', data)
    return save(fig, 'Extended_Data_Fig6', data)

def ed7():
    data = json.loads((P / 'source_data/ED7_plot_values.json').read_text())
    pooled = [r for r in data if r['panel'] == 'b']
    bins = ['1', '2–4', '5–9', '10+']
    fig = plt.figure(figsize=(183 / 25.4, 160 / 25.4))
    corpus_legend(fig, (0.965, 0.995))
    letter(fig, 'a', 0.028, 0.932)
    for j, role in enumerate(ROLES):
        left = [0.13, 0.59][j]
        ax = axes(fig, [left, 0.58, 0.36, 0.29])
        ax.text(0.5, 1.1, 'First author' if role == 'first' else 'Last author', transform=ax.transAxes, ha='center', fontsize=8)
        for cp, col, mark in CORPORA:
            rr = [r for r in data if r['panel'] == 'a' and r['corpus'] == cp and (r['role'] == role)]
            vals = [next((r['observed_pct'] for r in rr if r['paper_bin'] == bi)) for bi in bins]
            ax.plot(range(4), vals, marker=mark, color=col, lw=1.2, ms=4)
            for x, bi in enumerate(bins):
                n = next((r['n'] for r in rr if r['paper_bin'] == bi))
                ax.text(x, -0.27 if cp == 'AF' else -0.335, f'{n:,}', transform=ax.get_xaxis_transform(), ha='center', va='center', color=col, fontsize=6.5)
        ax.set(xlim=(-0.18, 3.18), ylim=(0, 85), xticks=range(4), xticklabels=bins, yticks=[0, 20, 40, 60, 80])
        if j == 0:
            ax.set_ylabel('Zero authorship credit (%)')
        else:
            ax.spines['left'].set_visible(False)
            ax.tick_params(axis='y', left=False, labelleft=False)
        ax.set_xlabel('Studies per country–institution unit', labelpad=5, fontsize=7)
        ax.text(-0.04, -0.27, 'AF n', transform=ax.transAxes, ha='right', va='center', fontsize=6.2, color=AF)
        ax.text(-0.04, -0.335, 'non-AF n', transform=ax.transAxes, ha='right', va='center', fontsize=6.2, color=REF)
    fig.add_artist(Line2D([0.105, 0.95], [0.43, 0.43], transform=fig.transFigure, color=GRID, lw=0.7))
    letter(fig, 'b', 0.028, 0.395)
    fig.legend(handles=[Line2D([0], [0], marker='o', ls='none', color=MUTED, ms=4, label='Observed'), Line2D([0], [0], marker='o', ls='none', color=MUTED, mfc='white', ms=4, label='Team-composition reference')], loc='upper center', bbox_to_anchor=(0.56, 0.413), ncol=2, frameon=False, fontsize=6.9, handletextpad=0.5, columnspacing=2)
    ax = axes(fig, [0.22, 0.08, 0.57, 0.27])
    ax.set_xlim(29, 59)
    ax.set_ylim(-0.65, 3.65)
    plotrows = [('AF', 'first'), ('AF', 'last'), ('reference', 'first'), ('reference', 'last')]
    labels = []
    for i, (cp, role) in enumerate(plotrows):
        r = next((r for r in pooled if r['corpus'] == cp and r['role'] == role))
        y = 3 - i
        col, mark = (AF, 'o') if cp == 'AF' else (REF, 's')
        o, e = (r['observed_pct'], r['expected_pct'])
        ax.plot([o, e], [y + 0.11, y - 0.11], color=col, lw=0.8)
        ax.plot(o, y + 0.11, marker=mark, color=col, ms=4)
        ax.errorbar(e, y - 0.11, xerr=[[e - r['reference_low']], [r['reference_high'] - e]], fmt=mark, mfc='white', mec=col, ms=4, mew=0.8, ecolor=col, elinewidth=0.8, capsize=2, capthick=0.7)
        ax.text(o, y + 0.26, f'{o:.2f}', ha='center', va='bottom', fontsize=6.6, color=col, weight='bold')
        ax.text(e, y - 0.26, f'{e:.2f}', ha='center', va='top', fontsize=6.6, color=col)
        ax.text(1.08, y, f"{r['n']:,}", transform=ax.get_yaxis_transform(), ha='center', va='center', fontsize=7, color=MUTED)
        labels.append(('AF' if cp == 'AF' else 'non-AF') + ' · ' + role.capitalize())
    ax.axhline(1.5, color=GRID, lw=0.65)
    ax.set(yticks=[3, 2, 1, 0], yticklabels=labels, xticks=[30, 40, 50, 60], xlabel='Zero authorship credit (%)')
    ax.set_xlim(29, 59)
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.text(1.08, 1.06, 'Units (n)', transform=ax.transAxes, ha='center', fontsize=6.7, color=MUTED)
    write_csv('Source_Data_ED7.csv', data)
    return save(fig, 'Extended_Data_Fig7', data)
if __name__ == '__main__':
    results = {'ED6': ed6(), 'ED7': ed7()}
    for name in ['Extended_Data_Fig6', 'Extended_Data_Fig7']:
        assert json.loads((OUT / (name + '_values.json')).read_text()) == json.loads((P / 'validation' / (name + '_values.json')).read_text())
    print(json.dumps(results, indent=2))
