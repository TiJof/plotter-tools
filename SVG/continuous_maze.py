#!/usr/bin/env python3
"""
continuous_maze.py - generate a one-stroke "maze" as an SVG.

The drawing is a single closed line that never crosses itself and fills the
whole sheet.  How it is built:

  1. Kruskal's algorithm builds a random spanning tree on a coarse grid of
     cells (shuffle all edges, add an edge if it joins two separate trees).
  2. Each coarse cell is split into 2x2 "fine" points.  The line passes through
     those points and hugs the tree on both sides.  Because a tree has no
     loops, the outline is ONE closed cycle visiting every fine point once.
  3. Corners are rounded with circular arcs so a pen can flow through them.

Every run uses a fresh random seed (printed to stderr), so every output is
different.  Pass --seed N to reproduce a drawing.

Examples
--------
  python continuous_maze.py A4
  python continuous_maze.py A3 --landscape --pitch 2.5 -o poster.svg
  python continuous_maze.py 30x20cm --pitch 3 --stroke 1 --color "#b5523b"
  python continuous_maze.py 12x8in --seed 42

Sizes: ISO A0-A6, LETTER, LEGAL, or WIDTHxHEIGHT with a unit (mm, cm, in, m).
A bare WIDTHxHEIGHT is read as millimetres.  All other lengths are in mm.
"""
from __future__ import annotations

import argparse
import html
import random
import re
import sys
from pathlib import Path

PAPER_MM = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
    "A4": (210, 297), "A5": (148, 210), "A6": (105, 148),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6),
}
UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "m": 1000.0}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_size(text: str) -> tuple[float, float]:
    """'A4' -> (210, 297) ; '30x20cm' -> (300, 200) ; '300x200' -> (300, 200)."""
    t = text.strip().lower().replace(" ", "")
    if t.upper() in PAPER_MM:
        return tuple(float(v) for v in PAPER_MM[t.upper()])
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(mm|cm|in|m)?[x\u00d7*](\d+(?:\.\d+)?)(mm|cm|in|m)?", t)
    if not m:
        raise ValueError(
            f"Cannot understand size {text!r}. Use A4, A3, ... or e.g. 30x20cm, 300x200mm, 12x8in."
        )
    w, u1, h, u2 = m.groups()
    unit = UNIT_MM[u2 or u1 or "mm"]
    return float(w) * UNIT_MM[u1 or u2 or "mm"], float(h) * unit


def fmt(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


# --------------------------------------------------------------------------- #
# 1. Random spanning tree (Kruskal)
# --------------------------------------------------------------------------- #
def kruskal_tree(cw: int, ch: int, rng: random.Random):
    """Return (right, down): right[y][x] = tree edge (x,y)-(x+1,y),
    down[y][x] = tree edge (x,y)-(x,y+1)."""
    parent = list(range(cw * ch))

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:            # path compression
            parent[i], i = root, parent[i]
        return root

    edges = [(x, y, 0) for y in range(ch) for x in range(cw - 1)]
    edges += [(x, y, 1) for y in range(ch - 1) for x in range(cw)]
    rng.shuffle(edges)

    right = [bytearray(cw) for _ in range(ch)]
    down = [bytearray(cw) for _ in range(ch)]
    needed = cw * ch - 1
    for x, y, vertical in edges:
        a = y * cw + x
        b = a + cw if vertical else a + 1
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            (down if vertical else right)[y][x] = 1
            needed -= 1
            if needed == 0:
                break
    return right, down


# --------------------------------------------------------------------------- #
# 2. Walk around the tree -> one closed cycle on the 2cw x 2ch fine grid
# --------------------------------------------------------------------------- #
def trace_outline(cw: int, ch: int, right, down) -> list[tuple[int, int]]:
    """Fine point (a, b) sits in coarse cell (a//2, b//2), quadrant (a%2, b%2).
    Each fine point has exactly two neighbours:
      * inside its cell, unless a tree edge on that side separates the quadrants;
      * across the cell border, only where the tree edge exists (the line runs
        along both sides of every tree edge)."""

    def neighbours(a: int, b: int):
        x, y, i, j = a >> 1, b >> 1, a & 1, b & 1
        has_l = x > 0 and right[y][x - 1]
        has_r = x < cw - 1 and right[y][x]
        has_u = y > 0 and down[y - 1][x]
        has_d = y < ch - 1 and down[y][x]
        blocks_h = has_u if j == 0 else has_d      # splits the cell's left/right
        blocks_v = has_l if i == 0 else has_r      # splits the cell's top/bottom
        out = []
        if i == 0:
            if not blocks_h: out.append((a + 1, b))
            if has_l:        out.append((a - 1, b))
        else:
            if not blocks_h: out.append((a - 1, b))
            if has_r:        out.append((a + 1, b))
        if j == 0:
            if not blocks_v: out.append((a, b + 1))
            if has_u:        out.append((a, b - 1))
        else:
            if not blocks_v: out.append((a, b - 1))
            if has_d:        out.append((a, b + 1))
        return out

    total = 4 * cw * ch
    start = (0, 0)
    cycle = [start]
    prev, cur = None, start
    while True:
        n0, n1 = neighbours(*cur)
        nxt = n0 if n0 != prev else n1
        if nxt == start:
            break
        cycle.append(nxt)
        prev, cur = cur, nxt
        if len(cycle) > total:
            raise RuntimeError("Outline did not close - this should never happen.")
    if len(cycle) != total:
        raise RuntimeError(f"Outline visits {len(cycle)} of {total} points - bug.")
    return cycle


# --------------------------------------------------------------------------- #
# 3. Cycle -> SVG path with rounded corners
# --------------------------------------------------------------------------- #
def cycle_to_path(cycle, pitch: float, ox: float, oy: float, rounding: float) -> str:
    n = len(cycle)
    d = rounding * pitch / 2                       # corner radius (<= half a step)
    pts = [(ox + (a + 0.5) * pitch, oy + (b + 0.5) * pitch) for a, b in cycle]

    # Start in the middle of the first segment so the closing join is smooth.
    sx, sy = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
    cur = [sx, sy]
    out = [f"M{fmt(sx)} {fmt(sy)}"]

    def line_to(x: float, y: float) -> None:
        if abs(x - cur[0]) < 1e-9 and abs(y - cur[1]) < 1e-9:
            return
        if abs(x - cur[0]) < 1e-9:
            out.append(f"V{fmt(y)}")
        elif abs(y - cur[1]) < 1e-9:
            out.append(f"H{fmt(x)}")
        else:
            out.append(f"L{fmt(x)} {fmt(y)}")
        cur[0], cur[1] = x, y

    for k in range(1, n + 1):
        a, b, c = cycle[k - 1], cycle[k % n], cycle[(k + 1) % n]
        din = (b[0] - a[0], b[1] - a[1])
        dout = (c[0] - b[0], c[1] - b[1])
        if din == dout:                            # straight: nothing to emit
            continue
        vx, vy = pts[k % n]
        if d < 1e-9:                               # sharp corners
            line_to(vx, vy)
            continue
        line_to(vx - din[0] * d, vy - din[1] * d)
        ex, ey = vx + dout[0] * d, vy + dout[1] * d
        sweep = 1 if din[0] * dout[1] - din[1] * dout[0] > 0 else 0
        out.append(f"A{fmt(d)} {fmt(d)} 0 0 {sweep} {fmt(ex)} {fmt(ey)}")
        cur[0], cur[1] = ex, ey

    line_to(sx, sy)
    out.append("Z")
    return "".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate a one-stroke, non-crossing maze-like line as an SVG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("size", nargs="?", default="A4",
                    help="A0-A6, LETTER, LEGAL, or WxH with unit, e.g. 30x20cm")
    orient = ap.add_mutually_exclusive_group()
    orient.add_argument("-l", "--landscape", action="store_true", help="force landscape")
    orient.add_argument("-p", "--portrait", action="store_true", help="force portrait")
    ap.add_argument("-o", "--output", default="maze.svg", help="output file")
    ap.add_argument("--pitch", type=float, default=3.0,
                    help="distance between neighbouring lines, in mm (smaller = denser)")
    ap.add_argument("--stroke", type=float, default=None,
                    help="line width in mm (default: pitch / 3)")
    ap.add_argument("--margin", type=float, default=10.0, help="page margin in mm")
    ap.add_argument("--round", dest="rounding", type=float, default=1.0,
                    help="corner rounding, 0 (sharp) to 1 (fully round)")
    ap.add_argument("--color", default="#222222", help="line colour")
    ap.add_argument("--background", default="none",
                    help="background colour, or 'none' for a transparent page")
    ap.add_argument("--seed", type=int, default=None,
                    help="random seed (default: new random seed every run)")
    args = ap.parse_args(argv)

    try:
        width, height = parse_size(args.size)
    except ValueError as e:
        ap.error(str(e))
    if args.landscape and width < height:
        width, height = height, width
    if args.portrait and width > height:
        width, height = height, width
    if not 0 <= args.rounding <= 1:
        ap.error("--round must be between 0 and 1")
    if args.pitch <= 0:
        ap.error("--pitch must be positive")

    pitch = args.pitch
    stroke = args.stroke if args.stroke is not None else pitch / 3

    # One coarse cell = 2 x 2 fine steps. Fit as many as possible, centre them.
    cw = int((width - 2 * args.margin) // (2 * pitch))
    ch = int((height - 2 * args.margin) // (2 * pitch))
    if cw < 1 or ch < 1:
        ap.error("Page too small for this pitch/margin - reduce --pitch or --margin.")
    ox = (width - 2 * cw * pitch) / 2
    oy = (height - 2 * ch * pitch) / 2

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 32)
    rng = random.Random(seed)

    right, down = kruskal_tree(cw, ch, rng)
    cycle = trace_outline(cw, ch, right, down)
    path = cycle_to_path(cycle, pitch, ox, oy, args.rounding)

    bg = ""
    if args.background.lower() != "none":
        bg = (f'  <rect width="100%" height="100%" '
              f'fill="{html.escape(args.background, quote=True)}"/>\n')

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}mm" height="{fmt(height)}mm" '
        f'viewBox="0 0 {fmt(width)} {fmt(height)}">\n'
        f'  <title>One-stroke maze, seed {seed}</title>\n'
        f'  <!-- Kruskal spanning tree {cw}x{ch} cells, pitch {fmt(pitch)} mm, seed {seed} -->\n'
        f'{bg}'
        f'  <path d="{path}" fill="none" stroke="{html.escape(args.color, quote=True)}" '
        f'stroke-width="{fmt(stroke)}" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '</svg>\n'
    )
    Path(args.output).write_text(svg, encoding="utf-8")

    length_m = len(cycle) * pitch / 1000
    print(f"{args.output}: {fmt(width)} x {fmt(height)} mm, {cw}x{ch} tree cells, "
          f"{len(cycle)} points, ~{length_m:.1f} m of line, seed {seed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
