#!/usr/bin/env python3
"""
space_art.py - SVG pictures of stars, planets, moons and constellations.

Stylised vector art meant to be *recognisable*, not astronomically exact.
Flat colour, at most 3 ink colours on a background (or --mono: a single ink,
with hatching for mid-tones).  Everything is plain SVG paths - no filters, no
bitmaps - so it scales, prints and plots well.

  stars          sun
  planets        mercury venus earth mars jupiter saturn uranus neptune pluto
  moons          moon io europa titan
  zodiac         aries taurus gemini cancer leo virgo libra scorpius sagittarius
                 capricornus aquarius pisces
  constellations also orion ursa-major ursa-minor cassiopeia cygnus crux lyra
                 aquila canis-major pegasus

--style illustrated   (constellations) draws the mythological creature as a ghostly silhouette
                behind the stars, solid lines for the main asterism and dotted lines for the
                rest, star names, glowing bright stars, a dusk-sky gradient and a mountain
                horizon.  Default is --style chart (a plain star chart).

--style drawing  (constellations) a hand-inked line drawing in the spirit of old engraved zodiac
                plates: wobbling variable-width ink outlines, engraving-style hatching, a continuous
                silhouette for each creature, star glyphs and dotted constellation lines, black ink on
                paper.  --background/--colors turn it into white chalk on a blackboard, --mono into
                pure black on white.

--view full     (default) the whole object, as on a poster
--view partial  a close-up of the surface (a window onto the object).
                Constellations are always drawn in full.

Every run uses a fresh random seed (printed to stderr and stored in the SVG),
so craters, storms, cracks and star fields differ each time.  --seed N
reproduces a picture.

Examples
--------
  python space_art.py jupiter A3
  python space_art.py earth A4 --center 15,25
  python space_art.py moon 30x40cm --view partial
  python space_art.py orion A4 --label
  python space_art.py leo A3 --style illustrated
  python space_art.py scorpius A3 --style drawing
  python space_art.py virgo A4 --style drawing --names --label
  python space_art.py taurus A4 --style drawing --background "#0c1633" --colors "#f2f0e6,#f2f0e6,#f2f0e6"
  python space_art.py taurus A4 --style illustrated --sky "#2a0a3a,#b8456a,#ffb36b"
  python space_art.py saturn A4 --mono
  python space_art.py mars A3 --colors "#b5452a,#5a2418,#ffffff" --seed 7

Sizes: ISO A0-A6, LETTER, LEGAL, or WIDTHxHEIGHT with a unit (mm, cm, in, m).
A bare WIDTHxHEIGHT is read as millimetres.
"""
from __future__ import annotations

import argparse
import html
import math
import random
import re
import sys
from pathlib import Path

TAU = math.tau
PAPER_MM = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
    "A4": (210, 297), "A5": (148, 210), "A6": (105, 148),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6),
}
UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "m": 1000.0}
ROLES = {"main": 0, "dark": 1, "bright": 2}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def parse_size(text: str) -> tuple[float, float]:
    t = text.strip().lower().replace(" ", "")
    if t.upper() in PAPER_MM:
        return tuple(float(v) for v in PAPER_MM[t.upper()])
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(mm|cm|in|m)?[x\u00d7*](\d+(?:\.\d+)?)(mm|cm|in|m)?", t)
    if not m:
        raise ValueError(
            f"Cannot understand size {text!r}. Use A4, A3, ... or e.g. 30x20cm, 300x200mm, 12x8in.")
    w, u1, h, u2 = m.groups()
    return float(w) * UNIT_MM[u1 or u2 or "mm"], float(h) * UNIT_MM[u2 or u1 or "mm"]


def fmt(v: float, nd: int = 2) -> str:
    s = f"{v:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def poly_d(pts, closed=True) -> str:
    d = f"M{fmt(pts[0][0])} {fmt(pts[0][1])}L" + " ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts[1:])
    return d + ("Z" if closed else "")


def smooth_d(pts, closed=True, k=1 / 6) -> str:
    """Catmull-Rom spline through pts as cubic Beziers."""
    n = len(pts)
    d = [f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"]
    for i in range(n if closed else n - 1):
        p0 = pts[(i - 1) % n] if (closed or i > 0) else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (closed or i + 2 < n) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
        c2 = (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
        d.append(f"C{fmt(c1[0])} {fmt(c1[1])} {fmt(c2[0])} {fmt(c2[1])} {fmt(p2[0])} {fmt(p2[1])}")
    return "".join(d) + ("Z" if closed else "")


def circ(cx, cy, r, fill, extra="") -> str:
    return f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{fill}"{extra}/>'


def ell(cx, cy, rx, ry, fill, extra="") -> str:
    return f'<ellipse cx="{fmt(cx)}" cy="{fmt(cy)}" rx="{fmt(rx)}" ry="{fmt(ry)}" fill="{fill}"{extra}/>'


def pth(d, fill="none", stroke=None, sw=0.0, extra="") -> str:
    s = f'<path d="{d}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{fmt(sw)}"'
    return s + extra + "/>"


def pip(x, y, poly) -> bool:
    """Point in polygon (ray casting)."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def arc_cmd(c, r, s, q, e) -> str:
    """SVG arc command from s to e along the circle (centre c, radius r) passing through q."""
    ang = lambda p: math.atan2(p[1] - c[1], p[0] - c[0])
    a0, aq, a1 = ang(s), ang(q), ang(e)
    span = (a1 - a0) % TAU
    if (aq - a0) % TAU <= span:
        sweep, sp = 1, span
    else:
        sweep, sp = 0, TAU - span
    return f"A{fmt(r, 3)} {fmt(r, 3)} 0 {1 if sp > math.pi else 0} {sweep} {fmt(e[0], 3)} {fmt(e[1], 3)}"


def crescent_d(dx, dy, r=1.0) -> str:
    """Unit-circle minus the same circle shifted by (dx, dy): a crescent on the far side."""
    D = math.hypot(dx, dy)
    u = (dx / D, dy / D)
    v = (-u[1], u[0])
    h = math.sqrt(r * r - (D / 2) ** 2)
    m = (u[0] * D / 2, u[1] * D / 2)
    p1 = (m[0] + v[0] * h, m[1] + v[1] * h)
    p2 = (m[0] - v[0] * h, m[1] - v[1] * h)
    q1 = (-u[0] * r, -u[1] * r)
    q2 = (dx - u[0] * r, dy - u[1] * r)
    return (f"M{fmt(p1[0], 3)} {fmt(p1[1], 3)}" + arc_cmd((0, 0), r, p1, q1, p2)
            + arc_cmd((dx, dy), r, p2, q2, p1) + "Z")


# --------------------------------------------------------------------------- #
# Noise (seeded gradient noise)
# --------------------------------------------------------------------------- #
class Noise:
    def __init__(self, rng: random.Random):
        perm = list(range(256))
        rng.shuffle(perm)
        self.p = perm + perm
        self.g = [(math.cos(t), math.sin(t)) for t in (rng.uniform(0, TAU) for _ in range(256))]

    def n(self, x: float, y: float) -> float:
        xi, yi = math.floor(x), math.floor(y)
        xf, yf = x - xi, y - yi
        xi &= 255
        yi &= 255
        x1, y1 = (xi + 1) & 255, (yi + 1) & 255
        p, g = self.p, self.g
        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        g00, g10, g01, g11 = g[p[p[xi] + yi]], g[p[p[x1] + yi]], g[p[p[xi] + y1]], g[p[p[x1] + y1]]
        d00 = g00[0] * xf + g00[1] * yf
        d10 = g10[0] * (xf - 1) + g10[1] * yf
        d01 = g01[0] * xf + g01[1] * (yf - 1)
        d11 = g11[0] * (xf - 1) + g11[1] * (yf - 1)
        a = d00 + u * (d10 - d00)
        b = d01 + u * (d11 - d01)
        return (a + v * (b - a)) * 1.41

    def fbm(self, x: float, y: float, octaves: int = 4) -> float:
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += amp * self.n(x * freq, y * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        return total / norm


# --------------------------------------------------------------------------- #
# Palette / style: at most 3 ink colours (+ background), or one ink in mono
# --------------------------------------------------------------------------- #
class Style:
    def __init__(self, colors, bg, mono_ink, hatch):
        self.colors = colors
        self.bg = bg
        self.ink = mono_ink
        self.mono = mono_ink is not None
        self.paper = bg if (bg and bg != "none") else "#ffffff"
        self.hatch = hatch

    def f(self, role: str) -> str:
        """Fill paint for a role (main / dark / bright)."""
        if self.mono:
            return {"main": "url(#hatch)", "dark": self.ink, "bright": self.paper}[role]
        return self.colors[ROLES[role]]

    def s(self, role: str) -> str:
        """Stroke colour for a role."""
        if self.mono:
            return self.paper if role == "bright" else self.ink
        return self.colors[ROLES[role]]

    def star(self) -> str:
        return self.ink if self.mono else self.colors[2]

    def line(self) -> str:
        return self.ink if self.mono else self.colors[0]

    def faint(self) -> str:
        return self.ink if self.mono else self.colors[1]

    def pattern(self) -> str:
        if not self.mono:
            return ""
        s = self.hatch
        return (f'<pattern id="hatch" width="{fmt(s)}" height="{fmt(s)}" patternUnits="userSpaceOnUse" '
                f'patternTransform="rotate(45)"><rect width="{fmt(s)}" height="{fmt(s)}" fill="{self.paper}"/>'
                f'<line x1="0" y1="0" x2="0" y2="{fmt(s)}" stroke="{self.ink}" stroke-width="{fmt(s * 0.24)}"/></pattern>')


# --------------------------------------------------------------------------- #
# Drawing context
# --------------------------------------------------------------------------- #
class Ctx:
    def __init__(self, W, H, args, rng, st):
        self.W, self.H, self.args, self.rng, self.st = W, H, args, rng, st
        self.noise = Noise(rng)
        self.partial = args.view == "partial"
        self.U = min(W, H)
        self.defs: list[str] = []
        self.out: list[str] = []
        self.n = 0
        self.R = self.cx = self.cy = 0.0
        self.sky = None                       # gradient stops for the illustrated style

    def uid(self, p="a") -> str:
        self.n += 1
        return f"{p}{self.n}"

    def add(self, s: str) -> None:
        self.out.append(s)

    def clip_circle(self, cx, cy, r) -> str:
        i = self.uid("c")
        self.defs.append(f'<clipPath id="{i}"><circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}"/></clipPath>')
        return i

    def on_page(self, x, y, m=0.0) -> bool:
        return -m <= x <= self.W + m and -m <= y <= self.H + m

    def pts_on_page(self, pts, m=0.0) -> bool:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return not (max(xs) < -m or min(xs) > self.W + m or max(ys) < -m or min(ys) > self.H + m)


def place(ctx: Ctx, fit: float, *, globe=False, focus=None, fmax=0.3, zoom_mult=1.0) -> None:
    """Decide the disc centre/radius.  Full: centred, radius `fit`.  Partial: the
    page becomes a window onto a much larger disc."""
    W, H = ctx.W, ctx.H
    if not ctx.partial:
        ctx.R, ctx.cx, ctx.cy = fit, W / 2, H / 2
        return
    zoom = ctx.args.zoom * zoom_mult
    if globe:
        ctx.R, ctx.cx, ctx.cy = 0.55 * math.hypot(W, H) * zoom, W / 2, H / 2
        return
    f = ctx.args.focus or focus
    if f is None:
        a = ctx.rng.uniform(0, TAU)
        d = fmax * math.sqrt(ctx.rng.random())
        f = (d * math.cos(a), d * math.sin(a))
    cover = 0.5 * math.hypot(W, H) / (1 - min(math.hypot(*f), 0.8))
    ctx.R = cover * zoom
    ctx.cx = W / 2 - f[0] * ctx.R
    ctx.cy = H / 2 - f[1] * ctx.R


def starfield(ctx: Ctx, keepouts) -> None:
    if ctx.partial or not ctx.args.stars:
        return
    rng, u = ctx.rng, ctx.U / 210
    for _ in range(int(ctx.W * ctx.H / 650)):
        x, y = rng.uniform(0, ctx.W), rng.uniform(0, ctx.H)
        if any(math.hypot(x - a, y - b) < r for a, b, r in keepouts):
            continue
        ctx.add(circ(x, y, u * rng.choice((0.22, 0.28, 0.35, 0.45, 0.6)), ctx.st.star()))


def open_disc(ctx: Ctx, base="main") -> None:
    cid = ctx.clip_circle(ctx.cx, ctx.cy, ctx.R)
    ctx.add(circ(ctx.cx, ctx.cy, ctx.R, ctx.st.f(base)))
    ctx.add(f'<g clip-path="url(#{cid})">')


def close_disc(ctx: Ctx) -> None:
    ctx.add("</g>")
    if ctx.st.mono and not ctx.partial:
        ctx.add(circ(ctx.cx, ctx.cy, ctx.R, "none",
                     f' stroke="{ctx.st.ink}" stroke-width="{fmt(ctx.U * 0.0025)}"'))


def blob_pts(ctx: Ctx, cx, cy, rx, ry, rot=0.0, rough=0.35, n=18):
    off = ctx.rng.random() * 80
    cr, sr = math.cos(rot), math.sin(rot)
    pts = []
    for i in range(n):
        a = TAU * i / n
        k = 1 + rough * ctx.noise.n(math.cos(a) * 1.3 + off, math.sin(a) * 1.3 + off)
        x, y = math.cos(a) * rx * k, math.sin(a) * ry * k
        pts.append((cx + x * cr - y * sr, cy + x * sr + y * cr))
    return pts


def roughen(ctx: Ctx, pts, amp, step, feature):
    """Subdivide a closed polygon and wobble it with noise (natural coastlines etc)."""
    n = len(pts)
    per = sum(math.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]) for i in range(n))
    step = max(step, per / 2500)
    out = []
    sc = 1.0 / feature
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        m = max(1, int(L / step))
        nx, ny = -dy / L, dx / L
        for j in range(m):
            t = j / m
            x, y = a[0] + dx * t, a[1] + dy * t
            if j:
                off = amp * ctx.noise.fbm(x * sc, y * sc, 3)
                x, y = x + nx * off, y + ny * off
            out.append((x, y))
    return out


# --------------------------------------------------------------------------- #
# Banded bodies (gas giants, Venus, Titan)
# --------------------------------------------------------------------------- #
def band(ctx: Ctx, y0, y1, role, amp=0.02, freq=2.5, off=0.0, shear=0.0) -> None:
    """A wavy horizontal band between y0 and y1 (disc units, -1 = top)."""
    R = ctx.R
    x0, x1 = max(ctx.cx - R, -5), min(ctx.cx + R, ctx.W + 5)
    n = max(24, int((x1 - x0) / (0.012 * ctx.U)))
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]

    def edge(x, y, o):
        xn = (x - ctx.cx) / R
        return ctx.cy + R * (y + shear * xn * y + amp * ctx.noise.fbm(xn * freq + o, y * 3.7 + o * 0.31, 4))

    top = [(x, edge(x, y0, off)) for x in xs]
    bot = [(x, edge(x, y1, off + 3.1)) for x in reversed(xs)]
    ys = [p[1] for p in top + bot]
    if max(ys) < -5 or min(ys) > ctx.H + 5:
        return
    ctx.add(pth(poly_d(top + bot), ctx.st.f(role)))


def ovals(ctx: Ctx, n, ys, role, size, flat=(0.4, 0.7)) -> None:
    R, rng = ctx.R, ctx.rng
    for _ in range(n):
        y = rng.choice(ys) + rng.uniform(-0.02, 0.02)
        lim = math.sqrt(max(0.0, 1 - y * y)) * 0.92
        x = rng.uniform(-lim, lim)
        rx = size * rng.uniform(0.5, 1.5) * R
        px, py = ctx.cx + x * R, ctx.cy + y * R
        if ctx.on_page(px, py, rx):
            ctx.add(ell(px, py, rx, rx * rng.uniform(*flat), ctx.st.f(role)))


def storm(ctx: Ctx, x, y, rx, ry, outer, ring, core, halo=True, swirl=False) -> None:
    """Concentric-ellipse storm (Great Red Spot style); x, y in disc units."""
    R = ctx.R
    px, py = ctx.cx + x * R, ctx.cy + y * R
    if halo:
        ctx.add(ell(px, py, rx * R * 1.28, ry * R * 1.5, ctx.st.f("bright")))
    ctx.add(ell(px, py, rx * R, ry * R, ctx.st.f(outer)))
    ctx.add(ell(px, py, rx * R * 0.62, ry * R * 0.6, ctx.st.f(ring)))
    ctx.add(ell(px, py, rx * R * 0.27, ry * R * 0.26, ctx.st.f(core)))
    if swirl:                                            # spiral arm winding into the storm
        pts = []
        for i in range(60):
            t = i / 59
            a = t * 3.4 * math.pi + 0.6
            k = 0.2 + 0.78 * t
            pts.append((px + rx * R * k * math.cos(a), py + ry * R * k * math.sin(a)))
        ctx.add(pth(smooth_d(pts, closed=False), "none", ctx.st.s("bright"), max(0.25, R * 0.008),
                    ' stroke-linecap="round"'))


JUPITER_BANDS = [
    (-1.10, -0.78, "dark"), (-0.70, -0.64, "dark"), (-0.64, -0.52, "bright"), (-0.52, -0.43, "dark"),
    (-0.43, -0.31, "bright"), (-0.31, -0.14, "dark"), (-0.14, 0.10, "bright"), (0.10, 0.30, "dark"),
    (0.30, 0.40, "bright"), (0.40, 0.48, "dark"), (0.48, 0.60, "bright"), (0.62, 0.68, "dark"),
    (0.78, 1.10, "dark"),
]


def draw_jupiter(ctx: Ctx) -> None:
    rng = ctx.rng
    place(ctx, 0.42 * ctx.U, focus=(-0.08, 0.30))
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.1)])
    open_disc(ctx)
    close = 2.2 if ctx.partial else 1.0                  # up close, edges show more turbulence
    for k, (y0, y1, role) in enumerate(JUPITER_BANDS):
        band(ctx, y0, y1, role, amp=0.018 * close, freq=3.0 * close, off=k * 1.7)
    for _ in range(9):                                   # thin streaks inside the zones
        y = rng.uniform(-0.9, 0.9)
        band(ctx, y, y + rng.uniform(0.006, 0.014), "dark", amp=0.012, freq=5.0, off=rng.uniform(0, 50))
    ovals(ctx, 10 if not ctx.partial else 26, [-0.58, -0.37, 0.35, 0.55, 0.04], "bright", 0.03 if not ctx.partial else 0.02)
    ovals(ctx, 6 if not ctx.partial else 16, [-0.47, -0.22, 0.2, 0.44], "dark", 0.025 if not ctx.partial else 0.016)
    gx = 0.15 if ctx.partial else rng.uniform(-0.25, 0.3)
    storm(ctx, gx, 0.345, 0.25, 0.115, "dark", "main", "dark", swirl=True)
    close_disc(ctx)


def _ring_d(rx, ry) -> str:
    return f"M{fmt(-rx)} 0a{fmt(rx)} {fmt(ry)} 0 1 0 {fmt(2 * rx)} 0a{fmt(rx)} {fmt(ry)} 0 1 0 {fmt(-2 * rx)} 0Z"


def _saturn_rings(ctx: Ctx, rot, k, front_only=False) -> None:
    R, st = ctx.R, ctx.st
    inner = []
    for ri, ro, role in ((1.24, 1.52, "dark"), (1.52, 1.95, "bright"), (2.03, 2.27, "main")):
        inner.append(f'<path d="{_ring_d(ro * R, ro * R * k)}{_ring_d(ri * R, ri * R * k)}" '
                     f'fill="{st.f(role)}" fill-rule="evenodd"/>')
    g = f'<g transform="translate({fmt(ctx.cx)} {fmt(ctx.cy)}) rotate({fmt(rot)})">'
    if front_only:
        cid = ctx.uid("c")
        ctx.defs.append(f'<clipPath id="{cid}"><rect x="{fmt(-4 * R)}" y="0" width="{fmt(8 * R)}" '
                        f'height="{fmt(4 * R)}"/></clipPath>')
        g += f'<g clip-path="url(#{cid})">'
    ctx.add(g + "".join(inner) + ("</g>" if front_only else "") + "</g>")


def draw_saturn(ctx: Ctx) -> None:
    rng = ctx.rng
    k = 0.34
    rot = (-30 if ctx.H > ctx.W else -14) * rng.choice((1, -1))
    a, b = 2.27, 2.27 * k
    th = math.radians(rot)
    hw = math.hypot(a * math.cos(th), b * math.sin(th))
    hh = math.hypot(a * math.sin(th), b * math.cos(th))
    if ctx.partial:
        ctx.R = 0.52 * max(ctx.W, ctx.H) * ctx.args.zoom / 1.5
        ctx.cx, ctx.cy = ctx.W * 0.08, ctx.H * 0.62
    else:
        ctx.R, ctx.cx, ctx.cy = min(0.46 * ctx.W / hw, 0.46 * ctx.H / hh), ctx.W / 2, ctx.H / 2
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 2.45)])
    _saturn_rings(ctx, rot, k)
    open_disc(ctx)
    for i, (y0, y1, role) in enumerate([(-1.1, -0.82, "dark"), (-0.62, -0.55, "dark"), (-0.55, -0.38, "bright"),
                                        (-0.30, -0.22, "dark"), (-0.22, 0.10, "bright"), (0.14, 0.20, "dark"),
                                        (0.30, 0.40, "dark"), (0.52, 0.58, "dark"), (0.75, 1.1, "dark")]):
        band(ctx, y0, y1, role, amp=0.006, freq=3.0, off=i * 2.3)
    close_disc(ctx)
    _saturn_rings(ctx, rot, k, front_only=True)


def draw_uranus(ctx: Ctx) -> None:
    place(ctx, 0.23 * ctx.U)
    R = ctx.R
    starfield(ctx, [(ctx.cx, ctx.cy, R * 2.1)])
    if not ctx.partial:                                  # faint rings, seen almost face-on
        for r, w in ((1.45, 0.012), (1.55, 0.008), (1.72, 0.014), (1.84, 0.008), (1.97, 0.018)):
            ctx.add(circ(ctx.cx, ctx.cy, R * r, "none",
                         f' stroke="{ctx.st.s("main")}" stroke-width="{fmt(R * w)}"'))
    open_disc(ctx)
    px, py = ctx.cx - 0.12 * R, ctx.cy + 0.06 * R        # the pole points roughly at us
    for r, role in ((1.6, "dark"), (1.25, "main"), (0.98, "dark"), (0.74, "main"), (0.52, "dark"), (0.36, "main"),
                    (0.2, "bright")):
        ctx.add(circ(px, py, r * R, ctx.st.f(role)))
    close_disc(ctx)


def draw_neptune(ctx: Ctx) -> None:
    rng = ctx.rng
    place(ctx, 0.40 * ctx.U, focus=(-0.1, 0.05))
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.1)])
    open_disc(ctx)
    for k, (y0, y1, role) in enumerate([(-1.1, -0.75, "dark"), (-0.55, -0.45, "dark"), (-0.28, -0.22, "bright"),
                                        (-0.05, 0.05, "dark"), (0.45, 0.62, "dark"), (0.78, 1.1, "dark")]):
        band(ctx, y0, y1, role, amp=0.025, freq=2.2, off=k * 3.7)
    gx = -0.2 if not ctx.partial else -0.1
    storm(ctx, gx, 0.12, 0.17, 0.09, "dark", "dark", "dark", halo=False)
    ctx.add(ell(ctx.cx + (gx + 0.34) * ctx.R, ctx.cy + 0.04 * ctx.R, 0.1 * ctx.R, 0.012 * ctx.R, ctx.st.f("bright")))
    for _ in range(8):                                   # high white cirrus streaks
        y = rng.uniform(-0.8, 0.8)
        x = rng.uniform(-0.6, 0.6)
        ctx.add(ell(ctx.cx + x * ctx.R, ctx.cy + y * ctx.R, rng.uniform(0.07, 0.18) * ctx.R,
                    rng.uniform(0.006, 0.014) * ctx.R, ctx.st.f("bright")))
    close_disc(ctx)


def draw_venus(ctx: Ctx) -> None:
    rng = ctx.rng
    place(ctx, 0.40 * ctx.U)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.1)])
    open_disc(ctx)
    y = -1.6
    k = 0
    while y < 1.6:                                      # thick, strongly wavy cloud streaks
        h = rng.uniform(0.07, 0.17)
        band(ctx, y, y + h, "dark" if k % 2 else "bright", amp=0.10, freq=1.6, off=k * 5.3, shear=0.55)
        y += h + rng.uniform(0.05, 0.12)
        k += 1
    close_disc(ctx)


def draw_titan(ctx: Ctx) -> None:
    place(ctx, 0.36 * ctx.U)
    R = ctx.R
    starfield(ctx, [(ctx.cx, ctx.cy, R * 1.2)])
    if not ctx.partial:                                  # the detached haze layer
        ctx.add(circ(ctx.cx, ctx.cy, R * 1.075, "none",
                     f' stroke="{ctx.st.s("bright")}" stroke-width="{fmt(R * 0.022)}"'))
    open_disc(ctx)
    for k, (y0, y1, role) in enumerate([(-1.1, -0.72, "dark"), (-0.72, -0.66, "bright"), (-0.35, -0.28, "dark"),
                                        (-0.05, 0.08, "bright"), (0.22, 0.30, "dark"), (0.55, 0.62, "bright")]):
        band(ctx, y0, y1, role, amp=0.02, freq=2.0, off=k * 2.9)
    close_disc(ctx)


# --------------------------------------------------------------------------- #
# Registry, assembly, command line
# --------------------------------------------------------------------------- #
CONSTELLATION_COLORS = ("#8fb0ff", "#5d6fa6", "#fff2c2")
ILLUSTRATED_COLORS = ("#ffffff", "#03050a", "#ffffff")      # figure+lines, horizon, stars
DRAWING_COLORS = ("#1b1814", "#1b1814", "#1b1814")           # one ink
DRAWING_PAPER = "#f4eedf"
DEFAULT_SKY = ("#06103a", "#1d4c9e", "#8fbfe9")               # zenith -> horizon
OBJECTS = {
    # name: (category, draw function, (main, dark, bright), title)
    "sun": ("star", "draw_sun", ("#f4961c", "#7d2a0c", "#ffd965"), "The Sun"),
    "mercury": ("planet", "draw_mercury", ("#8e8a85", "#58544f", "#c9c4bb"), "Mercury"),
    "venus": ("planet", "draw_venus", ("#e5c98a", "#c08f4e", "#f7ecc8"), "Venus"),
    "earth": ("planet", "draw_earth", ("#2b6fd0", "#4c9a45", "#f4f7fb"), "Earth"),
    "mars": ("planet", "draw_mars", ("#c5582f", "#6c3020", "#f1e6dc"), "Mars"),
    "jupiter": ("planet", "draw_jupiter", ("#dcb88a", "#a85f35", "#f6ecda"), "Jupiter"),
    "saturn": ("planet", "draw_saturn", ("#d9bf86", "#b4915a", "#efe1b0"), "Saturn"),
    "uranus": ("planet", "draw_uranus", ("#9edfe6", "#78c0cb", "#e2f7f9"), "Uranus"),
    "neptune": ("planet", "draw_neptune", ("#3b5fd0", "#24378c", "#a8c4ff"), "Neptune"),
    "pluto": ("planet", "draw_pluto", ("#c9a888", "#6f4331", "#f3e8d9"), "Pluto"),
    "moon": ("moon", "draw_moon", ("#bdb9b0", "#6e6b68", "#ece9e0"), "The Moon"),
    "io": ("moon", "draw_io", ("#dcbf3c", "#51341f", "#f4ecae"), "Io"),
    "europa": ("moon", "draw_europa", ("#dcd5c6", "#8e5f3f", "#f6f3ec"), "Europa"),
    "titan": ("moon", "draw_titan", ("#d98f2f", "#a2601d", "#f2bd68"), "Titan"),
}
ZODIAC = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpius",
          "sagittarius", "capricornus", "aquarius", "pisces"]
ALIASES = {"capricorn": "capricornus", "scorpio": "scorpius", "big-dipper": "ursa-major", "great-bear": "ursa-major", "little-dipper": "ursa-minor",
           "southern-cross": "crux", "canis-major-dog": "canis-major", "luna": "moon", "sol": "sun"}


def object_names() -> dict[str, list[str]]:
    cats: dict[str, list[str]] = {}
    for name, (cat, *_rest) in OBJECTS.items():
        cats.setdefault(cat, []).append(name)
    cats["constellation"] = sorted(CONSTELLATIONS)
    return cats


def parse_pair(text: str) -> tuple[float, float]:
    try:
        a, b = (float(v) for v in text.replace(";", ",").split(","))
        return a, b
    except ValueError:
        raise argparse.ArgumentTypeError("expected two numbers like 15,25") from None


def parse_colors(text: str) -> tuple[str, str, str]:
    parts = [c.strip() for c in text.split(",")]
    if len(parts) != 3 or not all(parts):
        raise argparse.ArgumentTypeError("give exactly 3 colours: MAIN,DARK,BRIGHT (e.g. '#c5582f,#6c3020,#ffffff')")
    return tuple(parts)


def parse_sky(text: str):
    parts = [c.strip() for c in text.split(",")]
    if len(parts) not in (2, 3) or not all(parts):
        raise argparse.ArgumentTypeError("give 2 or 3 colours: TOP,BOTTOM or TOP,MID,BOTTOM")
    return tuple(parts)


def assemble(ctx: Ctx, title: str, seed: int, label) -> str:
    W, H, st = ctx.W, ctx.H, ctx.st
    defs = [f'<clipPath id="page"><rect width="{fmt(W)}" height="{fmt(H)}"/></clipPath>']
    if st.pattern():
        defs.append(st.pattern())
    defs += ctx.defs
    bg = ""
    if ctx.sky:
        n = len(ctx.sky)
        stops = "".join(f'<stop offset="{fmt(i / (n - 1) if n > 2 else i)}" stop-color="{c}"/>' for i, c in enumerate(ctx.sky))
        if n == 3:
            stops = (f'<stop offset="0" stop-color="{ctx.sky[0]}"/><stop offset="0.6" stop-color="{ctx.sky[1]}"/>'
                     f'<stop offset="1" stop-color="{ctx.sky[2]}"/>')
        defs.append(f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">{stops}</linearGradient>')
        bg = f'<rect width="{fmt(W)}" height="{fmt(H)}" fill="url(#sky)"/>'
    elif st.bg and st.bg != "none":
        bg = f'<rect width="{fmt(W)}" height="{fmt(H)}" fill="{html.escape(st.bg, quote=True)}"/>'
    txt = ""
    if label:
        size = ctx.U * 0.032
        txt = (f'<text x="{fmt(W / 2)}" y="{fmt(H - ctx.U * 0.05)}" text-anchor="middle" '
               f'font-family="{"Georgia, serif" if ctx.args.style == "drawing" and ctx.args.object not in OBJECTS else "Helvetica, Arial, sans-serif"}" font-size="{fmt(size)}" '
               f'letter-spacing="{fmt(size * 0.35)}" fill="{st.star()}">{html.escape(label.upper())}</text>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{fmt(W)}mm" height="{fmt(H)}mm" viewBox="0 0 {fmt(W)} {fmt(H)}">\n'
        f'<title>{html.escape(title)}</title>\n<!-- seed {seed} -->\n'
        f'<defs>{"".join(defs)}</defs>\n{bg}\n<g clip-path="url(#page)">\n'
        + "\n".join(ctx.out) + f'\n{txt}\n</g>\n</svg>\n'
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SVG art of stars, planets, moons and constellations (see --list).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("object", nargs="?", help="what to draw (see --list)")
    ap.add_argument("size", nargs="?", default="A4",
                    help="A0-A6, LETTER, LEGAL, or WxH with unit, e.g. 30x40cm")
    orient = ap.add_mutually_exclusive_group()
    orient.add_argument("-l", "--landscape", action="store_true", help="force landscape")
    orient.add_argument("-p", "--portrait", action="store_true", help="force portrait")
    ap.add_argument("-o", "--output", default=None, help="output file (default: <object>.svg)")
    ap.add_argument("--view", choices=("full", "partial"), default="full",
                    help="full: the whole object; partial: a close-up window onto its surface")
    ap.add_argument("--zoom", type=float, default=1.5, help="partial view: magnification (>= 1)")
    ap.add_argument("--focus", type=parse_pair, default=None,
                    help="partial view: disc point to centre on, X,Y in -1..1 (y points down)")
    ap.add_argument("--center", type=parse_pair, default=None,
                    help="globes (earth, mars, moon, pluto): LON,LAT to face the viewer")
    ap.add_argument("--mono", nargs="?", const="#111111", default=None, metavar="INK",
                    help="single ink colour with hatching instead of the 3-colour palette")
    ap.add_argument("--colors", type=parse_colors, default=None, metavar="MAIN,DARK,BRIGHT",
                    help="override the 3 colours (surface, shadows/features, highlights)")
    ap.add_argument("--background", default=None,
                    help="background colour or 'none' (default: night blue, white with --mono)")
    ap.add_argument("--stars", action=argparse.BooleanOptionalAction, default=True,
                    help="scatter background stars around full views")
    ap.add_argument("--label", nargs="?", const=True, default=None, metavar="TEXT",
                    help="print a caption (the object's name unless TEXT is given)")
    ap.add_argument("--style", choices=("chart", "illustrated", "drawing"), default="chart",
                    help="constellations: 'chart' = plain star chart; 'illustrated' = ghostly creature behind the "
                         "stars on a dusk sky; 'drawing' = hand-inked line drawing (black ink on paper)")
    ap.add_argument("--sky", type=parse_sky, default=None, metavar="TOP[,MID],BOTTOM",
                    help="illustrated style: sky gradient colours (2 or 3), zenith to horizon")
    ap.add_argument("--names", action=argparse.BooleanOptionalAction, default=None,
                    help="label the named stars (default: on for --style illustrated)")
    ap.add_argument("--horizon", action=argparse.BooleanOptionalAction, default=True,
                    help="illustrated style: draw a mountain horizon")
    ap.add_argument("--rotate", type=float, default=None, metavar="DEG",
                    help="constellations: rotate the figure (default: auto - north up, unless a quarter "
                         "turn fills the page much better; 0 forces north up)")
    ap.add_argument("--seed", type=int, default=None, help="random seed (default: new every run)")
    ap.add_argument("--list", action="store_true", help="list everything that can be drawn")
    argv = list(sys.argv[1:] if argv is None else argv)
    for i, a in enumerate(argv[:-1]):          # let "--center -85,15" work (negative values)
        if a in ("--center", "--focus") and re.fullmatch(r"-?[\d.]+[,;]-?[\d.]+", argv[i + 1]):
            argv[i], argv[i + 1] = f"{a}={argv[i + 1]}", ""
    args = ap.parse_args([a for a in argv if a != ""])

    if args.list:
        for cat, names in object_names().items():
            print(f"{cat + 's':15s}" + " ".join(names))
        print(f"{'zodiac':15s}" + " ".join(ZODIAC) + "   (in calendar order)")
        return 0
    if not args.object:
        ap.error("name an object to draw (see --list)")
    name = args.object.lower().replace("_", "-").replace(" ", "-")
    name = ALIASES.get(name, name)
    is_const = name in CONSTELLATIONS
    if name not in OBJECTS and not is_const:
        ap.error(f"unknown object {args.object!r}. Choose from: " +
                 ", ".join(n for ns in object_names().values() for n in ns))
    if args.zoom < 1:
        ap.error("--zoom must be at least 1")

    try:
        W, H = parse_size(args.size)
    except ValueError as e:
        ap.error(str(e))
    if args.landscape and W < H:
        W, H = H, W
    if args.portrait and W > H:
        W, H = H, W

    if is_const:
        cat, title = "constellation", CONSTELLATIONS[name][0]
        colors = {"illustrated": ILLUSTRATED_COLORS, "drawing": DRAWING_COLORS}.get(args.style, CONSTELLATION_COLORS)
        if args.view == "partial":
            print("note: constellations are always drawn in full", file=sys.stderr)
            args.view = "full"
    else:
        cat, fn_name, colors, title = OBJECTS[name]
        if args.style != "chart":
            print(f"note: --style {args.style} only applies to constellations", file=sys.stderr)
    if args.colors:
        colors = args.colors
    mono = args.mono
    paper_style = is_const and args.style == "drawing"
    bg = args.background if args.background is not None else (
        "#ffffff" if mono else (DRAWING_PAPER if paper_style else "#0a0e1f"))
    U = min(W, H)
    sky = None
    if is_const and args.style == "illustrated" and not mono and args.background is None:
        sky = args.sky or DEFAULT_SKY
        bg = sky[0]
    st = Style(colors, bg, mono, hatch=U * 0.007)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 32)
    rng = random.Random(seed)
    ctx = Ctx(W, H, args, rng, st)
    ctx.sky = sky
    if is_const:
        draw_constellation(ctx, name)
    else:
        globals()[fn_name](ctx)

    label = None
    if args.label:
        label = title if args.label is True else args.label
    out = Path(args.output or f"{name}.svg")
    out.write_text(assemble(ctx, title, seed, label), encoding="utf-8")
    print(f"{out}: {title}, {fmt(W)} x {fmt(H)} mm, {args.view} view, "
          f"{'mono' if mono else '3 colours'}, seed {seed}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# Globes: lon/lat features projected orthographically onto a sphere
# --------------------------------------------------------------------------- #
class Globe:
    def __init__(self, ctx: Ctx, lon0: float, lat0: float):
        self.ctx, self.lon0 = ctx, lon0
        p0 = math.radians(lat0)
        self.sp0, self.cp0 = math.sin(p0), math.cos(p0)

    def xyz(self, lon, lat):
        l, p = math.radians(lon - self.lon0), math.radians(lat)
        cp = math.cos(p)
        x = cp * math.sin(l)
        y = self.cp0 * math.sin(p) - self.sp0 * cp * math.cos(l)
        z = self.sp0 * math.sin(p) + self.cp0 * cp * math.cos(l)
        return x, -y, z                       # screen y points down

    def screen(self, lon, lat):
        x, y, z = self.xyz(lon, lat)
        return self.ctx.cx + x * self.ctx.R, self.ctx.cy + y * self.ctx.R, z

    def poly(self, ll, step=4.0):
        """Project a lon/lat polygon; parts hidden behind the limb are pinned to the rim."""
        c, out, vis, n = self.ctx, [], False, len(ll)
        for i in range(n):
            a, b = ll[i], ll[(i + 1) % n]
            dlon, dlat = (b[0] - a[0] + 180) % 360 - 180, b[1] - a[1]
            m = max(1, int(max(abs(dlon), abs(dlat)) / step))
            for j in range(m):
                t = j / m
                x, y, z = self.xyz(a[0] + dlon * t, a[1] + dlat * t)
                if z >= 0:
                    vis = True
                else:
                    k = math.hypot(x, y) or 1e-9
                    x, y = x / k, y / k
                out.append((c.cx + x * c.R, c.cy + y * c.R))
        return out if vis else None


def parse_ll(s: str):
    return [tuple(float(v) for v in p.split(",")) for p in s.split()]


def ll_blob(ctx: Ctx, lon, lat, rx, ry, rot=0.0, rough=0.35, n=22):
    """A wobbly blob on the sphere, rx/ry in degrees."""
    off = ctx.rng.random() * 80
    cr, sr = math.cos(rot), math.sin(rot)
    pts = []
    for i in range(n):
        a = TAU * i / n
        k = 1 + rough * ctx.noise.n(math.cos(a) * 1.3 + off, math.sin(a) * 1.3 + off)
        x, y = math.cos(a) * rx * k, math.sin(a) * ry * k
        x, y = x * cr - y * sr, x * sr + y * cr
        la = max(-88, min(88, lat + y))
        pts.append((lon + x / max(0.25, math.cos(math.radians(la))), la))
    return pts


def draw_ll(ctx: Ctx, g: Globe, ll, role, amp=0.0045, seam=True):
    """Project, roughen and paint a lon/lat polygon.  Returns its screen points."""
    pts = g.poly(ll)
    if not pts or not ctx.pts_on_page(pts, 5):
        return None
    U = ctx.U
    pts = roughen(ctx, pts, amp * U, 0.012 * U, 0.05 * U)
    if seam:   # a hairline of the same colour hides seams between touching polygons
        ctx.add(pth(poly_d(pts), ctx.st.f(role), ctx.st.s(role), U * 0.0012, ' stroke-linejoin="round"'))
    else:
        ctx.add(pth(poly_d(pts), ctx.st.f(role)))
    return pts


def cap_ll(ctx: Ctx, lat, sign, wobble=3.0):
    """A ragged polar cap as a lon/lat loop."""
    off = ctx.rng.random() * 50
    return [(lon, sign * (abs(lat) + wobble * ctx.noise.fbm(lon / 40.0 + off, off, 3))) for lon in range(-180, 180, 6)]


EARTH_LAND = """
land africa 10,37 20,32 32,31 34,27 35,24 37,20 39,15 43,12 51,12 49,7 48,5 41,-2 39,-6 40,-11 40.5,-15 35,-20 35,-24 33,-26 32,-29 30,-31 27,-33.5 20,-35 18,-34 17,-29 14.5,-22 12,-17 13.5,-12 12,-6 9,-1 9.5,4 6,4.3 2,6.3 -2,5 -8,4.5 -12,7.5 -15,11 -17,14.7 -16.5,19 -17,21 -13,27.5 -10,30 -9.5,32 -6,35.7 -1,35.2 4,36.8
land madagascar 49.3,-12 50.5,-15.5 47.5,-24.5 45,-25.5 43.5,-22 44,-17 47,-15
land eurasia -9.5,38.7 -9,43 -2,43.5 -1.2,46 -4.5,48.4 -1.5,49.7 2,51 4,52 8.5,53.7 8.2,55.5 8.6,57 10.5,57.7 10.2,56.5 10.9,55.3 11,54 14,54.2 18.5,54.7 21,55.3 21,57 24,57.3 24.3,58.5 23.5,59.3 26,59.6 28,59.5 30,59.9 31,62 30.5,64 30,66 29,67.5 30,69.5 33,69.3 41,67.2 43,66 44,68.4 53,68.7 59,69 66,69 67,71 69,73 73,73.3 73,71 75,72 80,73.5 87,75 95,76 100,77.5 105,77.5 113,74 125,73.5 130,71 140,72.5 150,71 160,69.5 170,70 180,68.8 188,67.2 190,66 186,64.5 179,62.5 177,62 172,60.5 164,59.8 163,57 162,54.5 156.7,51 155.8,57 156,61.5 150,59.5 143,59.3 137,54 141,52.5 140.5,48 135.5,43.5 131,42.5 129.5,40.5 129.3,35.2 126.5,34.5 126.5,37.5 124.5,39.8 121.5,39 121,41 118,39 119,37.2 122.5,37 120.5,36 119,34.5 121.5,31.5 122,29.5 120,26.5 117,23.5 113.5,22 110.5,21 108.5,21.5 106.5,19.5 106,17.5 108.8,15 109,12 107,10.3 105,8.7 104.8,10.5 102.5,12 100.5,13.5 99.5,10 100.5,7 102.5,5 103.5,2.3 101.5,2.8 100.3,6 98.5,8 98.5,12 97.5,16.5 94.5,16.2 94,19 92,21.5 91,22.5 88,21.5 86.5,20 85,19.5 82,16.5 80.3,15.5 80.2,13 79.8,10.3 79,9 77.5,8.1 76.3,9.8 75,12.5 73.5,16.5 72.8,19.5 72.8,21.5 70.5,20.8 69,22.3 70,24 67,24.8 62,25.2 57.5,25.7 56.5,27 54,26.7 51.5,27.8 49,30 48,29.9 48.5,28 50,26.5 51.5,24.5 54,24 56.2,26 56.5,24.5 58.5,23.5 59.8,22.5 57.5,19 55.5,17.5 52,16 49,14.5 45,12.8 43.5,12.7 42.8,16 41,20 39,22.5 38,25 35,28 34.8,29.5 32.5,30.2 34.5,31.3 35.5,33.5 36,36.5 32,36.2 28,36.7 26.5,38.5 26,40.2 23.5,40.2 24,38 22.5,36.5 21.5,37 21,39 19.5,41 19,42 16,43.5 13.5,45.5 12.3,45.2 12.5,44 14,42 16,41 18.5,40.2 17,39 16,38 15.7,40 12.5,41.5 10,43.5 8.5,44.3 6.5,43.2 3,43.2 3.2,42 0.5,40.5 -0.5,38.5 -2,36.8 -5.5,36.1 -6.5,37 -9,37
land scandinavia 5.3,58.8 6.5,58.1 8.5,58.1 10,59 11,58.8 11.8,58.9 12.2,57.5 12.6,56.2 14.3,55.5 16,56.2 16.5,57.5 18.3,59.4 17.2,61 17.5,62.5 21,64.3 24.5,65.8 25,65 24,64 21.5,61.3 22.5,60 25,60.2 28,60.5 30,60.6 31,62 30.5,64 30,66 29,67.5 30,69.5 28.5,71 25,71 20,70 15,68.5 13.5,67 12.5,65 9,63.5 7,62.5 5,61.5 5,60
land britain -5.5,50 1.5,51 1.7,52.7 0,53.5 -2,55.5 -1.8,57.5 -3.5,58.6 -5,58.5 -6,56.5 -5,55 -3,54.5 -3,53.3 -4.5,52.5 -5.2,51.7 -3.5,51.2
land ireland -10,52 -6,52.2 -6,54.5 -8,55.2 -10,54
land iceland -24,65.5 -22,66.4 -16,66.5 -14,65 -18,63.5 -22.5,63.8
land honshu 130.9,34 132.5,35.5 135.5,35.7 137,37 139.8,39 141,40.7 142,39.5 141,38 140.8,35.7 139.5,35 137.5,34.6 135.2,33.5 134.5,34.4 132.5,34.2
land kyushu 129.8,33.2 131.7,33.5 131.5,31 130.2,31.2
land hokkaido 140,42 141.5,43.3 145.5,43.3 143.5,42 141,41.8
land sakhalin 142,46 143.5,49 143,54 142,54 142,50
land novaya 52,71.5 57,75 68,77 62,74.5 56,71
land srilanka 80,9.8 81.8,7.5 81.5,6.2 80,6 79.8,8
land taiwan 120.2,23 121.5,25 122,24.5 120.8,22
land sumatra 95.3,5.5 98.5,4 103,1 106,-3 105.8,-5.8 102,-4 98.5,0.5 95.5,3
land java 105.5,-6.5 108,-6.5 111,-6.5 114.5,-7.8 114,-8.5 108,-7.8 105.5,-6.8
land borneo 109,1 110,-3 114,-4 116,-3 117,1 119,5 117,7 115,5 111,2
land sulawesi 119.5,-5.5 120.5,-1 121,1 124.5,1 123,-1 122,-3 123,-5 121,-4 120.5,-5.5
land luzon 120,18.5 122,18.3 122,14.2 120.5,14.2 120,16
land mindanao 122,8 126,8 126.5,6.5 125,6 122.5,7
land newguinea 131,-1 135,-3.5 138,-1.8 141,-2.6 145,-4.5 147.5,-6 150,-10.5 146,-8 143,-9 141,-9 138,-8.2 135,-4.5 132,-3
land australia 113.5,-22 114,-26 115,-34 118,-35 123,-34 127,-32 131,-31.5 135,-34.7 138,-35 140,-38 144,-38.5 147,-38 150,-37 153,-31 153,-25 150,-22 146,-19 145.5,-14.5 143,-11 141.5,-13 141,-17 136,-15 136,-12 132,-11.5 130,-13 127,-14 123,-17 122,-18 118,-20
land tasmania 145,-41 148,-41 147.5,-43.5 146,-43.5
land nz_north 172.7,-34.5 175,-37 178,-37.7 176,-41 174.7,-39.5 173,-35.5
land nz_south 172.7,-40.5 174,-41.5 171,-44.5 169,-46.5 166.5,-46 168.5,-44 171.5,-42
land namerica -166,68.5 -162,70 -156.5,71.3 -150,70.5 -141,69.7 -135,69 -128,70 -121,69.5 -115,68 -108,68 -100,67.8 -95,68.5 -94,71.5 -90,69 -85,69.8 -82,68 -85,66 -87,64.5 -90,64 -94,62 -94,59.5 -92.5,57 -88,56 -85,55.2 -82.5,55.2 -82,53 -80,51.5 -79,52.5 -78.8,56 -77,58 -78,60.5 -77.5,62.3 -73,62 -70,60.5 -65,60.2 -62,57.5 -60.5,55.5 -57,53 -59,50.5 -64,50.3 -66.5,50 -70,47.5 -65.5,49 -64,48.5 -65,47.5 -62,46 -60.5,46.2 -61,45.5 -63.5,44.5 -66,43.7 -67,44.8 -70,43.7 -70.5,42 -70,41.6 -72,41 -74,40.5 -74,39 -75.5,37.5 -76,35.3 -78,34 -80.5,32 -81.2,30 -80,27 -80.2,25.5 -81.2,25.2 -82,26.5 -82.8,28.5 -83.5,30 -85,29.7 -88,30.3 -89.5,30.1 -89,29 -91.5,29.5 -94,29.6 -96.5,28 -97.3,26 -97.7,22 -97,20.5 -96,19 -94.5,18.2 -92,18.6 -91,19.2 -90.5,21 -87,21.5 -87.5,19 -88,17 -88.8,15.8 -86,15.9 -83.5,15.2 -83.5,11 -82,9 -79.5,9.5 -77.5,8.5 -78,7.5 -80,7.3 -83,8.2 -85.7,10 -87.5,13 -91,14 -94,16 -97,15.7 -101,17.3 -105.5,20 -106,23 -109,25.5 -111,27.5 -113,31 -114.8,31.8 -114,30 -112.5,27.5 -110,24 -109.5,23 -112,24.5 -114.5,27.5 -116,30 -117,32.5 -118.5,34 -120.5,34.5 -122.5,37.7 -124,40.3 -124.5,43 -124,46.5 -123,48.3 -125,49.5 -128,51 -130,54.5 -134,57.5 -137,58.5 -141,60 -146,60.7 -150.5,59.5 -154,58.5 -158,56.5 -163,54.8 -160,56.5 -157.5,58.5 -162,58.7 -165,60.5 -165,62.5 -161,64.5 -166,65 -168,65.7 -163,67
land baffin -80,73.5 -70,71 -62,67 -65,63 -72,63.5 -78,64.5 -74,68 -85,70 -90,72.5
land victoria -118,71.5 -105,73 -100,70 -110,68.8
land ellesmere -90,76.5 -80,83 -62,82.5 -76,78.5 -80,77
land cuba -85,22 -82,23.2 -77,21.6 -74.2,20.2 -77.5,19.9 -82,22.3
land hispaniola -74.4,18.5 -72.5,19.8 -69,19 -69.5,18.3 -72,18
land newfoundland -59.3,47.6 -55,51.5 -52.8,48 -53,46.7 -56,47.6
land samerica -77.3,8.8 -75.5,10.8 -72,12 -71.3,11.8 -68,10.5 -64,10.6 -61,10.5 -60,8.5 -57,6 -54,5.8 -51.5,4.2 -50,1.5 -50,0 -48,-1 -44,-2.5 -40,-3 -37,-5 -35,-6.5 -35,-9 -37,-12 -39,-14 -39,-18 -41,-22 -44,-23 -48,-25.5 -48.5,-28 -51,-31 -53,-34 -56,-34.8 -57.5,-36 -57,-38 -62,-39 -62.5,-41 -65,-41 -64,-43 -66,-45 -67.5,-46.5 -65.5,-48 -68.5,-50.5 -69,-52.5 -68,-54.5 -72,-53.7 -74,-52 -75.5,-48 -74,-43 -73.5,-38 -71.5,-32 -71.5,-28 -70.3,-23 -70.3,-18.5 -76,-14 -77.8,-10 -79.5,-7 -81.2,-5.8 -80,-3 -81,-1 -80,1 -78.8,2.5 -77.4,4 -77.5,7
ice greenland -73,78.5 -66,81 -50,82 -30,83.5 -20,81.5 -18,77 -22,72 -22,70.5 -26,68.5 -32,67.5 -40,65 -43,60 -48,61 -52,64.5 -54,67 -52,70 -56,73 -62,76.5 -68,76.8
ice antarctica -180,-78 -160,-77 -140,-75.5 -120,-74 -100,-73.5 -80,-73 -70,-70 -62,-64.5 -57,-63.3 -62,-67 -60,-73 -45,-78 -30,-76 -15,-72 0,-70 30,-69.5 60,-67.5 80,-68 100,-66.5 120,-66 140,-66.5 160,-70.5 170,-72
sea blacksea 28,41.5 31,41.2 36,41.7 41.5,41.5 41.8,43 39,44.5 37.5,45 35.5,45.3 33,44.4 32,46 30.5,46.4 29.5,45.2 28.5,43.5
sea caspian 47,45 49,46.5 53,47 54,45 52.5,42 53,40 54,37.3 51,36.7 49,38 49.5,40.5 50,44
"""
EARTH_VIEWS = [(15, 22), (-85, 15), (95, 25), (140, -12), (-58, -12), (30, 30), (-110, 30)]


def draw_earth(ctx: Ctx) -> None:
    rng = ctx.rng
    place(ctx, 0.42 * ctx.U, globe=True)
    lon0, lat0 = ctx.args.center or rng.choice(EARTH_VIEWS)
    g = Globe(ctx, lon0, lat0)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)                                        # ocean
    seas = []
    for line in EARTH_LAND.strip().splitlines():
        kind, _name, coords = line.split(" ", 2)
        ll = parse_ll(coords)
        if kind == "sea":
            seas.append(ll)
        else:
            draw_ll(ctx, g, ll, "dark" if kind == "land" else "bright")
    for ll in seas:
        draw_ll(ctx, g, ll, "main")
    draw_ll(ctx, g, cap_ll(ctx, 80, 1), "bright")         # sea ice around the poles
    for _ in range(15 if not ctx.partial else 9):         # cloud streaks
        lat = rng.choice((rng.uniform(-14, 14), rng.uniform(-14, 14), rng.uniform(30, 58) * rng.choice((1, -1))))
        lon = lon0 + rng.uniform(-80, 80)
        ll = ll_blob(ctx, lon, lat, rng.uniform(6, 17), rng.uniform(1.0, 2.6), rng.uniform(-0.4, 0.4), 0.5, 18)
        draw_ll(ctx, g, ll, "bright", amp=0.002, seam=False)
    close_disc(ctx)


# --------------------------------------------------------------------------- #
# Mars and Pluto
# --------------------------------------------------------------------------- #
MARS_DARK = [  # lon (east), lat, rx, ry (deg), rotation
    (69, 9, 6, 12, 0.25), (-10, -5, 22, 4.5, 0.0), (-30, 47, 22, 9, 0.0), (-90, -27, 8, 6, 0.0),
    (-150, -37, 30, 6, 0.1), (-145, -20, 24, 5, -0.1), (-105, -15, 14, 7, 0.0), (-60, -12, 26, 1.5, 0.06),
    (-120, -9, 3, 3, 0), (-113, 1, 3, 3, 0), (-104, 11, 3, 3, 0), (40, -30, 10, 5, 0.3), (110, 30, 12, 6, 0.2),
]
MARS_BRIGHT = [(70, -42, 13, 10, 0), (-43, -50, 9, 7, 0), (-134, 18, 4.5, 4.5, 0), (-65, 30, 18, 5, 0.1)]
MARS_VIEWS = [(70, 8), (-90, 5), (0, 0), (-140, 0), (-30, 20), (150, 5)]


def draw_mars(ctx: Ctx) -> None:
    rng = ctx.rng
    place(ctx, 0.42 * ctx.U, globe=True)
    lon0, lat0 = ctx.args.center or rng.choice(MARS_VIEWS)
    g = Globe(ctx, lon0, lat0 + (rng.uniform(-8, 8) if not ctx.args.center else 0))
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)
    for lon, lat, rx, ry, rot in MARS_BRIGHT:
        draw_ll(ctx, g, ll_blob(ctx, lon, lat, rx, ry, rot, 0.3), "bright", amp=0.003)
    for lon, lat, rx, ry, rot in MARS_DARK:
        draw_ll(ctx, g, ll_blob(ctx, lon, lat, rx * 1.3, ry * 1.3, rot, 0.4), "dark", amp=0.004)
    for _ in range(14):                                   # speckle of small dark and bright patches
        lon, lat = rng.uniform(-180, 180), rng.uniform(-60, 60)
        draw_ll(ctx, g, ll_blob(ctx, lon, lat, rng.uniform(3, 8), rng.uniform(2, 5), rng.uniform(0, 3), 0.5, 14),
                rng.choice(("dark", "bright")), amp=0.003, seam=False)
    if ctx.partial:                                        # close-up: mottled ground and craters
        for _ in range(48):
            lon, lat = lon0 + rng.uniform(-40, 40), max(-80, min(80, lat0 + rng.uniform(-30, 30)))
            draw_ll(ctx, g, ll_blob(ctx, lon, lat, rng.uniform(1.5, 6), rng.uniform(1, 4), rng.uniform(0, 3), 0.5, 12),
                    rng.choice(("dark", "dark", "bright")), amp=0.003, seam=False)
        crater_defs(ctx)
        scatter_craters(ctx, [], 0.006 * ctx.U, 0.16 * ctx.U, 0.006)
    draw_ll(ctx, g, cap_ll(ctx, 82, 1, 3), "bright")
    draw_ll(ctx, g, cap_ll(ctx, 78, -1, 4), "bright")
    close_disc(ctx)


def draw_pluto(ctx: Ctx) -> None:
    rng = ctx.rng
    place(ctx, 0.40 * ctx.U, globe=True)
    lon0, lat0 = ctx.args.center or (rng.uniform(150, 200), rng.uniform(5, 25))
    g = Globe(ctx, lon0, lat0)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)
    draw_ll(ctx, g, ll_blob(ctx, 100, -8, 42, 13, 0.0, 0.35), "dark")            # Cthulhu Macula
    draw_ll(ctx, g, ll_blob(ctx, 55, 12, 18, 8, 0.4, 0.4), "dark")
    for _ in range(12):
        lon, lat = lon0 + rng.uniform(-110, 110), rng.uniform(-40, 40)
        draw_ll(ctx, g, ll_blob(ctx, lon, lat, rng.uniform(4, 11), rng.uniform(3, 8), rng.uniform(0, 3), 0.5, 14),
                rng.choice(("dark", "bright", "dark")), amp=0.003, seam=False)
    heart = []                                             # Tombaugh Regio
    for i in range(48):
        t = TAU * i / 48
        hx = 16 * math.sin(t) ** 3
        hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        heart.append((178 + 1.6 * hx / math.cos(math.radians(18)), 18 + 1.5 * (hy - 2)))
    draw_ll(ctx, g, heart, "bright", amp=0.003)
    close_disc(ctx)


# --------------------------------------------------------------------------- #
# Cratered worlds: Moon, Mercury
# --------------------------------------------------------------------------- #
def crater_defs(ctx: Ctx) -> None:
    """Two reusable unit-circle crater symbols, lit from the upper left."""
    st = ctx.st
    floor = st.f("bright") if st.mono else st.f("main")
    ctx.defs.append(
        f'<g id="crh"><circle r="1" fill="{floor}" stroke="{st.s("dark")}" stroke-width="0.16"/>'
        f'<path d="{crescent_d(0.34, 0.34)}" fill="{st.f("dark")}" transform="scale(0.88)"/>'
        f'<path d="{crescent_d(-0.3, -0.3)}" fill="{st.f("bright")}" transform="scale(0.88)"/></g>')
    ctx.defs.append(
        f'<g id="crm"><circle r="1" fill="{st.f("dark")}" stroke="{st.s("bright")}" stroke-width="0.14"/></g>')


def rand_pt(ctx: Ctx, rho_max=0.95):
    """Random point on the page that lies inside the disc."""
    for _ in range(500):
        x, y = ctx.rng.uniform(0, ctx.W), ctx.rng.uniform(0, ctx.H)
        if math.hypot(x - ctx.cx, y - ctx.cy) <= rho_max * ctx.R:
            return x, y
    return ctx.cx, ctx.cy


def scatter_craters(ctx: Ctx, maria, rmin, rmax, density, maxn=900) -> None:
    rng, R = ctx.rng, ctx.R
    area = ctx.W * ctx.H if ctx.partial else math.pi * R * R
    n = min(maxn, int(density * area / (rmin * rmin)))
    boxes = [(min(p[0] for p in poly), max(p[0] for p in poly), min(p[1] for p in poly),
              max(p[1] for p in poly), poly) for poly in maria]
    items, tries = [], 0
    while len(items) < n and tries < n * 6:
        tries += 1
        x, y = rng.uniform(0, ctx.W), rng.uniform(0, ctx.H)
        dx, dy = x - ctx.cx, y - ctx.cy
        d = math.hypot(dx, dy)
        if d / R > 0.985:
            continue
        r = min(rmax, rmin * max(rng.random(), 1e-4) ** (-1 / 1.8))   # power-law sizes
        items.append((r, x, y, d, dx, dy))
    items.sort(reverse=True)                              # big and old first, small and new on top
    placed = []
    for r, x, y, d, dx, dy in items:
        if any((x - px) ** 2 + (y - py) ** 2 < (0.75 * (r + pr)) ** 2 for pr, px, py in placed):
            continue
        placed.append((r, x, y))
        z = math.sqrt(max(0.0, 1 - (d / R) ** 2))
        sq = max(0.2, z)                                  # foreshortening toward the limb
        ux, uy = (dx / d, dy / d) if d > 1e-6 else (1.0, 0.0)
        a, b, c = 1 - (1 - sq) * ux * ux, -(1 - sq) * ux * uy, 1 - (1 - sq) * uy * uy
        in_mare = any(x0 <= x <= x1 and y0 <= y <= y1 and pip(x, y, poly) for x0, x1, y0, y1, poly in boxes)
        ctx.add(f'<use xlink:href="#{"crm" if in_mare else "crh"}" transform="matrix('
                f'{fmt(r * a, 3)} {fmt(r * b, 3)} {fmt(r * b, 3)} {fmt(r * c, 3)} {fmt(x)} {fmt(y)})"/>')


def rays(ctx: Ctx, x, y, n, length, width) -> None:
    rng = ctx.rng
    for _ in range(n):
        a = rng.uniform(0, TAU)
        L, w = length * rng.uniform(0.25, 1.0), width * rng.uniform(0.5, 1.3)
        px, py = -math.sin(a) * w, math.cos(a) * w
        tip = (x + math.cos(a) * L, y + math.sin(a) * L)
        ctx.add(pth(poly_d([(x + px, y + py), tip, (x - px, y - py)]), ctx.st.f("bright")))


MOON_MARIA = [  # lon, lat, rx, ry (degrees), rotation
    (59, 17, 7, 5, 0), (18, 28, 8, 8, 0), (31, 9, 11, 7, -0.2), (52, -5, 8, 10, 0.2), (34, -15, 5, 5, 0),
    (-17, 33, 14, 11, 0), (0, 57, 22, 4, 0), (-57, 15, 20, 22, 0), (-15, -21, 10, 7, 0), (-39, -24, 6, 6, 0),
    (-23, -10, 6, 5, 0), (-22, 8, 10, 6, 0), (3, 13, 5, 4, 0), (87, 2, 3, 3, 0), (86, 13, 4, 3, 0),
]
MOON_BRIGHT = [  # name-less rayed craters: lon, lat, ray count, ray length (x R), crater radius (x R)
    (-11, -43, 26, 0.85, 0.028), (-20, 10, 12, 0.26, 0.026), (-38, 8, 7, 0.14, 0.016), (-47, 23, 5, 0.1, 0.016),
]


def draw_moon(ctx: Ctx) -> None:
    rng, U = ctx.rng, ctx.U
    place(ctx, 0.42 * U, globe=True)
    if ctx.args.center:
        lon0, lat0 = ctx.args.center
    elif ctx.partial:
        lon0, lat0 = rng.uniform(-50, 50), rng.uniform(-25, 35)
    else:
        lon0, lat0 = 0.0, 0.0
    g = Globe(ctx, lon0, lat0)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)
    crater_defs(ctx)
    maria = []
    for lon, lat, rx, ry, rot in MOON_MARIA:
        pts = draw_ll(ctx, g, ll_blob(ctx, lon, lat, rx, ry, rot, 0.38, 24), "dark", amp=0.005)
        if pts:
            maria.append(pts)
    for lon, lat, n, length, rad in MOON_BRIGHT:
        x, y, z = g.screen(lon, lat)
        if z > 0.05:
            rays(ctx, x, y, n, length * ctx.R, 0.006 * ctx.R)
    full = not ctx.partial
    scatter_craters(ctx, maria, (0.0035 if full else 0.006) * U, (0.085 * ctx.R) if full else 0.18 * U, 0.0065)
    for lon, lat, n, length, rad in MOON_BRIGHT:           # the bright rayed craters themselves
        x, y, z = g.screen(lon, lat)
        if z > 0.05:
            ctx.add(circ(x, y, rad * ctx.R, ctx.st.f("bright"), f' stroke="{ctx.st.s("dark")}" stroke-width="{fmt(rad * ctx.R * 0.16)}"'))
    close_disc(ctx)


def draw_mercury(ctx: Ctx) -> None:
    rng, U = ctx.rng, ctx.U
    place(ctx, 0.42 * U)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)
    crater_defs(ctx)
    plains = []
    for _ in range(2):                                     # smooth plains / basins
        x, y = rand_pt(ctx, 0.7)
        pts = blob_pts(ctx, x, y, U * rng.uniform(0.05, 0.1), U * rng.uniform(0.04, 0.08), rng.uniform(0, 3), 0.4, 20)
        ctx.add(pth(smooth_d(pts), ctx.st.f("dark")))
        plains.append(pts)
    for _ in range(2):
        x, y = rand_pt(ctx, 0.7)
        rays(ctx, x, y, 20, ctx.R * 0.5, 0.005 * ctx.R)
    full = not ctx.partial
    scatter_craters(ctx, plains, (0.004 if full else 0.007) * U, (0.1 * ctx.R) if full else 0.2 * U, 0.022)
    close_disc(ctx)


# --------------------------------------------------------------------------- #
# Io and Europa
# --------------------------------------------------------------------------- #
def draw_io(ctx: Ctx) -> None:
    rng, U, st = ctx.rng, ctx.U, ctx.st
    place(ctx, 0.40 * U)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)
    for _ in range(9 if not ctx.partial else 12):         # frost patches
        x, y = rand_pt(ctx)
        ctx.add(pth(smooth_d(blob_pts(ctx, x, y, U * rng.uniform(0.025, 0.07), U * rng.uniform(0.02, 0.05),
                                      rng.uniform(0, 3), 0.5, 16)), st.f("bright")))
    for _ in range(16):                                    # dark volcanic deposits
        x, y = rand_pt(ctx)
        ctx.add(pth(smooth_d(blob_pts(ctx, x, y, U * rng.uniform(0.02, 0.05), U * rng.uniform(0.015, 0.035),
                                      rng.uniform(0, 3), 0.5, 14)), st.f("dark")))
    for i in range(40 if not ctx.partial else 64):         # paterae: dark vents with pale halos
        x, y = rand_pt(ctx)
        r = U * (rng.uniform(0.007, 0.026) if i else 0.045)
        ctx.add(pth(smooth_d(blob_pts(ctx, x, y, r * rng.uniform(1.5, 2.1), r * rng.uniform(1.4, 1.9),
                                      rng.uniform(0, 3), 0.3, 14)), st.f("bright")))
        ctx.add(pth(smooth_d(blob_pts(ctx, x, y, r, r * rng.uniform(0.7, 1.0), rng.uniform(0, 3), 0.35, 12)),
                    st.f("dark")))
    close_disc(ctx)


def _wander(ctx: Ctx, x, y, a, L, step, curv):
    rng = ctx.rng
    n = max(2, int(L / step / 2))

    def walk(ang):
        pts, px, py = [], x, y
        for _ in range(n):
            ang += rng.gauss(0, curv)
            px, py = px + math.cos(ang) * step, py + math.sin(ang) * step
            pts.append((px, py))
        return pts

    return walk(a + math.pi)[::-1] + [(x, y)] + walk(a)


def draw_europa(ctx: Ctx) -> None:
    rng, U, st = ctx.rng, ctx.U, ctx.st
    place(ctx, 0.40 * U)
    starfield(ctx, [(ctx.cx, ctx.cy, ctx.R * 1.08)])
    open_disc(ctx)
    for _ in range(10):                                    # mottled chaos terrain
        x, y = rand_pt(ctx)
        ctx.add(pth(smooth_d(blob_pts(ctx, x, y, U * rng.uniform(0.015, 0.05), U * rng.uniform(0.012, 0.035),
                                      rng.uniform(0, 3), 0.5, 14)), st.f("dark")))
    reach = min(ctx.R * 1.6, 0.9 * max(ctx.W, ctx.H))
    for _ in range(40 if not ctx.partial else 30):         # the famous cracks (lineae)
        x, y = rand_pt(ctx, 0.97)
        pts = _wander(ctx, x, y, rng.uniform(0, TAU), rng.uniform(0.3, 1.0) * reach, 0.012 * U, 0.05)
        w = U * rng.uniform(0.003, 0.011)
        d = smooth_d(pts, closed=False)
        ctx.add(pth(d, "none", st.s("dark"), w, ' stroke-linecap="round" stroke-linejoin="round"'))
        if w > U * 0.006:
            ctx.add(pth(d, "none", st.s("bright"), w * 0.3, ' stroke-linecap="round" stroke-linejoin="round"'))
    close_disc(ctx)


# --------------------------------------------------------------------------- #
# The Sun
# --------------------------------------------------------------------------- #
def _sunspot(ctx: Ctx, x, y, r) -> None:
    st, rng = ctx.st, ctx.rng
    rot = rng.uniform(0, 3)
    ctx.add(pth(smooth_d(blob_pts(ctx, x, y, r, r * rng.uniform(0.75, 1.0), rot, 0.22, 14)),
                st.f("main"), st.s("dark"), r * 0.07))
    ctx.add(pth(smooth_d(blob_pts(ctx, x + r * 0.05, y, r * 0.5, r * 0.42, rot, 0.3, 12)), st.f("dark")))


def draw_sun(ctx: Ctx) -> None:
    rng, U, st, W, H = ctx.rng, ctx.U, ctx.st, ctx.W, ctx.H
    place(ctx, 0.30 * U, fmax=0.2)
    R, cx, cy = ctx.R, ctx.cx, ctx.cy
    if not ctx.partial:
        starfield(ctx, [(cx, cy, R * 1.8)])
        n = 84
        for i in range(n):                                  # corona streamers
            a = TAU * i / n + rng.uniform(-0.02, 0.02)
            L, w = R * (0.08 + 0.5 * rng.random() ** 2.2), TAU / n * 0.42
            p = [(cx + math.cos(a - w) * R * 0.96, cy + math.sin(a - w) * R * 0.96),
                 (cx + math.cos(a) * (R + L), cy + math.sin(a) * (R + L)),
                 (cx + math.cos(a + w) * R * 0.96, cy + math.sin(a + w) * R * 0.96)]
            ctx.add(pth(poly_d(p), st.f("bright")))
        for _ in range(5):                                  # prominences
            a, d, h = rng.uniform(0, TAU), rng.uniform(0.07, 0.16), rng.uniform(1.45, 1.9)
            P = lambda ang, k: (cx + math.cos(ang) * R * k, cy + math.sin(ang) * R * k)
            p0, c, p1 = P(a - d, 0.99), P(a, h), P(a + d, 0.99)
            ctx.add(pth(f"M{fmt(p0[0])} {fmt(p0[1])}Q{fmt(c[0])} {fmt(c[1])} {fmt(p1[0])} {fmt(p1[1])}",
                        "none", st.s("main"), R * 0.05, ' stroke-linecap="round"'))
    open_disc(ctx)
    s = R / 15 if not ctx.partial else math.hypot(W, H) / 34       # granule spacing
    if ctx.partial:
        j0, j1, x0, x1 = -1, int(H / (0.866 * s)) + 2, -s, W + s
        ox, oy = 0.0, 0.0
    else:
        j0, j1 = -int(R / (0.866 * s)) - 1, int(R / (0.866 * s)) + 2
        x0, x1 = cx - R - s, cx + R + s
        ox, oy = cx, cy
    for j in range(j0, j1):
        y = oy + j * 0.866 * s
        x = x0 + (0.5 * s if j & 1 else 0.0)
        while x < x1:
            gx, gy = x + rng.uniform(-0.18, 0.18) * s, y + rng.uniform(-0.18, 0.18) * s
            x += s
            if not ctx.partial and math.hypot(gx - cx, gy - cy) > R + s:
                continue
            if ctx.partial and not ctx.on_page(gx, gy, s):
                continue
            if rng.random() < 0.08:
                if rng.random() < 0.5:
                    ctx.add(circ(gx, gy, s * 0.09, st.f("dark")))
                continue
            rg = s * 0.5 * rng.uniform(0.8, 1.05)
            ctx.add(ell(gx, gy, rg, rg * rng.uniform(0.82, 1.0), st.f("bright")))
    if ctx.partial:
        gx, gy = W / 2 + rng.uniform(-0.1, 0.1) * U, H / 2 + rng.uniform(-0.1, 0.1) * U
        r = 0.11 * U
        _sunspot(ctx, gx, gy, r)
        for k in range(2):
            a = rng.uniform(0, TAU)
            _sunspot(ctx, gx + math.cos(a) * r * 2.3, gy + math.sin(a) * r * 2.3, r * rng.uniform(0.4, 0.6))
        for _ in range(7):
            a, d = rng.uniform(0, TAU), r * rng.uniform(1.6, 3.4)
            ctx.add(circ(gx + math.cos(a) * d, gy + math.sin(a) * d, r * rng.uniform(0.05, 0.1), st.f("dark")))
    else:
        for _ in range(2):
            a, d = rng.uniform(0, TAU), R * rng.uniform(0.12, 0.62)
            gx, gy = cx + math.cos(a) * d, cy + math.sin(a) * d
            r = R * rng.uniform(0.05, 0.085)
            _sunspot(ctx, gx, gy, r)
            for _k in range(rng.randint(1, 2)):
                b = rng.uniform(0, TAU)
                _sunspot(ctx, gx + math.cos(b) * r * 2.2, gy + math.sin(b) * r * 2.2, r * rng.uniform(0.4, 0.6))
            for _k in range(3):
                b, dd = rng.uniform(0, TAU), r * rng.uniform(1.5, 3.0)
                ctx.add(circ(gx + math.cos(b) * dd, gy + math.sin(b) * dd, r * 0.09, st.f("dark")))
    close_disc(ctx)


# --------------------------------------------------------------------------- #
# Constellations: real positions (RA hours, Dec degrees, magnitude), stick figures
# --------------------------------------------------------------------------- #
def _c(title, stars, lines):
    st = {}
    for item in stars.split(";"):
        k, ra, dec, mag = item.split()
        st[k] = (float(ra), float(dec), float(mag))
    return title, st, [ch.split() for ch in lines.split(";")]


CONSTELLATIONS = {
    "orion": _c("Orion",
        "bet 5.919 7.407 0.5;rig 5.242 -8.202 0.13;bel 5.419 6.350 1.64;sai 5.796 -9.670 2.06;min 5.533 -0.299 2.23;"
        "aln 5.603 -1.202 1.69;alt 5.679 -1.943 1.77;mei 5.586 9.934 3.54;pi1 4.755 10.151 4.7;pi2 4.830 8.900 4.36;"
        "pi3 4.831 6.961 3.19;pi4 4.901 5.605 3.69;pi5 4.976 2.441 3.72;pi6 5.003 1.714 4.47;s42 5.585 -4.838 4.59;"
        "the 5.588 -5.41 2.8;iot 5.592 -5.91 2.77;mu 6.039 9.647 4.12;xi 6.201 14.21 4.48",
        "mei bet;mei bel;bet alt;bel min;alt aln min;alt sai;min rig;bel pi3;pi1 pi2 pi3 pi4 pi5 pi6;"
        "aln s42 the iot;bet mu xi"),
    "ursa-major": _c("Ursa Major",
        "dub 11.062 61.751 1.79;mer 11.031 56.382 2.37;phe 11.897 53.695 2.44;meg 12.257 57.033 3.31;"
        "ali 12.900 55.960 1.77;miz 13.399 54.925 2.04;alk 13.792 49.313 1.86;h23 9.529 63.062 3.67;"
        "mus 8.504 60.718 3.36;the 9.547 51.678 3.17;tal 8.987 48.042 3.14;kap 9.061 47.157 3.60;"
        "chi 11.767 47.779 3.71;psi 11.161 44.499 3.01;lam 10.285 42.914 3.45;mu 10.372 41.499 3.05;"
        "nu 11.308 33.094 3.48;xi 11.303 31.529 3.79",
        "dub mer phe meg dub;meg ali miz alk;dub h23 mus;mer the tal kap;phe chi psi;psi lam mu;psi nu xi"),
    "ursa-minor": _c("Ursa Minor",
        "pol 2.530 89.264 1.98;yil 17.537 86.586 4.36;eps 16.766 82.037 4.21;zet 15.734 77.795 4.32;"
        "eta 16.292 75.755 4.95;gam 15.345 71.834 3.05;bet 14.845 74.156 2.08",
        "pol yil eps zet eta gam bet zet"),
    "cassiopeia": _c("Cassiopeia",
        "cap 0.153 59.150 2.28;sch 0.675 56.537 2.24;gam 0.945 60.717 2.47;rus 1.430 60.235 2.68;seg 1.907 63.670 3.38",
        "cap sch gam rus seg"),
    "cygnus": _c("Cygnus",
        "den 20.690 45.280 1.25;sad 20.370 40.257 2.23;alb 19.512 27.960 3.18;gie 20.770 33.970 2.46;"
        "del 19.750 45.131 2.87;eta 19.938 35.083 3.89",
        "den sad eta alb;del sad gie"),
    "scorpius": _c("Scorpius",
        "acr 16.090 -19.805 2.62;dsc 16.005 -22.622 2.32;pi 15.980 -26.114 2.89;sig 16.353 -25.593 2.89;"
        "ant 16.490 -26.432 1.06;tau 16.598 -28.216 2.82;eps 16.836 -34.293 2.29;mu1 16.865 -38.047 3.0;"
        "zet 16.909 -42.362 3.62;eta 17.203 -43.239 3.33;the 17.622 -42.998 1.87;iot 17.793 -40.127 3.0;"
        "kap 17.708 -39.030 2.41;lam 17.560 -37.104 1.62;ups 17.513 -37.296 2.7",
        "acr dsc pi;dsc sig ant tau eps mu1 zet eta the iot kap lam ups"),
    "leo": _c("Leo",
        "reg 10.140 11.967 1.36;den 11.818 14.572 2.14;alg 10.333 19.842 2.01;zos 11.235 20.524 2.56;"
        "cht 11.237 15.430 3.33;adh 10.278 23.417 3.44;ras 9.879 26.007 3.88;eps 9.764 23.774 2.98;"
        "eta 10.122 16.763 3.52",
        "reg eta alg adh ras eps;alg zos den cht zos;cht reg"),
    "crux": _c("Crux",
        "acr 12.443 -63.099 0.77;mim 12.795 -59.689 1.25;gac 12.519 -57.113 1.63;imi 12.252 -58.749 2.79;"
        "eps 12.354 -60.401 3.59",
        "gac acr;mim imi"),
    "gemini": _c("Gemini",
        "cas 7.577 31.889 1.58;pol 7.755 28.026 1.14;alh 6.629 16.399 1.93;meb 6.732 25.131 3.06;"
        "tej 6.383 22.514 2.88;pro 6.248 22.507 3.28;was 7.335 21.982 3.53;mek 7.069 20.570 3.79;lam 7.180 16.540 3.58",
        "cas meb tej pro;pol was mek alh;meb was;was lam"),
    "taurus": _c("Taurus",
        "ald 4.599 16.509 0.85;eln 5.438 28.608 1.65;zet 5.627 21.143 3.0;gam 4.330 15.628 3.65;"
        "del 4.382 17.543 3.76;eps 4.477 19.180 3.53;the 4.478 15.871 3.4;lam 4.011 12.490 3.47;"
        "alc 3.791 24.105 2.87;atl 3.820 24.053 3.62;ele 3.748 24.113 3.70;mai 3.763 24.368 3.87;"
        "mer 3.772 23.948 4.18;tay 3.753 24.467 4.3",
        "lam gam the ald;gam del eps eln;ald zet"),
    "lyra": _c("Lyra",
        "veg 18.616 38.784 0.03;she 18.834 33.363 3.52;sul 18.982 32.690 3.24;del 18.908 36.899 4.3;"
        "zet 18.746 37.605 4.36",
        "veg zet;zet del sul she zet"),
    "aquila": _c("Aquila",
        "alt 19.846 8.868 0.76;tar 19.771 10.613 2.72;als 19.922 6.407 3.71;del 19.425 3.115 3.36;"
        "zet 19.090 13.863 2.99;lam 19.104 -4.882 3.44;the 20.188 -0.821 3.23;eta 19.875 1.006 3.9",
        "tar alt als;alt del lam;alt eta the;tar zet"),
    "canis-major": _c("Canis Major",
        "sir 6.752 -16.716 -1.46;mir 6.378 -17.956 1.98;mul 7.063 -15.633 4.1;wez 7.140 -26.393 1.84;"
        "adh 6.977 -28.972 1.5;alu 7.402 -29.303 2.45;fur 6.339 -30.063 3.0;o2 7.050 -23.833 3.0",
        "mir sir mul;sir o2 wez adh fur;wez alu"),
    "pegasus": _c("Pegasus",
        "mak 23.079 15.205 2.49;sch 23.063 28.083 2.42;alg 0.221 15.184 2.83;alp 0.139 29.091 2.07;"
        "eni 21.736 9.875 2.39;hom 22.691 10.831 3.4;mat 22.717 30.221 2.94;sad 22.834 24.601 3.5;bih 22.170 6.198 3.53",
        "mak sch alp alg mak;mak hom bih eni;sch mat;mak sad"),
    "sagittarius": _c("Sagittarius",
        "kau 18.403 -34.385 1.85;kam 18.350 -29.828 2.72;kab 18.466 -25.422 2.81;nun 18.921 -26.297 2.02;"
        "asc 19.043 -29.880 2.6;tau 19.116 -27.670 3.32;phi 18.761 -26.991 3.17;aln 18.097 -30.424 2.99;"
        "eta 18.294 -36.762 3.11;pi 19.160 -21.024 2.89",
        "kau asc tau nun phi kab kam kau;kam aln;kau eta;kab pi"),
    "aries": _c("Aries",
        "ham 2.120 23.462 2.00;she 1.911 20.808 2.64;mes 1.892 19.294 3.86;c41 2.832 27.261 3.63",
        "c41 ham she mes"),
    "cancer": _c("Cancer",
        "alp 8.975 11.858 4.25;bet 8.275 9.185 3.52;del 8.745 18.154 3.94;gam 8.721 21.469 4.66;"
        "iot 8.778 28.765 4.02",
        "bet del;del gam iot;del alp"),
    "virgo": _c("Virgo",
        "spi 13.420 -11.161 0.97;por 12.694 -1.449 2.74;vin 13.036 10.959 2.83;zav 11.845 1.765 3.59;"
        "hez 13.578 -0.596 3.37;mil 12.927 3.397 3.38;zan 12.332 -0.668 3.89;tau 14.0 1.544 4.26;"
        "v109 14.77 1.893 3.72;iot 14.267 -6.001 4.08;mu 14.719 -5.658 3.88",
        "zav zan por hez spi;por mil vin;hez tau v109;hez iot mu"),
    "libra": _c("Libra",
        "alp 14.848 -16.042 2.75;bet 15.283 -9.383 2.61;gam 15.592 -14.789 3.91;sig 15.068 -25.282 3.29;"
        "ups 15.617 -28.135 3.58;tau 15.644 -29.778 3.66",
        "alp bet gam ups sig alp;ups tau"),
    "capricornus": _c("Capricornus",
        "alp 20.300 -12.545 3.57;bet 20.350 -14.781 3.05;psi 20.768 -25.271 4.14;ome 20.859 -26.919 4.11;"
        "zet 21.447 -22.411 3.74;del 21.784 -16.127 2.87;gam 21.668 -16.662 3.68;iot 21.370 -16.835 4.28;"
        "the 21.099 -17.233 4.07",
        "alp the iot gam del zet ome psi bet alp"),
    "aquarius": _c("Aquarius",
        "bet 21.526 -5.571 2.91;alp 22.096 -0.320 2.96;del 22.911 -15.821 3.27;gam 22.361 -1.387 3.84;"
        "zet 22.480 -0.020 3.65;eta 22.589 -0.117 4.0;pi 22.421 1.377 4.66;eps 20.795 -9.496 3.77;"
        "lam 22.877 -7.579 3.74;tau 22.826 -13.592 4.01;phi 23.240 -6.049 4.22",
        "eps bet alp zet;gam zet eta pi gam;eta lam tau del;lam phi"),
    "pisces": _c("Pisces",
        "kap 23.449 1.256 4.94;gam 23.286 3.282 3.69;the 23.466 6.379 4.28;iot 23.665 5.626 4.13;"
        "lam 23.700 1.780 4.50;ome 23.988 6.863 4.01;del 0.811 7.585 4.43;eps 1.049 7.890 4.28;"
        "mu 1.230 6.137 4.84;nu 1.688 5.488 4.44;alp 2.034 2.764 3.82;omi 1.756 9.157 4.26;"
        "eta 1.524 15.346 3.62",
        "kap gam the iot lam kap;iot ome del eps mu nu alp;alp omi eta"),
}



# --- illustrated style: creature silhouettes, star names, asterism labels ----------------
# Shapes are written in sky-degrees (x right, y down) relative to each figure's tangent point,
# in the upright frame of the figure's default rotation `rot`, so they stay aligned with the real
# stars at any page size or rotation.
#   c x0 y0 x1 y1 w0 w1   tapered capsule (limb, body)      e cx cy rx ry rot   ellipse (rot clockwise)
#   p x y x y ...         smooth closed blob (wing, mane)   d x y x y ...       thin detail line
#   o cx cy r             small detail dot (eye)
ART = {
    "leo": dict(rot=40, solid=[0], shapes=(
        "e 3.8 -10.2 3.4 2.7 15; e 6.6 -9.4 1.9 1.4 25; e 1.4 -12.6 0.9 1.1 0; e 0.2 -7.6 4.4 5.2 15; e 1.2 -3.2 3.3 3.3 0;"
        "c 1.5 -4 -6 6 2.6 3.0; e -7 6.5 3.2 3.8 -20; c -7 6 -5.3 9.3 2.8 1.8; c -5.3 9.3 -7 15 1.4 1.0; e -7.6 15.8 1.8 0.9 0;"
        "c -9 8 -10.5 14 1.7 1.1; e -11.3 15 1.6 0.8 0; c -9.5 4 -13 9 0.9 0.8; c -13 9 -12 14 0.8 0.7; e -11.9 15.3 1.0 1.6 10;"
        "c 3 -3.5 7.5 -2.5 1.9 1.6; c 7.5 -2.5 9.3 1.9 1.5 1.1; e 9.6 2.7 1.5 1.1 0; c 2 -1 5.5 3.5 1.6 1.2;"
        "c 5.5 3.5 4.6 7 1.2 0.9; e 4.5 7.6 1.2 0.8 0; o 5 -10.6 0.28")),
    "orion": dict(rot=0, solid=[2, 3, 4, 5, 6], shapes=(
        "e -3.5 -8.6 1.9 2.1 0; p -8 -5.8 1.2 -4.8 -0.8 4.8 -5.6 5.2; c -4.8 5 -6 12 1.9 1.3; c -1.5 5 3 11 1.9 1.3;"
        "e -6.3 12.8 1.7 0.8 0; e 3.5 11.8 1.7 0.8 0; c -2.8 5 -2.5 8.8 0.4 0.4; c -7.5 -5.5 -9.2 -7.5 1.5 1.2;"
        "c -9.2 -7.5 -11 -12 1.2 1.0; e -11.6 -13.8 2.0 3.2 15; c 0.5 -4.7 8.5 -5.5 1.5 1.2; e 7.2 -3.5 3.4 5.6 5")),
    "ursa-major": dict(rot=0, solid=[0, 1], shapes=(
        "e 16 -13.8 4.2 2.7 -5; e 12.5 -16.5 1.1 1.5 0; c 1.5 -9.5 11 -13 3.0 2.4; e -4.5 -5.5 8 5.5 -10;"
        "c -10 -6 -16 -7 1.7 1.2; c -16 -7 -20 -8 1.2 0.9; c -20 -8 -26 -5 0.9 0.6; c 1 -4 14 -2 2.0 1.5;"
        "c 14 -2 20.3 0.6 1.5 1.1; e 20.8 1.2 1.7 1.3 0; c -8 -1 -8 4 1.9 1.7; c -8 4 -2 8 1.7 1.5; c -2 8 7.2 9.6 1.5 1.2;"
        "e 7.8 10 1.6 1.3 0; c -2 8 -4 20.5 1.5 1.1; e -4 21.3 1.5 1.2 0; o 17.2 -14.2 0.35")),
    "ursa-minor": dict(rot=0, solid=[0], shapes=(
        "e 1 4.5 4.4 3.8 0; c 0 1.5 -2 -2 1.6 1.4; c -2 -2 -2 -7 1.4 1.0; c -2 -7 0 -11 1.0 0.4; e 6.3 5.8 2.6 1.9 -20;"
        "e 5.2 3.5 0.9 1.1 0; c -1 6.5 -2.5 10 1.2 0.9; c 2 7.5 2.8 11 1.2 0.9; c 4.5 6.5 6.5 10.5 1.1 0.9; o 7.3 5.4 0.28")),
    "cassiopeia": dict(rot=0, solid=[0], shapes=(
        "c -5.5 -6.5 -5.5 4.5 1.2 1.2; c -5.5 5 7.5 5 1.1 1.1; e -1 -6.8 1.7 1.9 0; c -1 -5 0.3 2 2.2 2.8;"
        "c 0.3 2.5 6.5 3.2 1.7 1.4; c 6.5 3.2 7.4 8 1.3 1.1; e 7.8 8.8 1.8 0.8 0; c -0.5 -3 -4 -1.5 1.0 0.9")),
    "cygnus": dict(rot=0, solid=[0, 1], shapes=(
        "c -6.5 -7.5 0 -0.5 1.6 1.4; c 0 -0.5 9 10 1.2 0.8; e 9.6 10.6 0.9 0.7 -40; c 10 11 11.6 12.4 0.35 0.3;"
        "e -7 -8 1.8 1.1 -50; p -2.5 -3.5 -0.5 -8.5 4 -10.5 8.5 -9.5 7 -6 3.2 -3 0.8 -1;"
        "p -3.5 -0.5 -9.5 -1.5 -12.5 3.5 -11 7.5 -6.5 6 -2.5 2")),
    "scorpius": dict(rot=0, solid=[1], shapes=(
        "c 10 -10 5 -7 2.3 2.0; c 5 -7 0 0 2.0 1.7; c 0 0 0 4 1.7 1.5; c 0 4 -1 8 1.5 1.3; c -1 8 -4 9.5 1.3 1.1;"
        "c -4 9.5 -8 10 1.1 0.9; c -8 10 -11 7 0.9 0.8; c -11 7 -10 6 0.8 0.7; c -10 6 -8 4 0.7 0.6; e -7.9 3.8 0.9 0.5 -40;"
        "c 10.5 -10 12.5 -14.5 1.3 0.9; e 11.8 -15.2 2.3 1.2 -60; c 11.5 -8.5 12.2 -6 1.3 0.9; e 12.2 -5.5 1.8 1.0 80;"
        "c 4 -6 6.5 -3 0.5 0.4; c 3 -5 4.5 -2 0.5 0.4; c 2 -2 4.5 1 0.5 0.4")),
    "gemini": dict(rot=-55, solid=[0, 1], shapes=(
        "e 3.4 -12.2 1.8 1.8 0; e -1.4 -12.3 1.8 1.8 0; c 3.2 -10 3.8 1.5 2.1 1.9; c -1.5 -10 -3 0 2.1 1.9;"
        "c 3.4 2 4.4 8.6 1.1 0.8; c 4.4 1.5 6 8.8 1.1 0.8; c -3 0.5 -2.5 8 1.1 0.8; c -3.5 0 -5.5 7.5 1.1 0.8;"
        "c -0.5 -8 1.5 -8 0.8 0.8; c 4.8 -9 6.5 -3 0.9 0.7; c -3 -9 -5 -3 0.9 0.7")),
    "taurus": dict(rot=0, solid=[0, 1], shapes=(
        "e -2.5 4.2 3.8 2.8 -20; e -7 6.5 1.8 1.2 -25; c -3 2.5 -9 -1 1.9 1.3; c -9 -1 -15 -9 1.3 0.3;"
        "c -5.5 4.5 -12 2 1.9 1.3; c -12 2 -19 -1 1.3 0.3; c -1 3 7 -3 3.6 3.8; e 8.5 -3.5 3.5 3.2 0;"
        "c 5 -1 3.5 6 1.5 1.1; c 3.5 6 4.5 9.5 1.1 0.8; c 8 -1 10 7 1.4 1.0; o -5.2 4.4 0.3")),
    "lyra": dict(rot=0, solid=[1], shapes=(
        "c -1.4 -1.3 1.5 -2.3 0.4 0.4; c -1.5 -1.5 -3.8 -0.5 0.35 0.3; c -3.8 -0.5 -3.4 2.5 0.3 0.45;"
        "c 1.6 -2.4 3.4 -1.6 0.35 0.3; c 3.4 -1.6 2.6 2.4 0.3 0.45; e -0.4 3.7 3.0 1.3 -5;"
        "d -1.5 -1 -2.2 3; d -0.6 -1.3 -1.1 3; d 0.3 -1.7 0.1 3; d 1.2 -2 1.2 3")),
    "aquila": dict(rot=0, solid=[0, 1], shapes=(
        "e -2.3 -7.3 1.4 1.4 0; c -2.8 -5.5 8 10 1.7 1.4; e 8.3 10.5 2.4 1.4 60;"
        "p -1.5 -5 3.5 -9.5 9.5 -10.5 9.5 -7 5 -2 1 0; p -4 -3.5 -9 0 -10.5 6.5 -8 7.5 -5 3.5 -2 0.5;"
        "c -1 3.5 -3 8 0.7 0.5; c 1 3.5 1.5 8.5 0.7 0.5; c -2.5 -7.8 -1 -9 0.35 0.3")),
    "canis-major": dict(rot=0, solid=[1], shapes=(
        "e 0 -8 4 2.2 10; c -2 -5.5 -3 3 1.9 2.3; c -1.5 -4.5 7 -6 1.3 1.0; c -1 -3.5 3 -2 1.1 0.9;"
        "c -3 3 -1 5.2 1.3 1.1; c -1 5.2 7 7 1.1 0.8; c -4 3.5 -6 7.5 1.4 1.0; c -4 2.5 -7.3 6.3 1.1 0.5; e 2.8 -7.6 1.5 0.9 10;"
        "o 0.5 -8.5 0.28")),
    "pegasus": dict(rot=180, solid=[0], shapes=(
        "p 0.5 -5.5 0.5 10.5 17 13 21 -4; c 2.5 -3 -4 -8 3.2 2.4; c -4 -8 -12 -12.5 2.4 1.8; e -16 -10.5 4 2.2 45;"
        "c 2 8 -3 11.5 1.7 1.0; c -3 11.5 -6 16 1.0 0.8; c 16 11 18 19 1.6 1.0; c 21 -3 26 2 1.2 0.7; c 26 2 27 8 0.7 0.4;"
        "p 3 -5 8 -15 18 -17 21 -4; e -14.5 -13 1.0 1.6 -30; o -17 -11 0.3")),
    "sagittarius": dict(rot=0, solid=[0], shapes=(
        "c -6 0 3 3 2.7 2.4; c 1 1 2 -6 1.6 1.4; e 2 -8 1.6 1.6 0; c 3 4 5 9 0.9 0.8; c 0.5 4.5 0.5 9.5 0.9 0.8;"
        "c -5 1.5 -6.5 6.5 0.9 0.8; c -3 2.5 -3.5 7.5 0.9 0.8; c -6 0 -9 -2 1.0 0.5; c 3 -5 7.5 2 0.5 0.5;"
        "c 7.5 2 3.5 6.5 0.5 0.5; d 6 2 -5 2")),
    "aries": dict(rot=0, solid=[0], shapes=(
        "e -5.5 -3.2 5.2 3.2 20; c -1.5 -2.2 2 0.2 1.9 1.5; e 3.4 2.1 2.3 1.8 40; c 0.8 -1.2 -1 -2.8 0.9 0.8;"
        "c -1 -2.8 -3.2 -2.2 0.8 0.6; c -3.2 -2.2 -3.4 -0.2 0.6 0.5; c -3.4 -0.2 -1.6 0.9 0.5 0.4;"
        "c -8.5 -1 -9 4.5 0.9 0.8; c -6.5 0 -7 5 0.9 0.8; c -3 0.2 -3.4 5 0.9 0.8; c -1.2 0.5 -1.4 5 0.9 0.8;"
        "c -10 -4.5 -12 -3 0.5 0.4; o 4.3 1.6 0.28")),
    "cancer": dict(rot=0, solid=[0, 1, 2], shapes=(
        "e 0 -1 4.6 4.1 0; c 0.5 -4 -1 -11 0.9 0.7; e -1 -11.8 2.6 1.4 20; c -2.5 -3 -7 -8 0.8 0.7; e -8 -8.8 2.2 1.3 50;"
        "c -3.5 1 -4 6 0.8 0.6; c 3.5 1.5 6 9 0.8 0.6; c -4.2 -1 -8.5 3 0.7 0.5; c 4.5 -1 10 4.5 0.7 0.5")),
    "virgo": dict(rot=70, solid=[0], shapes=(
        "e 6 -23.8 2.0 2.1 0; c 5.8 -21 4.5 -10 2.6 3.0; c 4.5 -10 -0.5 2 3.0 3.4; e -1 5.5 4.6 3.4 0;"
        "c -0.8 3 -5 7.5 1.8 1.4; c -5 7.5 -9.4 18.4 1.4 0.9; c -0.8 3 0.8 13.9 1.7 1.3; c 0.8 13.9 -1.8 20.3 1.3 0.9;"
        "c 4.5 -11 -1.2 -8.3 1.2 1.0; c -1.2 -8.3 -8.9 -9.3 1.0 0.8; c 3.5 -9 7 -3 1.2 1.0; c 7 -3 10 3.7 1.0 0.8;"
        "e 10.3 4.9 0.6 1.8 20; p 5 -18 9 -23 13 -19 11 -11 5.5 -10")),
    "libra": dict(rot=0, solid=[0], shapes=(
        "c -4 -6 7.5 -4 0.6 0.6; c 1.8 -5 1 -11 0.5 0.5; e -4.5 -0.2 3.4 1.0 0; e 7.5 1.8 3.4 1.0 0; c 0.5 -5 0 8 0.6 0.6;"
        "e 0 8.4 5.5 1.2 0; d -4 -6 -7.5 -0.5; d -4 -6 -1.5 -0.5; d 7.5 -4 4.5 1.8; d 7.5 -4 10.5 1.8")),
    "capricornus": dict(rot=0, solid=[0], shapes=(
        "p 11.5 -6.5 0 -3.2 -9 -3.2 -10.5 -1 -5 3 3 7.5 8 0 11.5 -3; e 12.2 -6.7 2.3 1.5 -25; c 11.5 -7.5 13.5 -10.5 0.5 0.3;"
        "c 8 -1 11 3 1.0 0.8; c -9 -2 -12.5 1 1.4 0.9; c -12.5 1 -10 4.5 0.9 0.5; e -10 5 2 1 -50; p -12.5 -1.5 -15 -4 -14 2")),
    "aquarius": dict(rot=70, solid=[0, 1], shapes=(
        "e 13 -21.5 1.9 1.9 0; c 12.5 -19 6 -10 2.3 2.7; c 6 -9 11 -1.5 1.6 1.1; c 5.5 -11.5 -3.3 -5.7 1.3 1.1;"
        "c -3.3 -5.7 -5.6 -0.8 1.1 1.0; e -5.3 -0.3 2.6 2.9 0; c -5.5 2 -0.4 7.8 0.9 0.7; c -0.4 7.8 5.5 9 0.7 0.6;"
        "c 5.5 9 7.3 10.9 0.6 0.5; c -0.4 7.8 -3.7 12.4 0.7 0.5")),
    "pisces": dict(rot=0, solid=[0], shapes=(
        "e 16.8 2.3 5.4 3.4 15; p 20.5 2 25 -1.5 25.5 5.5; c 13 1 9 -1 0.4 0.4; c 9 -1 -3 -1 0.4 0.4; c -3 -1 -10 0 0.4 0.4;"
        "c -10 0 -17 1 0.4 0.4; c -17 1 -22 3 0.4 0.4; c -18 -2 -14 -9 1.9 1.6; e -13.4 -9.6 2.2 1.9 0;"
        "p -18.5 -1 -21 1 -20 -4; e -22.2 3.3 1.2 1.0 0")),
    "crux": dict(rot=0, solid=[0, 1], shapes="c 0 -3.3 0 3.4 0.55 0.55; c -2.6 0.2 2.7 -1.1 0.5 0.5"),
}
# --- drawing style: reusable creature "stamps" ---------------------------------------------------------
# Each stamp is one properly proportioned drawing in its own local frame (facing right, y down), placed on a
# constellation by pinning two named landmarks to sky points (a star id or an (x, y) in degrees).
#   b x y ...  closed smooth outline     l x0 y0 x1 y1 x2 y2 w0 w1 w2   bent limb (3 points)
#   k n x y ... w ...  curved limb of n points with n half-widths        e cx cy rx ry rot  ellipse
#   m cx cy rx ry n jag  shaggy mane     w cx cy rx ry n jag  scalloped wool     s x y ...  ink stroke   d cx cy r  dot
# a trailing h on b/l/k/e/m/w adds engraving hatching.
STAMPS = {
    "lion": dict(anchors=dict(nose=(93, 26), tail=(-2, 48)), draw=(
        "bh 17 40 19 48 18.5 56 17.5 63 17 68.3 25 68.8 26 66 25 60 26 52 28 44 30 40;"
        "bh 41 40 40.5 48 40 56 39 64 38.5 68.3 47 68.8 48 66 47 60 48 52 49 44 50 40;"
        "k 3 9 24 -3 30 -2 44 1.6 1.2 0.8; e -2 48 3.2 5.5 8; s -2 52 -3 56; s -1 53 -1.5 57.5; s -3 51 -5 54.5;"
        "bh 50 22 42 19 32 19.5 22 21 14 22.5 8 27 7 34 9 40 12 45 11.5 52 11 60 10 66 9 68.5 17 69 20 67 19.5 61 20 54 "
        "24 47 26 45 29 40 33 38 40 38.5 47 40 51 41 52 47 52.5 54 52 61 51 67 50 69 59 69.2 60.5 67 59 61 59.5 53 60.5 46 61 40 60 33 56 26;"
        "s 15 27 22 30 21 38; s 14 33 18 37 24 42; s 52 28 55 34 53 40;"
        "mh 66 28 14.5 16.5 30 0.2; s 74 17 66 14 60 18; s 72 22 63 22 57 27; s 70 28 62 30 56 36; s 68 33 62 38 59 44; s 76 14 70 11 64 12;"
        "e 73 15.5 2.4 2.0 0;"
        "bh 73 16 78 14.5 84 16.5 88.5 21 91 24.5 91.5 27.5 89.5 29.5 86 31 82 32.5 77 32 73 28 71.5 22;"
        "d 82.5 21 0.9; d 90.8 25 1.0; s 91 28 87 29.5 84 28; s 79 19 82 18.5 85 19.5; d 88 27 0.25; d 89.5 28 0.25")),
    "bull": dict(anchors=dict(eye=(91, 42), rump=(7, 40), nose=(102, 56)), draw=(
        "bh 28 50 28.5 60 28 70 27.5 81.5 36 82 37 79 36.5 70 37.5 60 39 50;"
        "bh 43 52 43 62 42 72 41.5 81.5 49.5 82 50.5 79 49.5 70 50 60 51 52;"
        "k 4 8 32 2 38 2 52 4 62 1.4 1.1 0.8 0.5; e 4 66 2.8 5 0; s 4 71 3 75; s 5 71 6 75.5;"
        "bh 56 22 48 21 38 23 28 26 18 28 11 31 7 38 7 46 10 52 9.5 60 10 70 9 79 8.5 81 17 81.5 18.5 79 18 70 19.5 60 22 54 26 50 "
        "33 49 42 50 49 51 51 58 50.5 68 50 79 49 81.5 58 82 59.5 79 58.5 68 59 58 61 50 64 44 65 37 64 30 61 25;"
        "s 16 31 24 36 22 46; s 30 28 42 32 54 30; s 46 32 52 40 50 50; s 56 28 61 38 60 48;"
        "k 6 84 33 90 26 94 16 94 8 91 2 88 -1 2.0 1.7 1.3 0.9 0.5 0.15; k 5 80 33 84 24 85 14 83 6 80 2 1.8 1.5 1.1 0.6 0.15;"
        "e 81 34 3.2 1.5 -25;"
        "bh 60 24 68 23 76 26 82 31 90 36 98 44 102 52 102.5 57 99 60 93 60 87 56 80 54 74 54 68 52 64 46;"
        "d 91 42 0.9; d 101 53 0.7; s 102 58 96 58 92 56; s 86 38 90 37 94 40; s 66 32 72 38 76 48")),
    "ram": dict(anchors=dict(nose=(80, 41), tail=(8, 36)), draw=(
        "bh 22 46 23 52 23 58 22 62 22 64.5 28 64.5 28 62 28 57 29 52 31 46;"
        "bh 38 46 38 52 38 58 37 62 37 64.5 43 64.5 43 62 43 57 44 52 46 46; e 8 36 3 2.4 0;"
        "bh 14 46 15.5 52 15 58 14 62 14 64.5 20 64.5 20 62 20 57 21 52 23 46;"
        "bh 47 46 48 52 48 58 47.5 62 47 64.5 53 64.5 53 62 53 57 54 52 55 46;"
        "wh 33 38 23 15 24 0.09; s 18 30 26 27 34 30; s 24 38 32 35 40 38; s 14 40 22 44 30 42; s 38 30 44 27 50 32;"
        "kh 8 64 29 60 20 52 17 45 22 45 31 51 36 58 33 60 27 2.6 2.4 2.1 1.8 1.4 1.0 0.6 0.25; s 52 22 48 25 49 30;"
        "e 66 29 4 1.8 -35;"
        "bh 55 34 58 28 64 26 70 28 76 34 80 40 79 44 75 45 70 43 64 40 58 42;"
        "d 71 35 0.9; d 78 41 0.6; s 79 44 74 44 72 42")),
    "scorpion": dict(anchors=dict(stinger=(28, 14), claw=(108, 10)), draw=(
        "k 3 70 46 68 56 62 60 1.2 0.9 0.6; k 3 62 46 58 57 52 61 1.2 0.9 0.6; k 3 54 46 49 56 42 59 1.2 0.9 0.6; k 3 46 45 40 54 33 56 1.1 0.8 0.5;"
        "k 3 16 19 21 15 28 14 1.8 1.1 0.1; eh 14 21 4.6 3.8 0; eh 12.5 27 4.2 3.6 80; eh 13.5 34 4.6 3.8 70; eh 17 40 5.2 4.2 50;"
        "eh 23 43 5.8 4.6 20; eh 30 44 6.5 5 0; eh 35 43 8 7.5 0; eh 44 42 8.5 8 0; eh 53 41 9 8.5 0; eh 62 40 9.5 9 0;"
        "k 3 84 36 92 28 94 22 3 2.6 2.2; bh 90 16 95 11 102 12 106 17 104 23 99 27 93 25; k 3 98 16 104 11 108 8 1.6 1.1 0.3; s 96 23 100 20;"
        "k 3 84 45 94 49 99 46 2.8 2.4 2; bh 96 40 101 37 108 39 110 45 106 50 100 50; k 3 102 41 108 39 112 36 1.6 1.1 0.3;"
        "eh 76 40 11 8.5 0; d 80 36 0.8; d 83 38 0.8; s 40 36 48 36 56 35; s 60 34 66 34")),
    "crab": dict(anchors=dict(body=(60, 58), claw=(24, 8)), draw=(
        "k 4 44 66 30 74 22 90 24 102 2 1.6 1.2 0.6; k 4 42 60 24 64 14 78 12 92 2 1.6 1.2 0.6; k 4 42 54 24 54 10 62 6 76 2 1.6 1.2 0.6;"
        "k 4 76 66 90 74 98 90 96 102 2 1.6 1.2 0.6; k 4 78 60 96 64 106 78 108 92 2 1.6 1.2 0.6; k 4 78 54 96 54 110 62 114 76 2 1.6 1.2 0.6;"
        "k 4 46 46 36 36 26 28 24 20 3.2 3 2.8 2.4; eh 22 12 8 11 20; k 3 18 10 26 4 34 6 2.2 1.6 0.4; s 18 18 24 12;"
        "k 4 74 46 84 36 94 28 96 20 3.2 3 2.8 2.4; eh 98 12 8 11 -20; k 3 102 10 94 4 86 6 2.2 1.6 0.4; s 102 18 96 12;"
        "wh 60 58 25 19 20 0.06; s 40 52 56 48 76 52; s 38 60 60 56 82 60; s 48 70 60 68 74 70; d 54 40 1.2; d 66 40 1.2;"
        "k 2 54 42 52 36 0.8 0.8; k 2 66 42 68 36 0.8 0.8")),
    "goatfish": dict(anchors=dict(head=(100, 22), tailfin=(12, 16)), draw=(
        "bh 14 22 6 14 2 8 10 10 16 4 18 12 22 16;"
        "kh 6 38 36 28 46 16 50 8 42 8 30 14 22 8 8.6 7.2 5.8 4.4 3.0;"
        "s 30 40 24 44 16 44; s 24 36 18 40 12 38; s 14 30 10 34 9 38; s 34 34 30 38 24 38;"
        "k 3 66 46 74 56 70 64 4.2 3.4 2.6; e 69 66 5 2 0; k 3 56 48 60 58 56 66 4 3.2 2.4; e 55 68 5 2 0;"
        "bh 78 30 70 26 60 26 50 28 42 32 38 38 40 46 48 50 58 50 68 46 76 40;"
        "k 5 86 12 82 4 74 0 68 4 68 10 2.2 2 1.4 0.8 0.2; e 82 14 3 1.4 -30;"
        "bh 74 34 74 24 80 16 86 12 92 14 98 18 102 22 101 26 96 28 90 29 86 36 80 42;"
        "d 91 20 0.9; d 100 23 0.6; s 94 29 92 36 90 40; s 92 30 94 36; s 60 30 70 34 76 32; s 50 38 60 42 70 40")),
    "fish": dict(anchors=dict(head=(91, 42), tail=(2, 42)), draw=(
        "bh 16 40 2 26 7 42 2 58 16 44; bh 40 30 46 16 52 14 60 30; bh 44 54 48 62 56 56;"
        "bh 14 42 22 34 38 29 56 28 72 31 84 37 90 42 85 48 72 54 56 57 38 55 22 50;"
        "bh 70 46 64 58 74 54 76 48; s 72 33 75 42 72 51; d 80 40 1.4; s 90 42 85 44 82 43; s 20 42 50 41 70 42;"
        "s 30 36 34 42 30 48; s 40 35 44 42 40 49; s 50 35 54 42 50 49; s 60 36 64 42 60 48")),
    "jug": dict(anchors=dict(mouth=(50, 9), base=(50, 86)), draw=(
        "k 4 43 20 28 22 22 40 30 54 2.2 2.2 2.2 2.2;"
        "bh 50 30 62 32 70 42 72 56 68 72 58 84 50 86 42 84 32 72 28 56 30 42 38 32;"
        "bh 44 32 44 18 40 10 60 10 56 18 56 32; e 50 9 11 3.5 0; s 36 50 50 56 64 50; s 34 64 50 70 66 64; s 38 42 50 46 62 42;"
        "s 44 52 50 46 56 52 50 58 46 54; s 40 78 50 82 60 78")),
    "child": dict(anchors=dict(head=(30, 14), feet=(30, 86)), draw=(
        "k 3 25 56 24 70 26 84 3.6 3 2.4; k 3 35 56 37 70 35 84 3.6 3 2.4; eh 26 86 4.6 2 0; eh 35 86 4.6 2 0;"
        "k 3 21 28 13 40 14 52 2.6 2.2 1.8; e 14 54.5 2.2 2.2 0;"
        "bh 20 26 40 26 45 44 43 58 36 62 30 58 24 62 17 58 15 44;"
        "s 24 30 22 46 22 58; s 30 30 30 46 30 56; s 36 30 38 46 38 58; s 18 38 26 40 34 38 42 40;"
        "k 3 39 28 49 30 56 34 2.6 2.2 1.8; e 57.5 34 2.2 2.2 0;"
        "wh 30 10 9.5 8 11 0.14; e 22 15 1.4 2.2 0; eh 30 14 7.5 8.5 0; s 23 11 27 7 31 10 35 7 38 11;"
        "d 27 14 0.7; d 33.5 14 0.7; s 30 15 30.8 18 29 18.4; s 27 21 30 22.5 33 21")),
    "maiden": dict(anchors=dict(head=(50, 12), feet=(50, 98)), draw=(
        "bh 40 28 26 14 8 6 -6 12 4 22 -4 30 8 38 2 48 16 52 28 50 38 44; bh 60 28 74 14 92 6 106 12 96 22 104 30 92 38 98 48 84 52 72 50 62 44;"
        "s 36 30 20 22 6 14; s 36 36 18 32 4 26; s 36 42 18 42 6 40; s 64 30 80 22 94 14; s 64 36 82 32 96 26; s 64 42 82 42 94 40;"
        "s 44 6 36 16 34 40 38 62; s 40 8 30 20 28 44 32 66; s 56 6 64 18 64 40 62 58;"
        "bh 38 24 62 24 66 40 70 68 78 96 66 99 54 96 42 99 30 96 22 96 30 68 34 40;"
        "s 40 40 36 70 32 94; s 50 42 50 70 50 96; s 60 40 64 70 68 94; s 36 40 64 40; s 36 46 64 46; s 44 60 42 80; s 56 60 58 80;"
        "k 3 62 28 76 40 86 54 3.2 2.6 2.2; e 86 56 2.4 2.4 0; s 86 54 88 30; e 87 22 2 8 8; e 91 24 2 7 -8; e 83 25 2 7 22; s 87 30 87 14;"
        "k 3 38 28 24 34 10 40 3.2 2.6 2.2; e 8 46 4 5 0; e 5 50 3 3.5 0; e 11 51 3 3.5 0; s 8 41 9 36;"
        "k 2 50 20 50 26 3 3.4; wh 50 8 8.5 6 8 0.1; eh 50 12 7 8.5 0; d 47 12 0.7; d 53 12 0.7; s 47 18 50 19.5 53 18")),
    "centaur": dict(anchors=dict(arrowtip=(112, 30), rump=(6, 68)), draw=(
        "k 4 18 66 14 76 20 88 14 98 5 4 3 2.4; k 4 52 70 58 80 56 90 62 99 5 4 3 2.4;"
        "k 4 8 62 0 66 -2 78 4 90 2 2 1.5 0.6; s 2 70 -1 80; s 4 72 3 84;"
        "bh 56 50 44 52 30 54 18 56 10 60 6 68 8 76 16 80 28 80 40 80 52 78 60 72 62 62;"
        "k 4 20 72 26 82 24 92 28 100 6 4.6 3.4 2.6; e 29 101 4 1.6 0; k 4 54 74 64 82 72 88 80 90 5.6 4.4 3.4 2.6; e 83 91 4 1.6 0;"
        "bh 56 56 52 44 52 30 56 22 64 20 70 26 70 40 68 54 62 60; k 3 58 30 50 32 44 34 3 2.4 2; "
        "eh 62 12 6.5 7.5 0; s 58 8 50 10 42 18; s 59 12 50 16 44 26; s 58 6 50 4 40 8; d 65 11 0.7;"
        "k 3 62 30 80 30 94 30 3 2.4 2; kh 5 94 8 99 20 101 32 99 44 94 56 1.4 1.4 1.6 1.4 1.1;"
        "s 94 8 56 32 94 56; s 50 32 112 30; b 112 30 106 27 108 30 106 33")),
    "hero": dict(anchors=dict(head=(50, 10), feet=(52, 100)), draw=(
        "k 3 44 62 43 80 42 98 5 4 3.2; k 3 56 62 59 80 62 98 5 4 3.2; eh 41 100 5 2.2 0; eh 63 100 5 2.2 0;"
        "k 3 36 24 24 14 16 0 3.4 2.8 2.4; eh 14 -5 7 10 20; d 11 -8 0.6; d 16 -2 0.6; d 12 -1 0.6;"
        "bh 36 22 64 22 68 40 66 62 58 68 50 64 42 68 34 62 32 40; s 34 44 50 46 66 44; s 40 50 40 62; s 50 50 50 62; s 60 50 60 62;"
        "k 2 50 46 48 68 1.2 1; k 3 64 26 76 32 84 36 3.4 2.8 2.4; eh 90 36 12 20 8; s 90 18 90 54; s 80 36 100 36; s 82 26 98 46;"
        "wh 50 6 9 6 9 0.12; eh 50 12 7 8 0; s 44 18 50 24 56 18; d 47 11 0.7; d 53 11 0.7; s 47 16 50 17 53 16")),
    "bear": dict(anchors=dict(nose=(91, 34), rump=(6, 42)), draw=(
        "bh 20 46 21 56 20 66 19 71 28 71.5 29 68 28 58 30 46; bh 44 46 44 56 43 66 42 71 51 71.5 52 68 51 58 53 46;"
        "e 6 40 2.4 3 0;"
        "bh 56 24 46 20 34 21 22 26 12 32 7 40 8 50 12 58 12 66 11 71 20 71.5 22 68 22 60 26 52 34 50 44 52 52 54 54 62 54 70 53 71 "
        "62 71.5 64 68 62 60 63 52 66 44 68 36 66 28 62 24;"
        "s 40 24 50 26 58 30; s 14 36 22 40 24 48; s 30 30 40 34 44 44; s 56 36 58 46 56 56;"
        "e 70 17 3.2 3 0; bh 62 22 68 18 75 18 81 22 87 28 91 33 90 37 85 39 79 40 72 40 66 36 62 30;"
        "d 77 26 0.9; d 90 33 1.1; s 90 38 84 39 80 37; s 66 24 70 28 74 26")),
    "dog": dict(anchors=dict(nose=(96, 27), tail=(-2, 12)), draw=(
        "bh 12 40 14 52 13 62 12 70 19 70.5 19.5 66 18.5 58 20 46 22 40; bh 46 40 46 52 45 62 44 70 51 70.5 52 66 51 58 52 46 54 40;"
        "k 3 8 32 0 24 -2 12 1.8 1.4 0.6;"
        "bh 50 24 40 22 28 23 18 26 10 30 6 36 8 44 12 50 11 58 11 70 18 70.5 19.5 66 20 58 24 50 30 46 40 46 50 46 54 56 54 66 53 70 "
        "60 70.5 62 66 60 58 62 48 64 40 64 32 60 26;"
        "s 16 30 22 36 22 44; s 30 28 40 30 50 28; s 56 36 60 44 58 54;"
        "bh 66 12 64 2 72 6 72 14;"
        "bh 56 24 62 16 68 12 74 12 80 16 90 22 96 26 96 30 90 31 82 32 76 34 68 34 62 32;"
        "d 76 19 0.9; d 95.5 27 1.1; s 94 31 86 31 80 30")),
    "horse": dict(anchors=dict(nose=(108, 28), tail=(0, 70)), draw=(
        "k 4 22 62 20 70 24 78 20 86 4 3.2 2.6 2; k 4 56 62 60 70 58 78 62 86 4 3.2 2.6 2;"
        "k 4 12 54 4 58 0 72 6 86 3 3 2.4 1;"
        "bh 62 38 50 36 36 38 24 40 14 46 10 56 12 64 20 66 34 66 48 66 58 64 64 56 68 46;"
        "k 4 24 62 30 72 26 80 30 88 6 4.4 3.2 2.4; eh 31 89.5 4 1.6 0; k 4 58 64 66 72 72 80 80 84 5.6 4.2 3.2 2.4; eh 81.5 85.5 4 1.6 0;"
        "bh 44 38 40 22 44 6 56 -6 74 -10 66 0 80 0 70 10 82 14 68 22 76 28 62 32 60 38;"
        "s 52 30 56 14 66 2; s 58 32 66 16 76 8; s 64 32 74 20 80 14; s 50 24 54 6 62 -4;"
        "bh 58 40 64 28 70 18 78 12 84 12 90 18 86 26 80 34 74 44 68 52;"
        "s 80 10 74 14 68 22 62 32; s 84 12 78 18 72 28 66 38;"
        "bh 84 10 90 8 98 12 104 20 108 28 106 32 100 30 94 24 88 22 84 18; d 94 16 0.9; d 106 29 0.8; e 82 10 2.4 4.2 -20")),
    "swan": dict(anchors=dict(head=(100, 38), tail=(14, 50)), draw=(
        "bh 48 44 40 30 28 14 12 4 6 8 14 14 10 20 20 24 16 30 28 34 24 40 36 44; "
        "bh 48 56 40 70 28 86 12 96 6 92 14 86 10 80 20 76 16 70 28 66 24 60 36 56;"
        "s 40 34 30 20 14 8; s 36 38 24 28 12 14; s 40 66 30 80 14 92; s 36 62 24 72 12 86;"
        "bh 32 50 22 46 14 50 22 54; eh 50 50 20 8 0; "
        "k 5 66 48 76 46 84 40 90 36 96 38 3 2.6 2.2 2 1.8; eh 98 38 3.6 2.6 -10; bh 100 36 108 38 101 41; d 97 37 0.6")),
    "eagle": dict(anchors=dict(head=(50, 34), tail=(50, 96)), draw=(
        "bh 56 46 70 36 90 28 110 26 104 34 114 36 106 42 114 46 104 50 110 54 96 56 80 58 58 60;"
        "bh 44 46 30 36 10 28 -10 26 -4 34 -14 36 -6 42 -14 46 -4 50 -10 54 4 56 20 58 42 60;"
        "bh 44 72 38 92 50 96 62 92 56 72; s 50 74 50 92; s 46 74 44 90; s 54 74 56 90;"
        "bh 50 40 56 44 58 60 54 72 46 72 42 60 44 44; k 2 46 70 44 82 2 1.2; k 2 54 70 56 82 2 1.2;"
        "eh 50 34 5 6 0; bh 54 32 62 34 56 38; d 52 33 0.8; s 30 36 22 32; s 70 36 78 32")),
    "queen": dict(anchors=dict(head=(40, 20), seat=(40, 90)), draw=(
        "bh 14 90 14 10 18 4 30 4 34 10 34 90; bh 12 78 80 78 82 90 12 90; s 18 20 18 70; s 26 20 26 70;"
        "bh 30 30 50 30 56 60 62 78 14 78 22 60; s 30 40 26 70; s 40 36 40 72; s 48 40 54 72;"
        "k 3 50 34 62 44 68 56 3 2.6 2.2; e 69 58 2.6 2.6 0; k 3 30 34 24 46 24 58 3 2.6 2.2;"
        "wh 40 16 7.5 8 10 0.1; eh 40 20 6 7 0; bh 33 12 35 4 38 9 40 3 42 9 45 4 47 12; d 38 20 0.7; d 43 20 0.7; s 38 25 40 26 42 25")),
    "lyre": dict(anchors=dict(top=(50, 0), bottom=(50, 100)), draw=(
        "k 4 36 14 18 20 10 46 20 70 3.2 3 2.8 2.6; k 4 64 14 82 20 90 46 80 70 3.2 3 2.8 2.6;"
        "eh 50 76 30 22 0; bh 28 14 72 14 72 22 28 22;"
        "s 36 22 36 70; s 43 22 43 72; s 50 22 50 72; s 57 22 57 72; s 64 22 64 70; s 34 76 66 76; s 36 82 64 82")),
    "cross": dict(anchors=dict(top=(50, 0), bottom=(50, 100)), draw=(
        "bh 46 0 54 0 55 30 90 31 90 40 55 41 54 100 46 100 45 41 10 40 10 31 45 30; e 50 -3 5 5 0; e 50 103 5 5 0; e 6 36 5 5 0; e 94 36 5 5 0; s 50 6 50 94; s 14 36 86 36")),
}

# --- drawing style: hand-inked line drawings ------------------------------------------------
# A drawing is a list of `stamps` (creature, mirror?, landmark, sky point, landmark, sky point) plus optional
# extra ops in sky degrees (x right, y down) in the figure's upright frame `rot`.
INK = {
    "leo": dict(rot=0, solid=[0], stamps=[("lion", False, "nose", "eps", "tail", "den")]),
    "taurus": dict(rot=0, solid=[0, 1], stamps=[("bull", True, "eye", "ald", "rump", (19.0, -2.5))]),
    "aries": dict(rot=0, solid=[0], stamps=[("ram", False, "nose", (5.5, 3.2), "tail", (-11.0, 2.5))]),
    "gemini": dict(rot=-55, solid=[0, 1], stamps=[("child", False, "head", "pol", "feet", "alh"),
                                                   ("child", True, "head", "cas", "feet", (5.4, 8.6))]),
    "cancer": dict(rot=0, solid=[0, 1, 2], stamps=[("crab", False, "body", "del", "claw", (-9.0, -11.7))]),
    "virgo": dict(rot=70, solid=[0], stamps=[("maiden", False, "head", "zan", "feet", (-1.5, 16.0))]),
    "libra": dict(rot=0, solid=[0], draw=(
        "e 1.5 9.6 5 1.3 0; l 0.8 -11 1.4 -4 1.5 9 0.8 0.7 0.9; e 0.8 -13.2 1.3 1.5 0; e 0.8 -13.2 0.7 0.9 0;"
        "l -3.7 -5.8 1.7 -5.1 7.1 -4.4 0.45 0.55 0.45; s -3.7 -5.8 -8.5 -0.4; s -3.7 -5.8 -5.2 0.4; s -3.7 -5.8 -1.9 -0.4;"
        "s 7.1 -4.4 4.5 1.6; s 7.1 -4.4 8.6 2.2; s 7.1 -4.4 12 1.4; eh -5.2 0.6 3.4 1.1 0; eh 8.4 2.0 3.4 1.1 0; d 1.5 -5 0.3")),
    "scorpius": dict(rot=0, solid=[1], stamps=[("scorpion", False, "stinger", "lam", "claw", "acr")]),
    "sagittarius": dict(rot=0, solid=[0], stamps=[("centaur", False, "arrowtip", "aln", "rump", (-11.5, 3.5))]),
    "capricornus": dict(rot=0, solid=[0], stamps=[("goatfish", False, "head", (12.8, -5.2), "tailfin", (-10.5, -3.0))]),
    "aquarius": dict(rot=70, solid=[0, 1], stamps=[("jug", False, "mouth", (-1.0, 4.2), "base", (-9.5, -5.5))], draw=(
        "s -0.8 4.6 0.4 7.6 2.5 9.2 5 10 7.3 10.9; s -1.4 4.8 -0.4 8 1.6 9.8 4.4 10.8 7 11.8; s -0.4 4.7 1 7 3.2 8.6 5.7 9.5 7.8 10.3;"
        "s -0.8 4.8 -2 8.5 -3.7 12.4; s -1.3 4.9 -2.8 8.7 -4.4 12.2; s -0.3 4.9 -1.2 8.6 -2.8 12.6;"
        "d -1.5 10.5 0.2; d 3 11.5 0.2; d 5.5 12 0.2; d 1.8 12.5 0.2; d -3 13.8 0.2; d 7 13.2 0.2; d 0.5 14 0.2; d 9 12.5 0.2; d -5 14.8 0.2")),
    "pisces": dict(rot=0, free=True, solid=[0], stamps=[("fish", False, "head", (26.0, 3.5), "tail", (9.0, 2.4)),
                                                     ("fish", False, "head", (-10.5, -12.5), "tail", "alp")], draw=(
        "s 9.0 2.4 6.9 -0.6 -3.4 -1.3 -6.9 -1.6 -9.7 0.1 -16.6 0.6 -22 3.2")),
    "orion": dict(rot=0, solid=[2, 3, 4, 5, 6], stamps=[("hero", False, "head", "mei", "feet", (-1.5, 12.0))]),
    "ursa-major": dict(rot=0, solid=[0, 1], stamps=[("bear", False, "nose", (18.5, -13.5), "rump", (-13.0, -3.5))]),
    "ursa-minor": dict(rot=0, solid=[0], stamps=[("bear", False, "nose", (6.5, 5.5), "rump", (-3.5, 3.2))]),
    "canis-major": dict(rot=0, solid=[1], stamps=[("dog", False, "nose", (3.0, -7.5), "tail", (-7.3, 6.3))]),
    "pegasus": dict(rot=180, solid=[0], stamps=[("horse", True, "nose", "eni", "tail", (24.0, 2.0))]),
    "cygnus": dict(rot=0, solid=[0, 1], stamps=[("swan", False, "head", "alb", "tail", "den")]),
    "aquila": dict(rot=0, solid=[0, 1], stamps=[("eagle", False, "head", (-2.2, -7.2), "tail", "lam")]),
    "cassiopeia": dict(rot=0, solid=[0], stamps=[("queen", False, "head", (-1.0, -7.0), "seat", (0.5, 7.5))]),
    "lyra": dict(rot=0, solid=[1], stamps=[("lyre", False, "top", (0.3, -2.6), "bottom", (-1.3, 5.4))]),
    "crux": dict(rot=0, solid=[0, 1], stamps=[("cross", False, "top", "gac", "bottom", "acr")]),
}

NAMES = {
    "orion": dict(bet="Betelgeuse", rig="Rigel", bel="Bellatrix", sai="Saiph", min="Mintaka", aln="Alnilam", alt="Alnitak", mei="Meissa"),
    "ursa-major": dict(dub="Dubhe", mer="Merak", phe="Phecda", meg="Megrez", ali="Alioth", miz="Mizar", alk="Alkaid", mus="Muscida"),
    "ursa-minor": dict(pol="Polaris", bet="Kochab", gam="Pherkad"),
    "cassiopeia": dict(cap="Caph", sch="Schedar", gam="Gamma Cas", rus="Ruchbah", seg="Segin"),
    "cygnus": dict(den="Deneb", sad="Sadr", alb="Albireo", gie="Gienah"),
    "scorpius": dict(ant="Antares", acr="Acrab", dsc="Dschubba", the="Sargas", lam="Shaula", eps="Larawag", kap="Girtab"),
    "leo": dict(reg="Regulus", den="Denebola", alg="Algieba", zos="Zosma", cht="Chertan", adh="Adhafera", ras="Rasalas"),
    "crux": dict(acr="Acrux", mim="Mimosa", gac="Gacrux", imi="Imai"),
    "gemini": dict(cas="Castor", pol="Pollux", alh="Alhena", meb="Mebsuta", tej="Tejat", pro="Propus", was="Wasat", mek="Mekbuda"),
    "taurus": dict(ald="Aldebaran", eln="Elnath", alc="Alcyone"),
    "lyra": dict(veg="Vega", she="Sheliak", sul="Sulafat"),
    "aquila": dict(alt="Altair", tar="Tarazed", als="Alshain"),
    "canis-major": dict(sir="Sirius", mir="Mirzam", wez="Wezen", adh="Adhara", alu="Aludra", fur="Furud"),
    "pegasus": dict(mak="Markab", sch="Scheat", alg="Algenib", alp="Alpheratz", eni="Enif"),
    "sagittarius": dict(kau="Kaus Australis", kam="Kaus Media", kab="Kaus Borealis", nun="Nunki", asc="Ascella"),
    "aries": dict(ham="Hamal", she="Sheratan", mes="Mesarthim"),
    "cancer": {"alp": "Acubens", "bet": "Al Tarf", "del": "Asellus Australis"},
    "virgo": dict(spi="Spica", por="Porrima", vin="Vindemiatrix", zav="Zavijava", hez="Heze"),
    "libra": dict(alp="Zubenelgenubi", bet="Zubeneschamali", gam="Zubenelhakrabi"),
    "capricornus": {"del": "Deneb Algedi", "bet": "Dabih", "gam": "Nashira", "alp": "Algedi"},
    "aquarius": {"bet": "Sadalsuud", "alp": "Sadalmelik", "del": "Skat"},
    "pisces": dict(alp="Alrescha", eta="Alpherg"),
}
ASTERISMS = {   # (label, star, dx, dy) - offset in degrees, in the figure's upright frame
    "leo": [("Sickle", "adh", -2.0, 0.0)],
    "ursa-major": [("Big Dipper", "meg", 0.0, -4.5)],
    "ursa-minor": [("Little Dipper", "gam", 0.0, 4.6)],
    "cygnus": [("Northern Cross", "gie", -1.0, 3.0)],
    "orion": [("Belt", "alt", -5.0, 0.5)],
    "taurus": [("Pleiades", "alc", 0.0, -3.6)],
    "pegasus": [("Great Square", "alp", 0.0, 4.0)],
    "sagittarius": [("Teapot", "asc", -2.5, 2.2)],
}


def sky_raw(stars):
    """Stereographic projection about the mean direction of the stars: north up, east left,
    y pointing down, units are radians.  Returns (positions, ra0, dec0)."""
    vx = vy = vz = 0.0
    for ra, dec, *_ in stars.values():
        a, d = math.radians(ra * 15), math.radians(dec)
        vx += math.cos(d) * math.cos(a)
        vy += math.cos(d) * math.sin(a)
        vz += math.sin(d)
    ra0, dec0 = math.atan2(vy, vx), math.atan2(vz, math.hypot(vx, vy))
    raw = {}
    for k, (ra, dec, *_) in stars.items():
        a, d = math.radians(ra * 15), math.radians(dec)
        cosc = math.sin(dec0) * math.sin(d) + math.cos(dec0) * math.cos(d) * math.cos(a - ra0)
        kk = 2 / (1 + cosc)
        raw[k] = (-kk * math.cos(d) * math.sin(a - ra0),
                  -kk * (math.cos(dec0) * math.sin(d) - math.sin(dec0) * math.cos(d) * math.cos(a - ra0)))
    return raw, ra0, dec0


def parse_art(spec: str):
    shapes = []
    for item in spec.split(";"):
        parts = item.split()
        if parts:
            shapes.append((parts[0], [float(v) for v in parts[1:]]))
    return shapes


def generic_art(raw, chains):
    """Fallback ghost body: soft capsules along the stick figure (degrees)."""
    out = []
    for ch in chains:
        for a, b in zip(ch, ch[1:]):
            (x0, y0), (x1, y1) = raw[a], raw[b]
            x0, y0, x1, y1 = (math.degrees(v) for v in (x0, y0, x1, y1))
            w = 0.13 * math.hypot(x1 - x0, y1 - y0) + 0.5
            out.append(("c", [x0, y0, x1, y1, w, w]))
    return out


def _shape_discs(op, v):
    """(x, y, radius) control discs of a shape, for fitting the page."""
    if op == "c":
        return [(v[0], v[1], v[4]), (v[2], v[3], v[5])]
    if op == "e":
        return [(v[0], v[1], max(v[2], v[3]))]
    if op == "o":
        return [(v[0], v[1], v[2])]
    return [(v[i], v[i + 1], 0.0) for i in range(0, len(v) - 1, 2)]


def _label_pos(x, y, r, text, fs, boxes, W, H, order):
    tw, pad, gap = 0.58 * fs * len(text), 0.25 * fs, 0.6 * fs
    for side in order:
        if side == "r":
            tx, ty, an, x0 = x + r + gap, y + 0.33 * fs, "start", x + r + gap
        elif side == "l":
            tx, ty, an, x0 = x - r - gap, y + 0.33 * fs, "end", x - r - gap - tw
        elif side == "b":
            tx, ty, an, x0 = x, y + r + gap + 0.8 * fs, "middle", x - tw / 2
        else:
            tx, ty, an, x0 = x, y - r - gap, "middle", x - tw / 2
        box = (x0 - pad, ty - 0.95 * fs - pad, x0 + tw + pad, ty + 0.3 * fs + pad)
        if box[0] < 0.02 * W or box[2] > 0.98 * W or box[1] < 0.02 * H or box[3] > 0.98 * H:
            continue
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in boxes):
            continue
        return tx, ty, an, box
    return None



# --------------------------------------------------------------------------- #
# Drawing style: hand-inked line art (wobbly variable-width outlines, hatching)
# --------------------------------------------------------------------------- #
def parse_ink(spec: str):
    ops = []
    for item in spec.split(";"):
        parts = item.split()
        if parts:
            ops.append((parts[0][0], parts[0].endswith("h") and len(parts[0]) == 2, [float(v) for v in parts[1:]]))
    return ops


def ink_from_art(shapes):
    """Fallback: turn the ghost-style capsule shapes into inked shapes."""
    ops = []
    for op, v in shapes:
        if op == "c":
            ops.append(("l", True, [v[0], v[1], (v[0] + v[2]) / 2, (v[1] + v[3]) / 2, v[2], v[3], v[4], (v[4] + v[5]) / 2, v[5]]))
        elif op == "e":
            ops.append(("e", True, v))
        elif op == "p":
            ops.append(("b", True, v))
        elif op == "d":
            ops.append(("s", False, v))
        elif op == "o":
            ops.append(("d", False, v))
    return ops


def _ink_discs(op, v):
    if op == "m":
        return [(v[0], v[1], max(v[2], v[3]) * (1 + v[5]))]
    if op == "l":
        return [(v[0], v[1], v[6]), (v[2], v[3], v[7]), (v[4], v[5], v[8])]
    if op == "k":
        n = int(v[0])
        return [(v[1 + 2 * i], v[2 + 2 * i], v[1 + 2 * n + i]) for i in range(n)]
    if op == "e":
        return [(v[0], v[1], max(v[2], v[3]))]
    if op == "d":
        return [(v[0], v[1], v[2])]
    if op == "w":
        return [(v[0], v[1], max(v[2], v[3]) * (1 + v[5]))]
    return [(v[i], v[i + 1], 0.0) for i in range(0, len(v) - 1, 2)]


def catmull(pts, closed, n=6):
    m = len(pts)
    if m < 3:
        return list(pts)
    out = []
    for i in range(m if closed else m - 1):
        p0 = pts[(i - 1) % m] if (closed or i > 0) else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % m]
        p3 = pts[(i + 2) % m] if (closed or i + 2 < m) else p2
        for j in range(n):
            t = j / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                                    + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3) for c in (0, 1)))
    if not closed:
        out.append(tuple(pts[-1]))
    return out


def ribbon(pts, widths, closed):
    """Outline a polyline with a variable-width ink ribbon (closed: a ring)."""
    n = len(pts)
    L, R = [], []
    for i in range(n):
        a = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        b = pts[(i + 1) % n] if closed else pts[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny, w = -dy / d, dx / d, widths[i] / 2
        L.append((pts[i][0] + nx * w, pts[i][1] + ny * w))
        R.append((pts[i][0] - nx * w, pts[i][1] - ny * w))
    return poly_d(L) + poly_d(R[::-1]) if closed else poly_d(L + R[::-1])


def star_d(x, y, r, k=6, inner=0.36, rot=-90) -> str:
    pts = []
    for i in range(2 * k):
        a = math.radians(rot + i * 180 / k)
        rr = r if i % 2 == 0 else r * inner
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    return poly_d(pts)


def place_stamp(ops, anchors, flip, a_name, PA, b_name, PB):
    """Similarity-transform a local stamp so landmark a lands on PA and b on PB."""
    fx = -1.0 if flip else 1.0
    A = (fx * anchors[a_name][0], anchors[a_name][1])
    B = (fx * anchors[b_name][0], anchors[b_name][1])
    c = math.hypot(PB[0] - PA[0], PB[1] - PA[1]) / (math.hypot(B[0] - A[0], B[1] - A[1]) or 1.0)
    th = math.atan2(PB[1] - PA[1], PB[0] - PA[0]) - math.atan2(B[1] - A[1], B[0] - A[0])
    ct, st_ = math.cos(th), math.sin(th)

    def T(x, y):
        x, y = fx * x - A[0], y - A[1]
        return PA[0] + c * (x * ct - y * st_), PA[1] + c * (x * st_ + y * ct)

    out = []
    for op, hat, v in ops:
        if op in ("b", "s"):
            nv = []
            for i in range(0, len(v) - 1, 2):
                nv += list(T(v[i], v[i + 1]))
        elif op == "l":
            nv = list(T(v[0], v[1])) + list(T(v[2], v[3])) + list(T(v[4], v[5])) + [w * c for w in v[6:9]]
        elif op == "e":
            nv = list(T(v[0], v[1])) + [v[2] * c, v[3] * c, fx * v[4] + math.degrees(th)]
        elif op == "k":
            n = int(v[0])
            nv = [v[0]]
            for i in range(n):
                nv += list(T(v[1 + 2 * i], v[2 + 2 * i]))
            nv += [w * c for w in v[1 + 2 * n:1 + 3 * n]]
        elif op in ("m", "w"):
            nv = list(T(v[0], v[1])) + [v[2] * c, v[3] * c, v[4], v[5]]
        else:  # d
            nv = list(T(v[0], v[1])) + [v[2] * c]
        out.append((op, hat, nv))
    return out


def draw_constellation_drawing(ctx: Ctx, key: str) -> None:
    rng, st, W, H, U, args = ctx.rng, ctx.st, ctx.W, ctx.H, ctx.U, ctx.args
    title, stars, chains = CONSTELLATIONS[key]
    raw, ra0, dec0 = sky_raw(stars)
    entry = INK.get(key)
    if entry:
        rot0, solid = float(entry.get("rot", 0.0)), set(entry.get("solid", [0]))
        _t = math.radians(rot0)
        star_deg = {k: (math.degrees(x) * math.cos(_t) + math.degrees(y) * math.sin(_t),
                        -math.degrees(x) * math.sin(_t) + math.degrees(y) * math.cos(_t)) for k, (x, y) in raw.items()}
        ops = []
        for name, flip, a_name, pa, b_name, pb in entry.get("stamps", []):
            tgt = lambda q: star_deg[q] if isinstance(q, str) else q
            ops += place_stamp(parse_ink(STAMPS[name]["draw"]), STAMPS[name]["anchors"], flip, a_name, tgt(pa), b_name, tgt(pb))
        ops += parse_ink(entry.get("draw", ""))
    else:
        art = ART.get(key, {})
        shapes = parse_art(art["shapes"]) if "shapes" in art else generic_art(raw, chains)
        ops, rot0, solid = ink_from_art(shapes), float(art.get("rot", 0.0)), set(art.get("solid", [0]))
    ink, paper = st.line(), st.paper
    m = 0.09 * U
    extra = 0.07 * U if args.label else 0.0

    def rot_deg(x, y, d):
        t = math.radians(d)
        return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)

    def extent_pts(d):
        pts = [rot_deg(x, y, d) for x, y in raw.values()]
        pts = [(x, y) for x, y in pts]
        for op, _h, v in ops:
            for x, y, r in _ink_discs(op, v):
                rx, ry = rot_deg(x, y, d - rot0)
                pts += [(math.radians(rx - r), math.radians(ry - r)), (math.radians(rx + r), math.radians(ry + r))]
        return pts

    def scale_for(pts):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min((W - 2 * m) / max(max(xs) - min(xs), 1e-9), (H - 2 * m - extra) / max(max(ys) - min(ys), 1e-9))

    if args.rotate is not None:
        deg = args.rotate
    elif entry and entry.get("free"):
        cand = {c: scale_for(extent_pts(c)) for c in (rot0, rot0 + 90, rot0 - 90)}
        best = max(cand, key=cand.get)
        deg = best if cand[best] > 1.4 * cand[rot0] else rot0
    else:
        deg = rot0
    ext = extent_pts(deg)
    s = scale_for(ext)
    xs, ys = [p[0] for p in ext], [p[1] for p in ext]
    ox = W / 2 - s * (max(xs) + min(xs)) / 2
    oy = (H - extra) / 2 - s * (max(ys) + min(ys)) / 2
    kd = s * math.pi / 180

    def sp(xd, yd):
        rx, ry = rot_deg(xd, yd, deg - rot0)
        return ox + kd * rx, oy + kd * ry

    pos = {k: rot_deg(x, y, deg) for k, (x, y) in raw.items()}
    scr = {k: (ox + s * x, oy + s * y) for k, (x, y) in pos.items()}

    # ---- sky: a sprinkling of star glyphs and dots, behind everything --------------------------
    for _ in range(int(W * H / 1500)):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        if any(math.hypot(x - px, y - py) < 0.03 * U for px, py in scr.values()):
            continue
        if rng.random() < 0.4:
            ctx.add(pth(star_d(x, y, U * rng.uniform(0.0038, 0.0072), 6, 0.36, rng.uniform(-90, -60)), ink))
        else:
            ctx.add(circ(x, y, U / 210 * rng.uniform(0.2, 0.5), ink))

    # ---- the drawing -------------------------------------------------------------------------------
    amp, nsc = 0.0016 * U, 1 / (0.035 * U)
    base_w = max(0.3, 0.0024 * U)
    hs, hw = max(0.5, 0.0040 * U), max(0.13, 0.0010 * U)
    N = ctx.noise

    def wob(pts):
        return [(x + amp * N.n(x * nsc + 3.1, y * nsc), y + amp * N.n(x * nsc, y * nsc + 9.7)) for x, y in pts]

    def hatch(poly):
        ang = math.radians(rng.uniform(48, 66))
        ca, sa = math.cos(ang), math.sin(ang)
        P = [(x * ca + y * sa, -x * sa + y * ca) for x, y in poly]
        vmin, vmax = min(p[1] for p in P), max(p[1] for p in P)
        step = max(hs, (vmax - vmin) / 220)
        n, segs, v = len(P), [], vmin + step * 0.5
        while v < vmax:
            xs_ = []
            for i in range(n):
                (u0, v0), (u1, v1) = P[i], P[(i + 1) % n]
                if (v0 <= v < v1) or (v1 <= v < v0):
                    xs_.append(u0 + (v - v0) / (v1 - v0) * (u1 - u0))
            xs_.sort()
            for j in range(0, len(xs_) - 1, 2):
                a, b = xs_[j], xs_[j + 1]
                L = b - a
                if L < 1.4 * step:
                    continue
                pa, pb = (a * ca - v * sa, a * sa + v * ca), (b * ca - v * sa, b * sa + v * ca)
                f = 0.18 + 0.55 * (0.5 + 0.5 * N.n(pa[0] * nsc * 1.6, pa[1] * nsc * 1.6))
                if pa[0] * 0.35 + pa[1] > pb[0] * 0.35 + pb[1]:       # shade the end facing down/right
                    u0_, u1_ = a, a + f * L
                else:
                    u0_, u1_ = b - f * L, b
                q0 = (u0_ * ca - v * sa, u0_ * sa + v * ca)
                q1 = (u1_ * ca - v * sa, u1_ * sa + v * ca)
                segs.append(f"M{fmt(q0[0])} {fmt(q0[1])}L{fmt(q1[0])} {fmt(q1[1])}")
            v += step
        return "".join(segs)

    seed = [0.0]

    def closed_shape(pts, do_hatch):
        seed[0] += 1.37
        sd = seed[0]
        n = len(pts)
        w = [base_w * (0.62 + 0.76 * (0.5 + 0.5 * N.n(i * 0.21 + sd, sd * 1.7))) for i in range(n)]
        ctx.add(pth(poly_d(pts), paper))
        if do_hatch:
            h = hatch(pts)
            if h:
                ctx.add(pth(h, "none", ink, hw, ' stroke-linecap="round"'))
        ctx.add(f'<path d="{ribbon(pts, w, True)}" fill="{ink}" fill-rule="evenodd"/>')

    def open_stroke(pts, scale=0.85):
        seed[0] += 1.37
        sd = seed[0]
        n = len(pts)
        w = [base_w * scale * max(0.18, math.sin(math.pi * i / (n - 1)) ** 0.5)
             * (0.7 + 0.6 * (0.5 + 0.5 * N.n(i * 0.25 + sd, sd * 0.7))) for i in range(n)]
        ctx.add(f'<path d="{ribbon(pts, w, False)}" fill="{ink}"/>')

    def limb_pts(P, Wd):
        cl = catmull(P, False, 8)
        n = len(cl)
        ws = []
        for i in range(n):
            f = i / (n - 1) * (len(Wd) - 1)
            j = min(int(f), len(Wd) - 2)
            ws.append(Wd[j] + (Wd[j + 1] - Wd[j]) * (f - j))
        L, R = [], []
        for i in range(n):
            a, b = cl[max(i - 1, 0)], cl[min(i + 1, n - 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            d = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / d, dx / d
            L.append((cl[i][0] + nx * ws[i], cl[i][1] + ny * ws[i]))
            R.append((cl[i][0] - nx * ws[i], cl[i][1] - ny * ws[i]))
        e_ang = math.atan2(cl[-1][1] - cl[-2][1], cl[-1][0] - cl[-2][0])
        s_ang = math.atan2(cl[1][1] - cl[0][1], cl[1][0] - cl[0][0])
        end_cap = [(cl[-1][0] + ws[-1] * math.cos(e_ang + math.pi / 2 - math.pi * k / 6),
                    cl[-1][1] + ws[-1] * math.sin(e_ang + math.pi / 2 - math.pi * k / 6)) for k in range(1, 6)]
        start_cap = [(cl[0][0] + ws[0] * math.cos(s_ang - math.pi / 2 - math.pi * k / 6),
                      cl[0][1] + ws[0] * math.sin(s_ang - math.pi / 2 - math.pi * k / 6)) for k in range(1, 6)]
        return L + end_cap + R[::-1] + start_cap

    for op, hat, v in ops:
        if op == "b":
            closed_shape(wob(catmull([sp(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)], True, 6)), hat)
        elif op == "m":
            cx, cy, rx, ry, n, jag = v[0], v[1], v[2], v[3], int(v[4]), v[5]
            pts = []
            for i in range(2 * n):
                a = TAU * i / (2 * n)
                r = 1 + (jag * (0.3 + 1.4 * rng.random()) if i % 2 else -0.04 * rng.random())
                pts.append(sp(cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
            closed_shape(wob(pts), hat)
        elif op == "l":
            P = [sp(v[0], v[1]), sp(v[2], v[3]), sp(v[4], v[5])]
            closed_shape(wob(limb_pts(P, [v[6] * kd, v[7] * kd, v[8] * kd])), hat)
        elif op == "k":
            n = int(v[0])
            P = [sp(v[1 + 2 * i], v[2 + 2 * i]) for i in range(n)]
            closed_shape(wob(limb_pts(P, [w * kd for w in v[1 + 2 * n:1 + 3 * n]])), hat)
        elif op == "w":
            cx, cy, rx, ry, n, jag = v[0], v[1], v[2], v[3], int(v[4]), v[5]
            pts = []
            for i in range(2 * n):
                a = TAU * i / (2 * n)
                r = 1 + (jag * (0.4 + 1.2 * rng.random()) if i % 2 else 0.0)
                pts.append(sp(cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
            closed_shape(wob(catmull(pts, True, 3)), hat)
        elif op == "e":
            c = sp(v[0], v[1])
            a_ = math.radians(v[4] - (deg - rot0))
            pts = []
            for i in range(32):
                t = TAU * i / 32
                ex, ey = v[2] * kd * math.cos(t), v[3] * kd * math.sin(t)
                pts.append((c[0] + ex * math.cos(a_) - ey * math.sin(a_), c[1] + ex * math.sin(a_) + ey * math.cos(a_)))
            closed_shape(wob(pts), hat)
        elif op == "s":
            open_stroke(wob(catmull([sp(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)], False, 6)))
        elif op == "d":
            c = sp(v[0], v[1])
            ctx.add(circ(c[0], c[1], max(0.25, v[2] * kd), ink))

    # ---- constellation: dotted lines + star glyphs ------------------------------------------------
    rad = {k: min(0.0145, max(0.0045, 0.0052 + 0.0017 * (3.8 - stars[k][2]))) * U for k in stars}
    d_norm, d_sol = [], []
    for i, ch in enumerate(chains):
        for a, b in zip(ch, ch[1:]):
            (x0, y0), (x1, y1) = scr[a], scr[b]
            L = math.hypot(x1 - x0, y1 - y0)
            g = 0.006 * U
            if L < rad[a] + rad[b] + 2 * g:
                continue
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            p0 = (x0 + ux * (rad[a] + g), y0 + uy * (rad[a] + g))
            p1 = (x1 - ux * (rad[b] + g), y1 - uy * (rad[b] + g))
            (d_sol if i in solid else d_norm).append(f"M{fmt(p0[0])} {fmt(p0[1])}L{fmt(p1[0])} {fmt(p1[1])}")
    dw = max(0.28, 0.0030 * U)
    if d_norm:
        ctx.add(pth("".join(d_norm), "none", ink, dw, f' stroke-linecap="round" stroke-dasharray="0 {fmt(0.0115 * U)}"'))
    if d_sol:
        ctx.add(pth("".join(d_sol), "none", ink, dw, f' stroke-linecap="round" stroke-dasharray="0 {fmt(0.0066 * U)}"'))
    for k, (x, y) in scr.items():
        mag = stars[k][2]
        ctx.add(circ(x, y, rad[k] * 1.25, paper))
        ctx.add(pth(star_d(x, y, rad[k], 8 if mag < 1.6 else 6, 0.38, -90), ink))
    if args.names:
        fs = 0.021 * U
        boxes = [(x - rad[k], y - rad[k], x + rad[k], y + rad[k]) for k, (x, y) in scr.items()]
        for sid, label in sorted(NAMES.get(key, {}).items(), key=lambda kv: stars[kv[0]][2] if kv[0] in stars else 9):
            if sid not in scr or stars[sid][2] > 3.4:
                continue
            x, y = scr[sid]
            hit = _label_pos(x, y, rad[sid] * 1.4, label, fs, boxes, W, H, "lrbt" if x > 0.6 * W else "rlbt")
            if hit:
                tx, ty, an, box = hit
                boxes.append(box)
                ctx.add(f'<text x="{fmt(tx)}" y="{fmt(ty)}" text-anchor="{an}" font-family="Georgia, \'Times New Roman\', serif" '
                        f'font-style="italic" font-size="{fmt(fs)}" fill="{ink}">{html.escape(label)}</text>')


def draw_constellation(ctx: Ctx, key: str) -> None:
    rng, st, W, H, U, args = ctx.rng, ctx.st, ctx.W, ctx.H, ctx.U, ctx.args
    if args.style == "drawing":
        return draw_constellation_drawing(ctx, key)
    title, stars, chains = CONSTELLATIONS[key]
    illus = args.style == "illustrated"
    art = ART.get(key, {})
    raw, ra0, dec0 = sky_raw(stars)
    names = NAMES.get(key, {})
    show_names = args.names if args.names is not None else illus
    horizon = illus and args.horizon
    shapes = []
    if illus:
        shapes = parse_art(art["shapes"]) if "shapes" in art else generic_art(raw, chains)

    m = (0.11 if illus else 0.13) * U
    extra = (0.07 * U if args.label else 0.0) + (0.14 * H if horizon else 0.0)

    def turned(deg):
        t = math.radians(deg)
        return {k: (x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)) for k, (x, y) in raw.items()}

    def rot_deg(x, y, deg):
        t = math.radians(deg)
        return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)

    def extent_pts(deg):
        pts = list(turned(deg).values())
        for op, v in shapes:
            for x, y, r in _shape_discs(op, v):
                rx, ry = rot_deg(x, y, deg - float(art.get("rot", 0.0)))
                pts += [(math.radians(rx - r), math.radians(ry - r)), (math.radians(rx + r), math.radians(ry + r))]
        return pts

    def scale_for(pts):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min((W - 2 * m) / max(max(xs) - min(xs), 1e-9), (H - 2 * m - extra) / max(max(ys) - min(ys), 1e-9))

    if args.rotate is not None:
        deg = args.rotate
    elif illus:                                             # keep the pose unless a quarter turn fits far better
        r0 = float(art.get("rot", 0.0))
        cand = {c: scale_for(extent_pts(c)) for c in (r0, r0 + 90, r0 - 90)}
        best = max(cand, key=cand.get)
        deg = best if cand[best] > 1.5 * cand[r0] else r0
    else:                                                   # keep north up unless 90 degrees fits far better
        deg = 90.0 if scale_for(extent_pts(90)) > 1.3 * scale_for(extent_pts(0)) else 0.0
    pos = turned(deg)
    ext = extent_pts(deg)
    s = scale_for(ext)
    xs, ys = [p[0] for p in ext], [p[1] for p in ext]
    ox = W / 2 - s * (max(xs) + min(xs)) / 2
    oy = (H - extra) / 2 - s * (max(ys) + min(ys)) / 2
    scr = {k: (ox + s * x, oy + s * y) for k, (x, y) in pos.items()}
    k_deg = s * math.pi / 180                               # screen mm per degree of sky

    rot0 = float(art.get("rot", 0.0))

    def sp(xd, yd):                                         # shape coords: upright frame of the default pose
        rx, ry = rot_deg(xd, yd, deg - rot0)
        return ox + k_deg * rx, oy + k_deg * ry

    base = (0.0042 if illus else 0.0060) * U
    rad = {k: base * max(0.55, min(3.2, 1 + 0.42 * (3.5 - stars[k][2]))) for k in stars}

    # ---- background stars --------------------------------------------------------------
    dens = 230 if illus else 520
    for _ in range(int(W * H / dens)):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        if any(math.hypot(x - px, y - py) < 0.03 * U for px, py in scr.values()):
            continue
        if illus:
            r = U / 210 * (0.12 + 0.55 * rng.random() ** 3)
            op = "" if st.mono else f' opacity="{fmt(0.3 + 0.7 * rng.random())}"'
            ctx.add(circ(x, y, r, st.star(), op))
        else:
            r = U / 210 * rng.choice((0.16, 0.2, 0.26, 0.34, 0.45))
            ctx.add(circ(x, y, r, st.star() if (rng.random() < 0.18 and not st.mono) else st.faint()))

    # ---- the ghostly creature ------------------------------------------------------------
    if illus and shapes:
        fill = st.f("main")
        body, detail = [], []
        for op, v in shapes:
            if op == "c":
                (x0, y0), (x1, y1), r0, r1 = sp(v[0], v[1]), sp(v[2], v[3]), v[4] * k_deg, v[5] * k_deg
                body += [circ(x0, y0, r0, fill), circ(x1, y1, r1, fill)]
                L = math.hypot(x1 - x0, y1 - y0)
                if L > 1e-6:
                    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
                    body.append(pth(poly_d([(x0 + nx * r0, y0 + ny * r0), (x1 + nx * r1, y1 + ny * r1),
                                            (x1 - nx * r1, y1 - ny * r1), (x0 - nx * r0, y0 - ny * r0)]), fill))
            elif op == "e":
                cx, cy = sp(v[0], v[1])
                body.append(ell(cx, cy, v[2] * k_deg, v[3] * k_deg, fill,
                                f' transform="rotate({fmt(v[4] - (deg - rot0))} {fmt(cx)} {fmt(cy)})"'))
            elif op == "p":
                body.append(pth(smooth_d([sp(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]), fill))
            elif op == "d":
                detail.append(pth(smooth_d([sp(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)], closed=False),
                                  "none", st.s("main"), max(0.2, U * 0.0022), ' stroke-linecap="round"'))
            elif op == "o":
                cx, cy = sp(v[0], v[1])
                detail.append(circ(cx, cy, v[2] * k_deg, st.s("main")))
        gop = "" if st.mono else ' opacity="0.17"'
        ctx.add(f"<g{gop}>" + "".join(body) + "</g>")
        if detail:
            ctx.add(f'<g{"" if st.mono else " opacity=" + chr(34) + "0.45" + chr(34)}>' + "".join(detail) + "</g>")

    # ---- constellation lines: solid for the main asterism, dotted for the rest ------------
    solid = set(art.get("solid", [0])) if illus else set(range(len(chains)))
    gap = (0.007 if illus else 0.014) * U
    d_solid, d_dot = [], []
    for i, ch in enumerate(chains):
        for a, b in zip(ch, ch[1:]):
            (x0, y0), (x1, y1) = scr[a], scr[b]
            L = math.hypot(x1 - x0, y1 - y0)
            if L < rad[a] + rad[b] + 2 * gap:
                continue
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            p0 = (x0 + ux * (rad[a] + gap), y0 + uy * (rad[a] + gap))
            p1 = (x1 - ux * (rad[b] + gap), y1 - uy * (rad[b] + gap))
            (d_solid if i in solid else d_dot).append(f"M{fmt(p0[0])} {fmt(p0[1])}L{fmt(p1[0])} {fmt(p1[1])}")
    if illus:
        w = max(0.3, U * 0.0036)
        if d_dot:
            ctx.add(pth("".join(d_dot), "none", st.line(), w * 1.15,
                        f' stroke-linecap="round" stroke-dasharray="0 {fmt(U * 0.0125)}"'))
        ctx.add(pth("".join(d_solid), "none", st.line(), w, ' stroke-linecap="round" stroke-linejoin="round"'))
    else:
        ctx.add(pth("".join(d_solid), "none", st.line(), max(0.25, U * 0.0021), ' stroke-linecap="round"'))

    # ---- stars -------------------------------------------------------------------------------
    if illus and not st.mono:
        ctx.defs.append(f'<radialGradient id="glow"><stop offset="0" stop-color="{st.star()}" stop-opacity="0.9"/>'
                        f'<stop offset="0.3" stop-color="{st.star()}" stop-opacity="0.3"/>'
                        f'<stop offset="1" stop-color="{st.star()}" stop-opacity="0"/></radialGradient>')
    for k, (x, y) in scr.items():
        r, mag = rad[k], stars[k][2]
        if illus and not st.mono and mag <= 2.1:
            ctx.add(circ(x, y, r * (6.5 if mag < 1.2 else 4.2), "url(#glow)"))
        ctx.add(circ(x, y, r, st.star()))
        if mag <= 1.7:                                       # bright stars get diffraction spikes
            L = r * (3.4 if illus else 2.7)
            ctx.add(pth(f"M{fmt(x - L)} {fmt(y)}H{fmt(x + L)}M{fmt(x)} {fmt(y - L)}V{fmt(y + L)}", "none",
                        st.star(), max(0.15, r * 0.16), ' stroke-linecap="round"'))
        if mag <= 1.0 and not illus:
            ctx.add(circ(x, y, r * 1.75, "none", f' stroke="{st.star()}" stroke-width="{fmt(max(0.15, r * 0.1))}"'))

    # ---- labels: star names and asterism names -----------------------------------------------
    if show_names:
        fs = (0.026 if illus else 0.02) * U
        boxes = []
        txt = []
        for text, sid, dx, dy in ASTERISMS.get(key, []) if illus else []:
            rx, ry = rot_deg(dx, dy, deg - rot0)
            x, y = scr[sid][0] + k_deg * rx, scr[sid][1] + k_deg * ry
            an = "start" if rx > 0.3 * abs(ry) else ("end" if rx < -0.3 * abs(ry) else "middle")
            tw = 0.58 * fs * len(text)
            x0 = x if an == "start" else (x - tw if an == "end" else x - tw / 2)
            boxes.append((x0, y - fs, x0 + tw, y + 0.3 * fs))
            txt.append((x, y + 0.33 * fs, an, text))
        for sid, label in names.items():
            if sid not in scr or stars[sid][2] > 3.4:
                continue
            x, y = scr[sid]
            boxes.append((x - rad[sid], y - rad[sid], x + rad[sid], y + rad[sid]))
        for sid, label in sorted(names.items(), key=lambda kv: stars[kv[0]][2] if kv[0] in stars else 9):
            if sid not in scr or stars[sid][2] > 3.4:
                continue
            x, y = scr[sid]
            order = "lrbt" if x > 0.6 * W else "rlbt"
            hit = _label_pos(x, y, rad[sid] * (2.2 if stars[sid][2] <= 2.1 else 1.0), label, fs, boxes, W, H, order)
            if hit:
                tx, ty, an, box = hit
                boxes.append(box)
                txt.append((tx, ty, an, label))
        for tx, ty, an, label in txt:
            ctx.add(f'<text x="{fmt(tx)}" y="{fmt(ty)}" text-anchor="{an}" font-family="Lato, Helvetica, Arial, sans-serif" '
                    f'font-size="{fmt(fs)}" fill="{st.star()}">{html.escape(label)}</text>')

    # ---- mountain horizon ----------------------------------------------------------------------
    if horizon:
        n = 90
        base_y, amp = H - 0.075 * H, 0.05 * H
        off = rng.random() * 40
        pts = []
        for i in range(n + 1):
            x = W * i / n
            v = 0.55 * ctx.noise.fbm(x / U * 2.2 + off, 0.3, 4) + 0.45 * abs(ctx.noise.fbm(x / U * 5 + off, 1.7, 3))
            pts.append((x, base_y - amp * (0.5 + v)))
        ctx.add(pth(poly_d([(0, H + 1)] + pts + [(W, H + 1)]), st.f("dark")))


if __name__ == "__main__":
    sys.exit(main())
