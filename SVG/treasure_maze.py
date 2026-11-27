#!/usr/bin/env python3
"""
treasure_maze.py - generate a treasure-hunt maze as an SVG.

* The maze can be a rectangle, an ellipse or a circle (--shape).  The ellipse is the one inscribed
  in the page area, so on a portrait page it is a tall oval.
* --letter X (A-Z or 0-9) makes the SOLUTION trace that character: the route runs from the entrance to
  the middle of the maze, then hugs both sides of every stroke of a big pixel-font glyph, and ends
  next to where it entered (the chest is there).  The solution file shows it as an outlined letter.
  The four card suits work too: --letter spade|heart|diamond|club (alias --symbol).  By default a suit is
  filled with one continuous meander; --symbol-style outline traces just its contour.
  The rest of the maze grows around the letter as side branches, still with at most --max-children
  children per line.
* The entrance is a gap on one side of the maze (add --start-arrow to mark it
  with a green arrow).
* A treasure chest hides somewhere inside (by default at a random dead end
  that is far enough from the entrance to be worth finding).
* It is a "perfect" maze: exactly one route from the entrance to every cell,
  no loops, no sealed-off areas.
* Branching is bounded.  The maze is built from "lines": winding corridors that
  start at a junction and run on to a dead end.  A line may sprout at most
  --max-children (default 5) child lines.  Children are grown breadth-first,
  so you get a tidy river-delta hierarchy instead of a tangle.

Every run uses a fresh random seed (printed to stderr and stored in the SVG);
pass --seed N to reproduce a maze.  --solution also writes <name>_solution.svg.

Examples
--------
  python treasure_maze.py A4
  python treasure_maze.py A3 --landscape --cell 5 --solution
  python treasure_maze.py 30x20cm --start-side top --treasure far
  python treasure_maze.py A4 --max-children 3 --line-length 12 --seed 42
  python treasure_maze.py A4 --start-arrow
  python treasure_maze.py A4 --shape ellipse --cell 4
  python treasure_maze.py A3 --landscape --shape ellipse --start-side random --solution
  python treasure_maze.py 30x30cm --shape circle
  python treasure_maze.py A4 --letter R --start-arrow          # solution spells R
  python treasure_maze.py A3 --landscape --letter 7 --shape ellipse --cell 4
  python treasure_maze.py A4 --symbol heart --start-arrow
  python treasure_maze.py A4 --symbol spade --symbol-style outline --cell 4

Sizes: ISO A0-A6, LETTER, LEGAL, or WIDTHxHEIGHT with a unit (mm, cm, in, m).
A bare WIDTHxHEIGHT is read as millimetres.  All other lengths are in mm.
"""
from __future__ import annotations

import argparse
import html
import random
import re
import sys
from collections import deque
from pathlib import Path

PAPER_MM = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
    "A4": (210, 297), "A5": (148, 210), "A6": (105, 148),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6),
}
UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "m": 1000.0}
SIDES = ("left", "right", "top", "bottom")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_size(text: str) -> tuple[float, float]:
    t = text.strip().lower().replace(" ", "")
    if t.upper() in PAPER_MM:
        return tuple(float(v) for v in PAPER_MM[t.upper()])
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(mm|cm|in|m)?[x\u00d7*](\d+(?:\.\d+)?)(mm|cm|in|m)?", t)
    if not m:
        raise ValueError(
            f"Cannot understand size {text!r}. Use A4, A3, ... or e.g. 30x20cm, 300x200mm, 12x8in."
        )
    w, u1, h, u2 = m.groups()
    return float(w) * UNIT_MM[u1 or u2 or "mm"], float(h) * UNIT_MM[u2 or u1 or "mm"]


def fmt(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


# --------------------------------------------------------------------------- #
# Maze growth: bounded-branching "lines"
# --------------------------------------------------------------------------- #
class GenerationFailed(Exception):
    pass


class LineMaze:
    def __init__(self, cols, rows, rng, max_children, line_len, straightness, active=None):
        self.cols, self.rows, self.rng = cols, rows, rng
        self.cap, self.line_len, self.straight = max_children, line_len, straightness
        self.n = cols * rows
        self.active = active if active is not None else [True] * self.n   # cells that belong to the maze
        self.n_active = sum(self.active)
        # line_of: -1 = free cell of the maze, -2 = outside the maze shape, >= 0 = owned by that line
        self.line_of = [-1 if a else -2 for a in self.active]
        self.right = [bytearray(cols) for _ in range(rows)]   # passage (x,y)-(x+1,y)
        self.down = [bytearray(cols) for _ in range(rows)]    # passage (x,y)-(x,y+1)
        self.cells: list[list[int]] = []        # cells of each line, in walking order
        self.children: list[int] = []           # child lines sprouted so far
        self.parent: list[int] = []             # parent line (-1 for the root)
        self.want: list[int] = []               # children this line would like
        self.unvisited = self.n_active
        self.nbr = []
        for i in range(self.n):
            y, x = divmod(i, cols)
            nb = []
            if self.active[i]:                  # only neighbours inside the shape are reachable
                if x > 0 and self.active[i - 1]: nb.append(i - 1)
                if x < cols - 1 and self.active[i + 1]: nb.append(i + 1)
                if y > 0 and self.active[i - cols]: nb.append(i - cols)
                if y < rows - 1 and self.active[i + cols]: nb.append(i + cols)
            self.nbr.append(nb)

    # -- small utilities ---------------------------------------------------- #
    def carve(self, a: int, b: int) -> None:
        if a > b:
            a, b = b, a
        y, x = divmod(a, self.cols)
        if b - a == self.cols:
            self.down[y][x] = 1
        else:
            self.right[y][x] = 1

    def room(self, w: int) -> int:
        """Unvisited cells in the 5x5 window around w (how open the area is)."""
        y, x = divmod(w, self.cols)
        count = 0
        for yy in range(max(0, y - 2), min(self.rows, y + 3)):
            base = yy * self.cols
            for xx in range(max(0, x - 2), min(self.cols, x + 3)):
                if self.line_of[base + xx] == -1:
                    count += 1
        return count

    # -- growing one line --------------------------------------------------- #
    def grow_line(self, first: int, frm, parent: int, delta: int, want: int) -> int:
        lid = len(self.cells)
        cells = [first]
        self.cells.append(cells)
        self.children.append(0)
        self.parent.append(parent)
        self.want.append(want)
        self.line_of[first] = lid
        self.unvisited -= 1
        if frm is not None:
            self.carve(frm, first)

        target = max(2, round(self.rng.uniform(0.5, 1.5) * self.line_len))
        cur = first
        while len(cells) < target:
            opts = [j for j in self.nbr[cur] if self.line_of[j] == -1]
            if not opts:
                break
            ahead = cur + delta
            if ahead in opts and (len(opts) == 1 or self.rng.random() < self.straight):
                nxt = ahead
            else:
                others = [j for j in opts if j != ahead] or opts
                nxt = self.rng.choices(others, weights=[1 + self.room(j) for j in others])[0]
            self.carve(cur, nxt)
            self.line_of[nxt] = lid
            self.unvisited -= 1
            cells.append(nxt)
            delta, cur = nxt - cur, nxt
        return lid

    # -- sprouting children ------------------------------------------------- #
    def _want(self) -> int:
        """Children a line asks for while growing. One slot is always kept in reserve
        so that leftover pockets can still be attached to it later."""
        return self.rng.randint(1, max(1, self.cap - 1))

    def _spawn(self, lid: int, u: int, w: int, queue) -> None:
        child = self.grow_line(w, u, lid, w - u, self._want())
        self.children[lid] += 1
        queue.append(child)

    def spawn_children(self, lid: int, queue) -> None:
        used: list[int] = []
        for _ in range(self.want[lid]):
            if self.children[lid] >= self.cap:
                break
            cands = []
            for k, u in enumerate(self.cells[lid]):
                free = [w for w in self.nbr[u] if self.line_of[w] == -1]
                if not free:
                    continue
                crowd = 0.05 if any(abs(k - kk) <= 1 for kk in used) else 1.0
                for w in free:
                    cands.append((k, u, w, (1 + self.room(w)) * crowd))
            if not cands:
                break
            k, u, w, _ = self.rng.choices(cands, weights=[c[3] for c in cands])[0]
            used.append(k)
            self._spawn(lid, u, w, queue)

    def repair(self, queue) -> bool:
        """Attach a leftover pocket to any line that still has spare child slots."""
        cands = []
        for lid, cells in enumerate(self.cells):
            if self.children[lid] >= self.cap:
                continue
            for u in cells:
                for w in self.nbr[u]:
                    if self.line_of[w] == -1:
                        cands.append((lid, u, w))
        if not cands:
            return False
        lid, u, w = self.rng.choice(cands)
        self._spawn(lid, u, w, queue)
        return True

    def build(self, start: int, inward: int) -> None:
        self.grow_line(start, None, -1, inward, max(1, self.cap - 1))
        queue = deque([0])
        while True:
            while queue:
                self.spawn_children(queue.popleft(), queue)
            if self.unvisited == 0:
                return
            if not self.repair(queue):
                raise GenerationFailed

    def build_path(self, path, seg_len) -> None:
        """Grow the maze around a ready-made solution path (a list of adjacent cells).  The path is cut into
        line segments, each with one child (the next segment) plus its share of side branches, so the
        'at most --max-children children per line' rule holds for the solution too."""
        segs = [path[i:i + seg_len] for i in range(0, len(path), seg_len)]
        if len(segs) > 1 and len(segs[-1]) < 3:      # fold a tiny tail into the previous segment
            tail = segs.pop()
            segs[-1] = segs[-1] + tail
        prev = -1
        for k, seg in enumerate(segs):
            lid = len(self.cells)
            self.cells.append(list(seg))
            self.children.append(0)
            self.parent.append(prev)
            self.want.append(max(1, self.cap - 2) if k < len(segs) - 1 else max(1, self.cap - 1))
            for a, b in zip(seg, seg[1:]):
                self.carve(a, b)
            for cell in seg:
                self.line_of[cell] = lid
                self.unvisited -= 1
            if prev >= 0:
                self.carve(self.cells[prev][-1], seg[0])
                self.children[prev] += 1
            prev = lid
        queue = deque(range(len(segs)))
        while True:
            while queue:
                self.spawn_children(queue.popleft(), queue)
            if self.unvisited == 0:
                return
            if not self.repair(queue):
                raise GenerationFailed

    # -- analysis ----------------------------------------------------------- #
    def adjacency(self):
        adj = [[] for _ in range(self.n)]
        for y in range(self.rows):
            for x in range(self.cols):
                i = y * self.cols + x
                if x < self.cols - 1 and self.right[y][x]:
                    adj[i].append(i + 1); adj[i + 1].append(i)
                if y < self.rows - 1 and self.down[y][x]:
                    adj[i].append(i + self.cols); adj[i + self.cols].append(i)
        return adj

    def line_depth(self) -> int:
        depth = [0] * len(self.cells)
        for lid in range(1, len(self.cells)):          # parents are always created first
            depth[lid] = depth[self.parent[lid]] + 1
        return max(depth)


def auto_line_length(cells, cap) -> int:
    """Typical line length. A smaller child cap needs shorter lines (more lines,
    hence more branch points) or pockets of the maze can't be reached."""
    base = min(cells ** 0.5 / 2, 20)             # long lines can't fill big mazes
    return max(4, int(base * min(1.0, (cap - 1) / 4)))


def generate(cols, rows, start, inward, rng, args, active=None, attempts=40):
    cells = sum(active) if active is not None else cols * rows
    line_len = args.line_length or auto_line_length(cells, args.max_children)
    for _ in range(attempts):
        maze = LineMaze(cols, rows, rng, args.max_children, line_len, args.straightness, active)
        try:
            maze.build(start, inward)
        except GenerationFailed:
            continue
        adj = maze.adjacency()
        depth, parent = bfs(adj, start)
        edges = sum(len(a) for a in adj) // 2
        assert edges == maze.n_active - 1 and all(depth[i] >= 0 for i in range(maze.n) if maze.active[i]), \
            "not a spanning tree - bug"
        assert max(maze.children) <= args.max_children, "child limit violated - bug"
        return maze, adj, depth, parent
    raise SystemExit(
        f"Could not fill the maze with max {args.max_children} children per line and lines "
        f"of ~{line_len} cells. Try a shorter --line-length or a larger --max-children."
    )


def bfs(adj, start):
    depth = [-1] * len(adj)
    parent = [-1] * len(adj)
    depth[start] = 0
    dq = deque([start])
    while dq:
        i = dq.popleft()
        for j in adj[i]:
            if depth[j] < 0:
                depth[j] = depth[i] + 1
                parent[j] = i
                dq.append(j)
    return depth, parent


def pick_treasure(mode, adj, depth, start, min_frac, rng) -> int:
    far = max(depth)
    thr = max(1, int(min_frac * far))
    leaves = [i for i in range(len(adj)) if len(adj[i]) == 1 and i != start]
    if mode == "far" or not leaves:
        pool = [i for i in range(len(adj)) if depth[i] == far]
    elif mode == "any":
        pool = [i for i in range(len(adj)) if depth[i] >= thr]
    else:
        pool = [i for i in leaves if depth[i] >= thr]
    return rng.choice(pool or [depth.index(far)])


# --------------------------------------------------------------------------- #
# SVG output
# --------------------------------------------------------------------------- #
def border_point(entrance, ox, oy, c):
    """Middle of the cell edge where the entrance gap is."""
    sx, sy, side = entrance
    return {
        "left": (ox + sx * c, oy + (sy + 0.5) * c), "right": (ox + (sx + 1) * c, oy + (sy + 0.5) * c),
        "top": (ox + (sx + 0.5) * c, oy + sy * c), "bottom": (ox + (sx + 0.5) * c, oy + (sy + 1) * c),
    }[side]


def walls_path(maze, ox, oy, c, entrance) -> str:
    """Every wall between two cells, plus the outline of the maze shape (minus the entrance)."""
    cols, rows, act = maze.cols, maze.rows, maze.active
    sx, sy, side = entrance

    def on(x, y):
        return 0 <= x < cols and 0 <= y < rows and act[y * cols + x]

    def hwall(r, x):                               # wall on horizontal line r, between cells (x, r-1) and (x, r)
        above, below = on(x, r - 1), on(x, r)
        if above and below:
            return not maze.down[r - 1][x]
        if above or below:                         # outline of the shape
            return not ((side == "top" and x == sx and r == sy) or (side == "bottom" and x == sx and r == sy + 1))
        return False

    def vwall(q, y):                               # wall on vertical line q, between cells (q-1, y) and (q, y)
        left, right = on(q - 1, y), on(q, y)
        if left and right:
            return not maze.right[y][q - 1]
        if left or right:
            return not ((side == "left" and y == sy and q == sx) or (side == "right" and y == sy and q == sx + 1))
        return False

    parts = []
    for r in range(rows + 1):
        x = 0
        while x < cols:
            if hwall(r, x):
                x0 = x
                while x < cols and hwall(r, x):
                    x += 1
                parts.append(f"M{fmt(ox + x0 * c)} {fmt(oy + r * c)}H{fmt(ox + x * c)}")
            else:
                x += 1
    for q in range(cols + 1):
        y = 0
        while y < rows:
            if vwall(q, y):
                y0 = y
                while y < rows and vwall(q, y):
                    y += 1
                parts.append(f"M{fmt(ox + q * c)} {fmt(oy + y0 * c)}V{fmt(oy + y * c)}")
            else:
                y += 1
    return "".join(parts)


def chest_svg(cx, cy, size) -> str:
    return (
        f'<g transform="translate({fmt(cx)} {fmt(cy)}) scale({fmt(size)})" stroke="#4a2f05" '
        'stroke-width="0.045" stroke-linejoin="round" stroke-linecap="round">'
        '<rect x="-0.5" y="-0.02" width="1" height="0.4" rx="0.04" fill="#c98a1b"/>'
        '<path d="M-0.5 -0.02V-0.14C-0.5 -0.46 0.5 -0.46 0.5 -0.14V-0.02Z" fill="#e0a82e"/>'
        '<path d="M-0.5 -0.02H0.5M-0.3 -0.3V0.38M0.3 -0.3V0.38" fill="none"/>'
        '<rect x="-0.07" y="-0.09" width="0.14" height="0.2" rx="0.025" fill="#4a2f05"/>'
        '</g>'
    )


def arrow_svg(px, py, side, length, half, color) -> str:
    angle = {"left": 0, "top": 90, "right": 180, "bottom": 270}[side]
    return (
        f'<g transform="translate({fmt(px)} {fmt(py)}) rotate({angle})">'
        f'<path d="M{fmt(half * 0.4)} 0L{fmt(-length)} {fmt(-half)}L{fmt(-length)} {fmt(half)}Z" '
        f'fill="{color}"/></g>'
    )


def solution_path(maze, parent, treasure, ox, oy, c, entrance) -> str:
    chain = []
    i = treasure
    while i != -1:
        chain.append(i)
        i = parent[i]
    chain.reverse()                                # start ... treasure
    pts = [(ox + (i % maze.cols + 0.5) * c, oy + (i // maze.cols + 0.5) * c) for i in chain]
    pts.insert(0, border_point(entrance, ox, oy, c))
    d = [f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d.append(f"H{fmt(x1)}" if abs(y1 - y0) < 1e-9 else f"V{fmt(y1)}")
    return "".join(d)


def make_mask(cols, rows, shape):
    """Which grid cells belong to the maze. rectangle: all of them. ellipse/circle: the cells
    whose centre lies inside the ellipse inscribed in the grid (largest connected piece only)."""
    n = cols * rows
    if shape == "rectangle":
        return [True] * n
    a, b = cols / 2, rows / 2
    act = [((x + 0.5 - a) / a) ** 2 + ((y + 0.5 - b) / b) ** 2 <= 1.0 for y in range(rows) for x in range(cols)]
    seen, best = [False] * n, []
    for i in range(n):
        if act[i] and not seen[i]:
            comp, stack = [i], [i]
            seen[i] = True
            while stack:
                k = stack.pop()
                y, x = divmod(k, cols)
                for j in ((k - 1) if x > 0 else None, (k + 1) if x < cols - 1 else None,
                          (k - cols) if y > 0 else None, (k + cols) if y < rows - 1 else None):
                    if j is not None and act[j] and not seen[j]:
                        seen[j] = True
                        comp.append(j)
                        stack.append(j)
            if len(comp) > len(best):
                best = comp
    keep = set(best)
    return [i in keep for i in range(n)]


def pick_entrance(side, cols, rows, active, rng):
    """A random cell on the outline facing `side`: the outermost active cell of a random row/column."""
    lines = {}
    for i, on in enumerate(active):
        if on:
            y, x = divmod(i, cols)
            key, val = (y, x) if side in ("left", "right") else (x, y)
            lines.setdefault(key, []).append(val)
    key = rng.choice(sorted(lines))
    val = min(lines[key]) if side in ("left", "top") else max(lines[key])
    return (val, key) if side in ("left", "right") else (key, val)


# --------------------------------------------------------------------------- #
# Letter-shaped solutions
# --------------------------------------------------------------------------- #
# 5x7 skeleton glyphs: every stroke is one pixel wide, so scaling them up keeps strokes one cell thick.
FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": (".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
}


def _stair(x0, y0, x1, y1):
    """Cells of a 4-connected line from (x0, y0) to (x1, y1) (straight or a staircase diagonal)."""
    sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
    x, y, out = x0, y0, [(x0, y0)]
    while (x, y) != (x1, y1):
        if x != x1:
            x += sx
            out.append((x, y))
        if y != y1:
            y += sy
            out.append((x, y))
    return out


def glyph_cells(ch, s):
    """The glyph as a set of coarse cells, scaled by s (strokes stay one coarse cell thick)."""
    px = {(x, y) for y, row in enumerate(FONT[ch]) for x, v in enumerate(row) if v == "#"}
    cells = set()
    for x, y in px:
        cells.add((x * s, y * s))
        for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            if (x + dx, y + dy) in px:
                cells.update(_stair(x * s, y * s, (x + dx) * s, (y + dy) * s))
    return cells, 4 * s + 1, 6 * s + 1


# Card suits are drawn as silhouettes (implicit curves) sampled on the coarse grid.  --symbol-style decides
# whether the route traces only their outline or fills them completely.
SYMBOL_ALIASES = {
    "spade": "spade", "spades": "spade", "\u2660": "spade", "\u2664": "spade",
    "heart": "heart", "hearts": "heart", "\u2665": "heart", "\u2661": "heart",
    "diamond": "diamond", "diamonds": "diamond", "diam": "diamond", "\u2666": "diamond", "\u2662": "diamond",
    "club": "club", "clubs": "club", "\u2663": "club", "\u2667": "club",
}
SYMBOL_ASPECT = {"spade": 0.84, "heart": 1.0, "diamond": 0.70, "club": 0.96}


def _heart_in(x, y):                     # classic implicit heart, tip at y = -1, lobes at y ~ +1.2
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3 <= 0


def _suit_inside(name, u, v, ar):
    """Is the point (u, v) of the unit box (v downwards) inside the suit?  ar = width / height."""
    if name == "diamond":
        return abs(u - 0.5) / 0.5 + abs(v - 0.5) / 0.5 <= 1.0
    if name == "heart":
        return _heart_in((u - 0.5) * 2.3, 1.25 - v * 2.3)
    x, y = (u - 0.5) * ar, v                                       # centred, in units of the height
    if name == "spade":                                            # pointed top, two round lobes, flared stem
        if y <= 0.55 and abs(x) <= 0.42 * (y / 0.55) ** 0.6:
            return True
        if any((x - cx) ** 2 + (y - 0.57) ** 2 <= 0.22 ** 2 for cx in (-0.20, 0.20)):
            return True
        if 0.40 <= y <= 0.65 and abs(x) <= 0.20:
            return True
        return y >= 0.62 and abs(x) <= 0.045 + 0.20 * max(0.0, (y - 0.82) / 0.18) ** 2
    for cx, cy, r in ((0.0, 0.215, 0.215), (-0.265, 0.625, 0.215), (0.265, 0.625, 0.215), (0.0, 0.50, 0.12)):   # club
        if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
            return True
    return y >= 0.60 and abs(x) <= 0.05 + 0.20 * max(0.0, (y - 0.84) / 0.16) ** 1.5


def symbol_cells(name, s, style):
    """A suit as a set of coarse cells (height 6*s+1, like the letters of the same scale)."""
    H = 6 * s + 1
    W = max(3, round(SYMBOL_ASPECT[name] * H))
    ar = W / H
    subs = (1 / 6, 3 / 6, 5 / 6)                    # 3x3 supersampling keeps thin parts at low resolution
    mask = {(i, j) for j in range(H) for i in range(W)
            if sum(_suit_inside(name, (i + a) / W, (j + b) / H, ar) for a in subs for b in subs) >= 4}
    if style != "solid":
        mask = {(i, j) for (i, j) in mask if any((i + dx, j + dy) not in mask for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    best, seen = set(), set()                      # keep the largest 4-connected piece (tiny sizes can split)
    for start in sorted(mask):
        if start in seen:
            continue
        comp, stack = set(), [start]
        while stack:
            c = stack.pop()
            if c in comp:
                continue
            comp.add(c)
            x, y = c
            stack.extend(n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if n in mask and n not in comp)
        seen |= comp
        if len(comp) > len(best):
            best = comp
    return best, W, H


def shape_cells(ch, s, style):
    return symbol_cells(ch, s, style) if ch in SYMBOL_ALIASES.values() else glyph_cells(ch, s)


def glyph_cycle(S, rng):
    """One closed loop through the 2x2 fine cells of every coarse cell of S: it hugs both sides of a random
    spanning tree of S (the construction from continuous_maze.py), so it visits all 4*len(S) fine cells once."""
    cells = sorted(S)
    idx = {c: i for i, c in enumerate(cells)}
    parent = list(range(len(cells)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = [(x, y, 0) for x, y in cells if (x + 1, y) in S] + [(x, y, 1) for x, y in cells if (x, y + 1) in S]
    rng.shuffle(edges)
    hedge, vedge = set(), set()
    for x, y, vert in edges:
        ra, rb = find(idx[(x, y)]), find(idx[(x, y + 1)] if vert else idx[(x + 1, y)])
        if ra != rb:
            parent[ra] = rb
            (vedge if vert else hedge).add((x, y))
    if len({find(i) for i in range(len(cells))}) != 1:
        raise ValueError("internal error: glyph is not connected")

    def neighbours(a, b):
        x, y, i, j = a >> 1, b >> 1, a & 1, b & 1
        has_l, has_r = (x - 1, y) in hedge, (x, y) in hedge
        has_u, has_d = (x, y - 1) in vedge, (x, y) in vedge
        blocks_h = has_u if j == 0 else has_d
        blocks_v = has_l if i == 0 else has_r
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

    total = 4 * len(cells)
    start = (cells[0][0] * 2, cells[0][1] * 2)
    cycle, prev, cur = [start], None, start
    while True:
        n0, n1 = neighbours(*cur)
        nxt = n0 if n0 != prev else n1
        if nxt == start:
            break
        cycle.append(nxt)
        prev, cur = cur, nxt
        if len(cycle) > total:
            raise ValueError("internal error: outline did not close")
    if len(cycle) != total:
        raise ValueError("internal error: outline does not cover the glyph")
    return cycle


def plan_letter(ch, scale, cols, rows, active, entrance, rng, style="solid"):
    """Place the glyph in the middle of the maze and return the full solution path (entrance ... end of the
    letter) as a list of cell indices.  The path leads from the entrance straight to the glyph, then hugs
    every stroke of it, and ends right next to where it entered (the chest lives there)."""
    placed = None
    for sc in ([scale] if scale else range(14, 0, -1)):
        S, bw, bh = shape_cells(ch, sc, style)
        cx0, cy0 = (cols // 2 - bw) // 2, (rows // 2 - bh) // 2
        if cx0 < 0 or cy0 < 0:
            continue
        fine = {(2 * (cx0 + X) + i, 2 * (cy0 + Y) + j) for X, Y in S for i in (0, 1) for j in (0, 1)}
        if all(0 <= x + dx < cols and 0 <= y + dy < rows and active[(y + dy) * cols + x + dx]
               for x, y in fine for dx in range(-2, 3) for dy in range(-2, 3)):
            placed = (sc, S, cx0, cy0)
            break
    if not placed:
        raise ValueError("No room for the letter at this size - use a larger page, a smaller --cell, "
                         "--shape rectangle, or a smaller --letter-scale.")
    sc, S, cx0, cy0 = placed
    cyc = [(2 * cx0 + a) + (2 * cy0 + b) * cols for a, b in glyph_cycle(S, rng)]
    glyph = set(cyc)

    def around(i):
        y, x = divmod(i, cols)
        return [yy * cols + xx for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                if 0 <= xx < cols and 0 <= yy < rows and active[yy * cols + xx]]

    dist, prev, dq = {entrance: 0}, {entrance: None}, deque([entrance])
    while dq:                                              # shortest corridors from the entrance, outside the glyph
        i = dq.popleft()
        for j in around(i):
            if j not in glyph and j not in dist:
                dist[j], prev[j] = dist[i] + 1, i
                dq.append(j)
    best, bd = [], None
    for u in glyph:                                        # the glyph cell closest to the entrance
        for w in around(u):
            if w in dist and (bd is None or dist[w] < bd):
                best, bd = [(u, w)], dist[w]
            elif w in dist and dist[w] == bd:
                best.append((u, w))
    if not best:
        raise ValueError("The entrance cannot reach the letter - try another --start-side.")
    u, w = rng.choice(sorted(best))
    pos = {c: k for k, c in enumerate(cyc)}[u]
    n = len(cyc)
    step = rng.choice((1, -1))
    loop = [cyc[(pos + step * t) % n] for t in range(n)]  # starts at u, ends on u's neighbour in the loop
    lead = [w]
    while prev[lead[-1]] is not None:
        lead.append(prev[lead[-1]])
    lead.reverse()
    return lead + loop, sc


def generate_letter(cols, rows, path, rng, args, active, attempts=40):
    cells = sum(active)
    line_len = args.line_length or auto_line_length(cells, args.max_children)
    for _ in range(attempts):
        maze = LineMaze(cols, rows, rng, args.max_children, line_len, args.straightness, active)
        try:
            maze.build_path(path, max(6, line_len))
        except GenerationFailed:
            continue
        adj = maze.adjacency()
        depth, parent = bfs(adj, path[0])
        edges = sum(len(a) for a in adj) // 2
        assert edges == maze.n_active - 1 and all(depth[i] >= 0 for i in range(maze.n) if maze.active[i]), \
            "not a spanning tree - bug"
        assert max(maze.children) <= args.max_children, "child limit violated - bug"
        assert depth[path[-1]] == len(path) - 1, "the solution is not the planned letter - bug"
        return maze, adj, depth, parent
    raise SystemExit("Could not grow the maze around the letter - try a larger --max-children or a smaller --cell.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate a treasure-hunt maze (SVG) with bounded branching.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("size", nargs="?", default="A4",
                    help="A0-A6, LETTER, LEGAL, or WxH with unit, e.g. 30x20cm")
    orient = ap.add_mutually_exclusive_group()
    orient.add_argument("-l", "--landscape", action="store_true", help="force landscape")
    orient.add_argument("-p", "--portrait", action="store_true", help="force portrait")
    ap.add_argument("-o", "--output", default="treasure_maze.svg", help="output file")
    ap.add_argument("--cell", type=float, default=6.0, help="cell size in mm")
    ap.add_argument("--stroke", type=float, default=None, help="wall width in mm (default: 12%% of cell)")
    ap.add_argument("--margin", type=float, default=12.0, help="page margin in mm")
    ap.add_argument("--shape", choices=("rectangle", "ellipse", "circle"), default="rectangle",
                    help="outline of the maze: the full rectangle, the ellipse inscribed in it, "
                         "or the largest circle (use a smaller --cell for a smoother edge)")
    ap.add_argument("--max-children", type=int, default=5,
                    help="max child lines (side branches) any single line may have")
    ap.add_argument("--line-length", type=int, default=None,
                    help="typical line length in cells (default: auto, from maze size and cap)")
    ap.add_argument("--straightness", type=float, default=0.6,
                    help="0 = very twisty lines ... 1 = very straight lines")
    ap.add_argument("--start-side", choices=SIDES + ("random",), default="left",
                    help="side of the maze where the entrance is")
    ap.add_argument("--treasure", choices=("deadend", "far", "any"), default="deadend",
                    help="deadend: random dead end; far: the farthest cell; any: any cell")
    ap.add_argument("--min-distance", type=float, default=0.5,
                    help="treasure is at least this fraction of the longest route away (0-1)")
    ap.add_argument("--start-arrow", action=argparse.BooleanOptionalAction, default=False,
                    help="draw a green arrow pointing at the entrance (outside the maze)")
    ap.add_argument("--letter", "--symbol", dest="letter", metavar="CHAR|SUIT", default=None,
                    help="make the solution trace a letter A-Z, a digit 0-9 or a card suit "
                         "(spade, heart, diamond, club) - writes the solution file too; "
                         "the chest sits at the end of the shape")
    ap.add_argument("--symbol-style", choices=("solid", "outline"), default="solid",
                    help="card suits only: 'solid' fills the whole suit with one continuous meander, "
                         "'outline' traces only its contour")
    ap.add_argument("--letter-scale", type=int, default=None, metavar="N",
                    help="size of the letter/suit (its height is 6N+1 coarse cells; default: the largest that fits)")
    ap.add_argument("--solution-width", type=float, default=None, metavar="FRAC",
                    help="width of the red route as a fraction of a cell (default 0.25, or 0.5 with --letter)")
    ap.add_argument("--solution", action="store_true",
                    help="also write <output>_solution.svg with the route in red")
    ap.add_argument("--color", default="#222222", help="wall colour")
    ap.add_argument("--background", default="none", help="background colour or 'none'")
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
    if args.max_children < 2:
        ap.error("--max-children must be at least 2 (1 would force a single snake).")
    if args.line_length is not None and args.line_length < 2:
        ap.error("--line-length must be at least 2")
    if not 0 <= args.straightness <= 1 or not 0 <= args.min_distance <= 1:
        ap.error("--straightness and --min-distance must be between 0 and 1")
    if args.cell <= 0:
        ap.error("--cell must be positive")
    if args.letter is not None:
        raw = args.letter.strip()
        args.letter = SYMBOL_ALIASES.get(raw.lower(), raw.upper())
        if args.letter not in FONT and args.letter not in SYMBOL_ALIASES.values():
            ap.error("--letter takes a single character A-Z / 0-9, or a card suit: spade, heart, diamond, club")
        args.solution = True
        if args.letter_scale is not None and args.letter_scale < 1:
            ap.error("--letter-scale must be at least 1")

    c = args.cell
    cols = int((width - 2 * args.margin) // c)
    rows = int((height - 2 * args.margin) // c)
    if cols < 2 or rows < 2:
        ap.error("Page too small for this cell size/margin - reduce --cell or --margin.")
    if args.shape == "circle":
        cols = rows = min(cols, rows)
    active = make_mask(cols, rows, args.shape)
    if sum(active) < 12:
        ap.error("Maze too small for this cell size/margin/shape - reduce --cell or --margin.")
    ox = (width - cols * c) / 2
    oy = (height - rows * c) / 2
    stroke = args.stroke if args.stroke is not None else max(0.3, c * 0.12)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 32)
    rng = random.Random(seed)

    side = rng.choice(SIDES) if args.start_side == "random" else args.start_side
    sx, sy = pick_entrance(side, cols, rows, active, rng)
    entrance = (sx, sy, side)
    start = sy * cols + sx
    inward = {"left": 1, "right": -1, "top": cols, "bottom": -cols}[side]

    if args.letter:
        try:
            path, letter_scale = plan_letter(args.letter, args.letter_scale, cols, rows, active, start, rng,
                                             args.symbol_style)
        except ValueError as e:
            ap.error(str(e))
        maze, adj, depth, parent = generate_letter(cols, rows, path, rng, args, active)
        treasure = path[-1]
    else:
        maze, adj, depth, parent = generate(cols, rows, start, inward, rng, args, active=active)
        treasure = pick_treasure(args.treasure, adj, depth, start, args.min_distance, rng)
    ty, tx = divmod(treasure, cols)

    # ---- drawing --------------------------------------------------------- #
    walls = walls_path(maze, ox, oy, c, entrance)
    color = html.escape(args.color, quote=True)
    arrow_len = min(args.margin * 0.8, c * 1.2)
    border = border_point(entrance, ox, oy, c)
    arrow = f'  {arrow_svg(*border, side, arrow_len, c * 0.3, "#2e9e4f")}\n' if args.start_arrow else ""
    bg = ""
    if args.background.lower() != "none":
        bg = (f'  <rect width="100%" height="100%" '
              f'fill="{html.escape(args.background, quote=True)}"/>\n')

    def document(extra: str = "", dim: bool = False) -> str:
        wo = ' stroke-opacity="0.3"' if dim else ""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}mm" height="{fmt(height)}mm" '
            f'viewBox="0 0 {fmt(width)} {fmt(height)}">\n'
            f'  <title>Treasure maze, seed {seed}</title>\n'
            f'  <!-- {args.shape}, {cols}x{rows} grid, {maze.n_active} cells, max {args.max_children} children per line, seed {seed} -->\n'
            f'{bg}'
            f'  <path id="walls" d="{walls}" fill="none" stroke="{color}" '
            f'stroke-width="{fmt(stroke)}" stroke-linecap="round" stroke-linejoin="round"{wo}/>\n'
            f'{extra}'
            f'{arrow}'
            f'  {chest_svg(ox + (tx + 0.5) * c, oy + (ty + 0.5) * c, c * 0.72)}\n'
            '</svg>\n'
        )

    out = Path(args.output)
    out.write_text(document(), encoding="utf-8")

    if args.solution:
        sol = solution_path(maze, parent, treasure, ox, oy, c, entrance)
        extra = (f'  <path id="solution" d="{sol}" fill="none" stroke="#d62828" '
                 f'stroke-width="{fmt(c * (args.solution_width if args.solution_width is not None else (0.5 if args.letter else 0.25)))}" stroke-linecap="round" '
                 f'stroke-linejoin="round" opacity="0.85"/>\n')
        sol_file = out.with_name(out.stem + "_solution" + (out.suffix or ".svg"))
        sol_file.write_text(document(extra, dim=bool(args.letter)), encoding="utf-8")

    dead_ends = sum(1 for a in adj if len(a) == 1) - (1 if len(adj[start]) == 1 else 0)
    print(
        f"{out}: {fmt(width)} x {fmt(height)} mm, {args.shape} maze of {maze.n_active} cells "
        f"({cols}x{rows} grid), entrance on the {side}, "
        f"{len(maze.cells)} lines (nesting depth {maze.line_depth()}, "
        f"max {max(maze.children)} children/line), {dead_ends} dead ends, "
        f"route to treasure {depth[treasure]} steps"
        + (f" (traces '{args.letter}', letter scale {letter_scale})" if args.letter else "") + f", seed {seed}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
