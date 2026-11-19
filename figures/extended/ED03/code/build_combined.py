from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""ED3 display revision. Frozen v7 country credits; no new estimation.
Run: python code/build_ed3.py [--source /path/to/finding1_v7_final_v1]
Without --source, uses the included, portable CSV snapshots.
"""
from pathlib import Path
import argparse, csv, hashlib, json, math, shutil, re
from reportlab.graphics.shapes import Drawing, String, Line, PolyLine, Circle, Rect, Group
from reportlab.graphics import renderSVG, renderPDF
from reportlab.pdfbase.pdfmetrics import stringWidth, registerFont
from reportlab.pdfbase.ttfonts import TTFont
registerFont(TTFont(release_font_family(), release_font_path('/System/Library/Fonts/Supplemental/Arial.ttf')))
registerFont(TTFont('Arial-Bold', release_font_path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')))
from reportlab.lib.colors import HexColor, white
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--source', type=Path)
args = p.parse_args()

def read(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
ORDER = ['US', 'CN', 'JP', 'DE', 'GB', 'IN', 'FR', 'KR', 'IT', 'CA']
NAMES = {'US': 'United States', 'CN': 'China', 'JP': 'Japan', 'DE': 'Germany', 'GB': 'United Kingdom', 'IN': 'India', 'FR': 'France', 'KR': 'South Korea', 'IT': 'Italy', 'CA': 'Canada', 'ES': 'Spain', 'Other': 'Other'}
YEARS = list(range(2021, 2026))
if args.source:
    src = args.source
    selection = sorted(read(src / 'tables/normalization_country_selection.csv'), key=lambda r: int(r['baseline_rank']))[:10]
    assert [r['country_code'] for r in selection] == ORDER
    full = read(src / 'tables/Table_S4_country_year_R_first_observation.csv')
    annual = [r for code in ORDER for r in full if r['country_code'] == code and int(r['year']) in YEARS]
    assert len(annual) == 50
    for r in annual:
        r['baseline_rank'] = ORDER.index(r['country_code']) + 1
        r['baseline_period'] = '2015-2019'
    write(ROOT / 'source_data/ED3a_annual.csv', annual)
    for name in ['ED3b.csv', 'ED3c.csv']:
        shutil.copyfile(src / 'source_data' / name, ROOT / 'source_data' / name)
    shutil.copyfile(src / 'tables/normalization_country_selection.csv', ROOT / 'source_data/normalization_country_selection.csv')
    endpoints = read(src / 'source_data/ED3a.csv')
    lookup = {(r['country_code'], int(r['year'])): r for r in annual}
    assert all((float(r['R']) == float(lookup[r['country_code'], int(r['year'])]['R']) for r in endpoints))
    files = ['tables/Table_S4_country_year_R_first_observation.csv', 'tables/normalization_country_selection.csv', 'source_data/ED3a.csv', 'source_data/ED3b.csv', 'source_data/ED3c.csv']
    manifest = {'source_root': str(src), 'inputs': {f: hashlib.sha256((src / f).read_bytes()).hexdigest() for f in files}}
    (ROOT / 'source_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
annual = read(ROOT / 'source_data/ED3a_annual.csv')
top = sorted(read(ROOT / 'source_data/ED3b.csv'), key=lambda r: int(r['year']))
composition = read(ROOT / 'source_data/ED3c.csv')
lookup = {(r['country_code'], int(r['year'])): r for r in annual}
assert len(lookup) == 50 and len(top) == 5 and (len(composition) == 55)
for r in annual:
    expected = float(r['af_credit']) / float(r['A_total']) / (float(r['local_all_credit']) / float(r['T_total']))
    assert math.isclose(float(r['R']), expected, rel_tol=1e-12)
    assert 0.25 < float(r['R']) < 4
    assert math.isclose(math.log2(float(r['R'])), float(r['log2_R']), abs_tol=1e-12)
for yr in YEARS:
    rows = [r for r in composition if int(r['year']) == yr]
    assert math.isclose(sum((float(r['attributed_fraction']) for r in rows)), 1, abs_tol=1e-10)
    assert all((math.isclose(float(r['attributed_fraction']), float(r['credit']) / float(r['known_AF_studies']), abs_tol=1e-12) for r in rows))
for r in top:
    assert math.isclose(float(r['top5_percent']), 100 * float(r['af_top5']), abs_tol=1e-10)
    assert math.isclose(float(r['top10_percent']), 100 * float(r['af_top10']), abs_tol=1e-10)
W, H = (183 * 72 / 25.4, 630)
D = Drawing(W, H)
D.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
INK = HexColor('#11151C')
MUTED = HexColor('#657183')
GRID = HexColor('#E9EEF4')
BLUE = HexColor('#173873')
SECONDARY = HexColor('#7898C4')

def txt(x, y, s, size=7.5, color=INK, anchor='start', bold=False, angle=0):
    item = String(0 if angle else x, 0 if angle else y, s, fontName='Arial-Bold' if bold else release_font_family(), fontSize=size, fillColor=color, textAnchor=anchor)
    if angle:
        g = Group()
        g.add(item)
        g.translate(x, y)
        g.rotate(angle)
        D.add(g)
    else:
        D.add(item)

def ln(x1, y1, x2, y2, color=INK, width=0.55, dash=None):
    D.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=width, strokeDashArray=dash, strokeOpacity=0.75 if color == GRID else 0.95))

def circle(x, y, color, r=1.8):
    D.add(Circle(x, y, r, fillColor=color, fillOpacity=0.68, strokeColor=color, strokeOpacity=0.9, strokeWidth=0.35))

def path(points, color, width=1.2):
    D.add(PolyLine([v for xy in points for v in xy], strokeColor=color, strokeWidth=width, strokeOpacity=0.95, fillColor=None))

def legend(x, y, label, color, marker='circle', line=False):
    if line:
        ln(x, y + 2, x + 14, y + 2, color, 1.15)
        if marker == 'square':
            D.add(Rect(x + 5.4, y + 0.4, 3.2, 3.2, fillColor=color, fillOpacity=0.68, strokeColor=color, strokeOpacity=0.9, strokeWidth=0.25))
        else:
            circle(x + 7, y + 2, color, 1.7)
        dx = 19
    else:
        D.add(Rect(x, y - 0.5, 7, 6, fillColor=color, fillOpacity=0.9, strokeColor=None))
        dx = 11
    txt(x + dx, y, label, size=7)
    return dx + stringWidth(label, release_font_family(), 7) + 13
txt(13, 642, 'a', 10, bold=True)
txt(47, 623, 'R = 1: the same national share of AF and eligible life-science output', 7.5, color=MUTED)
px, py, pw, ph = (92, 266, 80, 306)
rx = lambda value: px + (math.log2(value) + 2) / 4 * pw
for value in [0.25, 0.5, 1, 2, 4]:
    ln(rx(value), py, rx(value), py + ph, MUTED if value == 1 else GRID, 0.65 if value == 1 else 0.4, [2.5, 2] if value == 1 else None)
    ln(rx(value), py - 2.5, rx(value), py, MUTED, 0.45)
    txt(rx(value), py - 12, str(value).rstrip('0').rstrip('.') if value >= 1 else str(value), 6.8, anchor='middle')
ln(px, py, px + pw, py, MUTED, 0.5)
for i, code in enumerate(ORDER):
    y = 557 - i * 30
    v1 = float(lookup[code, 2021]['R'])
    v5 = float(lookup[code, 2025]['R'])
    txt(85, y - 2.5, NAMES[code], 7.2, anchor='end')
    ln(rx(v1), y, rx(v5), y, HexColor('#A8B5C9'), 1.1)
    D.add(Circle(rx(v1), y, 3.0, fillColor=white, strokeColor=BLUE, strokeWidth=0.9))
    D.add(Circle(rx(v5), y, 1.7, fillColor=BLUE, fillOpacity=0.68, strokeColor=BLUE, strokeOpacity=0.9, strokeWidth=0.55))
txt(132, 238, 'Relative AF intensity (R)', 7.2, anchor='middle')
txt(132, 224, 'log2 scale', 6.8, color=MUTED, anchor='middle')
D.add(Circle(71, 214, 3.0, fillColor=white, strokeColor=BLUE, strokeWidth=0.9))
txt(79, 211.5, '2021', 7)
D.add(Circle(121, 214, 1.7, fillColor=BLUE, fillOpacity=0.68, strokeColor=BLUE, strokeOpacity=0.9, strokeWidth=0.55))
txt(129, 211.5, '2025', 7)
for i, code in enumerate(ORDER):
    col, row = divmod(i, 5)
    px = 218 + col * 160
    py = 524 - row * 68
    pw = 130
    ph = 44
    txt(px + pw / 2, py + 55, NAMES[code], 7.5, anchor='middle', bold=True)
    sx = lambda year: px + 5 + (year - 2021) / 4 * (pw - 10)
    sy = lambda value: py + (math.log2(value) + 2) / 4 * ph
    for value, label in [(0.25, '0.25'), (0.5, '0.5'), (1, '1'), (2, '2'), (4, '4')]:
        ln(px, sy(value), px + pw, sy(value), MUTED if value == 1 else GRID, 0.65 if value == 1 else 0.4, [2.5, 2] if value == 1 else None)
        txt(px - 5, sy(value) - 2, label, 6.4, anchor='end')
    ln(px, py, px, py + ph, MUTED, 0.5)
    ln(px, py, px + pw, py, MUTED, 0.5)
    for year in YEARS:
        ln(sx(year), py - 2, sx(year), py, MUTED, 0.45)
        if row == 4 and year in [2021, 2023, 2025]:
            txt(sx(year), py - 10, str(year), 6.6, anchor='middle')
    vals = [float(lookup[code, y]['R']) for y in YEARS]
    path([(sx(y), sy(v)) for y, v in zip(YEARS, vals)], BLUE, 1.1)
    for y, v in zip(YEARS, vals):
        circle(sx(y), sy(v), BLUE, 1.6)
    txt(sx(2025) - 1, sy(vals[-1]) + 5, f'{vals[-1]:.2f}', 6.8, color=BLUE, anchor='end')
txt(363, 228, 'Publication year', 7.5, anchor='middle')
upper = Group()
for item in list(D.contents)[1:]:
    upper.add(item)
D.contents = D.contents[:1]

def compress_a(node):
    if isinstance(node, Group):
        for child in node.contents:
            compress_a(child)
    elif isinstance(node, Line):
        node.y1 = 334 + 0.65 * (node.y1 - 214)
        node.y2 = 334 + 0.65 * (node.y2 - 214)
    elif isinstance(node, Circle):
        node.cy = 334 + 0.65 * (node.cy - 214)
    elif isinstance(node, Rect):
        node.y = 334 + 0.65 * (node.y - 214)
        node.height *= 0.65
    elif isinstance(node, String):
        node.y = 334 + 0.65 * (node.y - 214)
    elif isinstance(node, PolyLine):
        node.points = [v if i % 2 == 0 else 334 + 0.65 * (v - 214) for i, v in enumerate(node.points)]
    else:
        raise TypeError(type(node))
compress_a(upper)
D.add(upper)
txt(13, 314, 'b', 10, bold=True)
px, py, pw, ph = (47, 135, 155, 155)
sx = lambda year: px + 7 + (year - 2021) / 4 * (pw - 14)
sy = lambda value: py + (value - 50) / 35 * ph
for tick in [50, 60, 70, 80]:
    ln(px, sy(tick), px + pw, sy(tick), GRID, 0.4)
    txt(px - 6, sy(tick) - 2.5, str(tick), 7, anchor='end')
ln(px, py, px, py + ph, MUTED)
ln(px, py, px + pw, py, MUTED)
for year in YEARS:
    ln(sx(year), py - 3, sx(year), py, MUTED, 0.5)
    txt(sx(year), py - 13, str(year), 7, anchor='middle')
for field, col, shape in [('top5_percent', BLUE, 'circle'), ('top10_percent', SECONDARY, 'square')]:
    vals = [float(r[field]) for r in top]
    path([(sx(y), sy(v)) for y, v in zip(YEARS, vals)], col)
    for year, v in zip(YEARS, vals):
        if shape == 'square':
            D.add(Rect(sx(year) - 1.7, sy(v) - 1.7, 3.4, 3.4, fillColor=white, strokeColor=col, strokeWidth=0.8))
        else:
            circle(sx(year), sy(v), col, 2.0)
    for year, v, anchor in [(2021, vals[0], 'start'), (2025, vals[-1], 'end')]:
        txt(sx(year), sy(v) + 7, f'{v:.1f}%', 7, color=col, anchor=anchor)
txt(15, py + ph / 2, 'Attributed AF output (%)', 8, anchor='middle', angle=90)
txt(px + pw / 2, 108, 'Publication year', 7.5, anchor='middle')
legend(50, 87, 'Annual top five', BLUE, line=True)
legend(50, 72, 'Annual top ten', SECONDARY, marker='square', line=True)
txt(250, 314, 'c', 10, bold=True)
CODES = ['US', 'CN', 'DE', 'GB', 'FR', 'JP', 'CA', 'IT', 'ES', 'IN', 'Other']
BLUE_ANCHORS = ['#F2F5FA', '#D6DFED', '#8FAAD3', '#35558B', '#173873']

def ramp(t):
    u = min(1, max(0, t)) * 4
    i = min(3, int(u))
    f = u - i
    a, b = BLUE_ANCHORS[i:i + 2]
    return '#' + ''.join((f'{round(int(a[k:k + 2], 16) * (1 - f) + int(b[k:k + 2], 16) * f):02X}' for k in (1, 3, 5)))
PALETTE = [ramp(1 - i * 0.75 / 9) for i in range(10)] + ['#D4D9E1']
COLORS = [HexColor(c) for c in PALETTE]
px, py, pw, ph = (315, 235, 190, 55)
cw = pw / 5
sx = lambda year: px + (year - 2021 + 0.5) * cw
sy = lambda value: py + value / 100 * ph
for tick in [0, 50, 100]:
    ln(px, sy(tick), px + pw, sy(tick), GRID, 0.4)
    txt(px - 6, sy(tick) - 2.5, str(tick), 6.5, anchor='end')
for year in YEARS:
    bottom = 0
    for code, color in zip(CODES, COLORS):
        r = next((r for r in composition if int(r['year']) == year and r['country_code'] == code))
        value = float(r['attributed_fraction']) * 100
        D.add(Rect(sx(year) - 12, sy(bottom), 24, value / 100 * ph, fillColor=color, fillOpacity=0.9, strokeColor=white, strokeWidth=0.25))
        bottom += value
    txt(sx(year), py - 11, str(year), 6.8, anchor='middle')
ln(px, py, px, py + ph, MUTED)
ln(px, py, px + pw, py, MUTED)
txt(278, py + ph / 2, 'AF output (%)', 7, anchor='middle', angle=90)
heat_records = []
hy = 78
rh = 12
vmax = 40
for i, (code, col) in enumerate(zip(CODES, COLORS)):
    yy = hy + (len(CODES) - 1 - i) * rh
    D.add(Rect(251, yy + 3, 4, 5, fillColor=col, fillOpacity=0.9, strokeColor=None))
    txt(309, yy + 3.5, NAMES[code], 6.4, anchor='end')
    for j, year in enumerate(YEARS):
        r = next((r for r in composition if int(r['year']) == year and r['country_code'] == code))
        value = float(r['attributed_fraction']) * 100
        assert 0 <= value <= vmax
        xx = px + j * cw
        col = HexColor(ramp(value / vmax))
        D.add(Rect(xx, yy, cw, rh, fillColor=col, strokeColor=white, strokeWidth=0.6))
        txt(xx + cw / 2, yy + 3.4, f'{value:.1f}', 6.6, color=white if value >= 24 else INK, anchor='middle')
        heat_records.append({'country_code': code, 'year': year, 'share_percent': value})
    if code == 'Other':
        ln(px, yy + rh, px + pw, yy + rh, white, 1.6)
for j, year in enumerate(YEARS):
    txt(px + (j + 0.5) * cw, hy - 11, str(year), 6.8, anchor='middle')
txt(px + pw / 2, hy - 23, 'Publication year', 7, anchor='middle')
cbx, cby, cbw, cbh = (331, 32, 158, 5)
for k in range(160):
    D.add(Rect(cbx + k * cbw / 160, cby, cbw / 160 + 0.02, cbh, fillColor=HexColor(ramp(k / 159)), strokeColor=None))
for v in [0, 10, 20, 30, 40]:
    xx = cbx + v / vmax * cbw
    ln(xx, cby - 2, xx, cby, MUTED, 0.4)
    txt(xx, cby - 10, str(v), 6.5, anchor='middle')
txt(cbx + cbw / 2, 8, 'Country share of attributed AF output (%)', 7, anchor='middle')
(ROOT / 'validation/heatmap_values.json').write_text(json.dumps(heat_records, indent=2) + '\n')
renderSVG.drawToFile(D, str(ROOT / 'figures/Country_patterns_bar_heatmap.svg'))
svg_path = ROOT / 'figures/Country_patterns_bar_heatmap.svg'
svg = svg_path.read_text()
svg = re.sub('(<path d="M [^"MLZ]+ L [^"MLZ]+) Z(" style=)', '\\1\\2', svg)
svg = svg.replace('font-family: Arial-Bold;', 'font-family: Arial, Helvetica, sans-serif; font-weight: bold;')
svg = svg.replace('font-family: Arial;', 'font-family: Arial, Helvetica, sans-serif;')
svg = re.sub('viewBox="[^"]+"', f'viewBox="0 0 {W} {H}"', svg, count=1)

def leaves(item):
    if hasattr(item, 'contents'):
        for child in item.contents:
            yield from leaves(child)
    else:
        yield item
items = list(leaves(D))
counter = [0]

def svg_opacity(match):
    node = items[counter[0]]
    counter[0] += 1
    settings = []
    for attr, css in [('fillOpacity', 'fill-opacity'), ('strokeOpacity', 'stroke-opacity')]:
        value = getattr(node, attr, None)
        if value is not None:
            settings.append(f'{css}: {value};')
    return match[0].replace('style="', 'style="' + ' '.join(settings) + ' ', 1)
svg = re.sub('<(?:path|rect|circle|polyline|text)\\b[^>]*style="[^>]*>', svg_opacity, svg)
assert counter[0] == len(items), (counter, len(items))
svg_path.write_text(svg)
renderPDF.drawToFile(D, str(ROOT / 'figures/Country_patterns_bar_heatmap.pdf'))
validation = {'country_year_rows': len(annual), 'baseline_top_ten': ORDER, 'years': YEARS, 'relative_intensity_formula_checked': True, 'source_endpoint_values_unchanged': True, 'all_50_values_within_shared_axis': True, 'composition_sums_to_one': True, 'c_denominator': 'known-country AF fractional credit', 'b_yearly_leaders_re_ranked': True, 'a_common_axis': 'left x-axis and right y-axes: log2, R=0.25 to 4', 'b_axis_percent': [50, 85], 'c_axis_percent': [0, 100], 'dimensions_pt': [W, H], 'a_vertical_spacing_scale': 0.65, 'a_font_sizes_unchanged': True, 'font_family': release_font_family(), 'bold_titles': 'embedded Arial Bold TrueType', 'c_visualization': 'original fixed-country stacked shares plus 55-cell percentage heatmap', 'c_heatmap_scale_percent': [0, 40], 'c_country_legend': 'coloured swatches beside heatmap rows', 'b_legend_position': 'below b', 'c_colorbar_position': 'below c', 'smoothing': False, 'inference_or_new_estimation': False}
(ROOT / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
print(json.dumps(validation, indent=2))
(ROOT / 'style.json').write_text(json.dumps({'reference': 'Figure1_blue_red and Figure_S5_blue_A4, 2026-11-02', 'primary_blue': '#173873', 'secondary_blue': '#7898C4', 'blue_ramp': BLUE_ANCHORS, 'country_colors': dict(zip(CODES, PALETTE)), 'line_opacity': 0.95, 'marker_fill_opacity': 0.68, 'marker_stroke_opacity': 0.9, 'bar_fill_opacity': 0.9, 'grid_opacity': 0.75, 'numeric_changes': False, 'layout_changes': True}, indent=2) + '\n')
