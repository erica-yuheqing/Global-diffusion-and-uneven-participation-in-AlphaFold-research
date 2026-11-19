from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Country endpoint display with explicit undefined ratios; no new estimation."""
from pathlib import Path
from xml.sax.saxutils import escape
import csv, hashlib, json, math, os, subprocess
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source_data/country_endpoints.csv'
with SOURCE.open(newline='') as f:
    rows = list(csv.DictReader(f))
order = sorted([r for r in rows if r['year'] == '2021'], key=lambda r: int(r['plot_order']))
lookup = {(r['country'], int(r['year'])): r for r in rows}
undefined = [r['country'] for r in order if not r['R']]
expected_undefined = 'ID PT NO MY TH NG RO BD VN TN SK IQ SI BG MA ET PH DZ AE KE BY EC KZ UG'.split()
assert undefined == expected_undefined
assert len(rows) == 136 and len(order) == 68 and (len(undefined) == 24)
assert all((float(lookup[c, 2021]['H']) == float(lookup[c, 2021]['L']) == 0 for c in undefined))
assert all((lookup[r['country'], 2025]['R'] for r in order))
for r in rows:
    h, l = (float(r['H']), float(r['L']))
    assert math.isclose(float(r['G_pp']), 100 * (h - l), abs_tol=1e-10)
    if r['R']:
        assert h > 0 and math.isclose(float(r['R']), l / h, abs_tol=1e-12)
    else:
        assert h == 0
W, H = (183 * 72 / 25.4, 260 * 72 / 25.4)
NAVY = '#4B2368'
INK = '#11151C'
MUTED = '#657183'
GRID = '#E9EEF4'
COLORS = {'High': '#4B2368', 'Middle': '#9470AD', 'Low': '#C5AED6'}
pdfmetrics.registerFont(TTFont('FigureArial', release_font_path('/System/Library/Fonts/Supplemental/Arial.ttf')))
pdfmetrics.registerFont(TTFont('FigureArialBold', release_font_path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')))
pdf = canvas.Canvas(str(ROOT / 'figures/Extended_Data_Fig5_stars.pdf'), pagesize=(W, H))
pdf.setTitle('Extended Data Figure 5: Country-specific institutional coverage disparities')
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="183mm" height="260mm" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="white"/>']
text_boxes = []
artists = []

def text(x, y, s, size=7, anchor='start', color=INK, bold=False):
    font = 'FigureArialBold' if bold else 'FigureArial'
    pdf.saveState()
    pdf.setFillColor(HexColor(color))
    pdf.setFillAlpha(1)
    pdf.setFont(font, size)
    if anchor == 'middle':
        pdf.drawCentredString(x, H - y, s)
    elif anchor == 'end':
        pdf.drawRightString(x, H - y, s)
    else:
        pdf.drawString(x, H - y, s)
    pdf.restoreState()
    svg.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" fill="{color}"' + (' font-weight="bold"' if bold else '') + '>' + escape(s) + '</text>')
    tw = pdfmetrics.stringWidth(s, font, size)
    left = x - tw if anchor == 'end' else x - tw / 2 if anchor == 'middle' else x
    text_boxes.append((s, left, y - size, left + tw, y + size * 0.22))

def line(x1, y1, x2, y2, color=MUTED, width=0.55, alpha=1, dash=None):
    pdf.saveState()
    pdf.setStrokeColor(HexColor(color))
    pdf.setStrokeAlpha(alpha)
    pdf.setLineWidth(width)
    if dash:
        pdf.setDash(*dash)
    pdf.line(x1, H - y1, x2, H - y2)
    pdf.restoreState()
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-opacity="{alpha}"' + (f' stroke-dasharray="{dash[0]},{dash[1]}"' if dash else '') + '/>')

def rect(x, y, w, h, color, alpha):
    pdf.saveState()
    pdf.setFillColor(HexColor(color))
    pdf.setFillAlpha(alpha)
    pdf.rect(x, H - y - h, w, h, stroke=0, fill=1)
    pdf.restoreState()
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" fill-opacity="{alpha}"/>')

def marker(x, y, color, year, r=1.75):
    filled = year == 2025
    fill = color if filled else '#FFFFFF'
    alpha = 1
    pdf.saveState()
    pdf.setStrokeColor(HexColor(color))
    pdf.setStrokeAlpha(0.95)
    pdf.setFillColor(HexColor(fill))
    pdf.setFillAlpha(alpha)
    pdf.setLineWidth(0.65)
    pdf.circle(x, H - y, r, stroke=1, fill=1)
    pdf.restoreState()
    svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" stroke="{color}" stroke-opacity=".95" stroke-width=".65" fill="{fill}" fill-opacity="{alpha}"/>')
ys = [42 + i * 8.35 + (6 if i >= 23 else 0) + (6 if i >= 45 else 0) for i in range(68)]
top, bottom = (34, 622)
panels = [{'letter': 'a', 'metric': 'R', 'x': 48, 'w': 180, 'lo': -0.012, 'hi': 0.55, 'ticks': [0, 0.1, 0.2, 0.3, 0.4, 0.5], 'labelx': 40}, {'letter': 'b', 'metric': 'G_pp', 'x': 317, 'w': 189, 'lo': -1.25, 'hi': 55, 'ticks': [0, 10, 20, 30, 40, 50], 'labelx': 309}]
for p in panels:
    x, w = (p['x'], p['w'])
    X = lambda v: x + (v - p['lo']) / (p['hi'] - p['lo']) * w
    text(13 if p['letter'] == 'a' else 278, 14, p['letter'], 10, bold=True)
    for start, end, group in [(0, 22, 'High'), (23, 44, 'Middle'), (45, 67, 'Low')]:
        gy = ys[start] - 4
        gh = ys[end] - ys[start] + 8
        if group != 'Middle':
            rect(x, gy, w, gh, '#64748B', 0.022)
        rect(p['labelx'] - 26, gy, 2, gh, COLORS[group], 1)
    for v in p['ticks']:
        xx = X(v)
        line(xx, top, xx, bottom, GRID, 0.4, 0.75)
        line(xx, bottom, xx, bottom + 3, MUTED, 0.5, 0.9)
        text(xx, bottom + 13, '0' if v == 0 else f'{v:g}', 7.2, 'middle')
    line(x, bottom, x + w, bottom, MUTED, 0.55, 0.9)
    for last, first in [(22, 23), (44, 45)]:
        yy = (ys[last] + ys[first]) / 2
        line(p['labelx'] - 20, yy, x + w, yy, '#B7C3D3', 0.45, 0.6, (1.5, 2))
    for i, r in enumerate(order):
        c = r['country']
        group = r['context']
        color = COLORS[group]
        y = ys[i]
        text(p['labelx'], y + 2.3, c, 7.0, 'end')
        if p['metric'] == 'R' and c in undefined:
            text(p['labelx'] + 1.2, y - 0.2, '*', 5.8, bold=True)
        vals = [lookup[c, yr][p['metric']] for yr in [2021, 2025]]
        if all((v != '' for v in vals)):
            line(X(float(vals[0])), y, X(float(vals[1])), y, color, 0.7, 0.7)
        for year, v in zip([2021, 2025], vals):
            if v == '':
                continue
            value = float(v)
            xx = X(value)
            assert x + 2 < xx < x + w - 2
            marker(xx, y, color, year, r=1.05 if year == 2025 and all((vv != '' for vv in vals)) and (float(vals[0]) == float(vals[1])) else 1.75)
            artists.append({'panel': p['letter'], 'country': c, 'year': year, 'value': value, 'x': xx, 'y': y})
    if p['metric'] == 'R':
        text(x + w / 2, 654, 'Annual coverage ratio', 7.5, 'middle')
        text(x + w / 2, 665, '(Lower / Higher institutions)', 7.2, 'middle')
    else:
        text(x + w / 2, 654, 'Annual coverage gap (pp)', 7.5, 'middle')
        text(x + w / 2, 665, '(Higher − Lower institutions)', 7.2, 'middle')
text(W / 2, 686, 'National publication-output groups', 7, 'middle', MUTED)
items = [('High (n = 23)', COLORS['High']), ('Middle (n = 22)', COLORS['Middle']), ('Low (n = 23)', COLORS['Low'])]
widths = [15 + pdfmetrics.stringWidth(label, 'FigureArial', 7) + 15 for label, col in items] + [53, 53]
lx = (W - sum(widths)) / 2
for (label, col), width in zip(items, widths):
    line(lx, 699, lx + 12, 699, col, 2, 0.95)
    text(lx + 16, 701.2, label, 7)
    lx += width
for year, width in zip([2021, 2025], widths[-2:]):
    marker(lx + 3, 699, INK, year)
    text(lx + 12, 701.2, str(year), 7)
    lx += width
text(35, 719.5, '*', 5.8, color=INK, bold=True)
text(40, 722, '2021 ratio undefined (0/0): both institutional groups had zero AF coverage.', 7.0, color='#4D5C71')
pdf.showPage()
pdf.save()
svg.append('</svg>')
(ROOT / 'figures/Extended_Data_Fig5_stars.svg').write_text('\n'.join(svg))
assert len(artists) == 248
assert sum((a['panel'] == 'a' and a['year'] == 2021 for a in artists)) == 44
assert sum((a['panel'] == 'a' and a['year'] == 2025 for a in artists)) == 68
assert all((not (a['panel'] == 'a' and a['year'] == 2021 and (a['country'] in undefined)) for a in artists))
assert all((0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H for s, x0, y0, x1, y1 in text_boxes))
assert all((math.isclose(a['value'], float(lookup[a['country'], a['year']]['R' if a['panel'] == 'a' else 'G_pp']), abs_tol=1e-12) for a in artists))
paired = [r for r in order if r['R']]
increased_R = sum((float(lookup[r['country'], 2025]['R']) > float(r['R']) for r in paired))
increased_G = sum((float(lookup[r['country'], 2025]['G_pp']) > float(r['G_pp']) for r in order))
assert increased_R == 26 and increased_G == 67
pdftext = PdfReader(ROOT / 'figures/Extended_Data_Fig5_stars.pdf').pages[0].extract_text()
assert 'NA 2021' not in pdftext and '†' not in pdftext and (pdftext.count('*') == 25)
validation = {'countries': 68, 'undefined_2021_ratios': 24, 'undefined_countries': undefined, 'all_undefined_are_zero_over_zero': True, 'ratio_2021_points': 44, 'ratio_2025_points': 68, 'gap_2021_and_2025_points_each': 68, 'ratio_paired_increases': 26, 'gap_increases': 67, 'all_248_plotted_values_match_source': True, 'undefined_ratios_never_plotted_as_zero': True, 'zero_markers_inside_plot': True, 'country_order_identical_across_panels': True, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'national_group_colors': COLORS, 'marker_fill_opacity': 1, 'marker_stroke_opacity': 0.95, 'connector_opacity': 0.7, 'ratio_axis_limits': [-0.012, 0.55], 'gap_axis_limits': [-1.25, 55]}
(ROOT / 'validation/style_and_data.json').write_text(json.dumps(validation, indent=2) + '\n')
(ROOT / 'validation/plotted_values.json').write_text(json.dumps(artists, indent=2) + '\n')
assert artists == json.loads((ROOT / 'provenance/original_plotted_values.json').read_text())
assert pdftext.count('*') == 25
validation.update({'all_248_plot_records_and_coordinates_identical': True, 'superscript_country_stars_panel_a': 24, 'stars_panel_b': 0, 'footnote': '2021 ratio undefined (0/0): both institutional groups had zero AF coverage.', 'country_label_font_pt': 7.0, 'star_font_pt': 5.8, 'star_baseline_raise_pt': 2.5, 'original_zip': str(Path('/historical-workspace/Desktop/figures/zip/Extended/ED5.zip'))})
(ROOT / 'validation/style_and_data.json').write_text(json.dumps(validation, indent=2) + '\n')
print('ED5 exported: exact original coordinates preserved; 24 superscript country stars only in a.')
