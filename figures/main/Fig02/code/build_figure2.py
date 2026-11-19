from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Rebuild Figure 2 with a shared-axis repeat-publication comparison.
All estimates, counts and reference draws are frozen; no fits or simulations are rerun.
Requires numpy, reportlab, Pillow, pypdf and Poppler.
"""
from pathlib import Path
import csv, json, math, hashlib, os, subprocess, tempfile
from xml.sax.saxutils import escape
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from pypdf import PdfReader
P = Path(__file__).resolve().parents[1]

def read(name):
    with (P / 'source_data' / name).open(newline='') as f:
        return list(csv.DictReader(f))
A = read('Fig2a_cumulative.csv')
B = sorted(read('Fig2b_ratio.csv'), key=lambda r: int(r['year']))
D = read('entry_activities.csv')
R = read('repeat_reference.csv')
E = {r['group']: r for r in R if r['variant'] == 'primary_entry_conditioned'}
G = read('Fig2d_benchmark_summary.csv')[0]
F = {r['group']: r for r in read('Fig2e_growth_components.csv') if r['context'] == 'All'}
T = sorted(read('annual_gap_reference.csv'), key=lambda r: int(r['year']))
assert [int(r['year']) for r in T] == [int(r['year']) for r in B]
assert np.allclose([float(r['observed_G_pp']) for r in T], [float(r['G_pp']) for r in B], rtol=0, atol=1e-12)
assert math.isclose(float(T[-1]['analytic_expected_G_pp']) - float(T[0]['analytic_expected_G_pp']), float(G['expected_delta_G']), abs_tol=1e-12)
draws = np.array([float(r['delta_G_pp']) for r in read('Fig2d_benchmark_draws.csv')])
assert len(draws) == 5000 and np.isclose(draws.mean(), float(G['simulated_mean_delta_G']))
assert np.isclose(float(B[-1]['G_pp']) - float(B[0]['G_pp']), float(G['actual_delta_G']))
for r in B:
    assert np.isclose(float(r['annual_L_coverage_pct']) / float(r['annual_H_coverage_pct']), float(r['R']))
    assert np.isclose(float(r['annual_H_coverage_pct']) - float(r['annual_L_coverage_pct']), float(r['G_pp']))
INK, MUTED, GRID = ('#11151C', '#657183', '#E9EEF4')
COL = {'L': '#5B96C9', 'M': '#2F8B75', 'H': '#173F82'}
NAME = {'L': 'Lower', 'M': 'Middle', 'H': 'Higher'}
for f, n in [('Arial.ttf', 'FigureArial'), ('Arial Bold.ttf', 'FigureArialBold')]:
    p = Path('/System/Library/Fonts/Supplemental') / f
    if p.exists():
        pdfmetrics.registerFont(TTFont(n, release_font_path(str(p))))
FONT = 'FigureArial' if 'FigureArial' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
BOLD = 'FigureArialBold' if 'FigureArialBold' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'
W, H = (183 * 72 / 25.4, 150 * 72 / 25.4)
name = 'Figure2_unframed'
out = P / 'figures'
pdf = canvas.Canvas(str(out / f'{name}.pdf'), pagesize=(W, H))
pdf.setTitle('Figure 2 Institutional coverage and subsequent participation')
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="183mm" height="150mm" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="white"/>']
boxes = []
registry = []

def text(x, y, s, size=7, anchor='start', color=INK, bold=False):
    font = BOLD if bold else FONT
    pdf.saveState()
    pdf.setFillColor(HexColor(color))
    pdf.setFont(font, size)
    if anchor == 'middle':
        pdf.drawCentredString(x, H - y, s)
    elif anchor == 'end':
        pdf.drawRightString(x, H - y, s)
    else:
        pdf.drawString(x, H - y, s)
    pdf.restoreState()
    svg.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" fill="{color}"' + (' font-weight="bold"' if bold else '') + '>' + escape(s) + '</text>')
    w = pdfmetrics.stringWidth(s, font, size)
    left = x - w if anchor == 'end' else x - w / 2 if anchor == 'middle' else x
    boxes.append((s, left, y - size, left + w, y + size * 0.22))

def line(x1, y1, x2, y2, color=MUTED, lw=0.6, dash=None):
    pdf.saveState()
    pdf.setStrokeColor(HexColor(color))
    pdf.setLineWidth(lw)
    if dash:
        pdf.setDash(*dash)
    pdf.line(x1, H - y1, x2, H - y2)
    pdf.restoreState()
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{lw}"' + (f' stroke-dasharray="{dash[0]},{dash[1]}"' if dash else '') + '/>')

def point(x, y, col, shape='o', filled=True, r=2.3, lw=0.7):
    pdf.saveState()
    pdf.setStrokeColor(HexColor(col))
    pdf.setFillColor(HexColor(col if filled else '#FFFFFF'))
    pdf.setLineWidth(lw)
    if shape == 'o':
        pdf.circle(x, H - y, r, stroke=1, fill=1)
        svg.append(f'''<circle cx="{x}" cy="{y}" r="{r}" stroke="{col}" stroke-width="{lw}" fill="{(col if filled else '#FFFFFF')}"/>''')
    else:
        v = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
        path = pdf.beginPath()
        path.moveTo(v[0][0], H - v[0][1])
        for xx, yy in v[1:]:
            path.lineTo(xx, H - yy)
        path.close()
        pdf.drawPath(path, stroke=1, fill=1)
        svg.append('<polygon points="' + ' '.join((f'{xx},{yy}' for xx, yy in v)) + f'''" stroke="{col}" stroke-width="{lw}" fill="{(col if filled else '#FFFFFF')}"/>''')
    pdf.restoreState()

def rect(x, y, w, h, fill, stroke=None, lw=0.4):
    pdf.saveState()
    pdf.setFillColor(HexColor(fill))
    pdf.setLineWidth(lw)
    if stroke:
        pdf.setStrokeColor(HexColor(stroke))
    pdf.rect(x, H - y - h, w, h, stroke=bool(stroke), fill=1)
    pdf.restoreState()
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"' + (f' stroke="{stroke}" stroke-width="{lw}"' if stroke else '') + '/>')

def polygon(vertices, color):
    path = pdf.beginPath()
    path.moveTo(vertices[0][0], H - vertices[0][1])
    for xx, yy in vertices[1:]:
        path.lineTo(xx, H - yy)
    path.close()
    pdf.saveState()
    pdf.setFillColor(HexColor(color))
    pdf.setStrokeColor(HexColor(color))
    pdf.drawPath(path, stroke=0, fill=1)
    pdf.restoreState()
    svg.append('<polygon points="' + ' '.join((f'{xx},{yy}' for xx, yy in vertices)) + f'" fill="{color}"/>')

def groupmark(x, y, g, r=2.35):
    color = COL[g]
    if g == 'L':
        point(x, y, color, 'o', True, r, 0.55)
    elif g == 'M':
        rect(x - r, y - r, 2 * r, 2 * r, color)
    else:
        polygon([(x, y - r * 1.1), (x + r, y + r * 0.8), (x - r, y + r * 0.8)], color)

def vtext(x, y, s, size=7.5):
    pdf.saveState()
    pdf.setFillColor(HexColor(INK))
    pdf.setFont(FONT, size)
    pdf.translate(x, H - y)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, s)
    pdf.restoreState()
    svg.append(f'<text transform="translate({x},{y}) rotate(-90)" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{size}" fill="{INK}">' + escape(s) + '</text>')
    w = pdfmetrics.stringWidth(s, FONT, size)
    boxes.append((s, x - size, y - w / 2, x + size * 0.22, y + w / 2))

def axes(x, top, w, h, xlim, ylim, xticks, yticks, xformat=None, gridx=False, gridy=True, tickfont=7, xtickpad=12):
    X = lambda v: x + (float(v) - xlim[0]) / (xlim[1] - xlim[0]) * w
    Y = lambda v: top + h - (float(v) - ylim[0]) / (ylim[1] - ylim[0]) * h
    for v in yticks:
        yy = Y(v)
        if gridy:
            line(x, yy, x + w, yy, GRID, 0.4)
        line(x - 2.2, yy, x, yy, '#9CAABF', 0.5)
        text(x - 4.5, yy + 2.2, f'{v:g}', tickfont, 'end', MUTED)
    for v in xticks:
        xx = X(v)
        if gridx:
            line(xx, top, xx, top + h, GRID, 0.4)
        line(xx, top + h, xx, top + h + 2.3, '#9CAABF', 0.5)
        lab = xformat(v) if xformat else f'{v:g}'
        text(xx, top + h + xtickpad, lab, tickfont, 'middle', MUTED)
    line(x, top, x, top + h, '#9CAABF', 0.55)
    line(x, top + h, x + w, top + h, '#9CAABF', 0.55)
    return (X, Y)

def arrow(x1, y1, x2, y2, color='#8D99A9', lw=1):
    dx, dy = (x2 - x1, y2 - y1)
    length = math.hypot(dx, dy)
    ux, uy = (dx / length, dy / length)
    sx, sy = (x1 + ux * 4, y1 + uy * 4)
    ex, ey = (x2 - ux * 4.2, y2 - uy * 4.2)
    line(sx, sy, ex, ey, color, lw)
    polygon([(ex, ey), (ex - ux * 4 - uy * 1.6, ey - uy * 4 + ux * 1.6), (ex - ux * 4 + uy * 1.6, ey - uy * 4 - ux * 1.6)], color)

def panel_frame(x, y, w, h):
    col = '#DDE4EA'
    lw = 0.5
    pdf.saveState()
    pdf.setStrokeColor(HexColor(col))
    pdf.setLineWidth(lw)
    pdf.rect(x, H - y - h, w, h, stroke=1, fill=0)
    pdf.restoreState()
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
for g, x in [('L', 167), ('M', 245), ('H', 323)]:
    line(x - 8, 18, x + 6, 18, COL[g], 1.25)
    groupmark(x - 1, 18, g, 2.15)
    text(x + 12, 20.5, NAME[g], 7.8)
text(13, 45, 'a', 10.5, bold=True)
XA, YA = axes(50, 54, 190, 134, (2019.85, 2025.8), (0, 43), list(range(2020, 2026)), [0, 10, 20, 30, 40], tickfont=6.5)
vtext(18, 121, 'Cumulative coverage (%)', 7.3)
text(145, 212, 'Year', 7.2, 'middle')
for g in ['H', 'M', 'L']:
    q = sorted([r for r in A if r['group'] == g], key=lambda r: int(r['year']))
    xx = [int(r['year']) for r in q]
    yy = [float(r['coverage_pct']) for r in q]
    assert xx == list(range(2020, 2026)) and np.allclose(yy, [100 * float(r['C']) for r in q])
    for i in range(1, len(q)):
        line(XA(xx[i - 1]), YA(yy[i - 1]), XA(xx[i]), YA(yy[i]), COL[g], 1.25)
    for x, y in zip(xx, yy):
        groupmark(XA(x), YA(y), g, 2.0)
    text(XA(xx[-1]) + 5, YA(yy[-1]) + 2.2, f'{yy[-1]:.2f}%', 7.2, color=COL[g])
    registry.append({'panel': 'a', 'group': g, 'x': xx, 'y': yy})
pdf.saveState()
pdf.setFillColor(HexColor('#FFFFFF'))
pdf.setStrokeColor(HexColor('#B8C6D9'))
pdf.setLineWidth(0.55)
pdf.roundRect(65, H - 64 - 50, 82, 50, 1.5, stroke=1, fill=1)
pdf.restoreState()
svg.append('<rect x="65" y="64" width="82" height="50" rx="1.5" fill="#FFFFFF" stroke="#B8C6D9" stroke-width="0.55"/>')
text(68, 73, 'Lower', 6.8)
XI, YI = axes(77, 80, 61, 22, (2019.85, 2025.2), (0, 2.5), [2020, 2022, 2025], [0, 1, 2], gridy=True, tickfont=5.9, xtickpad=9)
q = sorted([r for r in A if r['group'] == 'L'], key=lambda r: int(r['year']))
for i, r in enumerate(q):
    x, y = (int(r['year']), float(r['coverage_pct']))
    if i:
        line(XI(int(q[i - 1]['year'])), YI(float(q[i - 1]['coverage_pct'])), XI(x), YI(y), COL['L'], 0.9)
    groupmark(XI(x), YI(y), 'L', 1.6)
registry.append({'panel': 'a_inset', 'group': 'L', 'x': [int(r['year']) for r in q], 'y': [float(r['coverage_pct']) for r in q], 'x_limits': [2019.85, 2025.2], 'y_limits': [0, 2.5], 'scale': 'linear'})
text(280, 45, 'b', 10.5, bold=True)
years = [int(r['year']) for r in B]
ratios = [float(r['R']) for r in B]
gaps = [float(r['G_pp']) for r in B]
expected_gap = [float(r['analytic_expected_G_pp']) for r in T]
ref_lo = [float(r['reference_low_pp']) for r in T]
ref_hi = [float(r['reference_high_pp']) for r in T]
text(321, 51, f'R = {ratios[0]:.4f} → {ratios[-1]:.4f}', 7.1, color='#526278')
XRT, YRT = axes(321, 58, 169, 38, (2020.75, 2025.5), (0, 0.05), [], [0, 0.025, 0.05], gridy=True, tickfont=6.5)
for year in years:
    line(XRT(year), 58, XRT(year), 96, GRID, 0.35)
for i in range(1, len(years)):
    line(XRT(years[i - 1]), YRT(ratios[i - 1]), XRT(years[i]), YRT(ratios[i]), '#526278', 1.15)
for i, (year, val) in enumerate(zip(years, ratios)):
    point(XRT(year), YRT(val), '#526278', 'o', i in [0, len(years) - 1], 2.0, 0.75)
text(291, 80.0, 'R', 8.0, 'middle')
text(321, 110, f'G = {gaps[0]:.2f} → {gaps[-1]:.2f} pp', 7.1, color='#526278')
line(321, 119, 333, 119, INK, 1.1)
point(327, 119, INK, 'o', True, 1.4, 0.4)
text(338, 121, 'Observed', 6.6)
line(386, 119, 398, 119, '#657183', 1.0, (3, 2))
text(403, 121, 'Expected', 6.6)
XGT, YGT = axes(321, 133, 169, 55, (2020.75, 2025.5), (0, 30), years, [0, 10, 20, 30], lambda v: str(int(v)), gridx=True, gridy=True, tickfont=6.5)
polygon([(XGT(y), YGT(v)) for y, v in zip(years, ref_lo)] + [(XGT(y), YGT(v)) for y, v in reversed(list(zip(years, ref_hi)))], '#E9EEF4')
for i in range(1, len(years)):
    line(XGT(years[i - 1]), YGT(expected_gap[i - 1]), XGT(years[i]), YGT(expected_gap[i]), '#657183', 1.1, (3, 2))
    line(XGT(years[i - 1]), YGT(gaps[i - 1]), XGT(years[i]), YGT(gaps[i]), INK, 1.2)
for i, (year, val) in enumerate(zip(years, gaps)):
    point(XGT(year), YGT(val), INK, 'o', i in [0, len(years) - 1], 1.95, 0.75)
text(291, 158.5, 'G', 8.0, 'middle')
text(291, 168, '(pp)', 6.5, 'middle', MUTED)
text(405.5, 212, 'Publication year', 7.1, 'middle')
text(XGT(years[-1]) + 4, YGT(expected_gap[-1]) - 3, f'{expected_gap[-1]:.2f}', 6.7, color=MUTED)
text(XGT(years[-1]) + 4, YGT(gaps[-1]) + 7, f'{gaps[-1]:.2f}', 6.7, bold=True)
registry.append({'panel': 'b', 'year': years, 'ratio': ratios, 'gap': gaps})
registry.append({'panel': 'b_annual_reference', 'year': years, 'observed_gap_pp': gaps, 'expected_gap_pp': expected_gap, 'reference_low_pp': ref_lo, 'reference_high_pp': ref_hi})
assert math.isclose(expected_gap[-1] - expected_gap[0], float(G['expected_delta_G']), abs_tol=1e-12)
text(21, 234, 'c', 10.5, bold=True)
left, width = (101, 144)
cw = width / 3
for j, g in enumerate(['L', 'M', 'H']):
    center = left + (j + 0.5) * cw
    text(center, 265, NAME[g], 7.3, 'middle', COL[g], True)
    line(left + j * cw + 3, 270, left + (j + 1) * cw - 3, 270, COL[g], 1.2)
labels = [['Precomputed', 'structures'], ['Prediction runs'], ['Method / tool', 'development'], ['Evaluation /', 'validation']]
for i, label in enumerate(labels):
    baseline = 283 + i * 33
    if len(label) == 1:
        text(94, baseline + 4, label[0], 6.4, 'end')
    else:
        text(94, baseline, label[0], 6.4, 'end')
        text(94, baseline + 8, label[1], 6.4, 'end')
    for j, g in enumerate(['L', 'M', 'H']):
        r = next((r for r in D if r['group'] == g and int(r['activity_order']) == i + 1))
        value = float(r['supported_pct'])
        n, d = (int(r['Y']), int(r['D']))
        assert np.isclose(value, 100 * n / d)
        center = left + (j + 0.5) * cw
        text(center, baseline, f'{value:.1f}', 8.5, 'middle')
        text(center, baseline + 10, f'{n:,} / {d:,}', 6.8, 'middle', MUTED)
        registry.append({'panel': 'c_activity', 'group': g, 'activity_order': i + 1, 'supported_pct': value})
    if i < 3:
        line(left, baseline + 21, 245, baseline + 21, '#E0E7F0', 0.4)
text(280, 234, 'd', 10.5, bold=True)
XR, YR = axes(314, 268, 187, 119, (0, 65), (0, 3), [0, 20, 40, 60], [], gridx=True, gridy=False, tickfont=6.6)
text(407.5, 416, 'Repeat publication (%)', 7.1, 'middle')
values = []
for row, g in zip([281, 324, 367], ['L', 'M', 'H']):
    r = E[g]
    col = COL[g]
    text(306, row + 1.8, NAME[g], 7.3, 'end', col, True)
    text(306, row + 11.0, f"n = {int(r['N']):,}", 6.6, 'end', MUTED)
    ob, ex, up, lo, hi = map(float, [r['observed_pct'], r['expected_pct'], r['registered_possible_upper_pct'], r['reference_lower_pct'], r['reference_upper_pct']])
    delta = ob - ex
    assert math.isclose(delta, float(r['observed_minus_expected_pp']), abs_tol=1e-12)
    assert lo <= ex <= hi and ob <= up
    obs_y, ref_y = (row - 5.5, row + 5.5)
    line(XR(lo), ref_y, XR(hi), ref_y, col, 1.0)
    for val in [lo, hi]:
        line(XR(val), ref_y - 2.6, XR(val), ref_y + 2.6, col, 0.8)
    point(XR(ex), ref_y, col, 'D', False, 1.2, 0.75)
    secondary = obs_y - 6.0
    line(XR(ob), obs_y, XR(ob), secondary, col, 0.6, (1.2, 1.6))
    line(XR(ob), secondary, XR(up), secondary, col, 0.6, (1.2, 1.6))
    point(XR(up), secondary, col, 'o', False, 1.65, 0.65)
    point(XR(ob), obs_y, col, 'o', True, 2.15, 0.5)
    text(XR(ob) - 5, obs_y + 2.2, f'{ob:.1f}', 7.2, 'end', INK, True)
    text(XR(hi) + 4, ref_y + 2.2, f'{ex:.1f}', 7.0, 'start', INK)
    assert obs_y + 2.4 < ref_y - 2.6
    assert secondary + 1.65 < obs_y - 2.15
    assert XR(lo) < XR(ex) < XR(hi)
    values.append({'group': g, 'N': int(r['N']), 'confirmed': int(r['confirmed']), 'observed_pct': ob, 'expected_pct': ex, 'reference_lower_pct': lo, 'reference_upper_pct': hi, 'including_unresolved_pct': up, 'observed_minus_expected_pp': delta})
point(317, 245, INK, 'o', True, 1.8, 0.45)
text(325, 247, 'Observed', 7.0)
line(380, 245, 393, 245, INK, 0.8)
line(380, 242.4, 380, 247.6, INK, 0.65)
line(393, 242.4, 393, 247.6, INK, 0.65)
point(386.5, 245, INK, 'D', False, 1.2, 0.65)
text(399, 247, 'Expected', 7.0)
for v in values:
    registry.append({'panel': 'd_repeat', 'group': v['group'], 'observed_pct': v['observed_pct'], 'reference_pct': v['expected_pct'], 'reference_low': v['reference_lower_pct'], 'reference_high': v['reference_upper_pct'], 'including_unresolved_pct': v['including_unresolved_pct']})
assert all((0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H for s, x0, y0, x1, y1 in boxes)), [b for b in boxes if b[1] < 0 or b[2] < 0 or b[3] > W or (b[4] > H)]
assert len(registry) == 21
pdf.showPage()
pdf.save()
svg.append('</svg>')
(out / f'{name}.svg').write_text('\n'.join(svg))
reader = PdfReader(out / f'{name}.pdf')
assert len(reader.pages) == 1 and '/XObject' not in reader.pages[0]['/Resources']
(P / 'validation/plotted_values.json').write_text(json.dumps(registry, indent=2) + '\n')
(P / 'validation/repeat_values.json').write_text(json.dumps(values, indent=2) + '\n')
(P / 'validation/style_and_layout.json').write_text(json.dumps({'size_mm': [183, 150], 'palette': COL, 'layout': 'two by two; a/b first row, c/d second row', 'source_csv_hashes': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (P / 'source_data').glob('*.csv')}, 'panel_count': 4, 'panel_frames': None, 'c_d_titles_removed': True, 'b_ratio': 'observed only, upper plot', 'b_gap': 'observed and analytic expected on one axis', 'b_reference_shading': 'pointwise central 95% conditional allocation ranges; not confidence intervals', 'b_reference_source': 'annual_gap_reference.csv; frozen primary All-country results', 'repeat_orientation': 'horizontal', 'repeat_axis_limits_pct': [0, 65], 'repeat_observed_expected_labels': 'observed bold left of upper dot; expected right of lower range', 'repeat_track_offsets_pt': {'observed': -5.5, 'expected': 5.5, 'unresolved': -11.5}, 'repeat_axis_width_pt': 187, 'repeat_expected_marker_radius_pt': 1.2, 'repeat_interval_lengths_unchanged': True, 'repeat_unresolved': 'open circles with dotted connectors', 'activity_counts_displayed': 'supported / assessable', 'activity_counts_font_pt': 6.8, 'retained_frozen_reference_allocations': 5000, 'numeric_estimates_changed': False, 'all_text_inside_canvas': True, 'vector_text_and_geometry': True}, indent=2) + '\n')
with tempfile.TemporaryDirectory(prefix='figure2_integrated_') as td:
    t = Path(td)
    (t / 'cache').mkdir()
    (t / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>/System/Library/Fonts/Supplemental</dir><cachedir>' + str(t / 'cache') + '</cachedir></fontconfig>')
    env = os.environ.copy()
    env['FONTCONFIG_FILE'] = str(t / 'fonts.conf')
    binary = release_executable('pdftoppm')
    for dpi, prefix in [(600, out / f'{name}_600dpi'), (200, P / 'validation/pdf_render')]:
        subprocess.run([binary, '-r', str(dpi), '-singlefile', '-png', str(out / f'{name}.pdf'), str(prefix)], env=env, check=True, timeout=45)
with Image.open(out / f'{name}_600dpi.png') as im:
    rgb = im.convert('RGB')
    rgb.save(out / f'{name}_600dpi.png', dpi=(600, 600))
    rgb.resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(out / f'{name}_preview.png')
print('Saved Figure 2 without outer frames or c/d subtitles; all estimates unchanged.')
