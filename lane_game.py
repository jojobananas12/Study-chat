#!/usr/bin/env python3
"""
lane_game.py - a small turn-based lane card game. It runs on its own (it does
not need the study chat) and can sit in the same folder as studychat.py.

  python lane_game.py                 play it
  python lane_game.py --debug         same, with a debug panel (also F1)
  python lane_game.py --seed 7        the same enemy every time (for bugs)
  python lane_game.py --test          play 2000 random games with no window
                                      and check the rules hold up
  python lane_game.py --png out.png   save a picture of a sample position
                                      (needs Pillow: pip install pillow)

How to play
  Hover a lane: your hands follow it.   Pick a card with 1 / 2 / 3 (or click
  it), then click a lane to cast. Every turn you do ONE thing:
     cast a card     -  a shot starts at your end of that lane
     A / D           -  move your shield one lane left / right
     SPACE           -  wait
  Then the Stalk-Eyed One does one thing too (cast, sidestep or wait) and
  every shot already flying moves SPD rows. Shots from opposite sides meet in
  a lane and the weaker one is wiped out. A shot of yours that reaches the far
  end hurts the enemy only if it is standing in that lane; a shot of its that
  reaches you hurts unless your shield is in that lane. 5 health each.
  R restarts, Q quits, F1 shows the debug panel.
"""

import argparse
import math
import random
import sys

W, H = 960, 600
LANES, ROWS = 3, 6                 # lanes across, rows (slots) deep
MAX_HP, MAX_TURNS = 5, 40
CARDS = (("BOLT", 3, 1), ("FIRE", 2, 2), ("METEOR", 1, 3))   # name, speed, damage
FOE_NAME = "THE STALK-EYED ONE"
FRAME_MS = 230                     # how long each step of a turn is shown


# ===================================================================== rules
class Game:
    """All the rules, with no drawing, so it can be tested without a window.

    A shot sits in a lane at a "slot" 0..ROWS-1; slot 0 is next to you and
    slot ROWS-1 is next to the enemy. Your shots move up the slots, the
    enemy's move down. One turn: both sides act, then every shot moves up to
    its speed (one slot at a time, so fast shots can't skip over a fight),
    and finally any new casts appear at their owner's end.
    """

    def __init__(self, seed=None):
        self.seed = seed if seed is not None else random.randrange(10 ** 6)
        self.rng = random.Random(self.seed)
        self.hp = {"you": MAX_HP, "foe": MAX_HP}
        self.turn = 1
        self.shield = 1               # the lane your shield is in
        self.foe_lane = 1             # the lane the enemy stands in
        self.shots = []
        self.over = False
        self.winner = None            # "you", "foe" or "draw"
        self.last_foe = "-"
        self._id = 1

    def snapshot(self, events=(), hit=()):
        return {"shots": [dict(s) for s in self.shots], "hp": dict(self.hp),
                "foe_lane": self.foe_lane, "shield": self.shield,
                "turn": self.turn, "over": self.over, "winner": self.winner,
                "events": list(events), "hit": set(hit)}

    def foe_decide(self):
        r = self.rng.random()
        if r < 0.55:
            card = self.rng.choices(range(3), weights=(4, 3, 3))[0]
            return ("cast", card, self.rng.randrange(LANES))
        if r < 0.80:
            opts = [d for d in (-1, 1) if 0 <= self.foe_lane + d < LANES]
            return ("move", self.rng.choice(opts))
        return ("wait",)

    @staticmethod
    def describe(who, act):
        if act[0] == "cast":
            return f"{who} cast {CARDS[act[1]][0]} in lane {act[2] + 1}"
        if act[0] == "shield":
            return f"{who} moved the shield {'left' if act[1] < 0 else 'right'}"
        if act[0] == "move":
            return f"{who} sidestepped {'left' if act[1] < 0 else 'right'}"
        return f"{who} waited"

    def play_turn(self, you_act):
        """you_act: ("cast", card, lane) | ("shield", -1 or 1) | ("wait",).
        Returns the frames to show, one per step of the turn."""
        if self.over:
            raise RuntimeError("the game is over")
        foe_act = self.foe_decide()
        self.last_foe = self.describe("enemy", foe_act)
        casts = []
        if you_act[0] == "shield":
            self.shield = min(LANES - 1, max(0, self.shield + you_act[1]))
        elif you_act[0] == "cast":
            casts.append(("you", you_act[1], you_act[2]))
        if foe_act[0] == "move":
            self.foe_lane = min(LANES - 1, max(0, self.foe_lane + foe_act[1]))
        elif foe_act[0] == "cast":
            casts.append(("foe", foe_act[1], foe_act[2]))
        frames = [self.snapshot([self.describe("you", you_act),
                                 self.last_foe])]
        for sub in (1, 2, 3):                       # one slot per sub-step
            moved = False
            for s in self.shots:
                if s["spd"] >= sub:
                    s["slot"] += 1 if s["owner"] == "you" else -1
                    moved = True
            if not moved:
                break
            ev, hit = [], set()
            self._collide(ev)
            self._arrive(ev, hit)
            frames.append(self.snapshot(ev, hit))
        for owner, card, lane in casts:             # new shots appear
            name, spd, dmg = CARDS[card]
            self.shots.append({"id": self._id, "owner": owner, "lane": lane,
                               "slot": 0 if owner == "you" else ROWS - 1,
                               "card": card, "spd": spd, "dmg": dmg})
            self._id += 1
        self._check_end()
        if not self.over:
            self.turn += 1
        frames.append(self.snapshot())
        return frames

    def _collide(self, ev):
        """Opposing shots in one lane that meet or pass: the stronger one
        survives with the weaker one's damage taken off; equals cancel."""
        for lane in range(LANES):
            while True:
                mine = sorted((s for s in self.shots if s["lane"] == lane
                               and s["owner"] == "you"),
                              key=lambda s: -s["slot"])
                theirs = sorted((s for s in self.shots if s["lane"] == lane
                                 and s["owner"] == "foe"),
                                key=lambda s: s["slot"])
                pair = next(((a, b) for a in mine for b in theirs
                             if a["slot"] >= b["slot"]), None)
                if pair is None:
                    break
                a, b = pair
                na, nb = CARDS[a["card"]][0], CARDS[b["card"]][0]
                if a["dmg"] == b["dmg"]:
                    self.shots.remove(a)
                    self.shots.remove(b)
                    ev.append(f"{na} and enemy {nb} cancel out")
                else:
                    win, lose = (a, b) if a["dmg"] > b["dmg"] else (b, a)
                    win["dmg"] -= lose["dmg"]
                    self.shots.remove(lose)
                    ev.append(f"{CARDS[win['card']][0]} breaks "
                              f"{CARDS[lose['card']][0]}")

    def _arrive(self, ev, hit):
        for s in list(self.shots):
            name = CARDS[s["card"]][0]
            if s["owner"] == "you" and s["slot"] >= ROWS:
                self.shots.remove(s)
                if s["lane"] == self.foe_lane:
                    self.hp["foe"] = max(0, self.hp["foe"] - s["dmg"])
                    hit.add("foe")
                    ev.append(f"your {name} hit the enemy (-{s['dmg']})")
                else:
                    ev.append(f"your {name} missed (it stood in lane "
                              f"{self.foe_lane + 1})")
            elif s["owner"] == "foe" and s["slot"] < 0:
                self.shots.remove(s)
                if s["lane"] == self.shield:
                    ev.append(f"you blocked the enemy {name}")
                else:
                    self.hp["you"] = max(0, self.hp["you"] - s["dmg"])
                    hit.add("you")
                    ev.append(f"the enemy {name} hit you (-{s['dmg']})")

    def _check_end(self):
        a, b = self.hp["you"], self.hp["foe"]
        if a <= 0 or b <= 0 or self.turn >= MAX_TURNS:
            self.over = True
            self.winner = ("draw" if a == b else "you" if a > b else "foe")


# =================================================================== picture
# The picture is built as a plain list of shapes, so the window and the PNG
# export (and any test) all draw the same thing.
FAR_Y, NEAR_Y = 250, 500
FAR_L, FAR_R = 410, 550
NEAR_L, NEAR_R = 90, 870
CARD_X, CARD_Y, CARD_W, CARD_H = (265, 430, 595), 515, 150, 80


def edge_y(k):
    """y of the edge between slots (k = 0 is the near edge)."""
    t = k / ROWS
    return NEAR_Y - (NEAR_Y - FAR_Y) * (1 - (1 - t) ** 2)


def lane_edges(y):
    u = (y - FAR_Y) / (NEAR_Y - FAR_Y)
    return (FAR_L + (NEAR_L - FAR_L) * u, FAR_R + (NEAR_R - FAR_R) * u)


def lane_x(y, lane, frac=0.5):
    left, right = lane_edges(y)
    return left + (right - left) * (lane + frac) / LANES


def lane_at(x, y):
    left, right = lane_edges(min(NEAR_Y, max(FAR_Y, y)))
    return min(LANES - 1, max(0, int((x - left) / (right - left) * LANES)))


def _static():
    """Background, trees and leaves: the same every time."""
    out, rnd = [], random.Random(7)
    bands = ("#0b0614", "#10081c", "#160a26", "#1c0d30", "#220f38", "#2a1244")
    step = FAR_Y // len(bands)
    for i, c in enumerate(bands):
        out.append(("rect", 0, i * step, W, (i + 1) * step + 1, c, None))
    out.append(("rect", 0, FAR_Y, W, H, "#12091d", None))
    for r in (150, 166, 182):                         # dotted glow behind it
        n = int(2 * math.pi * r / 11)
        for j in range(n):
            a = 2 * math.pi * j / n
            x, y = 480 + r * math.cos(a), 188 + r * math.sin(a)
            if y < FAR_Y - 6:
                out.append(("rect", x, y, x + 5, y + 5, "#3a1a58", None))
    for side in (0, 1):                               # branches
        for _ in range(9):
            y = rnd.randrange(30, H - 60)
            x = 0 if side == 0 else W
            length = rnd.randrange(5, 15)
            for j in range(length):
                x += 12 if side == 0 else -12
                y += rnd.choice((-8, 0, 0, 8))
                c = rnd.choice(("#3b2216", "#4a2b19", "#5a3320"))
                out.append(("rect", x - 6, y - 6, x + 7, y + 7, c, None))
    for _ in range(26):                               # red leaves on top
        x, y = rnd.randrange(0, W), rnd.randrange(-6, 26)
        out.append(("oval", x, y, x + rnd.randrange(30, 70),
                    y + rnd.randrange(14, 26), rnd.choice(("#a3121f",
                                                           "#7d0f1a")), None))
    return out


_STATIC = None


def _shot_glyph(shot, y, color_edge):
    t = 1 - (y - FAR_Y) / (NEAR_Y - FAR_Y)            # 0 near .. 1 far
    s = 1.45 - 0.9 * t
    x = lane_x(y, shot["lane"])
    kind = shot["card"]
    out = []
    if kind == 0:                                     # bolt
        pts = [(0, -15), (7, -15), (1, -3), (8, -3), (-5, 15), (0, 2), (-7, 2)]
        out.append(("poly", [(x + a * s, y + b * s) for a, b in pts],
                    "#ffd21f", color_edge))
    elif kind == 1:                                   # fireball
        r = 12 * s
        out.append(("oval", x - r, y - r, x + r, y + r, "#e8332a", "#ff9a3c"))
        r2 = 5 * s
        out.append(("oval", x - r2, y - r2, x + r2, y + r2, "#ffffff", None))
    else:                                             # meteor
        pts = [(0, -15), (12, 0), (0, 15), (-12, 0)]
        out.append(("poly", [(x + a * s, y + b * s) for a, b in pts],
                    "#9b5cff", "#e6d4ff"))
        pts = [(0, -6), (5, 0), (0, 6), (-5, 0)]
        out.append(("poly", [(x + a * s, y + b * s) for a, b in pts],
                    "#ffffff", None))
    label = CARDS[kind][0] if kind != 1 else "FIREBALL"
    out.append(("text", x + 16 * s, y - 14 * s, label,
                "#ffd21f" if shot["owner"] == "you" else "#ff7ad0",
                12, "w"))
    return out


def _enemy(cx, base, flash):
    body = "#ffffff" if flash else "#c4208f"
    out = []
    for dx in (-26, 0, 26):                           # three eye stalks
        out.append(("rect", cx + dx - 2, base - 112, cx + dx + 2, base - 68,
                    body, None))
        out.append(("rect", cx + dx - 9, base - 126, cx + dx + 9, base - 108,
                    "#c8e63a", "#6b8f10"))
        out.append(("rect", cx + dx - 3, base - 121, cx + dx + 3, base - 113,
                    "#1a0f2e", None))
    out.append(("rect", cx - 36, base - 76, cx + 36, base - 40, body, None))
    for dx in (-22, -8, 8, 22):                       # teeth
        out.append(("rect", cx + dx - 3, base - 62, cx + dx + 3, base - 56,
                    "#ffffff", None))
    out.append(("rect", cx - 42, base - 46, cx + 42, base - 8, body, None))
    for i in range(6):                                # checker belly
        for j in range(4):
            if (i + j) % 2 == 0:
                out.append(("rect", cx - 30 + i * 10, base - 40 + j * 8,
                            cx - 20 + i * 10, base - 32 + j * 8,
                            "#ff9a3c", None))
    for dx in (-34, 34):                              # feet
        out.append(("rect", cx + dx - 6, base - 10, cx + dx + 6, base,
                    "#2fd6c8", None))
    return out


def _hands(cx):
    out, gold, dark = [], "#e6b422", "#b8860b"
    for sign in (-1, 1):
        px = cx + sign * 52
        out.append(("rect", px - 30, 440, px + 30, 500, gold, dark))
        for i in range(4):
            fx = px - 30 + i * 15
            h = (58, 70, 66, 52)[i if sign > 0 else 3 - i]
            out.append(("rect", fx, 440 - h, fx + 13, 444, gold, dark))
        out.append(("rect", px - 4 + sign * 32, 452, px + 12 + sign * 32,
                    478, gold, dark))                 # thumb
    return out


def build_scene(snap, ui):
    """snap: a Game.snapshot(). ui: aim, sel, msg, debug, debug_lines."""
    global _STATIC
    if _STATIC is None:
        _STATIC = _static()
    out = list(_STATIC)
    aim = ui.get("aim", 1)
    # the lanes
    out.append(("rect", 56, FAR_Y - 1, W - 56, FAR_Y + 2, "#ff8a1f", None))
    for slot in range(ROWS):
        y_near, y_far = edge_y(slot), edge_y(slot + 1)
        ln, rn = lane_edges(y_near)
        lf, rf = lane_edges(y_far)
        shade = "#7a5a38" if slot % 2 == 0 else "#6a4c2f"
        out.append(("poly", [(ln, y_near), (rn, y_near), (rf, y_far),
                             (lf, y_far)], shade, None))
        if ui.get("aim") is not None:                 # the aimed lane
            a_l = ln + (rn - ln) * aim / LANES
            a_r = ln + (rn - ln) * (aim + 1) / LANES
            b_l = lf + (rf - lf) * aim / LANES
            b_r = lf + (rf - lf) * (aim + 1) / LANES
            out.append(("poly", [(a_l, y_near), (a_r, y_near),
                                 (b_r, y_far), (b_l, y_far)],
                        "#a88858", None))
            n = 7                                      # dotted pattern
            for i in range(n):
                for j in range(2):
                    if (i + slot + j) % 2:
                        continue
                    u0, u1 = i / n, (i + 1) / n
                    yy = y_near + (y_far - y_near) * (0.25 + 0.5 * j)
                    xl = a_l + (a_r - a_l) * u0 + (b_l - a_l) * 0.4 * (0.5 * j)
                    out.append(("rect", xl + 2, yy - 3,
                                xl + 2 + (a_r - a_l) / n * 0.5, yy + 3,
                                "#c4a470", None))
        out.append(("poly", [(ln, y_near), (rn, y_near), (rn, y_near + 3),
                             (ln, y_near + 3)], "#a82020", None))
    for k in range(1, LANES):                         # lane dividers
        y0, y1 = NEAR_Y, FAR_Y
        out.append(("poly", [(lane_x(y0, k - 1, 1.0) - 1, y0),
                             (lane_x(y0, k - 1, 1.0) + 1, y0),
                             (lane_x(y1, k - 1, 1.0) + 1, y1),
                             (lane_x(y1, k - 1, 1.0) - 1, y1)],
                    "#4a3320", None))
    # the enemy, at the far end of its lane
    flash = "foe" in snap["hit"]
    out += _enemy(lane_x(FAR_Y, snap["foe_lane"]), FAR_Y + 2, flash)
    # the shots: far ones first, so near ones are drawn on top
    for s in sorted(snap["shots"], key=lambda s: -s["slot"]):
        y = edge_y(min(ROWS, max(0, s["slot"])) + 0.5)
        out += _shot_glyph(s, y, "#ffffff" if s["owner"] == "you"
                           else "#ff7ad0")
    # your shield, at your end of its lane
    sh = snap["shield"]
    yb = NEAR_Y
    ln, rn = lane_edges(yb)
    sx0 = ln + (rn - ln) * sh / LANES + 6
    sx1 = ln + (rn - ln) * (sh + 1) / LANES - 6
    out.append(("rect", sx0, yb - 14, sx1, yb - 4, "#fff2a8", "#ffd21f"))
    out.append(("rect", sx0 + 8, yb - 24, sx1 - 8, yb - 14, "#ffd21f", None))
    # your hands follow the aimed lane
    out += _hands(lane_x(NEAR_Y, aim))
    out.append(("text", 480, 502, "A/D shield   SPACE wait", "#f0e6d0", 11,
                "center"))
    # health, turn
    for i in range(MAX_HP):
        on = i < snap["hp"]["you"]
        out.append(("rect", 24 + 72 * i, 48, 24 + 72 * i + 64, 68,
                    "#ffd21f" if on else "#1a1230", None))
        on = i >= MAX_HP - snap["hp"]["foe"]
        out.append(("rect", 584 + 72 * i, 48, 584 + 72 * i + 64, 68,
                    "#ff7a1a" if on else "#1a1230", None))
    out.append(("text", 24, 88, "YOU", "#ffd21f", 12, "w"))
    out.append(("text", 936, 88, FOE_NAME, "#ff7a1a", 12, "e"))
    out.append(("text", 480, 33, f"TURN {snap['turn']}", "#f0e6d0", 16,
                "center"))
    if "you" in snap["hit"]:                          # you were hit: red edge
        out.append(("rect", 0, 0, W, 8, "#e8332a", None))
        out.append(("rect", 0, H - 8, W, H, "#e8332a", None))
    # cards
    for i, (name, spd, dmg) in enumerate(CARDS):
        x, y = CARD_X[i], CARD_Y - (8 if ui.get("sel") == i else 0)
        edge = "#ffffff" if ui.get("sel") == i else "#d4a017"
        out.append(("rect", x, y, x + CARD_W, y + CARD_H, "#2a1a10", edge))
        out.append(("rect", x + 4, y + 4, x + CARD_W - 4, y + CARD_H - 4,
                    "#3b2416", "#6b4a2e"))
        for cx, cy in ((x, y), (x + CARD_W - 8, y), (x, y + CARD_H - 8),
                       (x + CARD_W - 8, y + CARD_H - 8)):
            out.append(("rect", cx, cy, cx + 8, cy + 8, "#c026a8", None))
        out.append(("text", x + 12, y + 14, f"{i + 1} {name}", "#f0e6d0", 12,
                    "w"))
        gx, gy = x + 34, y + 50
        if i == 0:
            out.append(("poly", [(gx + a, gy + b) for a, b in
                                 [(0, -15), (7, -15), (1, -3), (8, -3),
                                  (-5, 15), (0, 2), (-7, 2)]],
                        "#ffd21f", None))
        elif i == 1:
            out.append(("oval", gx - 12, gy - 12, gx + 12, gy + 12,
                        "#e8332a", "#ff9a3c"))
            out.append(("oval", gx - 5, gy - 5, gx + 5, gy + 5, "#fff", None))
        else:
            out.append(("poly", [(gx, gy - 15), (gx + 12, gy), (gx, gy + 15),
                                 (gx - 12, gy)], "#9b5cff", "#e6d4ff"))
        out.append(("text", x + 80, y + 40, f"SPD {spd}", "#f0e6d0", 12, "w"))
        out.append(("text", x + 80, y + 60, f"DMG {dmg}", "#f0e6d0", 12, "w"))
    out.append(("text", 30, 558, "HOVER A LANE", "#ffd21f", 11, "w"))
    out.append(("text", 30, 578, "hands follow it", "#f0e6d0", 11, "w"))
    out.append(("text", 756, 558, "CLICK = CAST", "#ffd21f", 11, "w"))
    out.append(("text", 756, 578, "pick card first", "#f0e6d0", 11, "w"))
    if ui.get("msg"):
        out.append(("text", 480, 118, ui["msg"], "#f0e6d0", 13, "center"))
    if snap["over"]:
        word = {"you": "YOU WIN", "foe": "YOU LOSE",
                "draw": "DRAW"}[snap["winner"]]
        out.append(("rect", 300, 250, 660, 340, "#14091f", "#ffd21f"))
        out.append(("text", 480, 285, word, "#ffd21f", 28, "center"))
        out.append(("text", 480, 320, "R = play again", "#f0e6d0", 13,
                    "center"))
    if ui.get("debug"):
        lines = ui.get("debug_lines", [])
        out.append(("rect", 6, 96, 330, 96 + 16 * len(lines) + 8, "#000000",
                    "#44ff88"))
        for i, line in enumerate(lines):
            out.append(("text", 12, 106 + 16 * i, line, "#44ff88", 11, "w"))
    return out


def draw_tk(cv, prims):
    cv.delete("all")
    for p in prims:
        kind = p[0]
        if kind == "rect":
            cv.create_rectangle(p[1], p[2], p[3], p[4], fill=p[5],
                                outline=p[6] or "", width=2 if p[6] else 0)
        elif kind == "oval":
            cv.create_oval(p[1], p[2], p[3], p[4], fill=p[5],
                           outline=p[6] or "", width=2 if p[6] else 0)
        elif kind == "poly":
            flat = [c for pt in p[1] for c in pt]
            cv.create_polygon(*flat, fill=p[2] or "", outline=p[3] or "",
                              width=2 if p[3] else 0)
        elif kind == "text":
            cv.create_text(p[1], p[2], text=p[3], fill=p[4], anchor=p[6],
                           font=("Courier", -p[5], "bold"))


def render_png(prims, path):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (W, H), "#000000")
    d = ImageDraw.Draw(im)
    anchors = {"center": "mm", "w": "lm", "e": "rm"}
    for p in prims:
        kind = p[0]
        if kind == "rect":
            d.rectangle([p[1], p[2], p[3], p[4]], fill=p[5], outline=p[6])
        elif kind == "oval":
            d.ellipse([p[1], p[2], p[3], p[4]], fill=p[5], outline=p[6])
        elif kind == "poly":
            d.polygon(p[1], fill=p[2], outline=p[3])
        elif kind == "text":
            try:
                font = ImageFont.load_default(size=p[5])
            except TypeError:
                font = ImageFont.load_default()
            d.text((p[1], p[2]), p[3], fill=p[4], anchor=anchors[p[6]],
                   font=font)
    im.save(path)


# ====================================================================== app
class App:
    def __init__(self, root, game, debug=False):
        import tkinter as tk
        self.root, self.game, self.debug = root, game, debug
        root.title("Lane game")
        root.resizable(False, False)
        self.cv = tk.Canvas(root, width=W, height=H, bg="#0b0614",
                            highlightthickness=0)
        self.cv.pack()
        self.aim, self.sel, self.msg = 1, None, ""
        self.frames, self.fi, self.frame, self.anim = [], 0, None, False
        self.cv.bind("<Motion>", self.on_move)
        self.cv.bind("<Button-1>", self.on_click)
        root.bind("<Key>", self.on_key)
        self.render()

    def ui(self):
        g = self.game
        lines = [f"seed {g.seed}   turn {g.turn}   anim {self.anim}",
                 f"hp you {g.hp['you']}  foe {g.hp['foe']}   "
                 f"shield lane {g.shield + 1}   foe lane {g.foe_lane + 1}",
                 f"last enemy action: {g.last_foe}",
                 f"aim lane {self.aim + 1}   card {self.sel}",
                 f"shots: {len(g.shots)}"]
        for s in g.shots[:6]:
            lines.append(f"  {s['owner']} {CARDS[s['card']][0]} lane "
                         f"{s['lane'] + 1} slot {s['slot']} dmg {s['dmg']}")
        return {"aim": self.aim, "sel": self.sel, "msg": self.msg,
                "debug": self.debug, "debug_lines": lines}

    def render(self):
        snap = self.frame or self.game.snapshot()
        draw_tk(self.cv, build_scene(snap, self.ui()))

    # ---- input
    def on_move(self, e):
        lane = lane_at(e.x, e.y)
        if lane != self.aim:
            self.aim = lane
            if not self.anim:
                self.render()

    def on_click(self, e):
        for i in range(3):                           # a card?
            if (CARD_X[i] <= e.x <= CARD_X[i] + CARD_W
                    and CARD_Y - 8 <= e.y <= CARD_Y + CARD_H):
                self.sel = i
                self.msg = f"{CARDS[i][0]} ready: click a lane"
                self.render()
                return
        if e.y > FAR_Y - 20:
            self.cast(lane_at(e.x, e.y))

    def cast(self, lane):
        if self.anim or self.game.over:
            return
        if self.sel is None:
            self.msg = "pick a card first (keys 1-3, or click a card)"
            self.render()
            return
        self.act(("cast", self.sel, lane))

    def on_key(self, e):
        k = e.keysym.lower()
        if k in ("q", "escape"):
            self.root.destroy()
        elif k == "f1":
            self.debug = not self.debug
            self.render()
        elif k == "r":
            self.game = Game(self.game.seed + 1 if getattr(
                self, "_fixed", False) else None)
            self.frame, self.msg, self.sel, self.anim = None, "", None, False
            self.render()
        elif k in ("1", "2", "3"):
            self.sel = int(k) - 1
            self.msg = f"{CARDS[self.sel][0]} ready: click a lane"
            self.render()
        elif k == "a":
            self.act(("shield", -1))
        elif k == "d":
            self.act(("shield", 1))
        elif k == "space":
            self.act(("wait",))

    # ---- playing a turn
    def act(self, action):
        if self.anim or self.game.over:
            return
        try:
            self.frames = self.game.play_turn(action)
        except Exception as ex:                      # show it, don't hang
            import traceback
            traceback.print_exc()
            self.msg = f"error: {ex}"
            self.render()
            return
        self.fi, self.anim = 0, True
        self._step()

    def _step(self):
        self.frame = self.frames[self.fi]
        for line in self.frame["events"]:
            print(f"[turn {self.frame['turn']}] {line}")
        if self.frame["events"]:
            self.msg = self.frame["events"][-1]
        self.render()
        self.fi += 1
        if self.fi < len(self.frames):
            self.root.after(FRAME_MS, self._step)
        else:
            self.root.after(FRAME_MS, self._done)

    def _done(self):
        self.anim, self.frame = False, None
        if self.game.over:
            print(f"game over: {self.game.winner}")
        self.render()


# ===================================================================== tests
def selftest(n):
    """Random games, no window: the rules must always hold together."""
    import collections
    wins, turns, hits = collections.Counter(), [], collections.Counter()
    for seed in range(n):
        g = Game(seed)
        prng = random.Random(seed + 10 ** 6)
        while not g.over:
            r = prng.random()
            if r < 0.6:
                act = ("cast", prng.randrange(3), prng.randrange(LANES))
            elif r < 0.85:
                act = ("shield", prng.choice((-1, 1)))
            else:
                act = ("wait",)
            frames = g.play_turn(act)
            for f in frames:
                assert 0 <= f["hp"]["you"] <= MAX_HP, f
                assert 0 <= f["hp"]["foe"] <= MAX_HP, f
                assert 0 <= f["shield"] < LANES and 0 <= f["foe_lane"] < LANES
                for s in f["shots"]:
                    assert -1 <= s["slot"] <= ROWS, s
                    assert s["dmg"] > 0 and 0 <= s["lane"] < LANES, s
                for e in f["events"]:
                    hits[e.split()[0] + " " + e.split()[1]] += 1
            assert g.turn <= MAX_TURNS + 1
        wins[g.winner] += 1
        turns.append(g.turn)
    print(f"{n} random games: {dict(wins)}   average length "
          f"{sum(turns) / len(turns):.1f} turns, longest {max(turns)}")
    # a few rules, spelled out
    g = Game(0)
    g.foe_decide = lambda: ("wait",)
    g.foe_lane = 1
    g.play_turn(("cast", 0, 1))                      # bolt: slot 0
    assert g.shots and g.shots[0]["slot"] == 0
    g.play_turn(("wait",))                           # 3 slots
    assert g.shots[0]["slot"] == 3
    g.play_turn(("wait",))                           # 6: reaches the enemy
    assert g.hp["foe"] == MAX_HP - 1 and not g.shots, (g.hp, g.shots)
    g = Game(0)
    g.foe_decide = lambda: ("wait",)
    g.foe_lane = 0
    g.play_turn(("cast", 0, 2))
    g.play_turn(("wait",))
    g.play_turn(("wait",))
    assert g.hp["foe"] == MAX_HP, "a shot into an empty lane must miss"
    g = Game(0)                                      # shield blocks, else hurt
    g.shield = 1
    seq = iter([("cast", 0, 1), ("wait",), ("wait",)])
    g.foe_decide = lambda: next(seq)
    for _ in range(3):
        g.play_turn(("wait",))
    assert g.hp["you"] == MAX_HP, "shield lane must block"
    g = Game(0)
    g.shield = 0
    seq = iter([("cast", 0, 1), ("wait",), ("wait",)])
    g.foe_decide = lambda: next(seq)
    for _ in range(3):
        g.play_turn(("wait",))
    assert g.hp["you"] == MAX_HP - 1, "an unshielded lane must hurt"
    g = Game(0)                                      # fire beats bolt
    seqs = iter([("cast", 1, 0), ("wait",), ("wait",), ("wait",)])
    g.foe_decide = lambda: next(seqs)
    g.play_turn(("cast", 0, 0))
    g.play_turn(("wait",))
    assert not [s for s in g.shots if s["card"] == 0], g.shots
    print("rule checks: ok")


def sample_game():
    g = Game(3)
    g.foe_lane = 1
    for act in (("cast", 2, 1), ("cast", 1, 0), ("shield", 1),
                ("cast", 0, 2)):
        g.play_turn(act)
    return g


def main():
    ap = argparse.ArgumentParser(description="a small lane card game")
    ap.add_argument("--seed", type=int, help="fix the enemy's choices")
    ap.add_argument("--debug", action="store_true", help="show debug panel")
    ap.add_argument("--test", nargs="?", const=2000, type=int, metavar="N",
                    help="run N random games with no window")
    ap.add_argument("--png", metavar="FILE",
                    help="save a picture of a sample position and exit")
    args = ap.parse_args()
    if args.test is not None:
        selftest(args.test)
        return
    if args.png:
        g = sample_game()
        render_png(build_scene(g.snapshot(), {"aim": 1, "sel": 1,
                                              "msg": "sample position"}),
                   args.png)
        print("saved", args.png)
        return
    import tkinter as tk
    root = tk.Tk()
    app = App(root, Game(args.seed), args.debug)
    app._fixed = args.seed is not None
    root.mainloop()


if __name__ == "__main__":
    main()
