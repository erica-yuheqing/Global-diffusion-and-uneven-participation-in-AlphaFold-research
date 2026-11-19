from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import csv, json, math, hashlib, shutil, os, subprocess, tempfile
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from pypdf import PdfReader
P = Path(__file__).resolve().parents[1]
SOURCE = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding4_v7_final_v1/tables')
for d in ['source_data', 'figures', 'validation']:
    (P / d).mkdir(exist_ok=True)
FILES = ['strict_main_structure.csv', 'strict_main_pairings.csv']
for f in FILES:
    if not (P / 'source_data' / f).exists():
        shutil.copy2(SOURCE / f, P / 'source_data' / f)

def rows(f):
    with (P / 'source_data' / f).open() as h:
        return [r for r in csv.DictReader(h) if r['setting'] == 'standardized']
S = {(r['corpus'], r['category']): r for r in rows(FILES[0])}
T = {(r['corpus'], r['first_group'], r['last_group']): r for r in rows(FILES[1])}
GROUPS = ['higher', 'middle', 'lower', 'outside']
LABELS = ['High', 'Middle', 'Low', 'Outside']
GP = ['#4A2368', '#9470AE', '#C4AFD6', '#BFC5CE']
AF = '#D5281D'
REF = '#131460'
INK = '#18212B'
MUTED = '#58697C'
GRID = '#E4E8ED'
W = 183 * 72 / 25.4
H = 581
for ff, fn in [('Arial.ttf', 'FigArial'), ('Arial Bold.ttf', 'FigArialBold')]:
    pdfmetrics.registerFont(TTFont(fn, release_font_path('/System/Library/Fonts/Supplemental/' + ff)))
name = 'Figure4_compact_legend'
out = P / 'figures'
pdf = canvas.Canvas(str(out / f'{name}.pdf'), pagesize=(W, H))
pdf.setTitle('Figure 4 First–last authorship pairings in international research')
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="183mm" height="{H * 25.4 / 72}mm" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="white"/>']
boxes = []
records = []

def txt(x, y, s, size=7, anchor='start', color=INK, bold=False):
    f = 'FigArialBold' if bold else 'FigArial'
    pdf.setFont(f, size)
    pdf.setFillColor(HexColor(color))
    if anchor == 'middle':
        pdf.drawCentredString(x, H - y, s)
    elif anchor == 'end':
        pdf.drawRightString(x, H - y, s)
    else:
        pdf.drawString(x, H - y, s)
    svg.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" fill="{color}"' + (' font-weight="bold"' if bold else '') + '>' + escape(s) + '</text>')
    w = pdfmetrics.stringWidth(s, f, size)
    left = x - w if anchor == 'end' else x - w / 2 if anchor == 'middle' else x
    boxes.append([s, left, y - size, left + w, y + size * 0.23])

def rotated(x, y, s, size=7.5):
    pdf.saveState()
    pdf.translate(x, H - y)
    pdf.rotate(90)
    pdf.setFont('FigArial', size)
    pdf.setFillColor(HexColor(INK))
    pdf.drawCentredString(0, 0, s)
    pdf.restoreState()
    svg.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{size}" fill="{INK}" transform="rotate(-90 {x} {y})">' + escape(s) + '</text>')

def line(x1, y1, x2, y2, col=GRID, lw=0.5, dash=None):
    pdf.saveState()
    pdf.setStrokeColor(HexColor(col))
    pdf.setLineWidth(lw)
    if dash:
        pdf.setDash(*dash)
    pdf.line(x1, H - y1, x2, H - y2)
    pdf.restoreState()
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{lw}"' + (f' stroke-dasharray="{dash[0]},{dash[1]}"' if dash else '') + '/>')

def rect(x, y, w, h, col):
    pdf.setFillColor(HexColor(col))
    pdf.rect(x, H - y - h, w, h, stroke=0, fill=1)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{col}"/>')

def blend(a, b, t):
    aa = [int(a[i:i + 2], 16) for i in [1, 3, 5]]
    bb = [int(b[i:i + 2], 16) for i in [1, 3, 5]]
    return '#' + ''.join((f'{round(x + (y - x) * t):02X}' for x, y in zip(aa, bb)))

def ribbon(x0, x1, y0, y1, h, col, alpha=0.55):
    dx = (x1 - x0) * 0.43
    q = pdf.beginPath()
    q.moveTo(x0, H - y0)
    q.curveTo(x0 + dx, H - y0, x1 - dx, H - y1, x1, H - y1)
    q.lineTo(x1, H - y1 - h)
    q.curveTo(x1 - dx, H - y1 - h, x0 + dx, H - y0 - h, x0, H - y0 - h)
    q.close()
    pdf.saveState()
    pdf.setFillColor(HexColor(col))
    pdf.setFillAlpha(alpha)
    pdf.drawPath(q, stroke=0, fill=1)
    pdf.restoreState()
    svg.append(f'<path d="M {x0},{y0} C {x0 + dx},{y0} {x1 - dx},{y1} {x1},{y1} L {x1},{y1 + h} C {x1 - dx},{y1 + h} {x0 + dx},{y0 + h} {x0},{y0 + h} Z" fill="{col}" fill-opacity="{alpha}"/>')
CATS = ['same_country_same_institution', 'same_country_different_institutions', 'same_country_institutional_relation_unresolved', 'different_countries']
for cp in ['AF', 'reference']:
    assert math.isclose(sum((float(S[cp, c]['share']) for c in CATS)), 1, abs_tol=1e-09)
    assert math.isclose(sum((float(T[cp, g, h]['observed_share']) for g in GROUPS for h in GROUPS)), 1, abs_tol=1e-09)
for g in GROUPS:
    for h in GROUPS:
        a = float(T['AF', g, h]['observed_minus_expected_pp'])
        r = float(T['reference', g, h]['observed_minus_expected_pp'])
        d = float(T['AF_minus_reference', g, h]['observed_minus_expected_pp'])
        assert math.isclose(a - r, d, abs_tol=1e-10)
txt(18, 23, 'a', 10.5, bold=True)
x0 = 58
ww = 446
for v in [0, 25, 50, 75, 100]:
    x = x0 + ww * v / 100
    line(x, 27, x, 78, GRID, 0.4)
    line(x, 81, x, 83, '#98A7B9', 0.5)
    txt(x, 93, str(v), 6.7, 'middle', MUTED)
line(x0, 81, x0 + ww, 81, '#98A7B9', 0.55)
for cp, y, col in [('AF', 32, AF), ('reference', 62, REF)]:
    txt(49, y + 9, 'AF' if cp == 'AF' else 'non-AF', 7.5, 'end', col)
    colors = [col, blend(col, '#FFFFFF', 0.54), '#BFC5CE', blend(col, '#FFFFFF', 0.86)]
    xx = x0
    for cat, cc in zip(CATS, colors):
        value = float(S[cp, cat]['share'])
        w = ww * value
        rect(xx, y, w, 14, cc)
        if value > 0.04:
            txt(xx + w / 2, y + 9.5, f'{100 * value:.1f}', 7.1, 'middle', '#FFFFFF' if cat == CATS[0] else INK)
        records.append({'panel': 'a', 'corpus': cp, 'category': cat, 'share': value})
        xx += w
    assert abs(xx - x0 - ww) < 1e-08
legend_items = [('Same institution', 0), ('Same country, different institutions', 1), ('Different countries', 3)]
legend_gap = 16
legend_widths = [15 + pdfmetrics.stringWidth(label, 'FigArial', 6.7) for label, k in legend_items]
legend_x = x0 + ww / 2 - (sum(legend_widths) + legend_gap * 2) / 2
legend = []
for (label, k), width in zip(legend_items, legend_widths):
    legend.append((legend_x, 117, label, k))
    legend_x += width + legend_gap
for x, y, label, k in legend:
    for off, col in [(0, AF), (6, REF)]:
        color = '#BFC5CE' if k == 2 else blend(col, '#FFFFFF', [0, 0.54, 0, 0.86][k])
        rect(x + off, y - 5, 5, 5, color)
    txt(x + 15, y, label, 6.7)
txt(x0 + ww / 2, 103, 'Pairing credit (%)', 7.5, 'middle')
txt(18, 149, 'b', 10.5, bold=True)
for cp, xl, xr, col, title in [('AF', 87, 230, AF, 'AF'), ('reference', 332, 475, REF, 'non-AF')]:
    txt((xl + xr + 7) / 2, 150, title, 8, 'middle', col, bold=True)
    txt(xl + 3.5, 165, 'First author', 7, 'middle', MUTED)
    txt(xr + 3.5, 165, 'Last author', 7, 'middle', MUTED)
    M = [[float(T[cp, g, h]['observed_share']) for h in GROUPS] for g in GROUPS]
    margins = [[sum(row) for row in M], [sum((M[i][j] for i in range(4))) for j in range(4)]]
    tops = []
    height = 120
    gap = 7
    start = 175
    for side in range(2):
        yy = start
        arr = []
        for v in margins[side]:
            arr.append(yy)
            yy += height * v + gap
        tops.append(arr)
    usedL = [0] * 4
    usedR = [0] * 4
    for i, g in enumerate(GROUPS):
        for j, h in enumerate(GROUPS):
            v = M[i][j]
            hh = v * height
            color = col
            if i == 3 or j == 3:
                color = '#BFC5CE'
            ribbon(xl + 7, xr, tops[0][i] + usedL[i], tops[1][j] + usedR[j], hh, color)
            usedL[i] += hh
            usedR[j] += hh
            records.append({'panel': 'b', 'corpus': cp, 'first_group': g, 'last_group': h, 'observed_share': v})
    for side, x in [(0, xl), (1, xr)]:
        for i in range(4):
            hh = margins[side][i] * height
            rect(x, tops[side][i], 7, hh, GP[i])
            txt(x - 4 if side == 0 else x + 11, tops[side][i] + hh / 2 + 2.2, LABELS[i], 6.8, 'end' if side == 0 else 'start')
    txt((xl + xr + 7) / 2, start + height * M[0][0] / 2 + 2.5, f'{100 * M[0][0]:.1f}%', 8, 'middle', INK)
txt(18, 348, 'c', 10.5, bold=True)
V = 2.7
NEG = REF
ZERO = '#F7F7F5'
POS = AF

def heatcol(v):
    return blend(ZERO, POS if v >= 0 else NEG, min(abs(v) / V, 1))
cell = 36
top = 368
xs = [94, 346]
for cp, x, title, sub in [('AF', xs[0], 'AF: observed − expected', ''), ('AF_minus_reference', xs[1], 'AF − non-AF', 'Difference in observed − expected')]:
    txt(x + 2 * cell, 347, title, 8, 'middle')
    if sub:
        txt(x + 2 * cell, 359, sub, 6.6, 'middle', MUTED)
    else:
        txt(x + 2 * cell, 359, 'Deviation from team-composition expectation', 6.6, 'middle', MUTED)
    for i, g in enumerate(GROUPS):
        y = top + i * cell
        rect(x - 3.5, y + 3, 1.6, cell - 6, GP[i])
        txt(x - 7, y + cell / 2 + 2.5, LABELS[i], 7, 'end')
        for j, h in enumerate(GROUPS):
            r = T[cp, g, h]
            v = float(r['observed_minus_expected_pp'])
            xx = x + j * cell
            rect(xx, y, cell, cell, heatcol(v))
            label = '0.00' if abs(v) < 0.005 else f'{v:+.2f}'
            txt(xx + cell / 2, y + cell / 2 + 2.5, label, 7.3, 'middle', '#FFFFFF' if abs(v) > 1.75 else INK)
            records.append({'panel': 'c', 'corpus': cp, 'first_group': g, 'last_group': h, 'value_pp': v, 'ci_low': float(r['deviation_ci_low'] if cp == 'AF' else r['ci_low']), 'ci_high': float(r['deviation_ci_high'] if cp == 'AF' else r['ci_high'])})
    for k in range(5):
        line(x + k * cell, top, x + k * cell, top + 4 * cell, '#FFFFFF', 0.6)
        line(x, top + k * cell, x + 4 * cell, top + k * cell, '#FFFFFF', 0.6)
    for j in range(4):
        rect(x + j * cell + 3, top + 4 * cell + 2, cell - 6, 1.6, GP[j])
        txt(x + (j + 0.5) * cell, top + 4 * cell + 13, LABELS[j], 7, 'middle', MUTED)
rotated(26, 440, 'First-author national output group', 7.5)
txt(292, 540, 'Last-author national output group', 7.5, 'middle')
cbx = 164
cbw = 254
cby = 548
cbh = 5
for k in range(300):
    rect(cbx + cbw * k / 300, cby, cbw / 300 + 0.03, cbh, heatcol(-V + 2 * V * (k + 0.5) / 300))
for v in [-2, -1, 0, 1, 2]:
    x = cbx + cbw * (v + V) / (2 * V)
    line(x, cby + cbh, x, cby + cbh + 2, '#98A7B9', 0.45)
    txt(x, 563, str(v), 6.5, 'middle', MUTED)
txt(292, 573, 'Deviation or difference in deviation (pp)', 7, 'middle')
bad = [b for b in boxes if not (0 <= b[1] < b[3] <= W and 0 <= b[2] < b[4] <= H)]
assert not bad, bad
assert len(records) == 72
pdf.showPage()
pdf.save()
svg.append('</svg>')
(out / f'{name}.svg').write_text('\n'.join(svg))
assert len(PdfReader(out / f'{name}.pdf').pages) == 1
(P / 'validation/plotted_values.json').write_text(json.dumps(records, indent=2))
(P / 'validation/verification.json').write_text(json.dumps({'all_values_from_standardized_source': True, 'structure_and_group_shares_sum_to_one': True, 'direct_contrasts_match_saved_AF_minus_reference_estimates': True, 'all_16_group_pairs_retained': True, 'unknown_institution_credit_retained': True, 'same_color_scale_for_both_heatmaps': [-V, V], 'heatmap_colors_encode_sign_not_corpus': True, 'text_within_canvas': True, 'size_mm': [183, H * 25.4 / 72], 'source_hashes': {f: hashlib.sha256((P / 'source_data' / f).read_bytes()).hexdigest() for f in FILES}}, indent=2))
with (P / 'source_data/Figure4_heatmaps.csv').open('w') as h:
    rr = [r for r in records if r['panel'] == 'c']
    w = csv.DictWriter(h, fieldnames=list(rr[0]))
    w.writeheader()
    w.writerows(rr)
caption = 'Figure 4 | First–last authorship pairings in international research.\nThe cohort, common support and weights are identical to Fig. 3.\na, Fractional pairing credit by country and institutional correspondence. AF is red and non-AF blue; shades distinguish categories. Same-institution pairs share a country and known institution. Same-country pairings with unresolved institutional correspondence remain included in the totals (AF, 0.10%; non-AF, 0.07%).\nb, Observed pairings between national output groups defined using 2015–2019 publications, with first authors on the left and last authors on the right. Purple shades identify output groups; ribbons are red for AF, blue for non-AF and grey for pairings involving Outside. Ribbon widths represent fractional shares, summing to 100% within each corpus; labels show high–high shares. Within-group pairings may involve different countries.\nc, AF observed-minus-expected shares (left) and the AF–non-AF difference in these deviations (right). Expectations derive from uniformly selecting two distinct authors from each observed team. Both matrices share a zero-centered scale in percentage points: red indicates positive values and blue negative values. Conditional 95% whole-study bootstrap intervals for the direct higher–higher and lower–lower contrasts include zero. Full estimates and intervals are reported in Supplementary Table S10 (Methods M7).\n'
(P / 'caption.txt').write_text(caption)
(P / 'README.txt').write_text('Figure 4 revision: panel a legend shortened; panel b observed pairings retained; panel c now shows AF deviations and directly estimated AF-minus-non-AF deviations. All 16 pairs are included. No estimates or uncertainty intervals were recomputed. Original standardized non-AF deviations and all joint intervals remain in source_data/strict_main_pairings.csv. The historical upstream package calls this pairing figure Figure5; the current manuscript figure number is Figure4. Rebuild with code/build_figure4.py using Python, reportlab, Pillow and pypdf.\n')
with tempfile.TemporaryDirectory(prefix='figure4_render_') as temp:
    t = Path(temp)
    (t / 'cache').mkdir()
    (t / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>/System/Library/Fonts/Supplemental</dir><cachedir>' + str(t / 'cache') + '</cachedir></fontconfig>')
    env = os.environ.copy()
    env['FONTCONFIG_FILE'] = str(t / 'fonts.conf')
    binary = release_executable('pdftoppm')
    subprocess.run([binary, '-r', '600', '-singlefile', '-png', str(out / f'{name}.pdf'), str(out / f'{name}_600dpi')], env=env, check=True, timeout=60)
with Image.open(out / f'{name}_600dpi.png') as im:
    rgb = im.convert('RGB')
    rgb.save(out / f'{name}_600dpi.png', dpi=(600, 600))
    rgb.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(out / f'{name}_preview.png')
print(json.dumps({'figure': str(out / f'{name}.pdf'), 'plotted_records': len(records), 'heatmap_cells': 32}))
