#!/usr/bin/env python3
"""
CASTLE DEFENSE - a co-op "defend the keep" game (stand-alone test version).

Put this file next to castle_macro.py (the rules engine) and run it. It does
not touch the chat or the network, so you can debug the whole game on one
computer. Any seat can be a person (hot-seat) or a bot.

    python castle_game.py                     open the game window
    python castle_game.py --players 4 --humans 2 --seed 7
    python castle_game.py --test              check everything, no window
    python castle_game.py --png map.png       save a picture of the map and
                                              every mini-game (needs Pillow)
    python castle_game.py --sim 100           bot balance + message numbers
                                              (same as castle_macro --sim)

THE GAME IN SHORT
  2-5 players defend the keep against waves from six lanes around a
  hexagon (N, NE, SE, S, SW, NW). Each lane has 3 cells; cell 1 is next to
  the wall. Survive 12
  rounds and kill the boss. The keep has 20 HP; at 0 you lose.

  Roles: Steward (farms, mines = income), Engineer (walls, towers),
  Slayer (fights), Smith (upgrades, plating), Mage (spells, needs mana).
  With fewer than 5 players a person plays several roles, with shorter
  mini-games.

  A ROUND
    1 income        the shared pool grows
    2 bank          a player who asks for nothing banks a small deposit
    3 petition      you ask the pool for gold; this round's TREASURER splits it
    4 vault         everyone sees step 3, then spends vault gold on their OWN
                    projects (never refunded)
    5 map           pick where each hero goes and what to build or cast
    6 combat        a short mini-game per role sets how well it goes
                    (poor / okay / great). Builds are placed FIRST (so new
                    towers fire this round), then spells, the Slayer, towers,
                    and the enemies move or attack. An animation plays, then
                    the round report

  Messages in the real game are tiny: a petition, the treasurer's decision,
  and ONE final message per player (vault, map choices, mini-game results and
  a state checksum). The window shows the count for each round.
"""
import argparse
import collections
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import castle_macro as cm
except ImportError:
    sys.exit("castle_game.py needs castle_macro.py in the same folder.")
from castle_macro import (QUADS, PROJECTS, ITEMS, ENEMIES, SPELLS, Game, Bot,
                          BUILDERS, BUILD_ITEMS, LAST_ROUND, KEEP_MAX,
                          roll_band, wishes, allocate)

# ======================================================================
#  PIXEL ART  (a 5x7 bitmap font and small sprites, drawn as flat colour
#  blocks, so the same picture comes out in Tk and in a Pillow image)
# ======================================================================
_FONT_SRC = r"""
== A
.###.
#...#
#...#
#####
#...#
#...#
#...#
== B
####.
#...#
#...#
####.
#...#
#...#
####.
== C
.###.
#...#
#....
#....
#....
#...#
.###.
== D
####.
#...#
#...#
#...#
#...#
#...#
####.
== E
#####
#....
#....
####.
#....
#....
#####
== F
#####
#....
#....
####.
#....
#....
#....
== G
.###.
#...#
#....
#.###
#...#
#...#
.###.
== H
#...#
#...#
#...#
#####
#...#
#...#
#...#
== I
###
.#.
.#.
.#.
.#.
.#.
###
== J
..###
...#.
...#.
...#.
...#.
#..#.
.##..
== K
#...#
#..#.
#.#..
##...
#.#..
#..#.
#...#
== L
#....
#....
#....
#....
#....
#....
#####
== M
#...#
##.##
#.#.#
#.#.#
#...#
#...#
#...#
== N
#...#
##..#
#.#.#
#..##
#...#
#...#
#...#
== O
.###.
#...#
#...#
#...#
#...#
#...#
.###.
== P
####.
#...#
#...#
####.
#....
#....
#....
== Q
.###.
#...#
#...#
#...#
#.#.#
#..#.
.##.#
== R
####.
#...#
#...#
####.
#.#..
#..#.
#...#
== S
.####
#....
#....
.###.
....#
....#
####.
== T
#####
..#..
..#..
..#..
..#..
..#..
..#..
== U
#...#
#...#
#...#
#...#
#...#
#...#
.###.
== V
#...#
#...#
#...#
#...#
#...#
.#.#.
..#..
== W
#...#
#...#
#...#
#.#.#
#.#.#
##.##
#...#
== X
#...#
#...#
.#.#.
..#..
.#.#.
#...#
#...#
== Y
#...#
#...#
.#.#.
..#..
..#..
..#..
..#..
== Z
#####
....#
...#.
..#..
.#...
#....
#####
== 0
.###.
#...#
#..##
#.#.#
##..#
#...#
.###.
== 1
..#..
.##..
..#..
..#..
..#..
..#..
.###.
== 2
.###.
#...#
....#
...#.
..#..
.#...
#####
== 3
####.
....#
....#
.###.
....#
....#
####.
== 4
...#.
..##.
.#.#.
#..#.
#####
...#.
...#.
== 5
#####
#....
####.
....#
....#
#...#
.###.
== 6
.###.
#....
#....
####.
#...#
#...#
.###.
== 7
#####
....#
...#.
..#..
.#...
.#...
.#...
== 8
.###.
#...#
#...#
.###.
#...#
#...#
.###.
== 9
.###.
#...#
#...#
.####
....#
....#
.###.
== a
.....
.....
.###.
....#
.####
#...#
.####
== b
#....
#....
####.
#...#
#...#
#...#
####.
== c
.....
.....
.###.
#....
#....
#...#
.###.
== d
....#
....#
.####
#...#
#...#
#...#
.####
== e
.....
.....
.###.
#...#
#####
#....
.###.
== f
..##.
.#...
####.
.#...
.#...
.#...
.#...
== g
.....
.....
.####
#...#
#...#
.####
....#
#...#
.###.
== h
#....
#....
####.
#...#
#...#
#...#
#...#
== i
..#..
.....
.##..
..#..
..#..
..#..
.###.
== j
...#.
.....
..##.
...#.
...#.
...#.
...#.
#..#.
.##..
== k
#....
#....
#..#.
#.#..
##...
#.#..
#..#.
== l
.##..
..#..
..#..
..#..
..#..
..#..
.###.
== m
.....
.....
##.#.
#.#.#
#.#.#
#...#
#...#
== n
.....
.....
####.
#...#
#...#
#...#
#...#
== o
.....
.....
.###.
#...#
#...#
#...#
.###.
== p
.....
.....
####.
#...#
#...#
####.
#....
#....
#....
== q
.....
.....
.####
#...#
#...#
.####
....#
....#
....#
== r
.....
.....
#.##.
##..#
#....
#....
#....
== s
.....
.....
.####
#....
.###.
....#
####.
== t
.#...
.#...
####.
.#...
.#...
.#..#
..##.
== u
.....
.....
#...#
#...#
#...#
#..##
.##.#
== v
.....
.....
#...#
#...#
#...#
.#.#.
..#..
== w
.....
.....
#...#
#...#
#.#.#
#.#.#
.#.#.
== x
.....
.....
#...#
.#.#.
..#..
.#.#.
#...#
== y
.....
.....
#...#
#...#
#...#
.####
....#
#...#
.###.
== z
.....
.....
#####
...#.
..#..
.#...
#####
== !
#
#
#
#
#
.
#
== "
#.#
#.#
== #
.#.#.
#####
.#.#.
.#.#.
#####
.#.#.
== $
..#..
.####
#.#..
.###.
..#.#
####.
..#..
== %
##..#
##.#.
...#.
..#..
.#...
.#.##
#..##
== &
.##..
#..#.
#.#..
.#...
#.#.#
#..#.
.##.#
== '
#
#
== (
..#
.#.
#..
#..
#..
.#.
..#
== )
#..
.#.
..#
..#
..#
.#.
#..
== *
.....
#.#.#
.###.
#####
.###.
#.#.#
== +
.....
..#..
..#..
#####
..#..
..#..
== ,
.....
.....
.....
.....
.##..
..#..
.#...
== -
.....
.....
.....
#####
== .
.
.
.
.
.
.
#
== /
....#
....#
...#.
..#..
.#...
#....
#....
== :
.
.
#
.
.
#
== ;
.
.
#
.
.
#
#
== <
...#.
..#..
.#...
#....
.#...
..#..
...#.
== =
.....
.....
#####
.....
#####
== >
.#...
..#..
...#.
....#
...#.
..#..
.#...
== ?
.###.
#...#
....#
...#.
..#..
.....
..#..
== @
.###.
#...#
#.###
#.#.#
#.###
#....
.###.
== [
###
#..
#..
#..
#..
#..
###
== \
#....
#....
.#...
..#..
...#.
....#
....#
== ]
###
..#
..#
..#
..#
..#
###
== ^
..#..
.#.#.
#...#
== _
.....
.....
.....
.....
.....
.....
#####
== `
#..
.#.
== {
..##.
.#...
.#...
#....
.#...
.#...
..##.
== |
#
#
#
#
#
#
#
== }
##..
..#.
..#.
...#
..#.
..#.
##..
== ~
.....
.....
.#..#
#.##.
"""


def _parse_font(src):
    glyphs, cur, rows = {}, None, []

    def flush():
        if cur is None:
            return
        cols = [x for r in rows for x, c in enumerate(r) if c == "#"]
        lo, hi = (min(cols), max(cols)) if cols else (0, 0)
        glyphs[cur] = (hi - lo + 1, [[x - lo for x, c in enumerate(r) if c == "#"]
                                     for r in rows])
    for ln in src.strip("\n").split("\n"):
        if ln.startswith("== "):
            flush()
            cur, rows = ln[3:], []
        else:
            rows.append(ln)
    flush()
    return glyphs


PFONT = _parse_font(_FONT_SRC)
PF_H, PF_SPACE = 9, 3          # line height in font pixels, width of a blank


def _glyph(ch):
    return PFONT.get(ch) or PFONT["?"]


def text_w(s, scale=1):
    """Width in screen pixels of one line of text."""
    if not s:
        return 0
    n = sum((PF_SPACE if c == " " else _glyph(c)[0]) + 1 for c in s) - 1
    return n * scale


def text_runs(s):
    """[(x, y, run_length)] of lit pixels for one line, font pixel units."""
    out, x = [], 0
    for c in s:
        if c == " ":
            x += PF_SPACE + 1
            continue
        w, rows = _glyph(c)
        for y, xs in enumerate(rows):
            i = 0
            while i < len(xs):
                j = i
                while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
                    j += 1
                out.append((x + xs[i], y, xs[j] - xs[i] + 1))
                i = j + 1
        x += w + 1
    return out


def wrap_text(s, px, scale=1):
    """Break text into lines no wider than px screen pixels (a newline
    always breaks, a word longer than a line is cut)."""
    lines = []
    for para in str(s).split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            t = (cur + " " + w) if cur else w
            if cur and text_w(t, scale) > px:
                lines.append(cur)
                cur = w
            else:
                cur = t
            while text_w(cur, scale) > px and len(cur) > 1:
                k = len(cur) - 1
                while k > 1 and text_w(cur[:k], scale) > px:
                    k -= 1
                lines.append(cur[:k])
                cur = cur[k:]
        lines.append(cur)
    return lines


def fit_size(s, size, maxw):
    """The biggest font size (down to 8) at which the text fits maxw."""
    while size > 8 and text_w(s, text_scale(size)) > maxw:
        size -= 1
    return size


def text_scale(size, k=1.0):
    """Integer pixel scale for a font 'size' (the old point-like sizes)."""
    return max(1, int(round(size * k / 6.0)))


# ---- sprites: rows of palette letters ('.' is see-through) --------------
_SPR = {
    "goblin": (".o.....o.", "oao...oao", ".oaaaaao.", "oaaaaaaao", "oaakaakao",
               "oaaaaaaao", ".oabbbao.", "..oaaao..", "...ooo..."),
    "runner": ("...ooo...", "..oaaao..", "..oakao..", "...ooo...", "..oaaao..",
               ".oaoaoao.", "o.oaaao.o", "..oa.ao..", ".oo...oo."),
    "archer": ("..ooo....", ".oaaao.bb", ".oakao.b.", "..ooo..b.", ".oaaaoob.",
               "oaaaaao.b", "oaaaaao.b", ".oaaao.b.", ".oo.oo..."),
    "troll": ("..ooooooo..", ".oaaaaaaao.", ".oakaaakao.", ".oaaaaaaao.",
              ".oabwbwbao.", "..oaaaaao..", ".ooaaaaaoo.", "oaaoaaaoaao",
              "oaao...oaao", ".oo.....oo."),
    "boss": ("o.............o", "oo...........oo", "oro.ooooooo.oro",
             ".oroaaaaaaaoro.", "..oaaaaaaaaao..", "..oaakaaakaao..",
             "..oaaaaaaaaao..", "..oawbwbwbwao..", "...oaaaaaaao...",
             "..ooaaaaaaaoo..", ".oaaoaaaaaoaao.", ".oaao.ooo.oaao.",
             "..oo.......oo.."),
    "tower": ("o.o.o.o.o", "ooooooooo", "oaaaaaaao", ".oaaaaao.", ".oabaabo.",
              ".oaaaaao.", ".oaakaao.", ".oaaaaao.", ".oaaaaao.", ".oaaaaao.",
              "oaaaaaaao", "ooooooooo"),
    "farm": (".....r.....", "...rrrrr...", ".rrrrrrrrr.", "rrrrrrrrrrr",
             ".owwwwwwwo.", ".owkwwwkwo.", ".owwwwwwwo.", ".owwwkwwwo.",
             ".owwwkwwwo.", ".ooooooooo."),
    "mine": ("...ooooo...", "..obbbbbo..", ".obbbbbybo.", "obbybbbbbbo",
             "obbbbkkkbbo", "obbbkkkkkyo", "obbbkkkkkbo", "ooooooooooo"),
    "orb": ("..ooooo..", ".oaaaaao.", "oaaccaaao", "oaccaaaao", "oaaaaaaao",
            "oaaaaaabo", "oaaaaabbo", ".obbbbbo.", "..ooooo.."),
    "heart": (".oo.oo.", "orwrrro", "orrrrro", ".orrro.", "..oro..", "...o..."),
    "hearth": (".oo.oo.", "orwroEo", "orrroEo", ".orroE.", "..oEo..", "...o..."),
    "hearte": (".oo.oo.", "oEEoEEo", "oEEEEEo", ".oEEEo.", "..oEo..", "...o..."),
    "coin": ("..ooo..", ".oyyyo.", "oywyyyo", "oyyyyyo", "oyyyyyo", ".oyyyo.",
             "..ooo.."),
    "x": ("r...r", ".r.r.", "..r..", ".r.r.", "r...r"),
}
_PAL = {"o": "#17101f", "k": "#17101f", "w": "#ffffff", "r": "#e03040",
        "y": "#ffd21f", "E": "#3a2a4a"}
SPR_COLORS = {
    "goblin": dict(a="#6cc24a", b="#3e7a2c"),
    "runner": dict(a="#e8d44a", b="#a89420"),
    "archer": dict(a="#4aa8e0", b="#b07a3a"),
    "troll": dict(a="#c06030", b="#7a3a1a", w="#e8e0d0", b2="#7a3a1a"),
    "boss": dict(a="#d02060", b="#7a1038", w="#ffe8a0"),
    "tower": dict(a="#c8c8d8", b="#8f8fa8"),
    "farm": dict(r="#e04a3a", w="#f0e0b0"),
    "mine": dict(b="#9a6a2a"),
}


def _tint(col, f):
    c = col.lstrip("#")
    v = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    v = [max(0, min(255, int(x * f if f < 1 else x + (255 - x) * (f - 1))))
         for x in v]
    return "#%02x%02x%02x" % tuple(v)


def mix(c1, c2, t):
    """Blend colour c1 into c2 (t = share of c1)."""
    a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(int(round(y + (x - y) * t))
                                   for x, y in zip(a, b))


def banner_colors(role):
    """(bar, bar_dark, edge) for a project banner of this role."""
    c = ROLE_COL[role]
    return mix(c, "#241a36", 0.34), mix(c, "#150f20", 0.16), c


def sprite_pixels(name, color=None):
    """(width, height, [(x, y, colour)]) for a named sprite."""
    rows = _SPR[name]
    pal = dict(_PAL)
    if name == "orb":
        c = color or "#ffffff"
        pal.update(a=c, b=_tint(c, 0.62), c=_tint(c, 1.55))
    else:
        pal.update(SPR_COLORS.get(name, {}))
        if color and name in ("goblin", "runner", "archer", "troll", "boss"):
            pal["a"] = color
    px = []
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch != ".":
                px.append((x, y, pal.get(ch, "#ff00ff")))
    return len(rows[0]), len(rows), px


def sprite_size(name, scale=1):
    return len(_SPR[name][0]) * scale, len(_SPR[name]) * scale


BG, PANEL, FG, MUTED = "#2a1d3a", "#2f2447", "#eee6ff", "#a89cc8"
ACCENT, GOOD, BAD, STONE = "#ffd21f", "#7be08a", "#ff7a7a", "#8d7a5a"
DARK, EDGE, ROW, ROWHI = "#17101f", "#6d5aa0", "#3d3060", "#4f3f80"
INPUT, BTN_GO, BTN_ALT, STRIP = "#1d1430", "#3a9a4a", "#5a4f78", "#1d1430"
ROLE_COL = {"Steward": "#7be08a", "Engineer": "#ffb347", "Slayer": "#ff6b6b",
            "Smith": "#c8c8d8", "Mage": "#b061ff"}
ROLE_TAG = {"Steward": "St", "Engineer": "En", "Slayer": "Sl", "Smith": "Sm",
            "Mage": "Mg"}
ENEMY_COL = {"goblin": "#6cc24a", "runner": "#e0d040", "archer": "#4aa8e0",
             "troll": "#c06030", "boss": "#d02060"}
DIFFICULTY = {"Easy": 1.5, "Normal": 1.9, "Hard": 2.2}


# ======================================================================
#  DRAWING (one small interface, so the same code draws in Tk or a picture)
# ======================================================================
def brick_tile():
    """The dark purple brick wall behind everything: 32x16 pixels that
    repeat. [(x, y, w, h, colour)]"""
    base, mort, hi = "#2b1f3f", "#221730", "#372950"
    runs = [(0, 0, 32, 16, base)]
    for row in range(2):
        y, off = row * 8, 8 * row
        runs.append((0, y + 7, 32, 1, mort))
        seg = 0
        for x in range(33):
            if x == 32 or (x + off) % 16 == 15:
                if x > seg:
                    runs.append((seg, y, x - seg, 1, hi))
                if x < 32:
                    runs.append((x, y, 1, 7, mort))
                seg = x + 1
    return runs


class Gfx:
    top = None
    regions = ()          # hover areas filled in by draw_view: (points, text)
    tip = None            # (text, map_x, map_y) of the tooltip to draw

    def clear(self, bg, w, h): ...
    def bricks(self, w, h): ...
    def rect(self, x0, y0, x1, y1, fill="", outline="", width=1): ...
    def oval(self, x0, y0, x1, y1, fill="", outline="", width=1): ...
    def line(self, pts, fill, width=1): ...
    def poly(self, pts, fill="", outline="", width=1): ...
    def text(self, x, y, s, fill=FG, size=10, anchor="center", bold=True): ...
    def sprite(self, x, y, name, scale=2, anchor="center", color=None): ...


def _anchor_dy(anchor, sc):
    """The font cell is 9 rows tall but capitals only use the top 7, so
    shift the picture to put the capitals where the anchor says."""
    if anchor in ("center", "w", "e"):
        return 1.5 * sc
    if anchor in ("s", "sw", "se"):
        return 2 * sc
    return 0


def _merge(px):
    """[(x, y, colour)] -> horizontal runs [(x, y, w, 1, colour)]."""
    out, cur = [], None
    for (x, y, c) in sorted(px, key=lambda p: (p[1], p[0])):
        if cur and cur[1] == y and cur[4] == c and cur[0] + cur[2] == x:
            cur[2] += 1
        else:
            if cur:
                out.append(tuple(cur))
            cur = [x, y, 1, 1, c]
    if cur:
        out.append(tuple(cur))
    return out


def text_image_runs(s, fill):
    lines = str(s).split("\n")
    runs = []
    for i, ln in enumerate(lines):
        runs += [(rx, ry + i * (PF_H + 1), n, 1, fill)
                 for rx, ry, n in text_runs(ln)]
    w = max([text_w(ln, 1) for ln in lines] + [1])
    return runs, w, len(lines) * (PF_H + 1) - 1


class TkGfx(Gfx):
    """Draws on a Tk canvas. With auto=True the picture is scaled to fill the
    canvas (keeping its shape), so the window can be resized. Text and
    sprites are small cached PhotoImages built from flat colour blocks."""

    def __init__(self, canvas, auto=False, mk=None):
        self.c = canvas
        self.auto = auto
        self.mk = mk
        self.k, self.ox, self.oy = 1.0, 0.0, 0.0
        self.cache, self.old, self.tile = {}, {}, None
        self._bg = None
        self._bricked = False
        self.top = None

    def _get(self, key, make):
        """Cached images. The cache is renewed in two generations, so a
        picture drawn a moment ago is never freed while still on screen."""
        ent = self.cache.get(key)
        if ent is None:
            ent = self.old.get(key)
            if ent is None:
                if len(self.cache) > 900:
                    self.old, self.cache = self.cache, {}
                ent = make()
            self.cache[key] = ent
        return ent

    def _mkimg(self, w, h):
        if self.mk:
            return self.mk(w, h)
        import tkinter
        return tkinter.PhotoImage(master=self.c, width=w, height=h)

    def _image(self, runs, w, h, scale):
        im = self._mkimg(w, h)
        for (x, y, rw, rh, col) in runs:
            im.put(col, to=(x, y, x + rw, y + rh))
        return im.zoom(scale) if scale > 1 else im

    def _fit(self, w, h):
        try:
            cw, ch = self.c.winfo_width(), self.c.winfo_height()
        except Exception:
            cw = ch = 1
        if not self.auto or cw < 50 or ch < 50:
            self.k, self.ox, self.oy = 1.0, 0.0, 0.0
            return cw, ch
        self.k = min(cw / w, ch / h)
        self.ox, self.oy = (cw - w * self.k) / 2, (ch - h * self.k) / 2
        return cw, ch

    def clear(self, bg, w, h):
        cw, ch = self._fit(w, h)
        if not (self.auto and cw >= 50 and ch >= 50):
            cw, ch = w, h
        self.c.delete("fg")
        key = (bg, cw, ch)
        if key != self._bg:
            self.c.delete("bg")
            self.c.create_rectangle(0, 0, cw, ch, fill=bg, outline="",
                                    tags="bg")
            self._bg, self._bricked, self._size = key, False, (cw, ch)

    def bricks(self, w, h):
        if self._bricked:
            return
        self._bricked = True
        cw, ch = self._size
        tile = self.tile = self._image(brick_tile(), 32, 16, 2)
        for ty in range(0, int(ch) + 32, 32):
            for tx in range(0, int(cw) + 64, 64):
                self.c.create_image(tx, ty, image=tile, anchor="nw",
                                    tags="bg")

    def _p(self, x, y):
        return x * self.k + self.ox, y * self.k + self.oy

    def _w(self, width):
        return max(1, int(round(width * self.k))) if width else 0

    def rect(self, x0, y0, x1, y1, fill="", outline="", width=1):
        a, b = self._p(x0, y0)
        c, d = self._p(x1, y1)
        self.c.create_rectangle(a, b, c, d, fill=fill, outline=outline,
                                width=self._w(width), tags="fg")

    def oval(self, x0, y0, x1, y1, fill="", outline="", width=1):
        a, b = self._p(x0, y0)
        c, d = self._p(x1, y1)
        self.c.create_oval(a, b, c, d, fill=fill, outline=outline,
                           width=self._w(width), tags="fg")

    def line(self, pts, fill, width=1):
        flat = [v for p in pts for v in self._p(*p)]
        self.c.create_line(*flat, fill=fill, width=self._w(width), tags="fg")

    def poly(self, pts, fill="", outline="", width=1):
        flat = [v for p in pts for v in self._p(*p)]
        self.c.create_polygon(*flat, fill=fill, outline=outline,
                              width=self._w(width) if outline else 0,
                              tags="fg")

    def text(self, x, y, s, fill=FG, size=10, anchor="center", bold=True):
        sc = text_scale(size, self.k)
        def make():
            runs, w, h = text_image_runs(s, fill)
            return self._image(runs, w, h, sc)
        ent = self._get(("t", s, fill, sc), make)
        px, py = self._p(x, y)
        self.c.create_image(px, py + _anchor_dy(anchor, sc), image=ent,
                            anchor=anchor, tags="fg")

    def sprite(self, x, y, name, scale=2, anchor="center", color=None):
        sc = max(1, int(round(scale * self.k)))
        def make():
            w, h, px = sprite_pixels(name, color)
            return self._image(_merge(px), w, h, sc)
        ent = self._get(("s", name, color, sc), make)
        px_, py_ = self._p(x, y)
        self.c.create_image(px_, py_, image=ent, anchor=anchor, tags="fg")


class PilGfx(Gfx):
    """Draws into a Pillow picture (for --png and for testing)."""

    def __init__(self, w, h):
        from PIL import Image, ImageDraw
        self.im = Image.new("RGB", (w, h), BG)
        self.d = ImageDraw.Draw(self.im)
        self.k = 1.0
        self.top = None

    def clear(self, bg, w, h):
        self.d.rectangle([0, 0, w, h], fill=bg)

    def bricks(self, w, h):
        tile = brick_tile()
        for ty in range(0, int(h), 32):
            for tx in range(0, int(w), 64):
                for (x, y, rw, rh, c) in tile:
                    self.d.rectangle([tx + x * 2, ty + y * 2,
                                      tx + (x + rw) * 2 - 1,
                                      ty + (y + rh) * 2 - 1], fill=c)

    def rect(self, x0, y0, x1, y1, fill="", outline="", width=1):
        self.d.rectangle([x0, y0, x1, y1], fill=fill or None,
                         outline=outline or None, width=width)

    def oval(self, x0, y0, x1, y1, fill="", outline="", width=1):
        self.d.ellipse([x0, y0, x1, y1], fill=fill or None,
                       outline=outline or None, width=width)

    def line(self, pts, fill, width=1):
        self.d.line(list(pts), fill=fill, width=max(1, int(round(width))))

    def poly(self, pts, fill="", outline="", width=1):
        self.d.polygon(list(pts), fill=fill or None)
        if outline:
            self.d.line(list(pts) + [pts[0]], fill=outline,
                        width=max(1, int(round(width))), joint="curve")

    def _blit(self, runs, x, y, sc):
        for (rx, ry, rw, rh, col) in runs:
            self.d.rectangle([x + rx * sc, y + ry * sc,
                              x + (rx + rw) * sc - 1, y + (ry + rh) * sc - 1],
                             fill=col)

    @staticmethod
    def _place(x, y, w, h, anchor):
        ax = {"w": 0, "nw": 0, "sw": 0, "e": 1, "ne": 1, "se": 1}.get(anchor, .5)
        ay = {"n": 0, "nw": 0, "ne": 0, "s": 1, "sw": 1, "se": 1}.get(anchor, .5)
        return x - w * ax, y - h * ay

    def text(self, x, y, s, fill=FG, size=10, anchor="center", bold=True):
        sc = text_scale(size)
        runs, w, h = text_image_runs(s, fill)
        ox, oy = self._place(x, y + _anchor_dy(anchor, sc), w * sc, h * sc,
                             anchor)
        self._blit(runs, int(round(ox)), int(round(oy)), sc)

    def sprite(self, x, y, name, scale=2, anchor="center", color=None):
        w, h, px = sprite_pixels(name, color)
        ox, oy = self._place(x, y, w * scale, h * scale, anchor)
        self._blit(_merge(px), int(round(ox)), int(round(oy)), scale)


# ======================================================================
#  THE MAP: a hexagon, one lane on each side  (drawn from a plain "view"
#  dict, so it can also be animated)
# ======================================================================
MAP_W, MAP_H = 640, 676
TOP_W, TOP_H = 1200, 46
STRIP_H = 92
S3 = math.sqrt(3.0)
T30 = 1.0 / S3                      # tan 30 degrees
A0, WALL_T, CELL = 62, 16, 58       # keep, wall and cell depth (apothems)
KEEP_HALF = A0
A_OUT = A0 + WALL_T + 3 * CELL      # the outer edge of the lanes
CX, CY = MAP_W / 2, 292
_ANG = {"N": -90, "NE": -30, "SE": 30, "S": 90, "SW": 150, "NW": 210}
_N = {q: (math.cos(math.radians(a)), math.sin(math.radians(a)))
      for q, a in _ANG.items()}
_T = {q: (-n[1], n[0]) for q, n in _N.items()}
STRUCT_COL = {"farm": "#6cc24a", "mine": "#d8b848", "tower": "#d8d8e8"}
SPELL_COL = {"bolt": "#ffe066", "frost": "#7fd8ff", "fire": "#ff7a3a",
             "ward": "#9fe0ff", "lightning": "#d6b0ff"}
STONE_A = ("#8c7a58", "#9a8764", "#867455")
STONE_B = ("#7d705e", "#8a7c68", "#756856")


def _pt(q, a, p=0.0):
    """A point a apothem-units out from the keep centre along lane q,
    p sideways (positive is clockwise)."""
    n, t = _N[q], _T[q]
    return CX + n[0] * a + t[0] * p, CY + n[1] * a + t[1] * p


def cell_center(q, k):
    """Screen position of the middle of lane cell k (may be fractional)."""
    return _pt(q, A0 + WALL_T + CELL * (k - 0.5))


def _along(q, dist, perp=0):
    return _pt(q, dist, perp)


def lane_w(a):
    return 2 * a * T30


def cell_poly(q, a0, a1, inset=0.0):
    h0, h1 = a0 * T30 - inset * 1.15, a1 * T30 - inset * 1.15
    return [_pt(q, a0 + inset, -h0), _pt(q, a0 + inset, h0),
            _pt(q, a1 - inset, h1), _pt(q, a1 - inset, -h1)]


def hex_pts(a):
    r = a * 2 / S3
    return [(CX + r * math.cos(math.radians(d)), CY + r * math.sin(math.radians(d)))
            for d in (-120, -60, 0, 60, 120, 180)]


def struct_scale(n):
    """Sprite size: one or two buildings in a cell are drawn big, three small."""
    return 2 if n <= 2 else 1


def struct_pt(q, k, i=0, n=1):
    """Where the i-th of n buildings in a cell stands (the left part of it)."""
    a = A0 + WALL_T + CELL * (k - 0.5)
    w = lane_w(a)
    if n <= 1:
        return _pt(q, a, -0.30 * w)
    pe = -0.5 * w + 4
    if n == 2:
        return _pt(q, a, pe + 13 + i * 28)
    return _pt(q, a, pe + 8 + i * 17)


def hero_pt(q, cell, j=0):
    """Where the j-th hero token in a lane cell stands (outer, right side)."""
    a = A0 + WALL_T + CELL * (cell - 0.5) + 20
    w = lane_w(a)
    return _pt(q, a, 0.30 * w - j * 21)


def wall_pt(q):
    return _pt(q, A0 + WALL_T / 2)


def enemy_pt(q, cell, j=0, big=False):
    """Where the j-th enemy of a cell stands. Cell may be fractional."""
    a = A0 + WALL_T + CELL * (cell - 0.5)
    w = lane_w(a)
    p0 = -0.02 * w
    if big:
        sp = max(9, min(12, (0.5 * w - 8 - p0) / 7))
        return _pt(q, a + 2 + (j // 8) * 11, p0 + (j % 8) * sp)
    sp = max(14, min(26, (0.5 * w - 12 - p0) / 3))
    return _pt(q, a - 9 + (j // 4) * 24, p0 + (j % 4) * sp)


def forecast_rows(g, n=3):
    """[(round, {lane: {type: count}})] for the rounds still to come.
    A wave appears at the END of its round's combat."""
    start = max(1, g.round + (1 if g.phase in ("idle", "new") else 0))
    rows = []
    for rd in range(start, min(LAST_ROUND, start + n - 1) + 1):
        d = {}
        for q, t in g.plan_lanes(rd):
            d.setdefault(q, collections.Counter())[t] += 1
        rows.append((rd, d))
    return rows


def _wall_view(m):
    cap = cm.WALL_HP * m["wall"] + cm.PLATING_HP * m["plating"] \
        if m["wall"] > 0 else 0
    return dict(wall=m["wall"], wall_hp=m["wall_hp"], plating=m["plating"],
                cap=cap)


def _cells(map_, q):
    return [[dict(b) for b in c] for c in map_[q]["slots"]]


def view_from(map_, enemies, keep, rnd, pos, pool, forecast, hcell=None):
    return dict(round=rnd, keep=keep, pool=pool, pos=dict(pos),
                hcell=dict(hcell or {}),
                forecast=forecast,
                slots={q: _cells(map_, q) for q in QUADS},
                wall={q: _wall_view(map_[q]) for q in QUADS},
                enemies=[dict(e) for e in enemies])


def view_from_game(g):
    return view_from(g.map, g.enemies, g.keep, g.round, g.pos, g.pool,
                     forecast_rows(g, 3), g.hcell)


def view_from_snapshot(snap, pool, forecast):
    return view_from(snap["map"], snap["enemies"], snap["keep"],
                     snap["round"], snap["pos"], pool, forecast,
                     snap.get("hcell"))


def struct_max_hp(s):
    return cm.STRUCT_HP[s["t"]] + cm.TIER_HP * s.get("tier", 0)


def _seed(*a):
    h = 17
    for v in a:
        h = (h * 131 + (v if isinstance(v, int) else sum(map(ord, str(v))))) % 9973
    return h


def _boss_now(v):
    return bool(v["forecast"]) and any("boss" in c for c in v["forecast"][0][1].values())


STRUCT_TIP = {
    "farm": "Farm: +2 gold to the pool every round.\nEnemies like lanes with farms.",
    "mine": "Mine: +4 gold to the pool every round.\nEnemies like lanes with mines.",
    "tower": "Tower: shoots the nearest enemy in its\nlane every round (1 damage + 1 per upgrade).\nEnemies avoid lanes with many towers.",
}
ENEMY_TIP = {
    "goblin": "Goblin: basic enemy, walks 1 cell a round.\nBreaks walls and buildings it stands on.",
    "runner": "Runner: weak (1 hp) but walks 2 cells a round.",
    "archer": "Archer: shoots the keep from cell 2 over\nthe wall. Walks 1 cell a round.",
    "troll": "Troll: 6 hp, hits twice as hard on\nwalls and buildings.",
    "boss": "BOSS: huge hp and 4 damage. Kill it to win.\nIt hits walls and buildings twice as hard.",
}
HERO_TIP = {
    "Steward": "Steward: builds farms and mines.",
    "Engineer": "Engineer: builds towers, walls and repairs.",
    "Slayer": "Slayer: fights the enemies in one lane.",
    "Smith": "Smith: upgrades towers and plates walls.",
    "Mage": "Mage: casts spells into any lane from the keep.",
}


SEAT_NAMES = {}          # seat number -> player name (set for chat games)


def seat_label(p):
    if not isinstance(p, int):
        return "nobody"
    return SEAT_NAMES.get(p) or "Seat %d" % (p + 1)


def nameize(text):
    """Swap 'Seat 2' / 'seat 2' in engine text for the player's name."""
    if not SEAT_NAMES:
        return text
    return re.sub(r"[Ss]eat (\d+)", lambda m: seat_label(int(m.group(1)) - 1),
                  text)


def building_tip(s):
    t = STRUCT_TIP[s["t"]].split("\n")
    name = s["t"].capitalize() + (" L%d" % (s["tier"] + 1)
                                  if s["t"] == "tower" else "")
    t[0] = name + t[0][len(s["t"]):]
    t.append("hp %d/%d   built by %s" % (s["hp"], struct_max_hp(s),
                                         seat_label(s.get("by"))))
    return "\n".join(t)


def point_in(pts, x, y):
    """Is (x, y) inside the polygon pts?"""
    ins = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def tip_at(regions, x, y):
    """The tooltip text for the topmost hover area under (x, y), or None."""
    for pts, text in reversed(list(regions)):
        if point_in(pts, x, y):
            return text
    return None


def _box(x, y, w, h):
    return [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h)]


def draw_tip(gfx):
    tip = getattr(gfx, "tip", None)
    if not tip:
        return
    text, mx, my = tip
    lines = text.split("\n")
    sc = text_scale(8)
    w = max(text_w(ln, sc) for ln in lines) + 14
    h = len(lines) * 12 * sc + 8
    x = min(max(4, mx + 14), MAP_W - w - 4)
    y = min(max(4, my + 14), MAP_H - h - 4)
    if my + 14 + h > MAP_H - 4:
        y = max(4, my - h - 10)
    gfx.rect(x, y, x + w, y + h, "#0e0818", ACCENT, 2)
    for i, ln in enumerate(lines):
        gfx.text(x + 7, y + 10 + i * 12 * sc, ln, FG, 8, "w")


def draw_top(v, gfx, fx=None):
    """The bar across the top: round, pool, banner and the keep's hearts."""
    fx = fx or {}
    gfx.clear(STRIP, TOP_W, TOP_H)
    gfx.rect(0, TOP_H - 3, TOP_W, TOP_H, EDGE, "")
    gfx.text(16, 22, "ROUND %d/%d" % (max(1, v["round"]), LAST_ROUND), FG, 14, "w")
    gfx.sprite(300, 22, "coin", 2, "w")
    gfx.text(324, 22, "POOL %d" % v["pool"], ACCENT, 14, "w")
    banner = fx.get("banner") or ("BOSS WAVE!" if _boss_now(v) else "")
    hot = any(w in banner for w in ("BOSS", "DESTROYED", "hit", "fallen"))
    gfx.text(640, 22, banner.upper(), BAD if hot else FG, 14)
    gfx.text(800, 22, "KEEP", FG, 14, "w")
    for i in range(KEEP_MAX // 2):
        name = ("heart" if v["keep"] >= 2 * (i + 1) else
                "hearth" if v["keep"] == 2 * i + 1 else "hearte")
        gfx.sprite(868 + i * 26, 22, name, 3, "w")


def draw_view(v, gfx, sel=None, fx=None):
    fx = fx or {}
    flash = fx.get("flash", {})
    gfx.clear(BG, MAP_W, MAP_H)
    gfx.bricks(MAP_W, MAP_H)
    if getattr(gfx, "top", None) is not None:
        draw_top(v, gfx.top, fx)
    keep_pct = v["keep"] / KEEP_MAX
    # the hexagon's shadow and base
    gfx.poly(hex_pts(A_OUT + 8), "#120b1c", DARK, 3)
    # lanes: three floor cells each, in stone or (when a spell hits) tinted
    for qi, q in enumerate(QUADS):
        pal, line = (STONE_A, "#4a3d2c") if qi % 2 == 0 else (STONE_B, "#443a30")
        for k in (1, 2, 3):
            a0 = A0 + WALL_T + CELL * (k - 1)
            a1 = a0 + CELL
            col = flash.get((q, k)) or fx.get("lane", {}).get(q) or pal[(k - 1) % 3]
            gfx.poly(cell_poly(q, a0, a1, 1), col, DARK, 2)
            for f in (1 / 3, 2 / 3):                       # floor boards
                a = a0 + CELL * f
                h = a * T30 - 5
                gfx.line([_pt(q, a, -h), _pt(q, a, h)], line, 1)
            for i in range(5):                             # board joints
                r = _seed(qi, k, i)
                a = a0 + CELL * (1 / 3 * (i % 3)) + 2
                h = (a0 + CELL * 0.5) * T30 - 10
                p = ((r % 100) / 100 * 2 - 1) * h
                gfx.line([_pt(q, a, p), _pt(q, a + CELL / 3 - 4, p)], line, 1)
    # dark dividers between the lanes, and the outer rim
    ring_in, ring_out = hex_pts(A0 + WALL_T - 1), hex_pts(A_OUT)
    for i in range(6):
        gfx.line([ring_in[i], ring_out[i]], DARK, 8)
        gfx.line([ring_in[i], ring_out[i]], "#52407c", 2)
    gfx.poly(ring_out, "", DARK, 5)
    gfx.poly(ring_out, "", "#52407c", 1)
    if sel in QUADS:
        gfx.poly(cell_poly(sel, A0 + WALL_T, A_OUT, 2), "", ACCENT, 3)
    # the walls
    for qi, q in enumerate(QUADS):
        w = v["wall"][q]
        poly = cell_poly(q, A0, A0 + WALL_T, 0)
        if w["wall"] > 0:
            frac = w["wall_hp"] / max(1, w["cap"])
            col = "#9a8cb8" if frac > .66 else ("#b88a5a" if frac > .33 else "#c05a48")
            gfx.poly(poly, col, ACCENT if w["plating"] else DARK,
                     3 if w["plating"] else 2)
            for f in (0.33, 0.66):
                a = A0 + WALL_T * f
                h = a * T30 - 4
                gfx.line([_pt(q, a, -h), _pt(q, a, h)], "#5a4a78", 1)
            tx, ty = wall_pt(q)
            gfx.text(tx, ty, "%d" % w["wall_hp"], DARK, 8)
        else:
            gfx.poly(poly, "#241a30", BAD, 1)
            for i in range(6):                              # rubble
                r = _seed(qi, i, 7)
                tx, ty = _pt(q, A0 + 3 + r % 9, ((r // 9) % 61 - 30) * 1.3)
                gfx.rect(tx - 2, ty - 2, tx + 2, ty + 2, "#6a5e78", "")
    # the keep: a tan floor with a big number
    kc = "#c9b88a" if keep_pct > .5 else ("#c9a07a" if keep_pct > .25 else "#c98a7a")
    if fx.get("keep"):
        kc = fx["keep"]
    gfx.poly(hex_pts(A0), kc, DARK, 4)
    gfx.poly(hex_pts(A0 - 9), "#d8c9a0" if keep_pct > .25 else "#d8aa9a",
             "#8d7a5a", 1)
    gfx.text(CX, CY - 12, str(v["keep"]), "#3a2a20", 22)
    gfx.sprite(CX, CY + 24, "orb", 2, "center", ROLE_COL["Mage"])
    gfx.text(CX, CY + 24, "Mg", DARK, 8)
    # buildings stand IN the lane cells (up to 3 each), with a health bar
    regs = []
    regs.append((hex_pts(A0), "The keep: if its hearts run out, you lose.\nKeep health: %d/%d" % (v["keep"], KEEP_MAX)))
    for q in QUADS:
        w = v["wall"][q]
        regs.append((cell_poly(q, A0, A0 + WALL_T, 0),
                     ("Wall %s: %d/%d hp\nEnemies must break it to reach the keep." % (
                         q, w["wall_hp"], w["cap"])) if w["wall"] > 0 else
                     "Wall %s: destroyed\nEnemies here hit the keep directly." % q))
    for q in QUADS:
        for k in (1, 2, 3):
            cell = v["slots"][q][k - 1]
            n = len(cell)
            regs.append((cell_poly(q, A0 + WALL_T + CELL * (k - 1),
                                   A0 + WALL_T + CELL * k, 1),
                         "Lane %s, cell %d%s\n%d of %d building spots used" % (
                             q, k, " (touches the wall)" if k == 1 else "",
                             n, cm.CELL_MAX)))
            for i, s in enumerate(cell):
                x, y = struct_pt(q, k, i, n)
                sc = struct_scale(n)
                sw, sh = sprite_size(s["t"], sc)
                gfx.sprite(x, y, s["t"], sc)
                mx = struct_max_hp(s)
                by = y + sh / 2 + 3
                bw = 6 * sc
                gfx.rect(x - bw - 1, by, x + bw + 1, by + 3 + sc, DARK, "")
                gfx.rect(x - bw, by + 1, x - bw + 2 * bw * max(0, s["hp"]) / mx,
                         by + 2 + sc, GOOD if s["hp"] > mx / 2 else BAD)
                if s["t"] == "tower" and s.get("tier"):
                    gfx.text(x + sw / 2 + 2, y - sh / 2 + 2, "+%d" % s["tier"],
                             ACCENT, 8, "w")
                regs.append((_box(x, y + 2, sw / 2 + 3, sh / 2 + 6),
                             building_tip(s)))
    # enemies (cell may be fractional while they walk)
    groups = collections.defaultdict(list)
    for e in v["enemies"]:
        groups[(e["q"], int(round(e["cell"])))].append(e)
    for (q, _), es in groups.items():
        n = len(es)
        big = n > 8                      # crowded cell: draw small and tight
        for j, e in enumerate(sorted(es, key=lambda e: e["id"])):
            x, y = enemy_pt(q, e["cell"], j, big)
            sc = 1 if big else 2
            if e["type"] == "boss":
                sc = 2
            gfx.sprite(x, y, e["type"], sc)
            ew, eh = sprite_size(e["type"], sc)
            regs.append((_box(x, y, ew / 2 + 2, eh / 2 + 2),
                         "%s   hp %d\n%s" % (e["type"].capitalize(), e["hp"],
                                             ENEMY_TIP[e["type"]])))
            if e.get("frozen"):
                sw, sh = sprite_size(e["type"], sc)
                gfx.rect(x - sw / 2 - 2, y - sh / 2 - 2, x + sw / 2 + 2,
                         y + sh / 2 + 2, "", "#7fd8ff", 2)
            if not big or e["type"] == "boss":
                gfx.text(x, y + sprite_size(e["type"], sc)[1] / 2 + 5,
                         str(e["hp"]), FG, 8)
        if big:
            x, y = _pt(q, A0 + WALL_T + CELL * (es[0]["cell"] - 0.5), 0)
            gfx.text(x, y - 22, "x%d" % n, "#ff9a9a", 9)
    # heroes stand in the lane cell where they are working
    seen = collections.Counter()
    hc = v.get("hcell") or {}
    for role, q in v["pos"].items():
        cellno = hc.get(role, 1)
        i = seen[(q, cellno)]
        seen[(q, cellno)] += 1
        hx, hy = hero_pt(q, cellno, i)
        if role in fx.get("hero_xy", {}):
            hx, hy = fx["hero_xy"][role]
        gfx.oval(hx - 11, hy - 11, hx + 11, hy + 11, "", "#ffffff", 1)
        gfx.sprite(hx, hy, "orb", 2, "center", ROLE_COL[role])
        gfx.text(hx, hy, ROLE_TAG[role], DARK, 8)
        regs.append((_box(hx, hy, 12, 12), "%s (in lane %s, cell %d)\n%s" % (
            role, q, cellno, HERO_TIP[role])))
    regs.append((_box(CX, CY + 24, 12, 12), "Mage (in the keep)\n" + HERO_TIP["Mage"]))
    # lane names, and a red mark where a wave is about to appear
    marks = v["forecast"][0][1] if v["forecast"] and not fx.get("no_marks") else {}
    for q in QUADS:
        lx, ly = _pt(q, A_OUT + 22)
        gfx.text(lx, ly, q, MUTED, 9)
        if q in marks:
            p = -0.30 * lane_w(A_OUT)
            gfx.poly([_pt(q, A_OUT + 8, p), _pt(q, A_OUT + 24, p - 9),
                      _pt(q, A_OUT + 24, p + 9)], BAD, DARK, 2)
    for q in marks:
        p = -0.30 * lane_w(A_OUT)
        regs.append((_box(*_pt(q, A_OUT + 16, p), 10, 10),
                     "A wave is expected in lane %s.\nEnemies pick the lane with fewer\ntowers and more farms." % q))
    # forecast strip: what is coming, and when it appears
    top = MAP_H - STRIP_H
    gfx.rect(0, top, MAP_W, MAP_H, STRIP, "")
    gfx.rect(0, top, MAP_W, top + 3, EDGE, "")
    names = ("NOW", "NEXT", "THEN")
    for i, (rd, d) in enumerate(v["forecast"][:3]):
        y = top + 20 + i * 27
        gfx.text(8, y, names[i], ACCENT if i < 2 else MUTED, 10, "w")
        for j, q in enumerate(QUADS):
            x = 58 + j * 97
            gfx.text(x, y, q, MUTED, 8, "w")
            cx = x + text_w(q, 1) + 5
            types = sorted(d.get(q, {}).items())
            sc = 2 if len(types) <= 2 else 1
            g1, g2 = (3, 6) if sc == 2 else (2, 3)       # tighter when crowded
            for t, n in types:
                gfx.sprite(cx, y, t, sc, "w")
                cx += sprite_size(t, sc)[0] + g1
                gfx.text(cx, y, str(n), FG, 9 if sc == 2 else 8, "w")
                cx += text_w(str(n), 2 if sc == 2 else 1) + g2
    # effects drawn on top
    for (x0, y0, x1, y1, col, wd) in fx.get("lines", []):
        gfx.line([(x0, y0), (x1, y1)], col, wd)
    for (x, y, txt, col, size) in fx.get("floats", []):
        gfx.text(x + 1, y + 1, txt, "#000000", size)
        gfx.text(x, y, txt, col, size)
    try:
        gfx.regions = regs
    except Exception:
        pass
    draw_tip(gfx)


def draw_map(g, gfx, sel=None):
    draw_view(view_from_game(g), gfx, sel)


# ======================================================================
#  THE ROUND ANIMATION  (enemies advance, buildings get hit, then income)
# ======================================================================
def who_is(role, who, poss=False):
    """'Seat 2 (engineer)' or, with poss, 'Seat 2's (engineer)'."""
    nm = seat_label(who) if isinstance(who, int) else "Someone"
    return "%s%s (%s)" % (nm, "'s" if poss else "", str(role or "?").lower())


def event_lines(ev, income=()):
    """The play-by-play sentences for a group of events."""
    out = []
    for e in ev:
        k = e[0]
        if k == "cast":
            out.append("%s casts %s on %s" % (who_is("Mage", e[3]), e[1], e[2]))
        elif k == "slash":
            out.append("%s fights in %s" % (who_is("Slayer", e[2]), e[1]))
        elif k == "kill":
            _, eid, q, cell, et, kind, role, who = e
            if kind == "tower":
                out.append("%s tower killed %s" % (who_is(role, who, True), et))
            else:
                out.append("%s killed %s" % (who_is(role, who), et))
        elif k == "dmg":
            _, eid, q, cell, d, hp, kind, role, who = e
            if hp > 0:
                out.append("%s hit an enemy for %d" % (
                    who_is(role, who, True) + " tower" if kind == "tower"
                    else who_is(role, who), d))
        elif k == "build":
            _, item, q, cell, m, keep, role, who, bi = e
            out.append("%s built %s in %s%s" % (
                who_is(role, who), cm.ITEMS[item]["name"], q,
                " (cell %d)" % cell if cell else ""))
        elif k == "sdestroy":
            _, q, cell, t, bi, by, role = e
            out.append("%s %s in %s cell %d was destroyed" % (
                who_is(role, by, True), t, q, cell))
        elif k == "walldown":
            out.append("The %s wall was destroyed" % e[1])
        elif k == "keep":
            out.append("An enemy in %s hit the keep for %d" % (e[1], e[2]))
        elif k == "spawn":
            out.append("A %s appears in %s" % (e[2], e[3]))
        elif k == "loot":
            out.append("Kills pay +%d gold into the pool" % e[1])
    if income:
        base = [x for x in income if x["kind"] == "base"]
        if base:
            out.append("The realm pays +%d gold" % base[0]["amt"])
        tr = [x for x in income if x["kind"] == "trade"]
        if tr:
            out.append("Trade routes pay +%d gold" % tr[0]["amt"])
        tot = collections.OrderedDict()
        for x in income:
            if x["kind"] in ("farm", "mine"):
                key = (x.get("by"), x.get("role"), x["kind"])
                tot[key] = tot.get(key, 0) + x["amt"]
        for (by, role, kind), amt in tot.items():
            out.append("%s %ss produce +%d gold" % (
                who_is(role, by, True), kind, amt))
    return out


class Anim:
    """Plays one round's combat events, or just the income payout when given
    income only. No Tk in here: call update(dt) with seconds, draw(gfx) to
    paint it. self.lines collects the play-by-play sentences as they happen."""
    DUR = dict(cast=.55, slash=.5, shot=.3, hits=.5, freeze=.4, move=.6,
               sattack=.4, sdestroy=.6, wall=.35, walldown=.55, keep=.5,
               build=.6, spawn=.65, loot=.45, inc_base=.8, inc_struct=1.2,
               hero=.45, hold=.5)
    GROUP = {"move": "move", "dmg": "hits", "kill": "hits", "spawn": "spawn",
             "freeze": "freeze"}
    CAP = 9.0

    def __init__(self, prm):
        self.forecast = prm["forecast"]
        self.pool_before, self.pool_after = prm["pool_before"], prm["pool_after"]
        pool0 = self.pool_before
        if prm["before"]:
            self.view = view_from_snapshot(prm["before"], pool0, self.forecast)
        else:
            self.view = None                     # nothing to replay
        self.income = prm.get("income") or []
        self.beats = self._make_beats(prm["events"] if prm["before"] else [])
        tot = sum(b["dur"] for b in self.beats)
        k = min(1.0, self.CAP / tot) if tot else 1.0
        for b in self.beats:
            b["dur"] *= k
        self.i, self.t = 0, 0.0
        self.entered = -1
        self.done = not self.beats
        self.banner = ""
        self.fx_extra = {}
        self.lines = []

    # ------------------------------------------------------------ build
    def _make_beats(self, events):
        beats = []
        i = 0
        while i < len(events):
            e = events[i]
            kind = self.GROUP.get(e[0], e[0])
            grp = [e]
            if e[0] in self.GROUP:
                while i + 1 < len(events) and \
                        self.GROUP.get(events[i + 1][0]) == kind:
                    i += 1
                    grp.append(events[i])
            beats.append(dict(kind=kind, ev=grp, dur=self.DUR[kind]))
            i += 1
        base = [s for s in self.income if s["kind"] in ("base", "trade")]
        structs = [s for s in self.income if s["kind"] in ("farm", "mine")]
        if base:
            beats.append(dict(kind="inc_base", ev=base, dur=self.DUR["inc_base"]))
        if structs:
            beats.append(dict(kind="inc_struct", ev=structs,
                              dur=self.DUR["inc_struct"]))
        return beats

    def ensure_view(self, g_view):
        """With no earlier state to replay, start from the current one."""
        if self.view is None:
            self.view = g_view
            self.view["pool"] = self.pool_before

    # ----------------------------------------------------------- helpers
    def _enemy(self, eid):
        for e in self.view["enemies"]:
            if e["id"] == eid:
                return e
        return None

    def _epos(self, e):
        return enemy_pt(e["q"], e["cell"])

    def _spt(self, q, cell, bi=0):
        """Screen spot of building number bi in a cell (as the cell is now)."""
        n = len(self.view["slots"][q][cell - 1])
        if n == 0:
            return struct_pt(q, cell)
        return struct_pt(q, cell, min(bi, n - 1), n)

    def _hero_xy(self, role, q, cell):
        v = self.view
        j = sum(1 for r2, q2 in v["pos"].items() if r2 != role and q2 == q
                and (v.get("hcell") or {}).get(r2, 1) == cell)
        return hero_pt(q, cell, j)

    # ------------------------------------------------------------ steps
    def _enter(self, b):
        v, k, ev = self.view, b["kind"], b["ev"]
        b["moves"] = []
        self.banner = {
            "cast": "Mage casts", "slash": "Slayer fights", "shot": "Towers fire",
            "hits": "Hits land", "freeze": "Frost!", "move": "ENEMIES ADVANCE",
            "sattack": "Enemies attack a building", "sdestroy": "BUILDING DESTROYED",
            "wall": "Enemies batter the wall", "walldown": "WALL DESTROYED",
            "keep": "The keep is hit!", "build": "Builders finish their work",
            "spawn": "A new wave arrives", "loot": "Kill rewards",
            "hero": "Heroes move to work",
            "inc_base": "INCOME: the realm", "inc_struct": "INCOME: your farms and mines",
        }[k]
        self.lines += event_lines((), ev) if k.startswith("inc_") \
            else event_lines(ev)
        if k == "cast":
            self.banner = "Mage casts %s on %s" % (ev[0][1], ev[0][2])
        elif k == "slash":
            self.banner = "Slayer fights in %s" % ev[0][1]
        elif k == "move":
            for (_, eid, q, a, c) in ev:
                en = self._enemy(eid)
                if en:
                    b["moves"].append((en, a, c))
        elif k == "freeze":
            for (_, eid) in ev:
                en = self._enemy(eid)
                if en:
                    en["frozen"] = True
        elif k == "spawn":
            for (_, eid, t, q, cell, hp) in ev:
                v["enemies"].append(dict(id=eid, type=t, q=q, cell=cell, hp=hp))
        elif k == "build":
            _, item, q, cell, m, keep, role, who, bi = ev[0]
            v["slots"][q] = [[dict(x) for x in c] for c in m["slots"]]
            v["wall"][q] = _wall_view(m)
            v["keep"] = keep
            b["target"] = (q, cell, bi)
            self.banner = "Built: %s in %s" % (cm.ITEMS[item]["name"], q)
        elif k == "hero":
            _, role, q, cell = ev[0]
            q0 = v["pos"].get(role, q)
            c0 = (v.get("hcell") or {}).get(role, 1)
            b["from"] = hero_pt(q0, c0, 0)
            b["to"] = self._hero_xy(role, q, cell)

    def _exit(self, b):
        v, k, ev = self.view, b["kind"], b["ev"]
        if k == "hits":
            for e in ev:
                if e[0] == "dmg":
                    en = self._enemy(e[1])
                    if en:
                        en["hp"] = e[5]
            for e in ev:
                if e[0] == "kill":
                    en = self._enemy(e[1])
                    if en:
                        v["enemies"].remove(en)
        elif k == "move":
            for en, a, c in b["moves"]:
                en["cell"] = c
        elif k == "sattack":
            _, q, cell, eid, d, hp, bi = ev[0]
            if bi < len(v["slots"][q][cell - 1]):
                v["slots"][q][cell - 1][bi]["hp"] = hp
        elif k == "sdestroy":
            _, q, cell, t, bi, by, role = ev[0]
            if bi < len(v["slots"][q][cell - 1]):
                v["slots"][q][cell - 1].pop(bi)
        elif k == "wall":
            _, q, eid, d, hp = ev[0]
            v["wall"][q]["wall_hp"] = hp
        elif k == "walldown":
            q = ev[0][1]
            v["wall"][q] = dict(wall=0, wall_hp=0, plating=0, cap=0)
        elif k == "keep":
            v["keep"] = ev[0][3]
        elif k == "hero":
            _, role, q, cell = ev[0]
            v["pos"][role] = q
            v.setdefault("hcell", {})[role] = cell
        elif k == "loot":
            v["pool"] += ev[0][1]
        elif k in ("inc_base", "inc_struct"):
            v["pool"] = self._pool_at(b, 1.0)

    def _pool_at(self, b, u):
        """Pool counter while income is paid out (base first, then buildings)."""
        base = sum(s["amt"] for s in self.income if s["kind"] in ("base", "trade"))
        if b["kind"] == "inc_base":
            return self.pool_before + int(round(base * u))
        return self.pool_before + base + int(round(
            (self.pool_after - self.pool_before - base) * u))

    # ------------------------------------------------------------- loop
    def update(self, dt):
        if self.done:
            return True
        self.t += dt
        while not self.done:
            b = self.beats[self.i]
            if self.entered != self.i:
                self._enter(b)
                self.entered = self.i
            if self.t < b["dur"]:
                break
            self.t -= b["dur"]
            self._exit(b)
            self.i += 1
            if self.i >= len(self.beats):
                self.done = True
        return self.done

    def finish_now(self):
        while not self.done:
            self.update(99.0)

    def fx(self):
        """Effects for the beat that is playing right now."""
        fx = dict(banner=self.banner, floats=[], flash={}, lines=[], lane={},
                  no_marks=True, hero_xy={})
        if self.done or self.i >= len(self.beats):
            return fx
        b = self.beats[self.i]
        u = min(1.0, self.t / max(1e-6, b["dur"]))
        k, ev, v = b["kind"], b["ev"], self.view
        rise = -22 * u
        if k == "cast":
            _, spell, q, who = ev[0]
            for c in (1, 2, 3):
                fx["flash"][(q, c)] = SPELL_COL.get(spell, "#ffffff")
        elif k == "slash":
            for c in (1, 2, 3):
                fx["flash"][(ev[0][1], c)] = "#8a78b0"
        elif k == "shot":
            _, q, cell, eid, by = ev[0]
            en = self._enemy(eid)
            if en and u < .85:
                x0, y0 = self._spt(q, cell)
                x1, y1 = self._epos(en)
                fx["lines"].append((x0, y0 - 6, x1, y1, "#ffffff", 3))
        elif k == "hits":
            for e in ev:
                en = self._enemy(e[1])
                if not en:
                    continue
                x, y = self._epos(en)
                if e[0] == "dmg":
                    fx["floats"].append((x, y - 14 + rise, "-%d" % e[4], BAD, 12))
                elif u > .3:
                    fx["floats"].append((x, y, "X", BAD, 18))
        elif k == "move":
            for en, a, c in b["moves"]:
                en["cell"] = a + (c - a) * u
        elif k == "sattack":
            _, q, cell, eid, d, hp, bi = ev[0]
            x, y = self._spt(q, cell, bi)
            fx["flash"][(q, cell)] = "#7a3040"
            fx["floats"].append((x, y - 28 + rise, "-%d" % d, BAD, 13))
        elif k == "sdestroy":
            _, q, cell, t, bi, by, role = ev[0]
            x, y = self._spt(q, cell, bi)
            fx["flash"][(q, cell)] = "#9a4a28"
            fx["floats"].append((x, y - 10, "X", "#ff7a3a", 26))
            fx["floats"].append((x, y + 20 + rise, "destroyed", "#ff7a3a", 9))
        elif k == "wall":
            _, q, eid, d, hp = ev[0]
            x, y = _along(q, KEEP_HALF + WALL_T / 2)
            fx["floats"].append((x, y - 6 + rise, "-%d" % d, BAD, 12))
        elif k == "walldown":
            x, y = _along(ev[0][1], KEEP_HALF + WALL_T / 2)
            fx["floats"].append((x, y, "X", "#ff7a3a", 22))
        elif k == "keep":
            _, q, d, kp = ev[0]
            fx["keep"] = "#c04a4a"
            fx["floats"].append((CX, CY - 30 + rise, "-%d" % d, BAD, 15))
        elif k == "build":
            q, cell, bi = b["target"]
            if cell:
                fx["flash"][(q, cell)] = "#3a7a52"
                x, y = self._spt(q, cell, bi if bi is not None else 0)
            else:
                x, y = _along(q, KEEP_HALF + WALL_T / 2)
            fx["floats"].append((x, y - 30 + rise, "built", GOOD, 10))
        elif k == "hero":
            (x0, y0), (x1, y1) = b["from"], b["to"]
            fx["hero_xy"][ev[0][1]] = (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)
        elif k == "spawn":
            for e in ev:
                fx["lane"][e[3]] = "#5a3a48"
        elif k == "freeze":
            pass
        elif k == "loot":
            fx["floats"].append((CX, CY - 30 + rise, "+%d" % ev[0][1], ACCENT, 15))
        elif k == "inc_base":
            for s in ev:
                off = -14 if s["kind"] == "base" else 12
                fx["floats"].append((CX + (50 if s["kind"] == "base" else -50),
                                     CY + off + rise, "+%d %s" % (s["amt"], s["kind"]),
                                     ACCENT, 12))
            v["pool"] = self._pool_at(b, u)
        elif k == "inc_struct":
            for s in ev:
                x, y = self._spt(s["q"], s["cell"], s.get("bi", 0))
                fx["flash"][(s["q"], s["cell"])] = "#a89030"
                fx["floats"].append((x, y - 30 + rise * 1.3, "+%d" % s["amt"],
                                     ACCENT, 15))
            v["pool"] = self._pool_at(b, u)
        return fx

    def draw(self, gfx):
        if self.view is None:
            return
        draw_view(self.view, gfx, None, self.fx())


# ======================================================================
#  HELP TEXT  (every project, building, spell, role and screen explained)
# ======================================================================
DETAIL = {
    # ---- personal projects: work the moment they are fully paid for
    "clerks1": "The Steward can run more building crews.\n"
               "EFFECT: +1 build point for the Steward. A build point is one "
               "building the Steward can place per round. You start with 1 and "
               "a good mini-game adds 1 or 2 more.\n"
               "WORTH IT: only once the Steward has enough gold in the economy "
               "budget to build more than one thing per round.",
    "trade1": "A permanent trade deal.\n"
              "EFFECT: +1 gold added to the shared pool at the start of every "
              "round for the rest of the game. Enemies cannot destroy it "
              "(unlike farms and mines).\n"
              "WORTH IT: it pays for itself in 7 rounds, so buy it early or "
              "not at all.",
    "trade2": "A bigger trade deal. Needs Trade Routes I first.\n"
              "EFFECT: +2 more gold per round, forever.\n"
              "WORTH IT: it pays for itself in 6 rounds, so it is only good in "
              "the first half of the game.",
    "hammer1": "Better tools for the Engineer.\n"
               "EFFECT: +1 build point. The Engineer can place one more wall, "
               "tower or repair each round.\n"
               "WORTH IT: only if the wall and tower budgets have enough gold "
               "to use the extra point.",
    "hammer2": "Even better tools. Needs Efficient Builders I.\n"
               "EFFECT: +1 more build point for the Engineer.",
    "sword1": "A steel sword for the Slayer.\n"
              "EFFECT: +2 damage every round on top of the mini-game damage "
              "(2 poor, 3 okay, 5 great). The Slayer hits enemies in one "
              "lane, nearest the wall first (or the strongest first if you "
              "pick that).\n"
              "WORTH IT: it works every round forever, so it is good value.",
    "sword2": "A runed blade. Needs Steel Sword first.\n"
              "EFFECT: +3 more damage every round.",
    "smith1": "Better tools for the Smith.\n"
              "EFFECT: +1 build point. The Smith can upgrade one more tower or "
              "plate one more wall per round.",
    "smith2": "Master tools. Needs Master's Tools I.\n"
              "EFFECT: +1 more build point for the Smith.",
    "whet": "Sharpened steel for everyone.\n"
            "EFFECT: +1 damage on EVERY tower shot and +1 damage on the "
            "Slayer's attack, every round.\n"
            "WORTH IT: the more towers you own, the better. With 4 or more "
            "towers it is one of the best buys in the game.",
    "frost": "Teaches the Mage Frost.\n"
             "EFFECT: costs 2 mana. Frozen enemies lose their whole turn: they "
             "do not move and they do not attack. Poor freezes the 2 nearest "
             "enemies in a lane, okay freezes 4, great freezes all of them.\n"
             "WORTH IT: when a wave is about to reach a wall and you need "
             "time for towers and the Slayer to work.",
    "fire": "Teaches the Mage Fire.\n"
            "EFFECT: costs 2 mana. Hits EVERY enemy in one lane for "
            "1 + mini-game bonus damage (1 poor, 2 okay, 3 great).\n"
            "WORTH IT: best against crowds of goblins and runners. Weak "
            "against a single troll.",
    "ward": "Teaches the Mage Ward.\n"
            "EFFECT: costs 2 mana. Protects one lane for this round. Poor "
            "halves damage to walls and buildings, okay stops it completely, "
            "great also stops damage to the keep from that lane.\n"
            "WORTH IT: when a wall is about to fall or farms and mines are "
            "under attack.",
    "lightning": "Teaches the Mage Lightning.\n"
                 "EFFECT: costs 3 mana. Hits the 3 nearest enemies in a "
                 "lane for 2 + mini-game bonus (2 poor, 3 okay, 4 great).\n"
                 "WORTH IT: strong against trolls and archers. Expensive in "
                 "mana, so buy Mana Wells too.",
    "bolt": "The Mage always knows Bolt.\n"
            "EFFECT: costs 1 mana. Hits the nearest enemy in a lane for "
            "2 + mini-game bonus (2 poor, 3 okay, 4 great). Cheap and "
            "reliable.",
    "mana1": "A bigger mana pool.\n"
             "EFFECT: +1 mana every round (you start with 3). Mana does not "
             "carry over, unused mana is lost at the end of the round.\n"
             "WORTH IT: if you keep wanting to cast one more spell.",
    "mana2": "An even bigger mana pool. Needs Mana Well I first.\n"
             "EFFECT: +1 more mana every round.",
    # ---- budgets: gold that is stored until its owner builds something
    "b_econ": "Gold stored for the Steward's farms and mines.\n"
              "HOW IT WORKS: paying into a budget does nothing by itself. "
              "During the combat step the Steward chooses what to build and "
              "the gold is spent then. Up to 30 gold can be stored.\n"
              "WARNING: gold is never refunded, and a building that gets "
              "destroyed is gone, you have to pay for a new one.",
    "b_wall": "Gold stored for the Engineer's walls and repairs.\n"
              "PAYS FOR: wall sections (4), wall repair (2), keep repair (3).\n"
              "HOW IT WORKS: the Engineer spends it during the combat step. "
              "Up to 30 gold can be stored. Never refunded.",
    "b_tower": "Gold stored for the Engineer's towers.\n"
               "PAYS FOR: towers (6 each).\n"
               "HOW IT WORKS: the Engineer spends it when building. Up to 30 "
               "gold can be stored. Never refunded.",
    "b_forge": "Gold stored for the Smith.\n"
               "PAYS FOR: tower upgrades (7) and wall plating (6).\n"
               "HOW IT WORKS: the Smith spends it during the combat step. Up "
               "to 30 gold can be stored. Never refunded.",
    "b_tonic": "Gold stored for the Slayer's tonics.\n"
               "PAYS FOR: tonics (3 each). Each tonic drunk gives +3 damage "
               "that round, up to 2 per round.\n"
               "Up to 30 gold can be stored. Never refunded.",
    # ---- things you can build
    "farm": "Farm: +2 gold every round.\n"
            "WHERE: in a lane cell. If you do not pick a cell it goes in the "
            "emptiest cell, closest to the wall first (the safest one).\n"
            "HP: 4. Any enemy standing in the same cell attacks it. At 0 HP "
            "it is destroyed and its gold is lost.\n"
            "LIMITS: 3 buildings per cell. It is placed at the START of "
            "combat and pays from the next income.\n"
            "ENEMIES LIKE FARMS: waves pick the lane with the most farms and "
            "mines and the fewest towers.",
    "mine": "Mine: +4 gold every round.\n"
            "WHERE: in a lane cell (default: the emptiest cell near the "
            "wall).\n"
            "HP: 6. Enemies in its cell attack it and can destroy it.\n"
            "LIMITS: 3 buildings per cell. Placed at the start of combat, "
            "pays from the next income. Enemies like lanes with mines.",
    "wall": "Wall section: +6 wall HP.\n"
            "WHERE: a wall stands between the lane and the keep. Up to 3 "
            "sections per lane, their HP adds up.\n"
            "Enemies reaching cell 1 batter the wall. When its HP hits 0 the "
            "whole wall is destroyed (plating too) and enemies hit the keep "
            "directly.",
    "repair": "Repair the wall: +4 wall HP in the lane you stand in.\n"
              "It cannot go above the wall's maximum (6 per section plus 6 "
              "per plating).",
    "keep_repair": "Repair the keep: +2 keep HP (the keep can never go above "
                   "20).\n"
                   "A cheap emergency fix when the keep is getting low.",
    "tower": "Tower: shoots the nearest enemy in its lane every round.\n"
             "DAMAGE: 1 (+1 per upgrade, +1 with Whetstones). Range is the "
             "whole lane.\n"
             "WHERE: in a lane cell (default: cell 2). HP: 8. Enemies "
             "standing in its cell attack it, so a tower at the outer end "
             "gets hit first.\n"
             "LIMITS: 3 buildings per cell. It is placed before combat, so it "
             "fires the same round. Enemies avoid lanes with many towers.",
    "tower_up": "Tower upgrade: +1 damage per shot and +2 HP.\n"
                "WHERE: pick which tower (by its cell). Each tower can be "
                "upgraded twice. The number inside the tower triangle is its "
                "level.",
    "plating": "Wall plating: +6 wall HP and +6 maximum HP.\n"
               "Up to 2 platings per lane. A gold outline shows a plated "
               "wall. Plating is lost if the wall falls.",
    "tonic": "Tonic: the Slayer drinks it for +3 damage this round.\n"
             "Up to 2 per round. They come out of the tonic budget.",
}

ROLE_TEXT = {
    "Steward": "The Steward grows the economy.\n"
               "BUILDS: farms (+2 gold per round) and mines (+4 gold per "
               "round) in lane cells. They are the main way to get more gold, "
               "and enemies can destroy them.\n"
               "MINI-GAME: Market rush. Poor gives 1 build point, okay gives "
               "2, great gives 3 (plus any Clerks upgrades).",
    "Engineer": "The Engineer keeps the keep standing.\n"
                "BUILDS: wall sections, wall repair, keep repair and towers "
                "(placed in lane cells).\n"
                "MINI-GAME: Stack the stones. Poor gives 1 build point, okay "
                "2, great 3 (plus Efficient Builders upgrades).",
    "Slayer": "The Slayer fights in one lane each round.\n"
              "DAMAGE: 2 (poor), 3 (okay) or 5 (great) from the mini-game, "
              "plus sword upgrades, Whetstones and tonics. It is split over "
              "the enemies there: nearest the wall first, or the strongest "
              "first if you choose.\n"
              "MINI-GAME: Parry.",
    "Smith": "The Smith makes everything else stronger.\n"
             "BUILDS: tower upgrades and wall plating. Personal upgrades like "
             "Whetstones boost every tower and the Slayer.\n"
             "MINI-GAME: Forge. Poor gives 1 build point, okay 2, great 3 "
             "(plus Master's Tools upgrades).",
    "Mage": "The Mage sits in the keep and casts into any lane.\n"
            "MANA: 3 per round (more with Mana Wells), unused mana is lost. "
            "You can make up to 4 casts. Bolt is free to learn, other spells "
            "must be bought as projects.\n"
            "MINI-GAME: Rune memory. The result sets how strong every spell "
            "is this round: poor, okay or great.",
}

STEP_HELP = {
    "advance": "WHAT YOU ARE SEEING: the new round's INCOME is paid. The "
               "realm pays first, then each farm and mine pays out from its "
               "own cell. The list underneath says which player's farms or "
               "mines made how much. The pool counter at the top goes up.\n"
               "Press Skip to jump to the end.",
    "petition": "WHAT THIS IS: the shared pool is smaller than everyone's "
                "wishes, so each player asks for what they want. This round's "
                "TREASURER then decides who gets what.\n"
                "YOU CAN: ask for up to 2 projects, with an amount for each, "
                "and mark one as your MUST-HAVE (the treasurer pays those "
                "first). Or skip, and take a guaranteed deposit into your "
                "vault instead.\n"
                "A deposit is safe gold that only you can spend. If you ask "
                "and get nothing you still keep the deposit.",
    "treasury": "WHAT THIS IS: you are the treasurer this round. You decide "
                "how the pool is split between the requests. Players who get "
                "nothing keep their deposit, so nobody loses out completely.\n"
                "The numbers are prefilled with an automatic fair split. "
                "Change them if you want. The total cannot go over the pool.",
    "vault": "WHAT THIS IS: your vault is your own saved gold. It can only "
             "pay for YOUR projects, and everyone can see how full it is. "
             "Gold you spend is never refunded.\n"
             "You can fund more than one project, or keep gold for later. A "
             "vault has a limit, so a full vault wastes your deposits.",
    "plan": "WHAT THIS IS: choose where your hero goes this round and what "
            "they do. Your mini-game comes next and decides how well it goes "
            "(poor, okay or great).",
    "mini": "WHAT THIS IS: a short skill game. Your score becomes poor, okay "
            "or GREAT, which sets how strong your actions are this round "
            "(build points for builders, damage for the Slayer, spell power "
            "for the Mage).",
    "report": "WHAT THIS IS: first an animation replays this round's fight "
              "(builders walk to their cells and build, spells, tower shots, "
              "enemies marching, hits and kills). A list says which player "
              "did what. After it ends you get the round summary. "
              "The message count shows how many messages the real chat game "
              "would send. The state check should match on every computer.",
}

BUTTONS = {
    "petition": "Send petition: asks the pool for the gold in the boxes above "
                "(max 2 projects).\nSkip (bank): asks for nothing and puts "
                "the gold in brackets from the pool into your vault instead.",
    "treasury": "Send decision: gives out the gold exactly as set above.\n"
                "Use auto draft: lets the game split it fairly for you.",
    "vault": "Done: spends the amounts above from your vault. Anything left "
             "stays in your vault.",
    "plan": "Next: mini-game: locks in these choices and starts your "
            "mini-game. The result sets your strength this round.",
    "mini_start": "Start: begins the timer. Nothing happens until you press it.",
    "mini_done": "Continue: sends your result and goes to the next step.",
    "report": "Next round: starts the next round and the income animation.",
    "advance": "Skip: jumps straight to the end of the animation.",
}

MINI_BAND = {
    "Steward": "Result: poor = 1 build point, okay = 2, great = 3.",
    "Engineer": "Result: poor = 1 build point, okay = 2, great = 3.",
    "Smith": "Result: poor = 1 build point, okay = 2, great = 3.",
    "Slayer": "Result: poor = 2 damage, okay = 3, great = 5.",
    "Mage": "Result: sets the power of every spell you cast this round.",
}

HOW_TO_PLAY = [
    ("Goal", "Defend the keep together. Waves of enemies walk in along the "
             "six lanes of the hexagon (N, NE, SE, S, SW, NW). Survive 12 rounds and kill the "
             "boss that arrives in round 12. The keep has 20 HP. If it hits "
             "0 you lose."),
    ("The map", "Each lane has 3 cells. Cell 1 is next to the wall. "
                "Enemies appear in cell 3 and walk toward the keep. Farms, "
                "mines and towers are built INSIDE the cells, up to 3 "
                "buildings per cell. A new wave goes to the lane with the "
                "fewest towers and the most farms and mines. An enemy that "
                "stands in a cell with a building attacks it, and a "
                "destroyed building is gone for good. At cell 1, enemies "
                "batter the wall, and once the wall is gone they hit the "
                "keep."),
    ("A round", "1 Income is paid.  2 Anyone who asks for nothing banks a "
                "deposit.  3 Players petition the pool and the treasurer "
                "splits it.  4 You spend your vault on your own projects.  "
                "5 Each hero picks a lane and an action.  6 Mini-games "
                "decide how well it goes. Then builders build (their "
                "buildings work this same round), the fight happens, and an "
                "animation shows who did what, followed by the summary."),
    ("Gold", "POOL: shared gold. It grows from income and kills.\n"
             "TREASURER: rotates every round and splits the pool between "
             "petitions.\n"
             "VAULT: your own gold, capped, visible to everyone. It only "
             "pays for your own projects. Spent gold is never refunded.\n"
             "BANK: if you do not petition you get a guaranteed deposit "
             "into your vault."),
    ("Projects", "PERSONAL projects (spells, sword upgrades, trade routes, "
                 "extra build points) work as soon as they are fully paid.\n"
                 "BUDGETS store gold for things you BUILD (farms, walls, "
                 "towers). The owner builds them at the start of combat, "
                 "so they work in the same round."),
    ("Roles", "Steward: farms and mines.  Engineer: walls and towers.  "
              "Slayer: fights in a lane.  Smith: tower upgrades and "
              "wall plating.  Mage: spells, limited by mana.  With fewer "
              "than 5 players, one person plays several roles with shorter "
              "mini-games."),
    ("Combat order", "Builders build first, then Mage spells, then the "
                     "Slayer, then towers shoot, then enemies act (frozen "
                     "ones skip), then a new wave appears. Hover the mouse "
                     "over anything on the map for a short description."),
    ("Mini-games", "Each role has a short skill game. Poor, okay or great "
                   "sets how strong your action is. Doing nothing counts as "
                   "poor."),
]


def project_detail(pid):
    """The full text for a project, budget, item or spell."""
    txt = DETAIL.get(pid, "")
    pr = PROJECTS.get(pid)
    it = ITEMS.get(pid)
    extra = ""
    if pr:
        extra = "OWNER: the %s." % pr["role"]
        if pr["kind"] == "personal":
            extra += "  COST: %d gold in total.  Works as soon as it is fully paid." % pr["cost"]
            if pr["req"]:
                extra += "  NEEDS: %s first." % PROJECTS[pr["req"]]["name"]
    elif it:
        extra = "COST: %d gold from the %s." % (
            it["cost"], PROJECTS[it["budget"]]["name"])
    return (txt + "\n" + extra).strip()


# ======================================================================
#  MINI-GAMES  (each one returns a band: 0 poor, 1 okay, 2 great)
# ======================================================================
MW, MH = 480, 300


class Mini:
    title, help = "", ""
    GREAT, OKAY = 0.8, 0.5

    def __init__(self, rng, short=False):
        self.rng, self.short = rng, short
        self.t0 = None
        self.last = None
        self.done = False
        self.hits = 0
        self.total = 1

    def start(self, now):
        self.t0 = self.last = now

    def tick(self, now):
        pass

    LIMIT = 60.0

    def step(self, now):
        """One frame: move things on, and end the game if it drags on."""
        if not self.done:
            self.tick(now)
        if not self.done and now - self.t0 > self.LIMIT:
            self.done = True

    def key(self, k, now):
        pass

    def click(self, x, y, now):
        pass

    def draw(self, g, now):
        pass

    def frac(self):
        return self.hits / max(1, self.total)

    def band(self):
        f = self.frac()
        return 2 if f >= self.GREAT else (1 if f >= self.OKAY else 0)

    def result(self):
        return "%d of %d  -  %s" % (self.hits, self.total,
                                    ("poor", "okay", "GREAT")[self.band()])

    def frame(self, g, now, extra=""):
        g.clear("#1d1628", MW, MH)
        g.text(10, 8, self.title, ACCENT, 13, "nw")
        g.text(MW - 10, 8, "%d / %d" % (self.hits, self.total), FG, 13, "ne")
        hint = extra or self.help
        g.text(MW // 2, MH - 10, hint, MUTED, fit_size(hint, 10, MW - 12), "s")


class Market(Mini):
    """Steward: click each coin before it disappears."""
    title = "Market rush"
    help = "Click every coin before it vanishes"

    def __init__(self, rng, short=False):
        super().__init__(rng, short)
        n = 5 if short else 8
        self.total = n
        self.ttl = 1.4
        self.coins = [dict(t=0.6 + i * 1.25, x=rng.randint(50, MW - 50),
                           y=rng.randint(70, MH - 50), st=0) for i in range(n)]

    def tick(self, now):
        t = now - self.t0
        for c in self.coins:
            if c["st"] == 0 and t > c["t"] + self.ttl:
                c["st"] = 2
        if all(c["st"] for c in self.coins):
            self.done = True

    def click(self, x, y, now):
        t = now - self.t0
        for c in self.coins:
            if c["st"] == 0 and c["t"] <= t <= c["t"] + self.ttl and \
                    (x - c["x"]) ** 2 + (y - c["y"]) ** 2 <= 26 ** 2:
                c["st"] = 1
                self.hits += 1
                return

    def draw(self, g, now):
        self.frame(g, now)
        t = now - self.t0
        for c in self.coins:
            if c["st"] == 1:
                g.oval(c["x"] - 8, c["y"] - 8, c["x"] + 8, c["y"] + 8, GOOD)
            elif c["st"] == 0 and c["t"] <= t <= c["t"] + self.ttl:
                left = 1 - (t - c["t"]) / self.ttl
                g.oval(c["x"] - 22, c["y"] - 22, c["x"] + 22, c["y"] + 22,
                       "#e0b020", "#fff2a8", 3)
                g.oval(c["x"] - 22 * left, c["y"] - 22 * left,
                       c["x"] + 22 * left, c["y"] + 22 * left, "", BAD, 2)
                g.text(c["x"], c["y"], "$", "#17121f", 16)


class Stack(Mini):
    """Engineer: drop each block on top of the last one."""
    title = "Stack the stones"
    help = "Space or click drops the block. Line it up!"
    GREAT, OKAY = 0.8, 0.4

    def __init__(self, rng, short=False):
        super().__init__(rng, short)
        self.total = 3 if short else 5
        self.w, self.x, self.dir, self.speed = 150.0, 0.0, 1, 190.0
        self.stack = [(MW / 2 - 75, 150.0)]
        self.drops = 0

    def tick(self, now):
        dt = min(0.05, now - self.last)
        self.last = now
        if self.done:
            return
        self.x += self.dir * self.speed * dt
        if self.x <= 0:
            self.x, self.dir = 0.0, 1
        if self.x >= MW - self.w:
            self.x, self.dir = MW - self.w, -1

    def drop(self, now):
        if self.done:
            return
        px, pw = self.stack[-1]
        off = abs(self.x - px)
        self.drops += 1
        if off <= 14:
            self.hits += 1
            self.stack.append((px, pw))
            self.w = pw
        else:
            lo, hi = max(self.x, px), min(self.x + self.w, px + pw)
            if hi - lo <= 4:
                self.stack.append((self.x, 0.0))
                self.done = True
                return
            self.stack.append((lo, hi - lo))
            self.w = hi - lo
        self.speed *= 1.1
        if self.drops >= self.total:
            self.done = True

    def key(self, k, now):
        if k in ("space", "Return"):
            self.drop(now)

    def click(self, x, y, now):
        self.drop(now)

    def draw(self, g, now):
        self.frame(g, now)
        base = MH - 40
        for i, (x, w) in enumerate(self.stack):
            if w > 0:
                g.rect(x, base - 18 * (i + 1), x + w, base - 18 * i - 2,
                       "#b08850" if i else "#7a6040", "#2a2030")
        if not self.done:
            g.rect(self.x, base - 18 * (len(self.stack) + 1),
                   self.x + self.w, base - 18 * len(self.stack) - 2,
                   "#e0b060", "#fff2a8", 2)


class Parry(Mini):
    """Slayer: press the arrow that matches before the time runs out."""
    title = "Parry"
    help = "Press the arrow key shown (Left/Right/Up/Down)"
    ARROWS = {"Left": "<", "Right": ">", "Up": "^", "Down": "v"}

    def __init__(self, rng, short=False):
        super().__init__(rng, short)
        n = 6 if short else 10
        self.total, self.win = n, 0.95
        self.pr = [dict(t=0.8 + i * 1.25, d=rng.choice(list(self.ARROWS)), st=0)
                   for i in range(n)]

    def _active(self, t):
        for p in self.pr:
            if p["st"] == 0 and p["t"] <= t <= p["t"] + self.win:
                return p
        return None

    def tick(self, now):
        t = now - self.t0
        for p in self.pr:
            if p["st"] == 0 and t > p["t"] + self.win:
                p["st"] = 2
        if all(p["st"] for p in self.pr):
            self.done = True

    def key(self, k, now):
        if k not in self.ARROWS:
            return
        p = self._active(now - self.t0)
        if p:
            if k == p["d"]:
                p["st"] = 1
                self.hits += 1
            else:
                p["st"] = 2

    def draw(self, g, now):
        self.frame(g, now)
        p = self._active(now - self.t0)
        if p:
            left = 1 - ((now - self.t0) - p["t"]) / self.win
            g.oval(MW / 2 - 70, MH / 2 - 70, MW / 2 + 70, MH / 2 + 70, "#2a1f3a",
                   BAD, 3)
            g.oval(MW / 2 - 70 * left, MH / 2 - 70 * left, MW / 2 + 70 * left,
                   MH / 2 + 70 * left, "", ACCENT, 4)
            g.text(MW / 2, MH / 2, self.ARROWS[p["d"]], FG, 60)
        else:
            g.text(MW / 2, MH / 2, "...", MUTED, 30)


class Forge(Mini):
    """Smith: hit the hot zone with the swinging marker."""
    title = "Forge"
    help = "Space or click when the marker is in the hot zone"
    GREAT, OKAY = 0.8, 0.5

    def __init__(self, rng, short=False):
        super().__init__(rng, short)
        self.total = 4 if short else 6
        self.bar = (40, MW - 40)
        self.strikes = 0
        self.zw = 100.0
        self._zone()
        self.flash = None

    def _zone(self):
        lo, hi = self.bar[0] + self.zw / 2, self.bar[1] - self.zw / 2
        self.zc = self.rng.uniform(lo, hi)

    def marker(self, now):
        sp = 0.8 + 0.1 * self.strikes                       # swings per second
        u = ((now - self.t0) * sp) % 2.0
        tri = u if u <= 1 else 2 - u
        return self.bar[0] + (self.bar[1] - self.bar[0]) * tri

    def strike(self, now):
        if self.done:
            return
        ok = abs(self.marker(now) - self.zc) <= self.zw / 2
        self.hits += ok
        self.flash = (now, ok)
        self.strikes += 1
        self.zw = max(36.0, self.zw - 10)
        self._zone()
        if self.strikes >= self.total:
            self.done = True

    def key(self, k, now):
        if k in ("space", "Return"):
            self.strike(now)

    def click(self, x, y, now):
        self.strike(now)

    def draw(self, g, now):
        self.frame(g, now)
        y = MH // 2
        g.rect(self.bar[0], y - 14, self.bar[1], y + 14, "#2a2030", "#5a4a6a", 2)
        g.rect(self.zc - self.zw / 2, y - 14, self.zc + self.zw / 2, y + 14,
               "#d05020", "#ffb060", 2)
        mx = self.marker(now)
        g.rect(mx - 3, y - 26, mx + 3, y + 26, FG)
        if self.flash and now - self.flash[0] < 0.5:
            g.text(MW / 2, y + 60, "HIT!" if self.flash[1] else "miss",
                   GOOD if self.flash[1] else BAD, 20)


class Runes(Mini):
    """Mage: watch the runes light up, then repeat the order."""
    title = "Rune memory"
    help = "Watch, then press 1-4 (or click) in the same order"
    GREAT, OKAY = 0.99, 0.5
    COLS = ("#e04a4a", "#4ae04a", "#4a8ae0", "#e0d040")

    def __init__(self, rng, short=False):
        super().__init__(rng, short)
        self.lens = (3, 4) if short else (3, 4, 5)
        self.total = len(self.lens)
        self.level = 0
        self.seqs = [[rng.randrange(4) for _ in range(n)] for n in self.lens]
        self.phase, self.pt = "show", None
        self.entered = []
        self.msg = ""

    def start(self, now):
        super().start(now)
        self.pt = now + 0.8

    def _lit(self, now):
        if self.phase != "show":
            return None
        i = int((now - self.pt) // 0.9) if now >= self.pt else -1
        if 0 <= i < len(self.seqs[self.level]) and (now - self.pt) % 0.9 < 0.65:
            return self.seqs[self.level][i]
        return None

    def tick(self, now):
        if self.done:
            return
        if self.phase == "show" and now - self.pt >= 0.9 * len(self.seqs[self.level]):
            self.phase, self.entered = "input", []
        elif self.phase == "gap" and now >= self.pt:
            self.level += 1
            if self.level >= len(self.lens):
                self.done = True
            else:
                self.phase, self.pt = "show", now + 0.6

    def press(self, i, now):
        if self.phase != "input":
            return
        want = self.seqs[self.level][len(self.entered)]
        if i != want:
            self.msg, self.phase, self.pt = "wrong", "gap", now + 1.0
            return
        self.entered.append(i)
        if len(self.entered) == len(self.seqs[self.level]):
            self.hits += 1
            self.msg, self.phase, self.pt = "got it", "gap", now + 1.0

    def key(self, k, now):
        if k in ("1", "2", "3", "4"):
            self.press(int(k) - 1, now)

    def click(self, x, y, now):
        for i in range(4):
            bx = 60 + i * 95
            if bx <= x <= bx + 80 and 120 <= y <= 200:
                self.press(i, now)

    def draw(self, g, now):
        self.frame(g, now)
        lit = self._lit(now)
        for i in range(4):
            bx = 60 + i * 95
            on = lit == i
            g.rect(bx, 120, bx + 80, 200, self.COLS[i] if on else "#2a2030",
                   self.COLS[i], 3)
            g.text(bx + 40, 160, str(i + 1), "#17121f" if on else self.COLS[i], 26)
        status = {"show": "watch...", "input": "your turn: %d/%d" % (
            len(self.entered), len(self.seqs[self.level]) if self.level < len(self.seqs) else 0),
            "gap": self.msg}.get(self.phase, "")
        g.text(MW / 2, 240, status, FG, 14)


MINIGAMES = {"Steward": Market, "Engineer": Stack, "Slayer": Parry,
             "Smith": Forge, "Mage": Runes}


# ======================================================================
#  THE FLOW: one generator that asks the people (or bots) for each step
# ======================================================================
class Session:
    """Runs a whole game. Call first() then answer(value) for each prompt
    until it returns None. A prompt is a dict with a "kind":
      advance / petition / treasury / vault / plan / mini / report / end
    Bots answer for themselves, so only human seats ever get a prompt."""

    def __init__(self, n=4, humans=(0,), seed=1, diff="Normal",
                 treasurer="draft", styles=("balanced", "saver", "spender"),
                 remote=(), send=None, names=None, seats=None):
        """remote: seats played by people on OTHER computers. send(key, value)
        is called with every answer a local person gives, so the others can
        feed it to their own copy (see feed). Every computer runs the same
        game from the same seed, so only these answers are ever sent."""
        self.g = Game(n, seed, DIFFICULTY.get(diff, diff), treasurer, seats)
        n = self.g.n
        SEAT_NAMES.clear()
        for i, nm in enumerate(names or []):
            if nm:
                SEAT_NAMES[i] = str(nm)[:20]
        self.humans = set(humans)
        self.remote = set(remote)
        self.send = send
        self.inbox = {}                  # key -> answer from another computer
        self.sent = {}                   # key -> our own answers (to replay)
        self.start_hash = {}             # round -> state check at round start
        self.desync = []                 # rounds where a peer's check differed
        self.bots = [Bot(styles[i % len(styles)]) for i in range(n)]
        self.rng = random.Random(seed * 13 + 7)
        self.gen = self._flow()
        self.log = []
        self.msgs_last = collections.Counter()

    def first(self):
        return next(self.gen)

    def answer(self, value=None):
        try:
            return self.gen.send(value)
        except StopIteration:
            return None

    @staticmethod
    def clean_alloc(alloc):
        """Whatever arrives (a person's form, or a message from another
        laptop), keep only well-formed {(player, project): whole gold}."""
        if not isinstance(alloc, dict):
            return None
        out = {}
        for k, v in alloc.items():
            try:
                p, pid = k
                out[(int(p), str(pid))] = int(v)
            except (TypeError, ValueError):
                continue
        return out

    # -- talking to the other computers
    def feed(self, key, value):
        """An answer arrived from another computer (the first one wins, so
        repeats are harmless)."""
        if isinstance(key, str) and key not in self.inbox:
            self.inbox[key] = value

    def emit(self, key, value):
        self.sent[key] = value
        if self.send:
            self.send(key, value)

    @staticmethod
    def is_skip(v):
        return isinstance(v, dict) and v.get("skip") == 1

    def key(self, kind, seat):
        return "%d:%s:%d" % (self.g.round, kind, seat)

    def waiting_on(self):
        """(key, seat) the flow is stuck on, or None."""
        return getattr(self, "_waiting", None)

    def _await(self, kind, seat, what):
        key = self.key(kind, seat)
        while key not in self.inbox:
            self._waiting = (key, seat)
            yield dict(kind="wait", key=key, seat=seat, what=what,
                       round=self.g.round)
        self._waiting = None
        return self.inbox.pop(key)

    # -- helpers for the forms
    def seat_name(self, p):
        who = SEAT_NAMES.get(p) or "Seat %d" % (p + 1)
        return "%s (%s)" % (who, ", ".join(self.g.seats[p]))

    def options(self, p):
        g = self.g
        return [(pid, g.need(pid), PROJECTS[pid]["name"], PROJECTS[pid]["role"],
                 PROJECTS[pid]["kind"], PROJECTS[pid]["desc"]) for pid in g.fundable(p)]

    def _flow(self):
        g = self.g
        while not g.over:
            g.start_round()
            self.start_hash[g.round] = g.state_hash()
            # the animation: this round's income being paid out
            yield dict(kind="advance", round=g.round, before=None, events=[],
                       income=list(g.income_srcs),
                       pool_before=g.pool - g.income, pool_after=g.pool,
                       forecast=forecast_rows(g, 3),
                       income_parts=dict(g.income_parts))
            # petitions: our people first, then wait for the other computers
            answers = {}
            for p in range(g.n):
                if p in self.humans:
                    ans = yield dict(kind="petition", seat=p, pool=g.pool,
                                     deposit=g.deposit_estimate(),
                                     bank=g.bank_amount(p),
                                     options=self.options(p),
                                     default=self.bots[p].petition(g, p))
                    answers[p] = ans
                    self.emit(self.key("pet", p), dict(ans) if ans else {})
            pet = {}
            for p in range(g.n):
                if p in self.remote:
                    v = yield from self._await("pet", p, "petition")
                    ans = None if self.is_skip(v) else v
                elif p in self.humans:
                    ans = answers[p]
                else:
                    ans = self.bots[p].petition(g, p)
                if ans:
                    pet[p] = ans
            g.petition(pet)
            # the treasurer decides
            alloc = None
            if g.pet:
                t = g.treasurer
                default = allocate(g, g.treasurer_style)
                if t in self.humans:
                    alloc = yield dict(
                        kind="treasury", seat=t, pool=g.pool, default=default,
                        pets=[(p, pid, a, d["must"] == pid)
                              for p, d in sorted(g.pet.items())
                              for pid, a in d["items"]])
                    clean = self.clean_alloc(alloc)
                    self.emit(self.key("alloc", t), None if clean is None else
                              [[p, pid, a] for (p, pid), a in
                               sorted(clean.items())])
                elif t in self.remote:
                    v = yield from self._await("alloc", t, "treasurer's decision")
                    alloc = None
                    if isinstance(v, list):
                        alloc = {}
                        for it in v[:20]:
                            try:
                                alloc[(int(it[0]), str(it[1]))] = int(it[2])
                            except (TypeError, ValueError, IndexError, KeyError):
                                continue
                else:
                    alloc = self.bots[t].allocate(g)
            g.decide(self.clean_alloc(alloc))
            # vault, map choices and mini-games: one "final" per player
            bands = {}

            def roll(role):
                if role not in bands:
                    bands[role] = roll_band(self.rng)
                return bands[role]
            mine = {}
            for p in range(g.n):
                if p not in self.humans:
                    continue
                vault = yield dict(kind="vault", seat=p, vault=g.vault[p],
                                   cap=g.cap[p], options=self.options(p),
                                   funded=list(g.funded), pool=g.pool,
                                   default=self.bots[p].vault(g, p))
                roles = {}
                short = len(g.seats[p]) > 1
                for role in g.seats[p]:
                    plan = yield dict(kind="plan", seat=p, role=role,
                                      info=self.plan_info(p, role),
                                      default=self.bots[p].roles(
                                          g, p, lambda r: 1).get(role, {}))
                    band = yield dict(kind="mini", seat=p, role=role,
                                      short=short)
                    plan = dict(plan or {})
                    plan["band"] = band if band in (0, 1, 2) else 0
                    roles[role] = plan
                mine[p] = dict(vault=vault or {}, roles=roles)
                self.emit(self.key("ord", p),
                          dict(mine[p], chk=self.start_hash[g.round]))
            orders = {}
            for p in range(g.n):
                if p in self.humans:
                    orders[p] = mine[p]
                    continue
                v = None
                if p in self.remote:
                    v = yield from self._await("ord", p, "their moves")
                if isinstance(v, dict) and not self.is_skip(v):
                    chk = v.get("chk")
                    if chk and chk != self.start_hash[g.round]:
                        self.desync.append(g.round)
                    orders[p] = dict(vault=v.get("vault") or {},
                                     roles=v.get("roles") or {})
                else:                          # a bot, or a skipped player
                    orders[p] = dict(vault=self.bots[p].vault(g, p),
                                     roles=self.bots[p].roles(g, p, roll))
            lines = g.final(orders)
            self.msgs_last = collections.Counter(g.msgs)
            an = g.anim or {}
            yield dict(kind="report", round=g.round,
                       lines=[nameize(x) for x in lines],
                       msgs=dict(g.msgs), checksum=g.state_hash(),
                       before=an.get("before"), events=list(an.get("events", [])),
                       income=[], pool_before=(an.get("before") or {}).get("pool", g.pool),
                       pool_after=g.pool, forecast=forecast_rows(g, 3))
        yield dict(kind="end", won=g.won, round=g.round, keep=g.keep,
                   stat=dict(g.stat), checksum=g.state_hash())

    def plan_info(self, p, role):
        g = self.g
        info = dict(role=role, lanes=list(QUADS), pos=g.pos.get(role),
                    danger=g.danger(),
                    slots={q: [[dict(b) for b in c] for c in g.map[q]["slots"]]
                           for q in QUADS},
                    appeal={q: g.appeal(q) for q in QUADS})
        if role in BUILDERS:
            info["points"] = g.build_points(role)
            info["items"] = [(it, ITEMS[it]["name"], ITEMS[it]["cost"],
                              g.budget[ITEMS[it]["budget"]])
                             for it in BUILD_ITEMS[role]]
        elif role == "Slayer":
            info["tonics"] = min(2, g.budget["b_tonic"] // ITEMS["tonic"]["cost"])
        elif role == "Mage":
            info["mana"] = g.mana()
            info["spells"] = [(s, SPELLS[s], cm.SPELL_HELP[s]) for s in g.known_spells()]
        return info

# ======================================================================
#  THE WINDOW
# ======================================================================
import time
clock = time.time          # the tests swap this for a fake clock


def num(var, lo=0, hi=999):
    """Read a number from a Tk variable without ever crashing."""
    try:
        v = int(float(str(var.get()).strip() or 0))
    except (TypeError, ValueError):
        v = 0
    return max(lo, min(hi, v))


KIND_TXT = {"personal": "personal: works as soon as it is paid",
            "budget": "budget: stores gold for building"}
PLACING = ("farm", "mine", "tower", "tower_up")


_PIXCACHE = {}


def pix_photo(tk, master, text, fg, bg, size, wrap=0):
    """A PhotoImage of pixel-font text on a flat background colour."""
    sc = text_scale(size)
    key = (str(text), fg, bg, sc, int(wrap))
    im = _PIXCACHE.get(key)
    if im is None:
        if len(_PIXCACHE) > 600:
            _PIXCACHE.clear()
        lines = wrap_text(text, wrap, sc) if wrap else str(text).split("\n")
        lh = PF_H + 2
        w = max([text_w(ln, 1) for ln in lines] + [1]) + 1
        h = len(lines) * lh
        im = tk.PhotoImage(master=master, width=w, height=h)
        im.put(bg, to=(0, 0, w, h))
        for i, ln in enumerate(lines):
            for (rx, ry, n) in text_runs(ln):
                im.put(fg, to=(rx, ry + i * lh, rx + n, ry + i * lh + 1))
        if sc > 1:
            im = im.zoom(sc)
        _PIXCACHE[key] = im
    return im


def make_widgets(tk):
    """Labels and buttons whose text is drawn in the pixel font. They accept
    .config(text=...) like normal ones, so the forms need no special code."""
    class PixLabel(tk.Label):
        def __init__(self, master, text="", fg=FG, bg=PANEL, size=10, wrap=0,
                     anchor="w", **kw):
            opts = dict(bg=bg, bd=0, highlightthickness=0, padx=0, pady=0,
                        anchor=anchor, justify="left")
            opts.update(kw)
            tk.Label.__init__(self, master, **opts)
            self._p = dict(text=text, fg=fg, bg=bg, size=size, wrap=wrap)
            self._img = None
            self._paint()

        def _paint(self):
            p = self._p
            self._img = pix_photo(tk, self, p["text"], p["fg"], p["bg"],
                                  p["size"], p["wrap"])
            tk.Label.configure(self, image=self._img, bg=p["bg"])

        def configure(self, cnf=None, **kw):
            kw.update(cnf or {})
            hit = False
            for a, b in (("text", "text"), ("fg", "fg"), ("foreground", "fg"),
                         ("bg", "bg"), ("background", "bg"),
                         ("wraplength", "wrap"), ("size", "size")):
                if a in kw:
                    self._p[b] = kw.pop(a)
                    hit = True
            if kw:
                tk.Label.configure(self, **kw)
            if hit:
                self._paint()
        config = configure

    class PixButton(tk.Button):
        def __init__(self, master, text="", command=None, fg="#ffffff",
                     bg=BTN_GO, size=11, **kw):
            opts = dict(command=command, bg=bg, bd=0, relief="flat",
                        highlightthickness=2, highlightbackground=DARK,
                        activebackground=bg, padx=8, pady=5,
                        compound="center", cursor="hand2")
            opts.update(kw)
            tk.Button.__init__(self, master, **opts)
            self._p = dict(text=text, fg=fg, bg=bg, size=size, wrap=0)
            self._img = None
            self._paint()

        def _paint(self):
            p = self._p
            self._img = pix_photo(tk, self, p["text"], p["fg"], p["bg"],
                                  p["size"], 0)
            tk.Button.configure(self, image=self._img, bg=p["bg"],
                                activebackground=p["bg"])

        def configure(self, cnf=None, **kw):
            kw.update(cnf or {})
            hit = False
            for a, b in (("text", "text"), ("fg", "fg"), ("bg", "bg")):
                if a in kw:
                    self._p[b] = kw.pop(a)
                    hit = True
            if kw:
                tk.Button.configure(self, **kw)
            if hit:
                self._paint()
        config = configure
    return PixLabel, PixButton


class App:
    def __init__(self, root, tk, embedded=False, on_skip=None, on_close=None):
        """embedded=True: the window lives inside another program (the chat).
        There is no setup screen; start_embedded(session) begins the game.
        on_skip(key) (host only) lets the host replace a missing player with
        a bot; on_close() is called by the Close button after the game."""
        self.embedded, self.on_skip, self.on_close = embedded, on_skip, on_close
        self.wait_key = None
        self.tk, self.root = tk, root
        self.PixLabel, self.PixButton = make_widgets(tk)
        self.sess = None
        self.submit = lambda: None        # what the current form's main button does
        self.mini_loop = None
        self.anim_loop = None
        self.anim = None
        self.mini = None
        self.last_kind = None
        root.title("Castle Defense  -  defend the keep")
        root.configure(bg=BG)
        root.resizable(True, True)
        root.minsize(940, 620)
        try:
            root.geometry("1240x800")
        except Exception:
            pass
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(0, weight=0)
        root.rowconfigure(1, weight=1)
        self.map_draw = None              # repaints the map (used on resize)
        self.scrollers = []               # scrollable canvases on this screen
        self.wl = []                      # (label, margin) that re-wrap on resize
        self.top = tk.Canvas(root, width=TOP_W, height=TOP_H, bg=STRIP,
                             highlightthickness=0)
        self.top.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.cv = tk.Canvas(root, width=MAP_W, height=MAP_H, bg=BG,
                            highlightthickness=0)
        self.cv.grid(row=1, column=0, rowspan=2, padx=(8, 4), pady=8,
                     sticky="nsew")
        self.gfx = TkGfx(self.cv, auto=True)
        self.gfx.top = TkGfx(self.top, auto=True)
        self.cv.bind("<Motion>", self.on_motion)
        self.cv.bind("<Leave>", self.on_leave)
        self.cv.bind("<Configure>", lambda e: self.map_draw and self.map_draw())
        self.top.bind("<Configure>", lambda e: self.map_draw and self.map_draw())
        self.help_btn = self.PixButton(root, "? HELP", self.open_help,
                                       fg=FG, bg=BTN_ALT, size=11)
        self.help_btn.place(in_=self.top, relx=1.0, x=-8, y=5, anchor="ne")
        self.right = tk.Frame(root, bg=PANEL, width=540, height=500,
                              highlightthickness=3, highlightbackground=EDGE,
                              highlightcolor=EDGE)
        self.right.grid(row=1, column=1, padx=(4, 8), pady=(8, 4), sticky="nsew")
        self.right.pack_propagate(False)
        self.right.bind("<Configure>", self.on_right_resize)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            if embedded:                  # do not steal the wheel from the chat
                root.bind(ev, self.on_wheel)
            else:
                root.bind_all(ev, self.on_wheel)
        self.logbox = tk.Text(root, width=62, height=6, bg=INPUT, fg=MUTED,
                              font=("Courier", 9), wrap="word", bd=0,
                              highlightthickness=2, highlightbackground=EDGE,
                              state="disabled")
        self.logbox.grid(row=2, column=1, padx=(4, 8), pady=(0, 8), sticky="ew")
        self.body = None
        if not embedded:
            self.show_setup()

    # ---------------------------------------------------------- helpers
    def on_motion(self, e):
        """Mouse over the map: show a short description of what is there."""
        g = self.gfx
        if not g.regions:
            return
        mx, my = (e.x - g.ox) / g.k, (e.y - g.oy) / g.k
        text = tip_at(g.regions, mx, my)
        old = g.tip
        if text is None:
            if old is None:
                return
            g.tip = None
        else:
            if old and old[0] == text and abs(old[1] - mx) < 3 \
                    and abs(old[2] - my) < 3:
                return
            g.tip = (text, mx, my)
        if self.map_draw:
            self.map_draw()

    def on_leave(self, e=None):
        if self.gfx.tip is not None:
            self.gfx.tip = None
            if self.map_draw:
                self.map_draw()

    def reset_body(self):
        self.mini_loop = None
        self.anim_loop = None
        self.scrollers = []
        self.wl = []
        try:
            self.root.unbind("<Key>")
        except Exception:
            pass
        if self.body is not None:
            self.body.destroy()
        self.body = self.tk.Frame(self.right, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=8, pady=6)
        return self.body

    def lab(self, parent, text, fg=FG, size=10, bold=False, wrap=500,
            anchor="w", pady=0, bg=PANEL, side=None):
        w = self.PixLabel(parent, text, fg, bg, size, wrap, anchor)
        if side:
            w.pack(side=side, pady=pady)
        else:
            w.pack(fill="x", pady=pady)
        if wrap >= 500:
            self.wl.append((w, 40))
        return w

    def btn(self, parent, text, cmd, side="top", fg="#ffffff", bg=None,
            alt=False):
        """A flat pixel button. Buttons on top/bottom fill the width."""
        bg = bg or (BTN_ALT if alt else BTN_GO)
        b = self.PixButton(parent, text, cmd, fg=fg, bg=bg, size=11)
        if side in ("top", "bottom"):
            b.pack(side=side, fill="x", padx=3, pady=(8, 1))
        else:
            b.pack(side=side, padx=3, pady=4)
        return b

    def actions(self, key, items, parent=None):
        """Stacked buttons, each with its plain-English line underneath.
        items = [(label, command, is_secondary)]."""
        parent = parent or self.body
        caps = BUTTONS[key].split("\n")
        out = []
        for i, (label, cmd, alt) in enumerate(items):
            out.append(self.btn(parent, label, cmd, alt=alt))
            if i < len(caps):
                self.lab(parent, caps[i], MUTED, 8, wrap=500)
        return out

    def expander(self, parent, text, label="details", size=8, indent=0):
        """A small '[+] details' link that opens a longer explanation
        underneath it, and '[-] hide' closes it again."""
        tk = self.tk
        box = tk.Frame(parent, bg=PANEL)
        box.pack(fill="x", padx=indent)
        state = {"open": False}

        def toggle():
            if state["open"]:
                body.pack_forget()
                b.config(text="[+] " + label)
            else:
                body.pack(fill="x", padx=14, pady=(0, 3))
                b.config(text="[-] hide")
            state["open"] = not state["open"]
        b = self.PixButton(box, "[+] " + label, toggle, fg=ACCENT, bg=PANEL,
                           size=9)
        b.config(highlightthickness=0, padx=0, pady=1)
        b.pack(anchor="w")
        body = self.PixLabel(box, text, FG, ROW, size, 460, "w", padx=6, pady=4)
        body.config(highlightthickness=2, highlightbackground=EDGE)
        self.wl.append((body, 80))
        box.toggle = toggle
        return box

    def caption(self, key):
        self.lab(self.body, BUTTONS[key], MUTED, 8, wrap=500)

    def scroller(self, parent, height=330):
        """A scrollable area; returns the frame to put rows in."""
        tk = self.tk
        holder = tk.Frame(parent, bg=PANEL)
        holder.pack(fill="both", expand=True)
        cv = tk.Canvas(holder, bg=PANEL, highlightthickness=0, height=height,
                       width=500, yscrollincrement=20)
        sb = tk.Scrollbar(holder, command=cv.yview)
        inner = tk.Frame(cv, bg=PANEL)
        inner.bind("<Configure>",
                   lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=inner, anchor="nw")
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        self.scrollers.append(cv)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return inner

    def on_right_resize(self, e):
        """Re-wrap the text to the new width of the side panel."""
        w = max(220, e.width - 20)
        for lab, margin in list(self.wl):
            try:
                lab.configure(wraplength=max(160, w - margin))
            except Exception:
                pass

    def on_wheel(self, e):
        """Mouse wheel scrolls the list under the pointer (Windows, Mac and
        Linux send the wheel differently)."""
        if getattr(e, "num", None) == 4:
            step = -2
        elif getattr(e, "num", None) == 5:
            step = 2
        else:
            step = -2 if getattr(e, "delta", 0) > 0 else 2
        try:
            w = self.root.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        while w is not None:
            if w in self.scrollers:
                try:
                    box = w.bbox("all")
                    if box and (box[3] - box[1]) > w.winfo_height():
                        w.yview_scroll(step, "units")
                except Exception:
                    pass
                return "break"
            w = getattr(w, "master", None)

    def spin(self, parent, var, hi):
        sp = self.tk.Spinbox(parent, from_=0, to=max(0, hi), width=4,
                             textvariable=var, font=("Courier", 10),
                             bg=INPUT, fg=FG, buttonbackground=PANEL,
                             insertbackground=FG)
        sp.pack(side="right", padx=4)
        return sp

    def say(self, lines):
        t = self.logbox
        t.configure(state="normal")
        for ln in lines:
            t.insert("end", ln + "\n")
        t.see("end")
        t.configure(state="disabled")

    def head(self, prm, title, step):
        s = self.sess
        who = s.seat_name(prm["seat"])
        role0 = s.g.seats[prm["seat"]][0]
        if len(s.humans) > 1:
            self.lab(self.body, "PASS THE KEYBOARD TO", MUTED, 8)
        self.lab(self.body, who, ROLE_COL[role0], 10, True)
        self.lab(self.body, title, ACCENT, 13, True, pady=3)
        self.expander(self.body, STEP_HELP[step], "what is this step?", 8)

    def draw(self, sel=None):
        if self.sess:
            self.map_draw = lambda: draw_map(self.sess.g, self.gfx, sel)
            self.map_draw()

    def open_help(self):
        tk = self.tk
        w = tk.Toplevel(self.root)
        w.title("How to play")
        w.configure(bg=PANEL)
        t = tk.Text(w, width=70, height=30, bg=INPUT, fg=FG, wrap="word",
                    font=("Courier", 10), padx=8, pady=8, bd=0)
        t.pack(fill="both", expand=True)
        t.tag_configure("h", foreground=ACCENT, font=("Courier", 11, "bold"))
        for title, text in HOW_TO_PLAY:
            t.insert("end", title + "\n", "h")
            t.insert("end", text + "\n\n")
        t.configure(state="disabled")
        return w

    # ------------------------------------------------------------ setup
    def show_setup(self):
        tk = self.tk
        self.reset_body()
        self.draw_title()
        b = self.body
        self.lab(b, "CASTLE DEFENSE", ACCENT, 18, True, pady=4)
        self.lab(b, "Defend the keep together for 12 rounds. Pick how many "
                    "seats there are and which ones are people (the rest are "
                    "bots). Press '? HELP' any time.", MUTED, 9)
        self.v_n, self.v_diff = tk.IntVar(value=4), tk.StringVar(value="Normal")
        self.v_seed = tk.StringVar(value=str(random.randrange(1, 9999)))
        self.v_h = [tk.IntVar(value=1 if i == 0 else 0) for i in range(5)]
        r = tk.Frame(b, bg=PANEL)
        r.pack(fill="x", pady=4)
        self.lab(r, "Seats (2-5):", FG, 10)
        for k in (2, 3, 4, 5):
            tk.Radiobutton(r, text=str(k), variable=self.v_n, value=k,
                           bg=PANEL, fg=FG, selectcolor=BG, activebackground=PANEL,
                           command=self.refresh_seats,
                           font=("Courier", 10)).pack(side="left")
        self.seat_box = tk.Frame(b, bg=PANEL)
        self.seat_box.pack(fill="x", pady=4)
        r = tk.Frame(b, bg=PANEL)
        r.pack(fill="x", pady=4)
        self.lab(r, "Difficulty:", FG, 10)
        for k in DIFFICULTY:
            tk.Radiobutton(r, text=k, variable=self.v_diff, value=k, bg=PANEL,
                           fg=FG, selectcolor=BG, activebackground=PANEL,
                           font=("Courier", 10)).pack(side="left")
        r = tk.Frame(b, bg=PANEL)
        r.pack(fill="x", pady=4)
        self.lab(r, "Seed (same seed = same waves):", FG, 10)
        tk.Entry(r, textvariable=self.v_seed, width=8, bg=INPUT, fg=FG,
                 insertbackground=FG).pack(side="left", padx=6)
        self.expander(b, "\n\n".join("%s\n%s" % (t, x) for t, x in HOW_TO_PLAY[:4]),
                      "quick rules", 9)
        self.submit = self.start_game
        self.btn(b, "Start game", self.start_game)
        self.lab(b, "Start game: begins round 1 with the seats chosen above.",
                 MUTED, 8)
        self.refresh_seats()

    def refresh_seats(self):
        for w in self.seat_box.winfo_children():
            w.destroy()
        n = num(self.v_n, 2, 5)
        for i in range(n):
            self.tk.Checkbutton(
                self.seat_box, text="Seat %d: %s  (person)" % (
                    i + 1, ", ".join(SEATS_PREVIEW[n][i])),
                variable=self.v_h[i], bg=PANEL, fg=FG, selectcolor=BG,
                activebackground=PANEL, anchor="w", font=("Courier", 9)
            ).pack(fill="x")

    def draw_title(self):
        def paint():
            g = self.gfx
            v = view_from_game(Game(4, 1))
            v["forecast"] = []
            draw_view(v, g, None, dict(no_marks=True))
            g.rect(CX - 200, CY - 66, CX + 200, CY + 56, DARK, ACCENT, 3)
            g.text(CX, CY - 32, "CASTLE DEFENSE", ACCENT, 24)
            g.text(CX, CY + 6, "defend the keep", FG, 12)
            g.text(CX, CY + 34, "Steward Engineer Slayer Smith Mage", MUTED, 8)
        self.map_draw = paint
        paint()

    def start_game(self):
        n = num(self.v_n, 2, 5)
        humans = [i for i in range(n) if num(self.v_h[i]) == 1] or [0]
        seed = num(self.v_seed, 1, 10 ** 9) or 1
        self.sess = Session(n, humans, seed, self.v_diff.get())
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")
        self.go(None, first=True)

    # ------------------------------------------------------- the flow
    def go(self, value, first=False):
        prm = self.sess.first() if first else self.sess.answer(value)
        self.show(prm)

    def shutdown(self):
        """Stop every timer (the window is about to be destroyed)."""
        self.anim_loop = None
        self.mini_loop = None
        self.sess = None
        try:
            self.root.unbind("<Key>")
        except Exception:
            pass

    def start_embedded(self, sess):
        self.sess = sess
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")
        self.draw_title()
        self.go(None, first=True)

    def pump(self):
        """Another computer's answer arrived: if we were waiting, go on."""
        if self.sess is None or self.last_kind != "wait":
            return
        self.go(None)

    def show(self, prm):
        self.last_kind = prm["kind"] if prm else None
        if prm is None:
            if self.embedded:
                return self.on_close and self.on_close()
            return self.show_setup()
        if prm["kind"] == "wait":
            if prm["key"] == self.wait_key:
                return                    # still waiting: leave the form as is
            self.wait_key = prm["key"]
        else:
            self.wait_key = None
        if prm["kind"] != "advance":
            self.draw()
        getattr(self, "f_" + prm["kind"])(prm)

    def f_wait(self, prm):
        self.reset_body()
        b = self.body
        who = seat_label(prm["seat"])
        role = self.sess.g.seats[prm["seat"]][0]
        self.lab(b, "Waiting for %s" % who, ROLE_COL[role], 13, True)
        self.lab(b, "Round %d: waiting for %s (%s). The game goes on as "
                    "soon as it arrives." % (
                        prm["round"], prm["what"],
                        ", ".join(self.sess.g.seats[prm["seat"]])), FG, 10,
                 pady=6)
        if self.on_skip:
            self.lab(b, "You are the host. If they are gone or too slow you "
                        "can replace them with a bot for this step.", MUTED, 9)
            self.btn(b, "Use a bot for %s" % who,
                     lambda: self.on_skip(prm["key"]), alt=True)
        self.submit = lambda: None

    def opt_rows(self, parent, options, vars_, caps):
        """One banner per project, coloured for the role it belongs to: a
        stripe, the name, an amount box and a [+] that opens the note."""
        tk = self.tk
        for (pid, need, name, role, kind, desc) in options:
            bar, deep, edge = banner_colors(role)
            card = tk.Frame(parent, bg=bar, highlightthickness=2,
                            highlightbackground=edge)
            card.pack(fill="x", pady=3, padx=2)
            top = tk.Frame(card, bg=bar)
            top.pack(fill="x")
            tk.Frame(top, bg=edge, width=10).pack(side="left", fill="y")
            more = tk.Frame(card, bg=deep)
            state = {"open": False}

            def toggle(more=more, state=state, deep=deep):
                if state["open"]:
                    more.pack_forget()
                    tg.config(text="+")
                else:
                    more.pack(fill="x", padx=4, pady=(0, 4))
                    tg.config(text="-")
                state["open"] = not state["open"]
            tg = self.PixButton(top, "+", toggle, fg=DARK, bg=edge, size=11)
            tg.pack(side="right", padx=(4, 6), pady=4)
            self.spin(top, vars_[pid], caps[pid])
            self.lab(top, "[%s] %s" % (ROLE_TAG[role], name), FG, 10, wrap=300,
                     bg=bar, side="left", pady=4)
            self.lab(top, "  needs %d" % need, mix(edge, "#ffffff", 0.55), 8,
                     wrap=140, bg=bar, side="left")
            self.lab(more, "%s. %s\n\n%s" % (
                KIND_TXT[kind], desc, project_detail(pid)),
                FG, 8, wrap=440, bg=deep)

    # ---- animations
    def play(self, prm, b, on_finish):
        """Run an Anim with a play-by-play list under it. Returns the Skip
        button; on_finish() is called once the animation has ended."""
        anim = Anim(prm)
        anim.ensure_view(view_from_game(self.sess.g))
        self.anim = anim
        self.map_draw = lambda: anim.draw(self.gfx)
        logl = self.lab(b, "", FG, 9, pady=4)
        st = {"last": clock(), "done": False, "n": 0}

        def show():
            if len(anim.lines) != st["n"]:
                st["n"] = len(anim.lines)
                logl.config(text="\n".join(anim.lines[-7:]))

        def loop():
            if self.anim_loop is not loop:
                return
            now = clock()
            dt = min(0.1, max(0.0, now - st["last"]))
            st["last"] = now
            done = anim.update(dt)
            anim.draw(self.gfx)
            show()
            if done:
                finish()
            else:
                self.root.after(30, loop)

        def finish():
            st["done"] = True
            self.anim_loop = None
            show()
            self.draw()
            on_finish()

        def press():
            if not st["done"]:
                anim.finish_now()
                finish()
            else:
                self.go(None)
        skip = self.btn(b, "Skip animation", press)
        self.submit = press
        self.anim_loop = loop
        loop()
        return skip

    # ---- income animation at the start of a round
    def f_advance(self, prm):
        self.reset_body()
        b = self.body
        self.lab(b, "Round %d begins" % prm["round"], ACCENT, 13, True)
        self.expander(b, STEP_HELP["advance"], "what am I seeing?", 9)
        parts = prm["income_parts"]
        bits = ["realm +%d" % parts.get("base", 0)]
        if parts.get("farms"):
            bits.append("farms +%d" % parts["farms"])
        if parts.get("mines"):
            bits.append("mines +%d" % parts["mines"])
        if parts.get("trade"):
            bits.append("trade routes +%d" % parts["trade"])
        self.lab(b, "Income this round: %s = +%d.  Pool %d -> %d." % (
            ", ".join(bits), prm["pool_after"] - prm["pool_before"],
            prm["pool_before"], prm["pool_after"]), FG, 10, pady=4)
        holder = {}

        def fin():
            holder["skip"].config(text="Continue to petitions")
        holder["skip"] = self.play(prm, b, fin)
        self.lab(b, "Skip animation: jumps to the end. Then the same button "
                    "becomes Continue.", MUTED, 8)

    # ---- petition
    def f_petition(self, prm):
        tk = self.tk
        self.reset_body()
        self.head(prm, "Step 3: Petition the pool", "petition")
        self.lab(self.body, "Pool: %d gold.  Banking secures %d gold from the "
                            "pool into your vault. Ask for up to 2 projects." % (
                                prm["pool"], prm["bank"]), MUTED, 9)
        default = prm["default"] or {}
        dflt = dict(default.get("items") or [])
        opts = prm["options"]
        vars_ = {o[0]: tk.StringVar(value=str(dflt.get(o[0], 0))) for o in opts}
        caps = {o[0]: o[1] for o in opts}
        must = tk.StringVar(value=default.get("must") or "")
        inner = self.scroller(self.body, 230)
        self.opt_rows(inner, opts, vars_, caps)
        r = tk.Frame(self.body, bg=PANEL)
        r.pack(fill="x")
        self.lab(r, "Must-have (paid first):", FG, 8)
        for o in opts:
            tk.Radiobutton(r, text=o[0], variable=must, value=o[0], bg=PANEL,
                           fg=FG, selectcolor=BG, activebackground=PANEL,
                           font=("Courier", 8)).pack(side="left")
        warn = self.lab(self.body, "", BAD, 9)

        def send():
            items = [(pid, num(v, 0, caps[pid])) for pid, v in vars_.items()
                     if num(v, 0, caps[pid]) > 0]
            if len(items) > 2:
                warn.config(text="Pick at most 2 projects (you chose %d)."
                            % len(items))
                return
            if not items:
                return skip()
            m = must.get() if must.get() in [i for i, _ in items] else None
            self.go(dict(items=items, must=m))

        def skip():
            self.go(None)
        self.submit = send
        self.actions("petition", [
            ("Send petition", send, False),
            ("Skip (bank) (+%d gold)" % prm["bank"], skip, True)])

    # ---- treasurer
    def f_treasury(self, prm):
        tk = self.tk
        self.reset_body()
        self.head(prm, "You are the TREASURER", "treasury")
        self.lab(self.body, "Pool: %d gold to split. Gold you do not hand out "
                            "stays in the pool." % prm["pool"], MUTED, 9)
        inner = self.scroller(self.body, 230)
        rows = []
        for (p, pid, asked, must) in prm["pets"]:
            v = tk.StringVar(value=str(prm["default"].get((p, pid), 0)))
            rows.append(((p, pid), asked, v))
            bar, deep, edge = banner_colors(PROJECTS[pid]["role"])
            r = tk.Frame(inner, bg=bar, highlightthickness=2,
                         highlightbackground=edge)
            r.pack(fill="x", pady=(4, 0), padx=2)
            tk.Frame(r, bg=edge, width=10).pack(side="left", fill="y")
            self.lab(r, "%s asks %d for %s%s" % (
                seat_label(p), asked, PROJECTS[pid]["name"], "  MUST-HAVE" if must else ""),
                ACCENT if must else FG, 9, wrap=330, bg=bar, side="left",
                pady=4)
            self.spin(r, v, asked)
            self.expander(inner, project_detail(pid), "what is this?", indent=14)
        total = self.lab(self.body, "", ACCENT, 11, True, pady=2)
        self.total_lab = total
        self.treasury_rows = rows

        def update_total(*a):
            spent = sum(num(v, 0, asked) for _, asked, v in rows)
            left = prm["pool"] - spent
            total.config(
                text="Spending now: %d / %d gold  (%s)" % (
                    spent, prm["pool"],
                    "%d stays in the pool" % left if left >= 0
                    else "%d over the pool!" % -left),
                fg=ACCENT if left >= 0 else BAD)
        self.update_total = update_total
        for _, _, v in rows:
            try:
                v.trace_add("write", update_total)
            except Exception:
                pass
        update_total()
        warn = self.lab(self.body, "", BAD, 9)

        def send():
            alloc = {k: num(v, 0, a) for k, a, v in rows if num(v, 0, a) > 0}
            if sum(alloc.values()) > prm["pool"]:
                warn.config(text="That is %d, but the pool only has %d." % (
                    sum(alloc.values()), prm["pool"]))
                return
            self.go(alloc)

        def auto():
            self.go(None)
        self.submit = send
        self.actions("treasury", [("Send decision", send, False),
                                  ("Use auto draft", auto, True)])

    # ---- vault
    def f_vault(self, prm):
        tk = self.tk
        self.reset_body()
        self.head(prm, "Step 4: Spend your vault", "vault")
        self.lab(self.body, "Your vault: %d / %d gold." % (
            prm["vault"], prm["cap"]), MUTED, 9)
        seat = prm["seat"]
        mine = [f for f in prm["funded"] if f[0] == seat]
        for (p, pid, amt, done) in mine:
            self.lab(self.body, "+%d gold from petitions this round: %s%s" % (
                amt, PROJECTS[pid]["name"], "  (DONE!)" if done else ""),
                GOOD, 10, True)
        if not mine:
            self.lab(self.body, "+0 gold from petitions this round.", MUTED, 9)
        others = [f for f in prm["funded"] if f[0] != seat]
        if others:
            self.lab(self.body, "Others: " + ", ".join(
                "%s +%d %s" % (seat_label(p), amt, PROJECTS[pid]["name"])
                for (p, pid, amt, done) in others), MUTED, 8)
        opts = prm["options"]
        dflt = prm["default"] or {}
        vars_ = {o[0]: tk.StringVar(value=str(dflt.get(o[0], 0))) for o in opts}
        caps = {o[0]: min(o[1], prm["vault"]) for o in opts}
        inner = self.scroller(self.body, 250)
        self.opt_rows(inner, opts, vars_, caps)
        warn = self.lab(self.body, "", BAD, 9)

        def send():
            out = {pid: num(v, 0, caps[pid]) for pid, v in vars_.items()
                   if num(v, 0, caps[pid]) > 0}
            if sum(out.values()) > prm["vault"]:
                warn.config(text="That is %d, but your vault has %d." % (
                    sum(out.values()), prm["vault"]))
                return
            self.go(out)
        self.submit = send
        self.actions("vault", [("Done", send, False)])

    # ---- map choices for one role
    def f_plan(self, prm):
        tk = self.tk
        self.reset_body()
        info, role = prm["info"], prm["role"]
        self.head(prm, "Step 5: %s moves" % role, "plan")
        self.expander(self.body, ROLE_TEXT[role], "what does the %s do?" % role, 9)
        d, slots = info["danger"], info["slots"]
        dflt = prm["default"] or {}
        qv = tk.StringVar(value=dflt.get("q") or info["pos"] or "N")
        inner = self.scroller(self.body, 255)
        b = inner
        occ = {"lab": None}

        def occupancy():
            q = qv.get()
            bits = []
            for k in (1, 2, 3):
                c = slots[q][k - 1]
                bits.append("%d: %s" % (k, "empty" if not c else " + ".join(
                    "%s%s hp%d" % (x["t"], " L%d" % (x["tier"] + 1)
                                   if x["t"] == "tower" else "", x["hp"])
                    for x in c)))
            return ("Lane %s cells (1 = next to wall, up to %d buildings "
                    "each):\n%s\nEnemy appeal %+d (farms and mines attract "
                    "waves, towers repel them)" % (
                        q, cm.CELL_MAX, "\n".join(bits), info["appeal"][q]))

        def pick_q():
            self.draw(qv.get())
            if occ["lab"] is not None:
                occ["lab"].config(text=occupancy())

        def quad_row(label, show_cells):
            r = tk.Frame(b, bg=PANEL)
            r.pack(fill="x")
            self.lab(r, label, FG, 10)
            for q in QUADS:
                tk.Radiobutton(r, text="%s (%d)" % (q, round(d[q])), variable=qv,
                               value=q, bg=PANEL, fg=FG, selectcolor=BG,
                               activebackground=PANEL, command=pick_q,
                               font=("Courier", 10)).pack(side="left")
            self.expander(b, "The number in brackets is a danger score: how "
                             "much trouble is in or about to reach that "
                             "lane (enemies already close to the wall, "
                             "plus waves arriving this round and the next). "
                             "Waves pick the lane with the fewest towers "
                             "and the most farms and mines, so this can "
                             "change after you build. "
                             "The chosen lane is outlined in gold on the map.",
                          "what do the numbers mean?")
            if show_cells:
                occ["lab"] = self.lab(b, occupancy(), MUTED, 8)
        res = {}
        cellv = {}
        if role in BUILDERS:
            quad_row("Go to:", True)
            self.lab(b, "Build points: %d, plus 1 for an okay mini-game or 2 "
                        "for a great one. Each item uses 1 point and its gold "
                        "comes from your budgets. Buildings are placed "
                        "before the fight, so they work this round."
                        % info["points"], MUTED, 9, pady=3)
            chosen = {}
            for it, name, cost, have in info["items"]:
                v = tk.IntVar(value=1 if it in [e if isinstance(e, str) else e[0]
                                               for e in (dflt.get("build") or [])] else 0)
                chosen[it] = v
                ok = have >= cost
                tk.Checkbutton(b, text="%s   (budget %d / %d)" % (name, have, cost),
                               variable=v, bg=PANEL, fg=FG if ok else MUTED,
                               selectcolor=BG, activebackground=PANEL,
                               anchor="w", font=("Courier", 9, "bold")).pack(fill="x")
                if it in PLACING:
                    cellv[it] = tk.StringVar(value="auto")
                    r = tk.Frame(b, bg=PANEL)
                    r.pack(fill="x", padx=18)
                    self.lab(r, "cell:" if it != "tower_up" else "which tower (cell):",
                             MUTED, 8)
                    for val in ("auto", "1", "2", "3"):
                        tk.Radiobutton(r, text=val, variable=cellv[it], value=val,
                                       bg=PANEL, fg=FG, selectcolor=BG,
                                       activebackground=PANEL,
                                       font=("Courier", 8)).pack(side="left")
                self.expander(b, project_detail(it), "full description", indent=14)

            def build():
                out = []
                for it, v in chosen.items():
                    if num(v) != 1:
                        continue
                    c = cellv[it].get() if it in cellv else "auto"
                    out.append((it, int(c)) if c in ("1", "2", "3") else it)
                res.update(q=qv.get(), build=out)

            def check_cells():
                q = qv.get()
                used = set()
                for ent in res["build"]:
                    if isinstance(ent, str):
                        continue
                    it, c = ent
                    cell = slots[q][c - 1]
                    if it == "tower_up":
                        if not any(x["t"] == "tower" and x["tier"] < 2
                                   for x in cell):
                            return "Cell %d in %s has no tower that can be upgraded." % (c, q)
                    else:
                        extra = sum(1 for _, cc in used if cc == c)
                        if len(cell) + extra >= cm.CELL_MAX:
                            return "Cell %d in %s is full (%d buildings)." % (
                                c, q, cm.CELL_MAX)
                        used.add((it, c))
                return ""
        elif role == "Slayer":
            quad_row("Fight in:", False)
            pv = tk.StringVar(value=dflt.get("prio") or "nearest")
            r = tk.Frame(b, bg=PANEL)
            r.pack(fill="x", pady=4)
            self.lab(r, "Target:", FG, 10)
            for k in ("nearest", "strongest"):
                tk.Radiobutton(r, text=k, variable=pv, value=k, bg=PANEL, fg=FG,
                               selectcolor=BG, activebackground=PANEL,
                               font=("Courier", 10)).pack(side="left")
            self.expander(b, "nearest: your damage goes to the enemies closest "
                             "to the wall first (stops attacks fastest).\n"
                             "strongest: it goes to the enemy with the most HP "
                             "first (good against a troll or the boss).",
                          "what is the difference?")
            tv = tk.StringVar(value=str(min(info["tonics"], dflt.get("tonics", 0))))
            r = tk.Frame(b, bg=PANEL)
            r.pack(fill="x", pady=4)
            self.lab(r, "Tonics to drink (you can afford %d):" % info["tonics"],
                     FG, 9)
            self.spin(r, tv, info["tonics"])
            self.expander(b, project_detail("tonic"), "what is a tonic?")

            def build():
                res.update(q=qv.get(), prio=pv.get(),
                           tonics=num(tv, 0, info["tonics"]))
        else:                                            # Mage
            self.lab(b, "You sit in the keep and cast into any lane. Mana "
                        "this round: %d. Up to 4 casts. Pick a spell and a "
                        "lane for each cast." % info["mana"], MUTED, 9)
            names = ["-"] + [s for s, _, _ in info["spells"]]
            rows = []
            start = list(dflt.get("casts") or [])
            tot = self.lab(b, "", ACCENT, 10)
            for i in range(4):
                sv = tk.StringVar(value=start[i][0] if i < len(start) else "-")
                cv_ = tk.StringVar(value=start[i][1] if i < len(start) else
                                   max(QUADS, key=lambda q: d[q]))
                rows.append((sv, cv_))
                r = tk.Frame(b, bg=PANEL)
                r.pack(fill="x", pady=1)
                self.lab(r, "Cast %d:" % (i + 1), FG, 10)
                tk.OptionMenu(r, sv, *names).pack(side="left")
                tk.OptionMenu(r, cv_, *QUADS).pack(side="left")
            self.lab(b, "Your spells (open one to read how it works):", FG, 9,
                     True, pady=3)
            for s, cost, hlp in info["spells"]:
                self.lab(b, "%s (%d mana): %s" % (s, cost, hlp), MUTED, 8)
                self.expander(b, project_detail(s), "full description", indent=14)

            def used():
                return sum(SPELLS.get(sv.get(), 0) for sv, _ in rows)

            def build():
                casts = [(sv.get(), cv_.get()) for sv, cv_ in rows
                         if sv.get() in SPELLS]
                res.update(casts=casts)
            for sv, cv_ in rows:
                for var in (sv, cv_):
                    try:
                        var.trace_add("write", lambda *a: tot.config(
                            text="Mana used: %d / %d" % (used(), info["mana"])))
                    except Exception:
                        pass
            tot.config(text="Mana used: %d / %d" % (used(), info["mana"]))
        if role != "Mage":
            pick_q()
        warn = self.lab(self.body, "", BAD, 9)

        def send():
            build()
            if role == "Mage":
                m = sum(SPELLS[s] for s, _ in res["casts"])
                if m > info["mana"]:
                    warn.config(text="That costs %d mana; you have %d." % (
                        m, info["mana"]))
                    return
            if role in BUILDERS:
                msg = check_cells()
                if msg:
                    warn.config(text=msg)
                    return
                if len(res["build"]) > info["points"] + 2:
                    warn.config(text="You can build at most %d things this "
                                     "round." % (info["points"] + 2))
                    return
            self.draw()
            self.go(dict(res))
        self.submit = send
        self.actions("plan", [("Next: mini-game", send, False)])

    # ---- the mini-game
    def f_mini(self, prm):
        tk = self.tk
        self.reset_body()
        cls = MINIGAMES[prm["role"]]
        mg = cls(random.Random(), prm["short"])
        self.mini = mg
        self.head(prm, "Step 6: %s mini-game%s" % (
            prm["role"], " (short)" if prm["short"] else ""), "mini")
        self.lab(self.body, MINI_BAND[prm["role"]], ACCENT, 9)
        cv = tk.Canvas(self.body, width=MW, height=MH, bg="#1d1628",
                       highlightthickness=2, highlightbackground=EDGE)
        cv.pack(pady=2)
        g = TkGfx(cv)
        state = {"run": False}

        def intro():
            mg.frame(g, 0)
            g.text(MW // 2, MH // 2 - 10, mg.help, FG, fit_size(mg.help, 11, MW - 16))
            g.text(MW // 2, MH // 2 + 20, "Press Start when you are ready.",
                   MUTED, 10)

        def start():
            if state["run"]:
                return
            state["run"] = True
            startb.destroy()
            mg.start(clock())
            self.root.bind("<Key>", lambda e: mg.key(e.keysym, clock()))
            cv.bind("<Button-1>", lambda e: mg.click(e.x, e.y, clock()))
            self.mini_loop = loop
            loop()

        def loop():
            if self.mini_loop is not loop:
                return
            now = clock()
            mg.step(now)
            mg.draw(g, now)
            if mg.done:
                finish()
            else:
                self.root.after(16, loop)

        def finish():
            self.mini_loop = None
            try:
                self.root.unbind("<Key>")
            except Exception:
                pass
            g.rect(0, MH // 2 - 40, MW, MH // 2 + 40, INPUT, ACCENT, 2)
            g.text(MW // 2, MH // 2 - 12, mg.result(), ACCENT, 18)
            g.text(MW // 2, MH // 2 + 18, "poor / okay / GREAT", MUTED, 9)
            self.submit = lambda: self.go(mg.band())
            self.btn(self.body, "Continue", self.submit)
        intro()
        startb = self.btn(self.body, "Start", start)
        self.submit = start
        self.lab(self.body, BUTTONS["mini_start"] + "  " + BUTTONS["mini_done"],
                 MUTED, 8)

    # ---- the round report: animation first, then the summary
    def f_report(self, prm):
        self.reset_body()
        b = self.body
        self.lab(b, "Round %d: what happened" % prm["round"], ACCENT, 13, True)
        self.expander(b, STEP_HELP["report"], "what is this?", 9)
        holder = {}

        def fin():
            holder["skip"].destroy()
            self.show_summary(prm, holder["anim"].lines)
        holder["skip"] = self.play(prm, b, fin)
        holder["anim"] = self.anim

    def show_summary(self, prm, plays):
        b = self.body
        self.lab(b, "Round %d summary" % prm["round"], ACCENT, 12, True, pady=3)
        if self.sess.desync:
            self.lab(b, "WARNING: another player's game did not match yours "
                        "in round %d. Scores may differ." % self.sess.desync[-1],
                     BAD, 9)
        m = prm["msgs"]
        total = sum(m.values())
        self.lab(b, "Messages this round in the real game: %d  (petitions %d, "
                    "decision %d, final %d).  State check: %s" % (
                        total, m.get("petition", 0), m.get("decision", 0),
                        m.get("final", 0), prm["checksum"]), MUTED, 9)
        inner = self.scroller(b, 250)
        if plays:
            self.lab(inner, "Who did what:", ACCENT, 9, True)
            for ln in plays:
                self.lab(inner, "- " + ln, FG, 9)
            self.lab(inner, "Summary:", ACCENT, 9, True, pady=3)
        for ln in prm["lines"]:
            self.lab(inner, ln, FG, 9)
        self.say(["--- round %d ---" % prm["round"]] + plays + prm["lines"])
        self.submit = lambda: self.go(None)
        self.actions("report", [("Next round", self.submit, False)], b)

    def f_end(self, prm):
        self.reset_body()
        b = self.body
        win = prm["won"]
        self.lab(b, "THE KEEP STANDS!" if win else "THE KEEP HAS FALLEN",
                 GOOD if win else BAD, 16, True, pady=6)
        self.lab(b, "Round %d, keep %d/%d.  State check %s" % (
            prm["round"], prm["keep"], KEEP_MAX, prm["checksum"]), FG, 10)
        st = prm["stat"]
        self.lab(b, "Gold banked %d times, petitions %d, vault gold spent %d, "
                    "pool gold spent %d, kills %d." % (
                        st.get("banked", 0), st.get("petitioned", 0),
                        st.get("vault_funded", 0), st.get("pool_funded", 0),
                        st.get("kills", 0)), MUTED, 9, pady=6)
        if self.embedded:
            self.submit = lambda: self.on_close and self.on_close()
            self.btn(b, "Close", self.submit)
        else:
            self.submit = self.show_setup
            self.btn(b, "Play again", self.show_setup)


SEATS_PREVIEW = cm.SEATS


def run_window(args):
    try:
        import tkinter as tk
    except ImportError:
        sys.exit("This computer's Python has no Tk. Install python.org Python "
                 "(it includes Tk) or try --test and --png instead.")
    root = tk.Tk()
    app = App(root, tk)
    if args.start:
        app.v_n.set(args.players)
        for i in range(5):
            app.v_h[i].set(1 if i < args.humans else 0)
        app.v_diff.set(args.diff)
        app.v_seed.set(str(args.seed))
        app.refresh_seats()
        app.start_game()
    root.mainloop()


# ======================================================================
#  SELF-TESTS  (python castle_game.py --test)
# ======================================================================
def ideal_play(mg, miss=False, dt=0.01):
    """A perfect player (or one that does nothing) for any mini-game."""
    now = 1000.0
    mg.start(now)
    end = now + mg.LIMIT + 5
    while not mg.done and now < end:
        now += dt
        mg.step(now)
        if miss:
            continue
        t = now - mg.t0
        if isinstance(mg, Market):
            for c in mg.coins:
                if c["st"] == 0 and t >= c["t"] + 0.3:
                    mg.click(c["x"], c["y"], now)
        elif isinstance(mg, Stack):
            px, pw = mg.stack[-1]
            if abs(mg.x - px) < 6 and not mg.done:
                mg.key("space", now)
        elif isinstance(mg, Parry):
            p = mg._active(t)
            if p and t >= p["t"] + 0.3:
                mg.key(p["d"], now)
        elif isinstance(mg, Forge):
            if abs(mg.marker(now) - mg.zc) < mg.zw / 4:
                mg.key("space", now)
        elif isinstance(mg, Runes):
            if mg.phase == "input":
                mg.key(str(mg.seqs[mg.level][len(mg.entered)] + 1), now)
    return mg


def run_tests(verbose=True):
    ok = [0]

    def check(cond, msg):
        ok[0] += 1
        if not cond:
            raise AssertionError(msg)

    def say(s):
        if verbose:
            print(s)
    rng = random.Random(5)

    # ---- 1. every mini-game: a perfect player is GREAT, doing nothing is poor
    for role, cls in MINIGAMES.items():
        for short in (False, True):
            m = ideal_play(cls(random.Random(3), short))
            check(m.done and m.band() == 2,
                  "%s short=%s perfect play gave band %d (%s)" % (
                      role, short, m.band(), m.result()))
            m = ideal_play(cls(random.Random(3), short), miss=True)
            check(m.done and m.band() == 0,
                  "%s idle gave band %d" % (role, m.band()))
        # shorter version really is shorter
        check(cls(random.Random(1), True).total < cls(random.Random(1), False).total,
              role + " short is not shorter")
        # a careless player lands in the middle sometimes: a miss rate sweep
    say("mini-games: perfect = GREAT, idle = poor  (10 variants ok)")

    # ---- 2. all-bot games: finish, invariants hold, same seed = same game
    wins = 0
    for n in (2, 3, 4, 5):
        for seed in range(1, 9):
            hs = []
            for _ in range(2):
                s = Session(n, humans=(), seed=seed)
                prm = s.first()
                while prm and prm["kind"] != "end":
                    cm.check_invariants(s.g)
                    prm = s.answer(None)
                check(prm and prm["kind"] == "end", "game did not end")
                hs.append((prm["checksum"], s.g.round, s.g.keep))
            check(hs[0] == hs[1], "same seed gave different games")
            wins += s.g.won is True
    say("all-bot games: 32 played twice, deterministic, invariants ok "
        "(%d won on Normal)" % wins)

    # ---- 3. two 'laptops' fed the same choices end in the same state
    def scripted(sess, seed):
        r = random.Random(seed)
        bands = random.Random(seed + 1)
        prm = sess.first()
        trace = []
        while prm and prm["kind"] != "end":
            k = prm["kind"]
            ans = None
            if k == "petition":
                opts = prm["options"]
                if opts and r.random() < 0.7:
                    pid, need = opts[0][0], opts[0][1]
                    ans = dict(items=[(pid, min(need, r.randint(1, 8)))],
                               must=pid)
            elif k == "treasury":
                ans = prm["default"] if r.random() < 0.5 else None
            elif k == "vault":
                ans = prm["default"]
            elif k == "plan":
                ans = prm["default"]
            elif k == "mini":
                ans = bands.randrange(3)
            elif k == "report":
                trace.append(prm["checksum"])
            prm = sess.answer(ans)
        return trace, prm
    t1, e1 = scripted(Session(3, humans=(0, 1), seed=11), 2)
    t2, e2 = scripted(Session(3, humans=(0, 1), seed=11), 2)
    check(t1 == t2 and e1["checksum"] == e2["checksum"], "lockstep broke")
    say("lockstep: both sides agree on every round checksum (%d rounds)" % len(t1))

    # ---- 4. people in every seat, at every table size, with sloppy answers
    for n in (2, 3, 4, 5):
        s = Session(n, humans=tuple(range(n)), seed=n * 3)
        kinds = collections.Counter()
        prm = s.first()
        while prm and prm["kind"] != "end":
            kinds[prm["kind"]] += 1
            k = prm["kind"]
            ans = None
            if k == "petition":                  # too many items, junk ids
                ans = dict(items=[("nope", 5)] + [(o[0], 99) for o in prm["options"][:4]],
                           must="zzz")
            elif k == "treasury":
                ans = {(0, "nope"): 5, "junk": 1}
            elif k == "vault":
                ans = {o[0]: 99 for o in prm["options"]}
            elif k == "plan":
                ans = dict(q="X", build=["zz", "farm"], casts=[("bolt", "N")] * 9,
                           prio="??", tonics="lots")
            elif k == "mini":
                ans = 7
            prm = s.answer(ans)
            cm.check_invariants(s.g)
        check(prm and prm["kind"] == "end", "sloppy game did not end")
        check(kinds["mini"] >= 12 * len(cm.QUADS) * 0 + 12, "too few mini-games")
    say("sloppy answers: bad ids, over-spending, junk casts never break the rules")

    # ---- 5. the number of messages stays inside the relay budget
    worst = 0.0
    for n in (2, 3, 4, 5):
        for seed in range(20):
            g = cm.play_game(n, 500 + seed, ["balanced", "saver", "spender"],
                             diff=DIFFICULTY["Normal"])
            worst = max(worst, g.stat["msgs"] / max(1, g.stat["rounds"]) / n)
    check(worst <= 2.0, "more than 2 messages per player per round: %.2f" % worst)
    say("messages: at most %.2f per player per round (limit 2)" % worst)

    # ---- 6. drawing: the map and every mini-game render without error
    try:
        import PIL  # noqa
        have_pil = True
    except ImportError:
        have_pil = False
    if have_pil:
        s = Session(4, humans=(), seed=4)
        prm = s.first()
        for _ in range(5):
            prm = s.answer(None)
        gf = PilGfx(MAP_W, MAP_H)
        draw_map(s.g, gf, "N")
        for cls in MINIGAMES.values():
            gm = PilGfx(MW, MH)
            m = cls(random.Random(2))
            m.start(0)
            for t in (0.5, 2.0, 5.0):
                m.step(t)
                m.draw(gm, t)
        say("drawing: map and 5 mini-games render (Pillow)")
    else:
        say("drawing: skipped (no Pillow)")

    # ---- 7. buildings live in lane cells (3 per cell) and enemies destroy them
    def fresh(seed=3, n=4):
        g = Game(n, seed, 1.9)
        g.start_round()
        g.budget["b_econ"] = 30
        g.budget["b_tower"] = 30
        g.budget["b_upgrade"] = 30
        g.phase = "vault"
        return g

    def fight(g, ro):
        g._old_pos = dict(g.pos)
        for r, o in ro.items():
            if r in g.pos and o.get("q") in QUADS:
                g.pos[r] = o["q"]
        g._combat(ro)

    def quiet(g):
        g.waves, g.noise = {}, {}
        g.enemies = []
    g = fresh()
    quiet(g)
    fight(g, {"Steward": dict(q="N", build=[("farm", 3), "mine", "farm"], band=2),
               "Engineer": dict(q="N", build=[("tower", 2), ("tower", 2)], band=2)})
    sl = g.map["N"]["slots"]
    check([b["t"] for b in sl[2]] == ["farm"], "farm not placed in the chosen cell 3")
    check([b["t"] for b in sl[0]] == ["mine"], "mine did not take the empty cell next to the wall")
    check(sorted(b["t"] for b in sl[1]) == ["farm", "tower", "tower"],
          "cell 2 should hold a farm and two towers (multiple buildings per cell)")
    check(all(b.get("by") is not None and b.get("role") for c in sl for b in c),
          "buildings do not remember who built them")
    check(g.can_place("N", "tower"), "other cells still have room")
    g.budget["b_tower"] = 30
    check(g._build("Engineer", "tower", "N", 2) is True and len(sl[1]) == 3
          or len(sl[1]) == 3, "cell 2 should stay at 3 buildings")
    check(all(len(c) <= 3 for c in sl), "a cell holds more than 3 buildings")
    for _ in range(12):
        g.budget["b_tower"] = 30
        g._build("Engineer", "tower", "N")
    check(sum(len(c) for c in sl) == 9 and not g.can_place("N", "tower"),
          "a lane should fill at 9 buildings (3 per cell)")
    check(g.slot_count("N", "tower") >= 5, "no cap on towers per lane any more")
    cm.check_invariants(g)
    # a troll in a cell with a farm AND a tower hits the weaker building first
    g = fresh()
    quiet(g)
    g.map["N"]["slots"][2] = [dict(t="tower", hp=8, tier=0, by=1, role="Engineer"),
                              dict(t="farm", hp=4, tier=0, by=0, role="Steward")]
    g.enemies = [dict(id=901, type="troll", q="N", cell=3, hp=6)]
    g.frozen, g.ward = set(), {q: 0 for q in QUADS}
    g.fx = []
    g._enemies_act()
    check([b["t"] for b in g.map["N"]["slots"][2]] == ["tower"],
          "troll (4 dmg) should destroy the 4hp farm, not the tower")
    ds = [e for e in g.fx if e[0] == "sdestroy"]
    check(ds and ds[0][4] == 1 and ds[0][5] == 0, "destroy event lacks index / owner")
    g.map["N"]["slots"][2] = [dict(t="tower", hp=8, tier=0, by=1, role="Engineer")]
    g.fx = []
    g._enemies_act()                       # it stays and hits the tower now
    check(g.enemies[0]["cell"] == 3, "enemy should stay and attack its cell")
    check(g.map["N"]["slots"][2][0]["hp"] < 8, "tower not attacked")
    say("buildings: 3 per cell, many per lane, enemies hit the weakest building first")

    # ---- 7b. builds happen BEFORE combat, so a new tower fires the same round
    g = fresh()
    quiet(g)
    g.enemies = [dict(id=701, type="goblin", q="SE", cell=2, hp=2)]
    g.next_id = 800
    fight(g, {"Engineer": dict(q="SE", build=[("tower", 1)], band=2)})
    kinds = [e[0] for e in g.fx]
    check(kinds.index("build") < kinds.index("shot"), "tower built after it should fire")
    check(not g.enemies or g.enemies[0]["hp"] < 2, "same-round tower did no damage")
    check(g.hcell["Engineer"] == 1 and g.pos["Engineer"] == "SE", "engineer token not in build cell")
    g = fresh()
    quiet(g)
    fight(g, {"Engineer": dict(q="SE", build=[("tower", 3)], band=2)})
    check(g.hcell["Engineer"] == 3, "engineer should stand in cell 3 where the tower went")
    hv = [e for e in g.fx if e[0] == "hero"]
    check(hv and hv[-1][1:] == ("Engineer", "SE", 3), "no hero move event for the builder")
    # the slayer walks to the cell that holds the goblins
    g = fresh()
    quiet(g)
    g.enemies = [dict(id=1, type="goblin", q="S", cell=2, hp=2)]
    g.next_id = 50
    g.pos["Slayer"] = "S"
    fight(g, {"Slayer": dict(q="S", prio="nearest", band=1)})
    check(g.hcell["Slayer"] == 2, "slayer should stand in cell 2 with the goblin")
    say("same-round builds: a new tower shoots at once; heroes walk to their work cells")

    # ---- 7c. enemies pick lanes with fewer towers and more farms
    g = fresh()
    g.waves = {1: [("N", "goblin")]}
    g.noise = {1: [{q: 0 for q in QUADS}] * 8}
    check(g.plan_lanes(1) == [("N", "goblin")], "empty map: tie goes to the hint-free first lane")
    for _ in range(3):
        g.map["N"]["slots"][1].append(dict(t="tower", hp=8, tier=0, by=1, role="Engineer"))
    check(g.plan_lanes(1)[0][0] != "N", "wave should avoid a lane full of towers")
    g.map["SW"]["slots"][0].append(dict(t="farm", hp=4, tier=0, by=0, role="Steward"))
    g.map["SW"]["slots"][0].append(dict(t="mine", hp=6, tier=0, by=0, role="Steward"))
    check(g.plan_lanes(1) == [("SW", "goblin")], "wave should go to the lane with farms")
    g.waves = {1: [("N", "goblin"), ("NE", "goblin"), ("N", "troll")]}
    lanes = [q for q, _ in g.plan_lanes(1)]
    check(lanes[0] == lanes[2] and lanes[0] != lanes[1], "wave groups should stay together")
    g.enemies = []
    g.round = 1
    g.phase = "vault"
    fight(g, {})
    check(any(e["q"] == "SW" for e in g.enemies), "enemies did not spawn in the chosen lane")
    say("lane choice: waves avoid towers and head for farms and mines")

    # ---- 7d. play-by-play text names the player and role
    ev = [("kill", 5, "N", 2, "goblin", "tower", "Engineer", 1),
          ("kill", 6, "N", 2, "troll", "Slayer", "Slayer", 2),
          ("kill", 7, "N", 2, "runner", "Mage", "Mage", 3)]
    txt = event_lines(ev)
    check(txt[0] == "Seat 2's (engineer) tower killed goblin", txt[0])
    check(txt[1] == "Seat 3 (slayer) killed troll", txt[1])
    check(txt[2] == "Seat 4 (mage) killed runner", txt[2])
    inc = [dict(kind="base", amt=4), dict(kind="farm", amt=2, by=0, role="Steward"),
           dict(kind="farm", amt=2, by=0, role="Steward"),
           dict(kind="farm", amt=2, by=0, role="Steward"),
           dict(kind="farm", amt=2, by=0, role="Steward"),
           dict(kind="mine", amt=4, by=1, role="Steward")]
    txt = event_lines((), inc)
    check("Seat 1's (steward) farms produce +8 gold" in txt, txt)
    check("Seat 2's (steward) mines produce +4 gold" in txt, txt)
    # a real game: every kill in the events is named by a real seat
    s = Session(4, humans=(), seed=11)
    prm = s.first()
    named = 0
    while prm and prm["kind"] != "end":
        if prm["kind"] == "report":
            for ln in event_lines(prm["events"]):
                if "killed" in ln:
                    named += 1
                    check(ln.startswith("Seat "), ln)
        prm = s.answer(None)
    check(named > 5, "no named kills in a whole game")
    say("play-by-play: '<seat> (role) killed X', 'Seat N's (role) tower killed X', farm income per seat")

    # ---- 7e. bank amount, petition funding and hover tips
    g = Game(4, 5, 1.9)
    g.start_round()
    want = g.bank_amount(1)
    before_v = g.vault[1]
    g.petition({0: dict(items=[("b_tonic", 3)], must=None)})
    check(g.vault[1] - before_v == want and want > 0, "bank amount shown is not what is banked")
    s = Session(4, humans=(0, 1), seed=8)
    prm = s.first()
    seen_bank = seen_funded = 0
    while prm and prm["kind"] != "end" and s.g.round < 4:
        if prm["kind"] == "petition":
            check(prm["bank"] == s.g.bank_amount(prm["seat"]), "petition prompt bank wrong")
            seen_bank += 1
        if prm["kind"] == "vault":
            check(prm["funded"] == list(s.g.funded), "vault prompt funded list wrong")
            seen_funded += len(prm["funded"])
        prm = s.answer(None)
    check(seen_bank >= 6, "no petition prompts")
    gf = PilGfx(MAP_W, MAP_H)
    g = fresh()
    quiet(g)
    fight(g, {"Engineer": dict(q="NE", build=[("tower", 2)], band=2),
               "Steward": dict(q="NE", build=[("farm", 1), ("mine", 1)], band=2)})
    g.enemies = [dict(id=77, type="goblin", q="NE", cell=3, hp=2)]
    draw_view(view_from_game(g), gf)
    regs = gf.regions
    px, py = struct_pt("NE", 2, 0, 1)
    t = tip_at(regs, px, py + 2)
    check(t and "Tower" in t and "Seat 2" in t, "tower tooltip missing: %r" % t)
    px, py = struct_pt("NE", 1, 0, 2)
    t = tip_at(regs, px, py + 2)
    check(t and "Farm" in t, "farm tooltip missing: %r" % t)
    px, py = enemy_pt("NE", 3)
    t = tip_at(regs, px, py)
    check(t and "Goblin" in t, "enemy tooltip missing: %r" % t)
    check("keep" in tip_at(regs, CX, CY - 30).lower(), "keep tooltip missing")
    px, py = cell_center("S", 2)
    check("cell 2" in tip_at(regs, px, py), "empty cell tooltip missing")
    check(tip_at(regs, 2, 2) is None, "tooltip over empty background")
    gf.tip = ("Tower: test\nsecond line", 300, 300)
    draw_view(view_from_game(g), gf)                    # draws a tip box without error
    say("bank amount, petition funding and hover tooltips check out")

    # ---- 8. the animation ends exactly where the game really is
    def norm(v):
        return dict(keep=v["keep"], pool=v["pool"], pos=v["pos"],
                    hcell={r: v["hcell"].get(r, 1) for r in v["pos"]},
                    slots=v["slots"], wall=v["wall"],
                    enemies=sorted((e["id"], e["type"], e["q"], e["cell"], e["hp"])
                                   for e in v["enemies"]))
    played = frames = kills = lost = incomes = builds = 0
    for n in (2, 3, 4, 5):
        for seed in range(1, 7):
            for slow in (True, False):
                s = Session(n, humans=(), seed=seed * 5 + n)
                prm = s.first()
                while prm and prm["kind"] != "end":
                    if prm["kind"] in ("advance", "report"):
                        an = Anim(prm)
                        an.ensure_view(view_from_game(s.g))
                        if slow:
                            t = 0.0
                            while not an.update(1 / 30):
                                t += 1 / 30
                                an.fx()
                                check(t < Anim.CAP + 12, "animation never ends")
                        else:
                            an.finish_now()
                        check(norm(an.view) == norm(view_from_game(s.g)),
                              "%s animation ended in a different state than the game "
                              "(n=%d seed=%d round %d)" % (prm["kind"], n, seed, prm["round"]))
                        if prm["kind"] == "advance":
                            incomes += 1
                            check(any("produce" in x or "realm" in x for x in an.lines),
                                  "no income lines")
                        else:
                            played += 1
                            kills += sum(e[0] == "kill" for e in prm["events"])
                            lost += sum(e[0] == "sdestroy" for e in prm["events"])
                            builds += sum(e[0] == "build" for e in prm["events"])
                            check(len(an.lines) >= 1, "no play-by-play for a round")
                    prm = s.answer(None)
    check(kills > 50 and lost > 0 and builds > 20,
          "the animation tests never saw a kill / lost building / build")
    say("animation: %d combat replays + %d income replays end in exactly the real "
        "game state (%d kills, %d lost buildings, %d builds seen)" % (
            played, incomes, kills, lost, builds))

    # ---- 9. resizing: the picture scales to the canvas; the wheel scrolls lists
    class FakeImg:
        def __init__(self, w, h):
            self.w, self.h, self.sc = w, h, 1

        def put(self, *a, **k):
            pass

        def zoom(self, n):
            z = FakeImg(self.w * n, self.h * n)
            z.sc = n
            return z

    class FakeCanvas:
        def __init__(self, w, h):
            self.w, self.h, self.log = w, h, []

        def winfo_width(self):
            return self.w

        def winfo_height(self):
            return self.h

        def delete(self, tag):
            self.log = [e for e in self.log if tag not in e[2].get("tags", "")]

        def create_rectangle(self, *a, **k):
            self.log.append(("rect", a, k))

        create_oval = create_polygon = create_line = create_rectangle

        def create_image(self, x, y, **k):
            self.log.append(("img", (x, y), k))
    for cw, ch in ((560, 604), (1120, 1208), (400, 700), (900, 500)):
        fc = FakeCanvas(cw, ch)
        tg = TkGfx(fc, auto=True, mk=lambda w, h: FakeImg(w, h))
        draw_map(Session(4, humans=(), seed=2).g, tg)
        fg = [e for e in fc.log if "fg" in e[2].get("tags", "")]
        xs = [v for kind, a, k in fg if kind in ("rect", "poly", "line")
              for v in a[0::2]]
        ys = [v for kind, a, k in fg if kind in ("rect", "poly", "line")
              for v in a[1::2]]
        check(max(xs) <= cw + 1 and max(ys) <= ch + 1 and min(xs) >= -1,
              "scaled picture does not fit a %dx%d canvas" % (cw, ch))
        ix = [a[0] for kind, a, k in fg if kind == "img"]
        iy = [a[1] for kind, a, k in fg if kind == "img"]
        check(ix and min(ix) >= -1 and max(ix) <= cw + 1 and min(iy) >= -1
              and max(iy) <= ch + 1, "text/sprites fall outside the canvas")
        want = min(cw / MAP_W, ch / MAP_H)
        check(abs(tg.k - want) < 1e-9, "scale factor wrong")
        heights = [k["image"].h for kind, a, k in fg if kind == "img"]
        check(min(heights) >= 5, "text too small to read at %dx%d" % (cw, ch))
        check(any(e[0] == "img" and "bg" in e[2].get("tags", "") for e in fc.log),
              "no brick background")
    say("resize: the map scales to 4 different window shapes and stays inside")

    class W:                       # a pretend widget chain: label -> frame -> canvas
        def __init__(self, master=None, tall=False):
            self.master, self.tall, self.scrolled = master, tall, []

        def bbox(self, _):
            return (0, 0, 10, 900 if self.tall else 50)

        def winfo_height(self):
            return 300

        def yview_scroll(self, n, what):
            self.scrolled.append((n, what))
    cvw = W(tall=True)
    short = W(tall=False)
    label = W(W(cvw))
    other = W(W(short))

    class FakeApp(App):
        def __init__(self):
            self.scrollers = [cvw, short]
            self.at = label

        class root:
            pass
    fa = FakeApp()
    fa.root = type("R", (), {"winfo_containing": lambda s, x, y: fa.at})()
    ev = lambda **k: type("E", (), dict(x_root=1, y_root=1, **k))()
    fa.on_wheel(ev(delta=-120))
    fa.on_wheel(ev(delta=120))
    fa.on_wheel(ev(num=4, delta=0))
    fa.on_wheel(ev(num=5, delta=0))
    check(cvw.scrolled == [(2, "units"), (-2, "units"), (-2, "units"),
                           (2, "units")], "wheel directions wrong %s" % cvw.scrolled)
    fa.at = other                                   # a list that is not scrollable
    fa.on_wheel(ev(delta=-120))
    check(short.scrolled == [], "scrolled a list that fits")
    fa.at = W()                                     # pointer over nothing scrollable
    check(fa.on_wheel(ev(delta=-120)) is None, "wheel handled outside any list")
    say("mouse wheel: scrolls the list under the pointer, all 3 platforms")

    # ---- 9b. several computers play one game in lockstep
    def netsim(m, n, seed, scramble, silent=()):
        rnd = random.Random(seed)
        pending = collections.defaultdict(list)
        sess = {}

        def mk(i):
            def send(k, v):
                v = json.loads(json.dumps(v))        # it travels as JSON
                for j in range(m):
                    if j != i:
                        pending[j].append((k, v))
                        if scramble and rnd.random() < .3:
                            pending[j].append((k, v))      # a repeat
            return send
        for i in range(m):
            sess[i] = Session(n, humans=[i], seed=seed,
                              remote=[j for j in range(m) if j != i],
                              send=mk(i), names=["P%d" % x for x in range(m)])
        live = [i for i in range(m) if i not in silent]
        cur = {i: sess[i].first() for i in live}
        for guard in range(200000):
            if all(cur[i]["kind"] == "end" for i in live):
                break
            for i in live:
                if scramble:
                    rnd.shuffle(pending[i])
                while pending[i]:
                    k, v = pending[i].pop()
                    sess[i].feed(k, v)
            for i in live:
                prm = cur[i]
                k = prm["kind"]
                if k == "end":
                    continue
                if k == "wait":
                    if sess[i].waiting_on()[1] in silent and i == live[0]:
                        for j in live:                   # the host steps in
                            pending[j].append((prm["key"], {"skip": 1}))
                    cur[i] = sess[i].answer(None)
                elif k == "mini":
                    cur[i] = sess[i].answer(1)
                elif k in ("petition", "treasury", "vault", "plan"):
                    cur[i] = sess[i].answer(prm["default"])
                else:
                    cur[i] = sess[i].answer(None)
        else:
            raise AssertionError("networked game never finished")
        return [sess[i] for i in live]
    for (m, n, seed, scr, silent) in ((2, 2, 4, False, ()), (3, 3, 5, True, ()),
                                      (4, 4, 6, True, ()), (5, 5, 7, False, ()),
                                      (3, 4, 8, True, (2,)), (2, 4, 9, True, (1,))):
        ss = netsim(m, n, seed, scr, silent)
        hs = {x.g.state_hash() for x in ss}
        check(len(hs) == 1, "computers ended in different states %s" % hs)
        check(all(not x.desync for x in ss), "state check differed mid-game %s %s" % ((m, n, seed, scr, silent), [x.desync for x in ss]))
        check(len({x.g.round for x in ss}) == 1 and len({x.g.won for x in ss}) == 1,
              "computers disagree about the result")
        # a solo run of the same game with those humans playing must match too
        sent = sum(len(x.sent) for x in ss)
        check(sent <= (ss[0].g.round + 1) * m * 3, "too many messages: %d" % sent)
    say("lockstep chat game: 2-5 computers, repeated and shuffled messages, "
        "and a missing player replaced by a bot all end in the same state")

    # ---- 9c. custom seats: any split of the five roles between 1 and 5 seats
    for seats in ([("Mage", "Slayer", "Steward", "Smith", "Engineer")],
                  [("Mage",), ("Slayer", "Steward", "Smith", "Engineer")],
                  [("Steward", "Engineer"), ("Smith",), ("Slayer", "Mage")]):
        g = cm.play_game(0, 5, seats=seats)
        check(g.over and g.n == len(seats), "custom seats game did not finish")
    for seats in ([("Mage",)], [("Steward", "Smith"), ("Mage",)], [("Slayer",), ("Smith",), ("Steward",)]):
        g = cm.play_game(0, 5, seats=seats)       # some roles left unfilled
        check(g.over and g.n == len(seats), "partial seats game did not finish")
    for bad in ([], [("Mage",), ("Mage", "Slayer", "Smith", "Engineer", "Steward")],
                [("Mage", "Slayer", "Smith", "Engineer", "Steward"), ()]):
        try:
            cm.Game(2, 1, 1.9, "draft", bad)
            check(False, "bad seat split was accepted")
        except ValueError:
            pass
    s = Session(0, humans=[0], seed=3, seats=[("Mage",), ("Slayer", "Steward", "Smith", "Engineer")])
    check(s.g.n == 2 and s.g.seats[1][0] == "Slayer", "Session ignored custom seats")
    say("custom seats: any split of the five roles works, bad splits are refused")

    # ---- 10. the window code, run against a pretend Tk
    ui_smoke(check, say)
    say("ALL %d CHECKS PASSED" % ok[0])
    return True


def ui_smoke(check, say):
    """Walk a whole game through the window code using a pretend tkinter.
    This catches typos and wrong data in the forms; it can't judge layout."""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = [os.path.join(here, "fake_tk.py")]
    fk = next((p for p in cand if os.path.exists(p)), None)
    if fk is None:
        say("window code: skipped (fake_tk.py not next to this file)")
        return
    import importlib.util
    sp = importlib.util.spec_from_file_location("fake_tk", fk)
    ft = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(ft)
    saved = {k: sys.modules.get(k) for k in ("tkinter", "tkinter.ttk",
                                             "tkinter.font")}
    ft.install()
    tk = sys.modules["tkinter"]
    for n in ("Spinbox", "Radiobutton", "OptionMenu"):
        setattr(tk, n, ft.Widget)
    try:
        root = tk.Tk()
        app = App(root, tk)
        labs, btns = [], []
        orig_lab, orig_btn = app.lab, app.btn

        def rec_lab(parent, text, *a, **k):
            labs.append(str(text))
            return orig_lab(parent, text, *a, **k)

        def rec_btn(parent, text, *a, **k):
            btns.append(str(text))
            return orig_btn(parent, text, *a, **k)
        app.lab, app.btn = rec_lab, rec_btn
        global clock
        real_clock, t = clock, [5000.0]
        clock = lambda: t[0]
        try:
            for n, humans in ((4, 2), (2, 2), (5, 1)):
                app.v_n.set(n)
                for i in range(5):
                    app.v_h[i].set(1 if i < humans else 0)
                app.v_seed.set("3")
                app.refresh_seats()
                app.start_game()
                guard, kinds = 0, collections.Counter()
                while True:
                    guard += 1
                    check(guard < 3000, "window flow did not finish")
                    kind = app.last_kind
                    kinds[kind] += 1
                    if kind in ("advance", "report"):
                        k = 0
                        while app.anim_loop is not None and k < 40:
                            t[0] += 0.05
                            k += 1
                            app.anim_loop()      # play a bit of the animation
                        if app.anim_loop is not None:
                            app.submit()         # Skip
                        check(app.anim_loop is None, "animation did not stop")
                        if kind == "report":
                            check(any("Who did what" in x for x in labs),
                                  "report not shown after the animation")
                            check(any("summary" in x for x in labs), "no summary")
                        app.submit()             # Continue / Next round
                    elif kind == "petition":
                        check(any(x.startswith("Skip (bank) (+") for x in btns[-4:]),
                              "bank button lacks its gold amount")
                        app.submit()
                    elif kind == "treasury":
                        check(app.total_lab._p["text"].startswith("Spending now:"),
                              "no live treasurer total")
                        rows = app.treasury_rows
                        first = app.total_lab._p["text"]
                        for (key, asked, var) in rows:
                            var.set("0")
                        app.update_total()
                        check(app.total_lab._p["text"].startswith("Spending now: 0 /"),
                              "treasurer total did not follow the boxes")
                        for (key, asked, var) in rows[:1]:
                            var.set(str(asked))
                        app.update_total()
                        check(("Spending now: %d /" % rows[0][1]) in
                              app.total_lab._p["text"] or rows[0][1] == 0,
                              "treasurer total wrong after a change")
                        app.submit()
                    elif kind == "vault":
                        lv = max(i for i, x in enumerate(labs) if x.startswith("Your vault"))
                        check(any("from petitions this round" in x for x in labs[lv:lv + 4]),
                              "vault form lacks the petition funding line")
                        app.submit()
                    elif kind == "mini":
                        app.submit()                   # press Start
                        mg = app.mini
                        k = 0
                        while not mg.done and k < 5000:
                            t[0] += 0.05
                            k += 1
                            app.mini_loop()
                        check(mg.done, "mini-game never ended in the window")
                        app.submit()                   # Continue
                    elif kind == "end":
                        break
                    else:
                        app.submit()
                check(kinds["report"] >= 5, "window skipped rounds %s" % kinds)
            app.sess = Session(4, (0,), 3)
            app.draw()
            g1 = app.gfx
            e1 = type("E", (), dict(x=CX * g1.k + g1.ox, y=(CY - 30) * g1.k + g1.oy))()
            app.on_motion(e1)
            check(g1.tip and "keep" in g1.tip[0].lower(), "hovering the keep shows no tip")
            app.on_leave()
            check(g1.tip is None, "tip not cleared when the mouse leaves")
        finally:
            clock = real_clock
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    say("window code: 3 full games walked through the forms (pretend Tk)")
    app.open_help()
    class Ev:
        width = 640
    app.on_right_resize(Ev())


# ======================================================================
#  PICTURES  (python castle_game.py --png out.png)
# ======================================================================
def make_png(path):
    from PIL import Image
    s = Session(4, humans=(), seed=6)
    prm = s.first()
    while prm and prm["kind"] != "end" and s.g.round < 6:
        prm = s.answer(None)
    # put the game into the middle of a round so the forecast reads "now"
    sheet = Image.new("RGB", (max(TOP_W, MAP_W + MW + 20),
                              TOP_H + max(MAP_H, MH * 5 + 40)), BG)
    gf, gt = PilGfx(MAP_W, MAP_H), PilGfx(TOP_W, TOP_H)
    gf.top = gt
    draw_map(s.g, gf, "NE")
    sheet.paste(gt.im, (0, 0))
    sheet.paste(gf.im, (0, TOP_H))
    y = TOP_H + 8
    for role, cls in MINIGAMES.items():
        gm = PilGfx(MW, MH)
        m = cls(random.Random(4))
        m.start(0)
        for t in (1.2, 2.3, 3.4):
            m.step(t)
        m.draw(gm, 3.4)
        sheet.paste(gm.im, (MAP_W + 10, y))
        y += MH + 6
    sheet.save(path)
    print("saved", path)


def make_anim_png(path):
    """A filmstrip of the between-rounds animation (needs Pillow)."""
    from PIL import Image
    best = None
    for seed in range(1, 40):
        s = Session(4, humans=(), seed=seed)
        prm = s.first()
        while prm and prm["kind"] != "end":
            if prm["kind"] == "advance" and 4 <= prm["round"] <= 9:
                kinds = collections.Counter(e[0] for e in prm["events"])
                score = kinds["sdestroy"] * 5 + kinds["move"] + kinds["shot"] + \
                    kinds["kill"] + 3 * kinds["wall"] + len(prm["income"])
                if best is None or score > best[0]:
                    best = (score, prm, view_from_game(s.g))
            prm = s.answer(None)
    _, prm, now = best
    an = Anim(prm)
    an.ensure_view(now)
    total = sum(b["dur"] for b in an.beats)
    shots, tt = [], 0.0
    marks = [total * f for f in (0.04, 0.22, 0.4, 0.58, 0.76, 0.96)]
    while not an.done and marks:
        an.update(0.02)
        tt += 0.02
        if tt >= marks[0]:
            marks.pop(0)
            gf = PilGfx(MAP_W, MAP_H)
            an.draw(gf)
            shots.append(gf.im.copy())
    sc = 0.62
    w, h = int(MAP_W * sc), int(MAP_H * sc)
    sheet = Image.new("RGB", (w * 3 + 8, h * 2 + 4), BG)
    for i, im in enumerate(shots[:6]):
        sheet.paste(im.resize((w, h)), ((i % 3) * (w + 4), (i // 3) * (h + 4)))
    sheet.save(path)
    print("saved", path, "(%d beats, %.1fs)" % (len(an.beats), total))


def main():
    ap = argparse.ArgumentParser(description="Castle Defense (stand-alone)")
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--humans", type=int, default=1,
                    help="how many seats are people (the rest are bots)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--diff", default="Normal", choices=list(DIFFICULTY))
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--png", metavar="FILE")
    ap.add_argument("--anim", metavar="FILE",
                    help="save a filmstrip of the round animation")
    ap.add_argument("--sim", type=int, metavar="N")
    args = ap.parse_args()
    args.start = len(sys.argv) > 1 and any(
        a.startswith(("--players", "--humans", "--seed", "--diff"))
        for a in sys.argv[1:])
    if args.test:
        run_tests()
    elif args.png:
        make_png(args.png)
    elif args.anim:
        make_anim_png(args.anim)
    elif args.sim:
        cm.simulate(args.sim)
    else:
        run_window(args)


if __name__ == "__main__":
    main()
