#!/usr/bin/env python3
"""
treasure_maze.py - generate a treasure-hunt maze as an SVG.

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
    def __init__(self, cols, rows, rng, max_children, line_len, straightness):
        self.cols, self.rows, self.rng = cols, rows, rng
        self.cap, self.line_len, self.straight = max_children, line_len, straightness
        self.n = cols * rows
        self.line_of = [-1] * self.n            # which line owns each cell
        self.right = [bytearray(cols) for _ in range(rows)]   # passage (x,y)-(x+1,y)
        self.down = [bytearray(cols) for _ in range(rows)]    # passage (x,y)-(x,y+1)
        self.cells: list[list[int]] = []        # cells of each line, in walking order
        self.children: list[int] = []           # child lines sprouted so far
        self.parent: list[int] = []             # parent line (-1 for the root)
        self.want: list[int] = []               # children this line would like
        self.unvisited = self.n
        self.nbr = []
        for i in range(self.n):
            y, x = divmod(i, cols)
            nb = []
            if x > 0: nb.append(i - 1)
            if x < cols - 1: nb.append(i + 1)
            if y > 0: nb.append(i - cols)
            if y < rows - 1: nb.append(i + cols)
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
                if self.line_of[base + xx] < 0:
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
            opts = [j for j in self.nbr[cur] if self.line_of[j] < 0]
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
                free = [w for w in self.nbr[u] if self.line_of[w] < 0]
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
                    if self.line_of[w] < 0:
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


def auto_line_length(cols, rows, cap) -> int:
    """Typical line length. A smaller child cap needs shorter lines (more lines,
    hence more branch points) or pockets of the grid can't be reached."""
    base = min((cols * rows) ** 0.5 / 2, 20)     # long lines can't fill big pages
    return max(4, int(base * min(1.0, (cap - 1) / 4)))


def generate(cols, rows, start, inward, rng, args, attempts=40):
    line_len = args.line_length or auto_line_length(cols, rows, args.max_children)
    for _ in range(attempts):
        maze = LineMaze(cols, rows, rng, args.max_children, line_len, args.straightness)
        try:
            maze.build(start, inward)
        except GenerationFailed:
            continue
        adj = maze.adjacency()
        depth, parent = bfs(adj, start)
        edges = sum(len(a) for a in adj) // 2
        assert edges == maze.n - 1 and min(depth) >= 0, "not a spanning tree - bug"
        assert max(maze.children) <= args.max_children, "child limit violated - bug"
        return maze, adj, depth, parent
    raise SystemExit(
        f"Could not fill the page with max {args.max_children} children per line and lines "
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
def walls_path(maze, ox, oy, c, side, eidx) -> str:
    cols, rows = maze.cols, maze.rows

    def hwall(r, x):                               # wall on horizontal line r above cell (x, r)
        if r == 0:
            return not (side == "top" and x == eidx)
        if r == rows:
            return not (side == "bottom" and x == eidx)
        return not maze.down[r - 1][x]

    def vwall(q, y):                               # wall on vertical line q left of cell (q, y)
        if q == 0:
            return not (side == "left" and y == eidx)
        if q == cols:
            return not (side == "right" and y == eidx)
        return not maze.right[y][q - 1]

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


def solution_path(maze, parent, treasure, start, ox, oy, c, side, eidx) -> str:
    chain = []
    i = treasure
    while i != -1:
        chain.append(i)
        i = parent[i]
    chain.reverse()                                # start ... treasure
    pts = [(ox + (i % maze.cols + 0.5) * c, oy + (i // maze.cols + 0.5) * c) for i in chain]
    sx, sy = pts[0]
    if side == "left":
        pts.insert(0, (ox, sy))
    elif side == "right":
        pts.insert(0, (ox + maze.cols * c, sy))
    elif side == "top":
        pts.insert(0, (sx, oy))
    else:
        pts.insert(0, (sx, oy + maze.rows * c))
    d = [f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d.append(f"H{fmt(x1)}" if abs(y1 - y0) < 1e-9 else f"V{fmt(y1)}")
    return "".join(d)


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

    c = args.cell
    cols = int((width - 2 * args.margin) // c)
    rows = int((height - 2 * args.margin) // c)
    if cols < 2 or rows < 2:
        ap.error("Page too small for this cell size/margin - reduce --cell or --margin.")
    ox = (width - cols * c) / 2
    oy = (height - rows * c) / 2
    stroke = args.stroke if args.stroke is not None else max(0.3, c * 0.12)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 32)
    rng = random.Random(seed)

    side = rng.choice(SIDES) if args.start_side == "random" else args.start_side
    if side in ("left", "right"):
        eidx = rng.randrange(rows)
        sx, sy = (0 if side == "left" else cols - 1), eidx
    else:
        eidx = rng.randrange(cols)
        sx, sy = eidx, (0 if side == "top" else rows - 1)
    start = sy * cols + sx
    inward = {"left": 1, "right": -1, "top": cols, "bottom": -cols}[side]

    maze, adj, depth, parent = generate(cols, rows, start, inward, rng, args)
    treasure = pick_treasure(args.treasure, adj, depth, start, args.min_distance, rng)
    ty, tx = divmod(treasure, cols)

    # ---- drawing --------------------------------------------------------- #
    walls = walls_path(maze, ox, oy, c, side, eidx)
    color = html.escape(args.color, quote=True)
    arrow_len = min(args.margin * 0.8, c * 1.2)
    border = {
        "left": (ox, oy + (sy + 0.5) * c), "right": (ox + cols * c, oy + (sy + 0.5) * c),
        "top": (ox + (sx + 0.5) * c, oy), "bottom": (ox + (sx + 0.5) * c, oy + rows * c),
    }[side]
    arrow = f'  {arrow_svg(*border, side, arrow_len, c * 0.3, "#2e9e4f")}\n' if args.start_arrow else ""
    bg = ""
    if args.background.lower() != "none":
        bg = (f'  <rect width="100%" height="100%" '
              f'fill="{html.escape(args.background, quote=True)}"/>\n')

    def document(extra: str = "") -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}mm" height="{fmt(height)}mm" '
            f'viewBox="0 0 {fmt(width)} {fmt(height)}">\n'
            f'  <title>Treasure maze, seed {seed}</title>\n'
            f'  <!-- {cols}x{rows} cells, max {args.max_children} children per line, seed {seed} -->\n'
            f'{bg}'
            f'  <path id="walls" d="{walls}" fill="none" stroke="{color}" '
            f'stroke-width="{fmt(stroke)}" stroke-linecap="round" stroke-linejoin="round"/>\n'
            f'{extra}'
            f'{arrow}'
            f'  {chest_svg(ox + (tx + 0.5) * c, oy + (ty + 0.5) * c, c * 0.72)}\n'
            '</svg>\n'
        )

    out = Path(args.output)
    out.write_text(document(), encoding="utf-8")

    if args.solution:
        sol = solution_path(maze, parent, treasure, start, ox, oy, c, side, eidx)
        extra = (f'  <path id="solution" d="{sol}" fill="none" stroke="#d62828" '
                 f'stroke-width="{fmt(c * 0.25)}" stroke-linecap="round" '
                 f'stroke-linejoin="round" opacity="0.85"/>\n')
        sol_file = out.with_name(out.stem + "_solution" + (out.suffix or ".svg"))
        sol_file.write_text(document(extra), encoding="utf-8")

    dead_ends = sum(1 for a in adj if len(a) == 1) - (1 if len(adj[start]) == 1 else 0)
    print(
        f"{out}: {fmt(width)} x {fmt(height)} mm, {cols}x{rows} cells, entrance on the {side}, "
        f"{len(maze.cells)} lines (nesting depth {maze.line_depth()}, "
        f"max {max(maze.children)} children/line), {dead_ends} dead ends, "
        f"route to treasure {depth[treasure]} steps, seed {seed}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
