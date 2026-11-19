from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os
O = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(O / 'mpl_config'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, PathPatch, Patch, Arc, Wedge, Rectangle
from matplotlib.path import Path as MPath
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgba
import numpy as np
import pandas as pd
import json
G = ['Lower', 'Middle', 'Higher', 'Other']
COL = {'Lower': '#5799CF', 'Middle': '#26917C', 'Higher': '#183F85', 'Other': '#A3ACBA'}
AF = '#DF2317'
REF = '#191660'
INK = '#17202D'
MUTED = '#52627B'
GRID = '#E6ECF4'
plt.rcParams.update({'font.family': release_font_family(), 'font.size': 9, 'axes.labelsize': 9, 'axes.titlesize': 11, 'axes.linewidth': 0.6, 'axes.edgecolor': '#9CABC0', 'xtick.color': MUTED, 'ytick.color': MUTED, 'xtick.labelsize': 8, 'ytick.labelsize': 8, 'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none', 'savefig.facecolor': 'white'})

def tidy(ax):
    for s in ['top', 'right', 'left']:
        ax.spines[s].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.tick_params(axis='x', length=3, width=0.6)
    ax.set_axisbelow(True)

def val(x):
    return f'{x:.2f}' if x < 1 else f'{x:.1f}'

def network_square(ax, corpus, data):
    color = AF if corpus == 'AF' else REF
    positions = {'Lower': (-0.7, 0.58), 'Middle': (0.7, 0.58), 'Higher': (0.7, -0.58), 'Other': (-0.7, -0.58)}
    edge = {(r.group_1, r.group_2): r.share_pct for r in data.itertuples() if r.corpus == corpus}

    def get(g, h):
        return edge[g, h] if (g, h) in edge else edge[h, g]

    def width(x):
        return 0.3 + 5.3 * np.sqrt(x / 100)
    for i, g in enumerate(G):
        x, y = positions[g]
        sgn = -1 if x < 0 else 1
        v = get(g, g)
        verts = [(x, y + 0.07), (x + sgn * 0.62, y + 0.55), (x + sgn * 0.62, y - 0.55), (x, y - 0.07)]
        ax.add_patch(PathPatch(MPath(verts, [MPath.MOVETO, *[MPath.CURVE4] * 3]), lw=width(v), edgecolor=color, facecolor='none', alpha=0.58, capstyle='round'))
        ax.text(x + sgn * 0.58, y, val(v), ha='center', va='center', fontsize=9, color=INK, bbox=dict(facecolor='white', edgecolor='none', pad=1.5))
    for i, g in enumerate(G):
        for h in G[i + 1:]:
            x1, y1 = positions[g]
            x2, y2 = positions[h]
            v = get(g, h)
            if abs(x1 - x2) > 0.5 and abs(y1 - y2) > 0.5:
                if set([g, h]) == set(['Lower', 'Higher']):
                    verts = [(x1, y1), (-0.38, 0.2), (0.38, -0.2), (x2, y2)]
                    label = (-0.16, 0.18)
                else:
                    verts = [(x1, y1), (0.38, 0.2), (-0.38, -0.2), (x2, y2)]
                    label = (-0.22, -0.21)
                ax.add_patch(PathPatch(MPath(verts, [MPath.MOVETO, *[MPath.CURVE4] * 3]), lw=width(v), edgecolor=color, facecolor='none', alpha=0.58))
            else:
                ax.plot([x1, x2], [y1, y2], lw=width(v), color=color, alpha=0.58, zorder=1)
                label = ((x1 + x2) / 2, (y1 + y2) / 2)
            ax.text(*label, val(v), ha='center', va='center', fontsize=9, color=INK, bbox=dict(facecolor='white', edgecolor='none', pad=1.5), zorder=4)
    for g, (x, y) in positions.items():
        ax.add_patch(Circle((x, y), 0.1, facecolor=COL[g], edgecolor='white', lw=1.2, zorder=5))
        ax.text(x, y + (0.21 if y > 0 else -0.23), g, ha='center', va='center', color=COL[g], weight='bold', fontsize=9.5)
    ax.set_xlim(-1.55, 1.55)
    ax.set_ylim(-1.05, 1.05)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', pad=6)

def network_circular(ax, corpus, data):
    color = AF if corpus == 'AF' else REF
    angles = {'Lower': 90.0, 'Middle': 0.0, 'Higher': -90.0, 'Other': 180.0}
    positions = {g: np.array([np.cos(np.deg2rad(t)), np.sin(np.deg2rad(t))]) * 0.86 for g, t in angles.items()}
    edge = {(r.group_1, r.group_2): r.share_pct for r in data.itertuples() if r.corpus == corpus}

    def get(g, h):
        return edge[g, h] if (g, h) in edge else edge[h, g]

    def width(x):
        return 0.3 + 5.3 * np.sqrt(x / 100)
    ax.add_patch(Circle((0, 0), 1.035, facecolor='none', edgecolor=GRID, lw=0.7, zorder=0))
    for g, t in angles.items():
        ax.add_patch(Arc((0, 0), 2.07, 2.07, theta1=t - 34, theta2=t + 34, color=COL[g], lw=2.7, zorder=2))
        ax.add_patch(Arc((0, 0), 1.72, 1.72, theta1=t - 26, theta2=t + 26, color=color, lw=width(get(g, g)), alpha=0.58, capstyle='round', zorder=1))
        ux, uy = (np.cos(np.deg2rad(t)), np.sin(np.deg2rad(t)))
        if abs(ux) > 0.5:
            ax.text(1.48 * ux, -0.115, val(get(g, g)), ha='center', va='center', fontsize=9, color=INK)
            ax.text(1.48 * ux, 0.115, g, ha='center', va='center', fontsize=9.3, color=COL[g], fontweight='bold')
        else:
            ax.text(1.18 * ux, 1.18 * uy, val(get(g, g)), ha='center', va='center', fontsize=9, color=INK)
            ax.text(1.43 * ux, 1.43 * uy, g, ha='center', va='center', fontsize=9.3, color=COL[g], fontweight='bold')
    for i, g in enumerate(G):
        for h in G[i + 1:]:
            p0, p3 = (positions[g], positions[h])
            if set([g, h]) == {'Lower', 'Higher'}:
                p1 = np.array([0.0, 0.35])
                p2 = np.array([0.0, -0.35])
                label = (0.0, 0.22)
            elif set([g, h]) == {'Middle', 'Other'}:
                p1 = np.array([0.35, 0.0])
                p2 = np.array([-0.35, 0.0])
                label = (-0.22, 0.0)
            else:
                p1 = 0.54 * p0
                p2 = 0.54 * p3
                label = 0.34 * (p0 + p3)
            verts = [p0, p1, p2, p3]
            ax.add_patch(PathPatch(MPath(verts, [MPath.MOVETO, *[MPath.CURVE4] * 3]), lw=width(get(g, h)), edgecolor=color, facecolor='none', alpha=0.58, zorder=1))
            if 'Higher' in (g, h):
                ax.text(*label, val(get(g, h)), ha='center', va='center', fontsize=8.8, color=INK, bbox=dict(facecolor='white', edgecolor='none', pad=1.2), zorder=4)
    for g, p in positions.items():
        ax.add_patch(Circle(p, 0.035, facecolor=COL[g], edgecolor='white', lw=0.65, zorder=5))
    ax.set_xlim(-1.85, 1.85)
    ax.set_ylim(-1.62, 1.62)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', pad=8)

def network_chord(ax, corpus, data):
    """Equal categorical sectors with a common sqrt share scale for ribbons.

    Both ends of each undirected ribbon have the same angular width. A
    within-group ribbon has two ends in that group's sector; it is not an
    institution self-link. Values and denominators are unchanged.
    """
    color = AF if corpus == 'AF' else REF
    angles = {'Lower': 90.0, 'Middle': 0.0, 'Higher': -90.0, 'Other': 180.0}
    edge = {(r.group_1, r.group_2): r.share_pct for r in data.itertuples() if r.corpus == corpus}

    def get(g, h):
        return edge[g, h] if (g, h) in edge else edge[h, g]

    def width(x):
        return 2.75 * np.sqrt(x)

    def xy(t, r=0.965):
        t = np.deg2rad(t)
        return np.array([r * np.cos(t), r * np.sin(t)])
    slots = {}
    for g, t in angles.items():
        partners = [h for h in G if h != g]
        partners.sort(key=lambda h: (angles[h] - t) % 360)
        entries = [(g, 0), (g, 1)] + [(h, 0) for h in partners]
        total = sum((width(get(g, h)) for h, k in entries)) + 1.1 * (len(entries) - 1)
        assert total < 80, (g, total)
        start = t - total / 2
        for h, k in entries:
            w = width(get(g, h))
            slots[g, h, k] = (start, start + w)
            start += w + 1.1
        ax.add_patch(Wedge((0, 0), 1.045, t - 41, t + 41, width=0.047, facecolor=COL[g], edgecolor='none', zorder=5))
        if g in ('Lower', 'Higher'):
            ax.text(0, 1.21 if g == 'Lower' else -1.21, g, ha='center', va='center', color=COL[g], fontsize=9.4, fontweight='bold')
        else:
            ax.text(1.14 if g == 'Middle' else -1.14, 0, g, ha='left' if g == 'Middle' else 'right', va='center', color=COL[g], fontsize=9.4, fontweight='bold')

    def ribbon(s1, s2, self_link=False):
        a, b = s1
        c, d = s2
        arc1 = [xy(t) for t in np.linspace(a, b, 12)]
        arc2 = [xy(t) for t in np.linspace(c, d, 12)]
        pull = 0.38 if self_link else 0.58
        verts = arc1 + [xy(b) * pull, xy(c) * pull, xy(c)] + arc2[1:] + [xy(d) * pull, xy(a) * pull, xy(a), xy(a)]
        codes = [MPath.MOVETO] + [MPath.LINETO] * 11 + [MPath.CURVE4] * 3 + [MPath.LINETO] * 11 + [MPath.CURVE4] * 3 + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), facecolor=color, edgecolor=color, lw=0.35, alpha=0.2 if self_link else 0.27, zorder=1 if self_link else 2))
    for g in G:
        ribbon(slots[g, g, 0], slots[g, g, 1], True)
    for i, g in enumerate(G):
        for h in G[i + 1:]:
            ribbon(slots[g, h, 0], slots[h, g, 0])
    ax.text(-0.25, -0.58, f"{get('Higher', 'Higher'):.1f}%", ha='center', va='center', fontsize=11, color=color, fontweight='bold', zorder=7)
    ax.text(-0.25, -0.74, 'Higher–Higher', ha='center', va='center', fontsize=7.8, color=MUTED, zorder=7)
    ax.set_xlim(-1.69, 1.69)
    ax.set_ylim(-1.38, 1.38)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', pad=8)

def network_proportional(ax, corpus, data):
    """Conventional undirected chord plot, with linear endpoint allocation."""
    color = AF if corpus == 'AF' else REF
    edge = {(r.group_1, r.group_2): r.share_pct for r in data.itertuples() if r.corpus == corpus}

    def get(g, h):
        return edge[g, h] if (g, h) in edge else edge[h, g]
    scale = (360 - 4 * 3) / 200.0
    width = lambda share: scale * share
    slots = {}
    centres = {}
    cursor = 80.0

    def xy(t, r=0.97):
        t = np.deg2rad(t)
        return np.array([r * np.cos(t), r * np.sin(t)])
    for g in G:
        start = cursor
        entries = [(g, 0), (g, 1)] + [(h, 0) for h in G if h != g]
        for h, k in entries:
            end = cursor + width(get(g, h))
            slots[g, h, k] = (cursor, end)
            cursor = end
        centres[g] = (start + cursor) / 2
        ax.add_patch(Wedge((0, 0), 1.045, start, cursor, width=0.055, facecolor=COL[g], edgecolor='none', zorder=5))
        cursor += 3
    assert abs(cursor - 440) < 1e-08

    def ribbon(s1, s2, self_link=False):
        a, b = s1
        c, d = s2
        n1 = max(5, int((b - a) / 2) + 1)
        n2 = max(5, int((d - c) / 2) + 1)
        arc1 = [xy(t) for t in np.linspace(a, b, n1)]
        arc2 = [xy(t) for t in np.linspace(c, d, n2)]
        pull = 0.23 if self_link else 0.58
        verts = arc1 + [xy(b) * pull, xy(c) * pull, xy(c)] + arc2[1:] + [xy(d) * pull, xy(a) * pull, xy(a), xy(a)]
        codes = [MPath.MOVETO] + [MPath.LINETO] * (n1 - 1) + [MPath.CURVE4] * 3 + [MPath.LINETO] * (n2 - 1) + [MPath.CURVE4] * 3 + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), facecolor=color, edgecolor=color, lw=0.15, alpha=0.14 if self_link else 0.3, zorder=1 if self_link else 2))
    for g in G:
        ribbon(slots[g, g, 0], slots[g, g, 1], True)
    for i, g in enumerate(G):
        for h in G[i + 1:]:
            ribbon(slots[g, h, 0], slots[h, g, 0])
    anchors = {'Lower': (0.1, 1.33), 'Middle': (-1.17, 0.99), 'Other': (1.17, 0.99)}
    for g, anchor in anchors.items():
        p = xy(centres[g], 1.075)
        ax.annotate(g, xy=p, xytext=anchor, ha='center', va='center', color=COL[g], fontsize=9.1, fontweight='bold', arrowprops=dict(arrowstyle='-', color=COL[g], lw=0.65, connectionstyle='arc3,rad=0'))
    ax.text(0, -1.19, 'Higher', ha='center', va='center', color=COL['Higher'], fontsize=9.4, fontweight='bold')
    ax.text(0, -0.22, f"{get('Higher', 'Higher'):.1f}%", ha='center', va='center', fontsize=12, color=color, fontweight='bold', zorder=7)
    ax.text(0, -0.4, 'Higher–Higher', ha='center', va='center', fontsize=8.2, color=MUTED, zorder=7)
    ax.set_xlim(-1.69, 1.69)
    ax.set_ylim(-1.38, 1.5)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', pad=8)

def network_donut(ax, corpus, data):
    """Pair-credit composition with literal percentage-proportional angles."""
    color = AF if corpus == 'AF' else REF
    sub = data[data.corpus == corpus]
    hh = float(sub[(sub.group_1 == 'Higher') & (sub.group_2 == 'Higher')].share_pct.iloc[0])
    rest = float(sub.share_pct.sum() - hh)
    assert np.isclose(hh + rest, 100)
    wedges, _ = ax.pie([hh, rest], colors=[color, '#E4E8EE'], radius=0.94, startangle=90, counterclock=False, wedgeprops={'width': 0.19, 'edgecolor': 'white', 'linewidth': 0.8}, normalize=True)
    for wedge, share in zip(wedges, [hh, rest]):
        assert abs(wedge.theta2 - wedge.theta1 - 3.6 * share) < 5e-05
    ax.text(0, 0.075, f'{hh:.1f}%', ha='center', va='center', fontsize=16, color=color, fontweight='bold')
    ax.text(0, -0.17, 'Higher–Higher', ha='center', va='center', fontsize=9.3, color=INK)
    theta = (wedges[1].theta1 + wedges[1].theta2) / 2
    point = np.array([np.cos(np.deg2rad(theta)), np.sin(np.deg2rad(theta))]) * 0.99
    ax.annotate(f'{rest:.1f}%', xy=point, xytext=(-1.04, 1.02), ha='center', va='center', fontsize=9, color=MUTED, arrowprops=dict(arrowstyle='-', color='#A3ACBA', lw=0.65, connectionstyle='angle,angleA=0,angleB=90,rad=3'))
    ax.set_xlim(-1.55, 1.55)
    ax.set_ylim(-1.16, 1.18)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', pad=10)

def network_refined_chord(ax, corpus, data, minimal=False, shared_legend=False):
    """Linear chord geometry, with pale within-group ribbons.

    Reordering endpoints within the Higher sector separates the selected
    cross-group links. It changes neither sector angles nor ribbon widths.
    """
    color = AF if corpus == 'AF' else REF
    edge = {(r.group_1, r.group_2): r.share_pct for r in data.itertuples() if r.corpus == corpus}

    def get(g, h):
        return edge[g, h] if (g, h) in edge else edge[h, g]
    scale = 348 / 200.0
    slots = {}
    centres = {}
    cursor = 80.0

    def xy(t, r=0.97):
        t = np.deg2rad(t)
        return np.array([r * np.cos(t), r * np.sin(t)])
    for g in G:
        start = cursor
        entries = [(g, 0), ('Lower', 0), ('Middle', 0), (g, 1), ('Other', 0)] if g == 'Higher' else [(g, 0), (g, 1)] + [(h, 0) for h in G if h != g]
        for h, k in entries:
            end = cursor + scale * get(g, h)
            slots[g, h, k] = (cursor, end)
            cursor = end
            assert np.isclose(end - slots[g, h, k][0], scale * get(g, h))
        strength = 2 * get(g, g) + sum((get(g, h) for h in G if h != g))
        assert np.isclose(cursor - start, scale * strength)
        centres[g] = (start + cursor) / 2
        ax.add_patch(Wedge((0, 0), 1.045, start, cursor, width=0.045, facecolor=COL[g], edgecolor='none', zorder=5))
        cursor += 3
    assert abs(cursor - 440) < 1e-08
    anchors = {}

    def ribbon(g, h, s1, s2):
        a, b = s1
        c, d = s2
        n1 = max(5, int((b - a) / 2) + 1)
        n2 = max(5, int((d - c) / 2) + 1)
        arc1 = [xy(t) for t in np.linspace(a, b, n1)]
        arc2 = [xy(t) for t in np.linspace(c, d, n2)]
        same = g == h
        selected = set((g, h)) in ({'Lower', 'Higher'}, {'Middle', 'Higher'})
        pull = 0.23 if same else 0.58
        verts = arc1 + [xy(b) * pull, xy(c) * pull, xy(c)] + arc2[1:] + [xy(d) * pull, xy(a) * pull, xy(a), xy(a)]
        codes = [MPath.MOVETO] + [MPath.LINETO] * (n1 - 1) + [MPath.CURVE4] * 3 + [MPath.LINETO] * (n2 - 1) + [MPath.CURVE4] * 3 + [MPath.CLOSEPOLY]
        face_alpha = 0.025 if same and g == 'Higher' else 0.1 if same else 0.56 if selected else 0.22
        edge_alpha = 0.08 if same else 0.65 if selected else 0.28
        ax.add_patch(PathPatch(MPath(verts, codes), facecolor=to_rgba(color, face_alpha), edgecolor=to_rgba(color, edge_alpha), lw=0.25, zorder=1 if same else 3 if selected else 2))
        if selected:
            t = 0.28 if g == 'Lower' else 0.65
            p0 = xy((a + b) / 2)
            p3 = xy((c + d) / 2)
            point = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * pull * p0 + 3 * (1 - t) * t * t * pull * p3 + t ** 3 * p3
            anchors[g, h] = point
    for g in G:
        ribbon(g, g, slots[g, g, 0], slots[g, g, 1])
    for i, g in enumerate(G):
        for h in G[i + 1:]:
            ribbon(g, h, slots[g, h, 0], slots[h, g, 0])
    if not shared_legend:
        labels = {'Lower': (0.1, 1.33), 'Middle': (-1.17, 0.99), 'Other': (1.17, 0.99)}
        for g, anchor in labels.items():
            ax.annotate(g, xy=xy(centres[g], 1.075), xytext=anchor, ha='center', va='center', color=COL[g], fontsize=9.1, fontweight='bold', arrowprops=dict(arrowstyle='-', color=COL[g], lw=0.65))
        ax.text(0, -1.19, 'Higher', ha='center', va='center', color=COL['Higher'], fontsize=9.4, fontweight='bold')
    ax.text(0.43, -0.16, f"{get('Higher', 'Higher'):.1f}%", ha='center', va='center', fontsize=12, color=color, fontweight='bold', zorder=8)
    ax.text(0.43, -0.35, 'Higher–Higher', ha='center', va='center', fontsize=8.0, color=MUTED, zorder=8)
    for g, where in [('Lower', (1.47, 0.36)), ('Middle', (-1.47, 0.16))]:
        ax.annotate(f"{g}–Higher\n{get(g, 'Higher'):.2f}%", xy=anchors[g, 'Higher'], xytext=where, ha='center', va='center', fontsize=8.1, color=INK, linespacing=1.4, arrowprops=dict(arrowstyle='-', color='#8996A9', lw=0.55), zorder=9)
    ax.set_xlim(-1.95, 1.95)
    ax.set_ylim(-1.38, 1.5)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', fontsize=10 if minimal else 11, pad=4 if minimal else 8)

def network_matrix(ax, corpus, data):
    """Ten unordered group-pair shares, shown once with a common area scale."""
    color = AF if corpus == 'AF' else REF
    sub = data[data.corpus == corpus]
    assert len(sub) == 10 and np.isclose(sub.share_pct.sum(), 100)
    radius = lambda v: 0.4 * np.sqrt(v / 90)
    for row in sub.itertuples():
        i = G.index(row.group_1)
        j = G.index(row.group_2)
        v = row.share_pct
        assert i <= j
        ax.add_patch(Rectangle((j - 0.49, i - 0.49), 0.98, 0.98, facecolor='white', edgecolor=GRID, lw=0.7, zorder=0))
        ax.add_patch(Circle((j, i - 0.08), radius(v), facecolor=color, edgecolor='none', alpha=0.75, zorder=2))
        if v > 50:
            ax.text(j, i - 0.08, f'{v:.2f}', ha='center', va='center', fontsize=9.8, color='white', fontweight='bold', zorder=4)
        else:
            ax.text(j, i + 0.27, f'{v:.2f}', ha='center', va='center', fontsize=8.8, color=INK, zorder=4)
    for i, g in enumerate(G):
        ax.text(i, -0.72, g, ha='center', va='center', fontsize=9, color=COL[g], fontweight='bold')
        ax.text(-0.62, i, g, ha='right', va='center', fontsize=9, color=COL[g], fontweight='bold')
    ax.text(0.7, 2.34, 'Area scale (%)', ha='center', va='center', fontsize=7.8, color=MUTED)
    for x, v in [(0, 1), (0.72, 10), (1.48, 50)]:
        ax.add_patch(Circle((x, 2.94), radius(v), facecolor='#B7C1CE', edgecolor='none', alpha=0.72, zorder=1))
        ax.text(x, 3.39, str(v), ha='center', va='center', fontsize=7.8, color=MUTED)
    ax.set_xlim(-1.18, 3.57)
    ax.set_ylim(3.62, -1.02)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('AF' if corpus == 'AF' else 'non-AF', color=color, fontweight='bold', pad=8)

def main(layout='square', legend_below=False):
    data = pd.read_csv(O / 'collaboration_group_shares.csv')
    p = pd.read_csv(O / 'partner_composition.csv')
    ci = pd.read_csv(O / 'estimates_with_intervals.csv')
    compact = layout == 'donut'
    shared_legend = layout == 'shared-legend'
    minimal = layout in ('minimal-chord', 'shared-legend')
    fig = plt.figure(figsize=(8.5, 6.4 if minimal else 6.2 if compact else 7.15))
    axa = fig.add_axes([0.055, 0.55 if minimal else 0.6 if compact else 0.545, 0.425, 0.39 if minimal else 0.28 if compact else 0.35])
    axb = fig.add_axes([0.535, 0.55 if minimal else 0.6 if compact else 0.545, 0.425, 0.39 if minimal else 0.28 if compact else 0.35])
    network = {'square': network_square, 'circular': network_circular, 'chord': network_chord, 'proportional': network_proportional, 'donut': network_donut, 'matrix': network_matrix, 'refined-chord': network_refined_chord, 'minimal-chord': network_refined_chord, 'shared-legend': network_refined_chord}[layout]
    kwargs = {'minimal': True, 'shared_legend': shared_legend} if minimal else {}
    network(axa, 'AF', data, **kwargs)
    network(axb, 'reference', data, **kwargs)
    fig.text(0.025, 0.955 if minimal else 0.925, 'a', fontsize=13, fontweight='bold', color=INK)
    fig.text(0.505, 0.955 if minimal else 0.925, 'b', fontsize=13, fontweight='bold', color=INK)
    if shared_legend:
        fig.legend(handles=[Patch(facecolor=COL[g], label=g) for g in G], ncol=4, frameon=False, loc='center', bbox_to_anchor=(0.5, 0.565 if legend_below else 0.915), handlelength=1.0, handletextpad=0.4, columnspacing=1.4, fontsize=8.5)
    if not minimal:
        fig.text(0.5, 0.978, 'Institutional collaboration links', ha='center', fontsize=12, color=INK)
        fig.text(0.5, 0.947, 'Within-country output groups · link credit (%)', ha='center', fontsize=9, color=MUTED)
        note = {'circular': 'Inner arcs show collaboration within output groups.', 'square': 'Loops connect different institutions within the same output group.', 'chord': 'Ribbon widths: square-root scale · equal-sized sectors identify groups', 'proportional': 'Sector size: link-endpoint share · ribbon width: link share', 'donut': 'Grey: all other institutional pairs', 'matrix': 'Undirected institution pairs · circle area and labels show link credit (%)', 'refined-chord': 'Proportional sectors and ribbons · within-group links lightly shaded'}[layout]
        fig.text(0.5, 0.585 if compact else 0.541, note, ha='center', fontsize=8.4, color=MUTED)
    line_y = 0.535 if minimal else 0.565 if compact else 0.525
    fig.add_artist(Line2D([0.065, 0.96], [line_y, line_y], transform=fig.transFigure, color=GRID, lw=0.8))
    title_y = 0.49 if minimal else 0.52 if compact else 0.483
    fig.text(0.025, title_y, 'c', fontsize=13, fontweight='bold', color=INK)
    fig.text(0.645, title_y, 'd', fontsize=13, fontweight='bold', color=INK)
    if not minimal:
        fig.text(0.345, title_y, 'Partner composition', ha='center', fontsize=10.5, color=INK)
        fig.text(0.815, title_y, 'Higher-output partner share', ha='center', fontsize=10.5, color=INK)
    axc = fig.add_axes([0.175, 0.11 if minimal else 0.13 if compact else 0.12, 0.425, 0.33 if minimal else 0.3 if compact else 0.285])
    axd = fig.add_axes([0.7, 0.11 if minimal else 0.13 if compact else 0.12, 0.25, 0.33 if minimal else 0.3 if compact else 0.285])
    ycenters = [5.2, 3.2, 1.2]
    for k, g in enumerate(G[:3]):
        y = ycenters[k]
        for corpus, yy in [('AF', y + 0.3), ('reference', y - 0.3)]:
            row = p[(p.corpus == corpus) & (p.focal_group == g)].set_index('partner_group').loc[G]
            start = 0
            for h in G:
                v = float(row.loc[h, 'share_pct'])
                axc.barh(yy, v, left=start, height=0.42, color=COL[h], edgecolor='white', linewidth=0.5)
                if h == 'Higher':
                    axc.text(start + v / 2, yy, f'{v:.1f}', ha='center', va='center', color='white', fontsize=8.5)
                start += v
            axc.text(-2.8, yy, 'AF' if corpus == 'AF' else 'non-AF', ha='right', va='center', fontsize=8.2, color=AF if corpus == 'AF' else REF)
        axc.text(-21, y, g, ha='right', va='center', fontsize=9.5, color=COL[g], weight='bold')
        r = ci[(ci.measure == 'partner_composition') & (ci.corpus == 'AF - non-AF') & (ci.focal_group == g) & (ci.partner_group == 'Higher')].iloc[0]
        axd.errorbar(r.estimate, y, xerr=np.array([[r.estimate - r.ci_low], [r.ci_high - r.estimate]]), fmt='o', ms=5.3, color=COL[g], ecolor=COL[g], elinewidth=1.2, capsize=3, capthick=0.9, zorder=3)
        axd.text(r.estimate, y + 0.39, f'{r.estimate:+.1f}', ha='center', va='bottom', fontsize=9, color=INK)
    axc.set_xlim(0, 100)
    axc.set_ylim(0.3, 6.15)
    axc.set_xticks([0, 25, 50, 75, 100])
    axc.set_yticks([])
    axc.grid(axis='x', color=GRID, lw=0.55)
    tidy(axc)
    axc.set_xlabel('Partner credit (%)', labelpad=7)
    if not shared_legend:
        axc.legend(handles=[Patch(facecolor=COL[g], label=g) for g in G], ncol=4, frameon=False, loc='lower center', bbox_to_anchor=(0.5, 1.025), handlelength=1.0, handletextpad=0.4, columnspacing=1.2, fontsize=8.2)
    axd.set_xlim(-3, 12)
    axd.set_ylim(0.3, 6.15)
    axd.set_xticks([0, 5, 10])
    axd.set_yticks([])
    tidy(axd)
    axd.axvline(0, color='#8C9BB0', lw=0.8, ls=(0, (3, 3)))
    axd.grid(axis='x', color=GRID, lw=0.55)
    axd.set_xlabel('AF − non-AF (pp)' if minimal else 'AF − non-AF\n(percentage points)', labelpad=7)
    if not minimal:
        fig.text(0.5, 0.025, '2020–2025 · 5,055 AF and 331,101 non-AF studies', ha='center', fontsize=8.5, color=MUTED)
    stem = {'circular': 'Extended_Data_Fig8_circular_v2', 'square': 'Extended_Data_Fig8_collaboration_draft', 'chord': 'Extended_Data_Fig8_chord_v3', 'proportional': 'Extended_Data_Fig8_proportional_v4', 'donut': 'Extended_Data_Fig8_composition_v5', 'matrix': 'Extended_Data_Fig8_pair_matrix_v6', 'refined-chord': 'Extended_Data_Fig8_refined_chord_v7', 'minimal-chord': 'Extended_Data_Fig8_minimal_chord_v8', 'shared-legend': 'Extended_Data_Fig8_shared_legend_v9'}[layout]
    if shared_legend and legend_below:
        stem = 'Extended_Data_Fig8_legend_below_v10'
    for ext in ['pdf', 'svg']:
        fig.savefig(O / f'{stem}.{ext}')
    fig.savefig(O / f'{stem}.png', dpi=250)
    fig.savefig(O / (stem + '_600dpi.png' if layout != 'square' else 'Extended_Data_Fig8_collaboration_600dpi.png'), dpi=600)
    plt.close(fig)
    print('Figure saved', flush=True)
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--layout', choices=['square', 'circular', 'chord', 'proportional', 'donut', 'matrix', 'refined-chord', 'minimal-chord', 'shared-legend'], default='square')
    parser.add_argument('--legend-below', action='store_true')
    args = parser.parse_args()
    main(args.layout, legend_below=args.legend_below)
