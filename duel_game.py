"""Turn-based duel rules, simulation, and pixel-art rendering."""
import random

# ------------------------------------------------------------------ duel
# A tiny fighting game, as a pure integer simulation. It is turn based: each
# turn both fighters who are free pick one move, and every move takes a whole
# number of turns. The same picks always give the same fight on every laptop,
# so players only send their picks (one small message per pick). Nothing in
# here touches Tk or the network.
DUEL_W = 10                  # the arena is a row of tiles 0..DUEL_W
DUEL_HP = 5
DUEL_START = (3, 7)
DUEL_MAX_ROUNDS = 25         # turns; then whoever has more HP wins
DUEL_SUB = 8                 # animation frames drawn per turn

# Rules: turns = how many turns it takes, reach = how many tiles away it can
# hit, dmg = damage. The su/act/rec/steps numbers are only for the drawing.
DUEL_MOVES = {
    "jab":     dict(kind="strike", turns=1, reach=1, dmg=1,
                    su=3, act=2, rec=4,
                    help="1 turn, hits the 1 tile in front, 1 damage. Beats "
                         "grab, and cancels a heavy wind-up. If it's blocked "
                         "you lose your next turn."),
    "heavy":   dict(kind="strike", turns=2, reach=2, dmg=2,
                    su=7, act=3, rec=8,
                    help="2 turns (wind up, then strike), hits the 2 tiles in "
                         "front, 2 damage. A hit on the wind-up cancels it. "
                         "If it's blocked you lose your next turn."),
    "grab":    dict(kind="throw", turns=1, reach=1, dmg=0,
                    su=2, act=2, rec=3,
                    help="1 turn, hits the 1 tile in front, no damage. Beats "
                         "block. If it lands, they lose 2 turns. If it fails, "
                         "you lose 3 turns. A stunned fighter can be grabbed "
                         "once before they recover. "
                         "Loses to jab and heavy."),
    "block":   dict(kind="guard", turns=1, su=1, act=7, rec=3,
                    help="1 turn, covers your own tile. Stops jab and heavy, "
                         "and then the attacker loses their next turn. Loses "
                         "to grab. If nothing was blocked you lose your next "
                         "turn."),
    "advance": dict(kind="walk", turns=1, dir=1, steps=2, su=0, act=0, rec=1,
                    help="1 turn, step 1 tile forward."),
    "dash":    dict(kind="walk", turns=2, dir=1, distance=3, first=2,
                    steps=4, su=0, act=0, rec=1,
                    help="2 turns: move 2 tiles forward now and 1 more next turn."),
    "retreat": dict(kind="walk", turns=1, dir=-1, steps=2, su=0, act=0, rec=1,
                    help="1 turn, step 1 tile back."),
    "dash_back": dict(kind="walk", turns=2, dir=-1, distance=3, first=2,
                      steps=4, su=0, act=0, rec=1,
                      help="2 turns: move 2 tiles back now and 1 more next turn."),
    "wait":    dict(kind="idle", turns=1, su=0, act=0, rec=3,
                    help="1 turn, do nothing."),
}
DUEL_ORDER = ("jab", "heavy", "grab", "block", "wait")
DUEL_MOVE_CHOICES = ("advance", "dash")

# What each fighter does on one turn. "wind" and "strike" are the two halves
# of a heavy attack; "stunned" is a turn lost.
_ATTACKS = {"jab": ("jab", 1, 1), "strike": ("heavy", 2, 2),
            "grab": ("grab", 1, 0)}          # act: (art move, reach, damage)


def _anim_total(m):
    d = DUEL_MOVES[m]
    return d["steps"] + d["rec"] if d["kind"] == "walk" \
        else d["su"] + d["act"] + d["rec"]


def duel_new():
    """A fresh fight. Fighter 0 starts on the left."""
    def fighter(x, f):
        return {"x": x, "f": f, "hp": DUEL_HP, "move": None, "t": 0,
                "stun": 0, "stun_grabbed": False,
                "grab_protected": False}
    return {"p": [fighter(DUEL_START[0], 1), fighter(DUEL_START[1], -1)],
            "round": 0, "over": False, "winner": None}


def duel_free(fi):
    return fi["stun"] == 0 and fi["move"] is None


def duel_need(S):
    """Which fighters must pick a move this turn. Anyone winding up or
    stunned has no choice, so they send nothing."""
    return [i for i in (0, 1) if duel_free(S["p"][i])]


def duel_turn_lead(S, i):
    """Positive means fighter i has fewer committed/lost turns remaining."""
    def unavailable(fi):
        return fi["stun"] + (
            1 if fi["move"] in ("heavy", "dash", "dash_back") else 0)
    return unavailable(S["p"][1 - i]) - unavailable(S["p"][i])


def duel_frame_lead(S, i):
    """Turn advantage expressed in the duel's animation frames."""
    return duel_turn_lead(S, i) * DUEL_SUB


def duel_movement_action(direction, action):
    """Resolve the selected relative direction and movement type."""
    if direction not in ("forward", "back"):
        raise ValueError("movement direction must be forward or back")
    if action not in DUEL_MOVE_CHOICES:
        raise ValueError("movement type must be advance or dash")
    if direction == "forward":
        return action
    return "retreat" if action == "advance" else "dash_back"


def duel_move_tiles(m, x, f):
    """The tiles a move affects for a fighter on tile x facing f (+1 means
    the right). Returns (tiles, kind) for the hover highlight."""
    d = DUEL_MOVES.get(m)
    if not d:
        return [], None
    k = d["kind"]
    if k == "walk":
        distance = d.get("distance", 1)
        tiles = [x + d["dir"] * f * n for n in range(1, distance + 1)]
        kind = "move"
    elif k in ("strike", "throw"):
        tiles = [x + f * j for j in range(1, d["reach"] + 1)]
        kind = "attack" if k == "strike" else "grab"
    elif k == "guard":
        tiles, kind = [x], "guard"
    else:
        return [], None
    return [t for t in tiles if 0 <= t <= DUEL_W], kind


def _art_t(fi):
    """Where the drawing of a held move is (a heavy wind-up stays raised)."""
    return DUEL_MOVES["heavy"]["su"] if fi["move"] == "heavy" else 0


def duel_frame(S):
    """A plain snapshot of the fight for drawing."""
    out = []
    for fi in S["p"]:
        out.append({"x": fi["x"], "f": fi["f"], "hp": fi["hp"],
                    "move": fi["move"], "stun": fi["stun"],
                    "t": _art_t(fi), "ko": fi["hp"] <= 0, "ev": [],
                    "guard": False, "active": False, "reach": 0})
    return {"p": out, "ev": []}


def _hit_sub(am, lo, hi):
    """The animation frame (1..DUEL_SUB) where a hit shows up: the first one
    past the start-up of the move."""
    su = DUEL_MOVES[am]["su"]
    for k in range(1, DUEL_SUB + 1):
        if lo + (hi - lo) * k // DUEL_SUB > su:
            return k
    return DUEL_SUB


def duel_round(S, choices):
    """Play one turn. choices: {fighter index: move name} for every fighter
    in duel_need(S); a bad or missing choice becomes 'wait'.
    Returns (frames, events). frames[0] is the start of the turn."""
    P = S["p"]
    # ---- what everyone does this turn
    acts = [None, None]
    for i in (0, 1):
        fi = P[i]
        if fi["stun"] > 0:
            acts[i] = "stunned"
        elif fi["move"] == "heavy":
            acts[i] = "strike"                   # second half of the heavy
        elif fi["move"] in ("dash", "dash_back"):
            acts[i] = "dash_follow"
        else:
            m = choices.get(i)
            m = m if m in DUEL_MOVES else "wait"
            acts[i] = "wind" if m == "heavy" else m
    start = [dict(P[i]) for i in (0, 1)]
    ev = []
    # ---- 1. walking (a step that would make them touch is cancelled)
    step = [0, 0]
    for i in (0, 1):
        if acts[i] in ("advance", "dash", "retreat", "dash_back"):
            move = DUEL_MOVES[acts[i]]
            distance = move.get("first", move.get("distance", 1))
            step[i] = move["dir"] * P[i]["f"] * distance
        elif acts[i] == "dash_follow":
            move = DUEL_MOVES[P[i]["move"]]
            step[i] = move["dir"] * P[i]["f"]
    nx = [min(DUEL_W, max(0, P[i]["x"] + step[i])) for i in (0, 1)]
    if nx[1] - nx[0] < 1:
        for i in (0, 1):
            if step[i] * P[i]["f"] > 0:          # moving toward the other
                nx[i] = P[i]["x"]
    gap = nx[1] - nx[0]
    start_gap = P[1]["x"] - P[0]["x"]
    # ---- 2. who hits whom, all decided from this turn's picks
    reach = [_ATTACKS[a][1] if a in _ATTACKS else 0 for a in acts]
    land = [
        a in _ATTACKS and (start_gap if a == "grab" else gap) <= reach[i]
        for i, a in enumerate(acts)
    ]
    hurt = [0, 0]                                # damage taken
    stun = [0, 0]                                # turns lost from now on
    cut = [False, False]                         # move cancelled
    grabbed = [False, False]                     # successful grab by fighter
    grabbed_target = [False, False]
    seen = [None, None]                          # animation frame it shows on
    blocked = [False, False]                     # a block that stopped a hit
    for a in (0, 1):
        if not land[a]:
            continue
        d = 1 - a
        act = acts[a]
        k = _hit_sub(_ATTACKS[act][0],
                     DUEL_MOVES["heavy"]["su"] if act == "strike" else 0,
                     _anim_total(_ATTACKS[act][0]))
        if act == "grab":
            if (acts[d] in ("jab", "wind", "strike")
                    or (P[d].get("grab_protected", False)
                        and P[d]["stun"] == 0)
                    or (P[d]["stun"] > 0
                        and P[d].get("stun_grabbed", False))):
                continue                         # attacks beat a grab
            if land[d]:
                if a == 0:
                    ev.append((k, "tech"))       # both grabbed: nothing
                continue
            grabbed[a] = True
            grabbed_target[d] = True
            nx[d] = P[d]["x"]
            stun[d] = max(stun[d], 2)
            P[d]["grab_protected"] = True
            if P[d]["stun"] > 0:
                P[d]["stun_grabbed"] = True
            cut[d] = True
            seen[d] = k
            ev.append((k, "grab:%d" % d))
        elif acts[d] == "block":
            blocked[d] = True
            ev.append((k, "blocked:%d" % d))
            stun[a] = max(stun[a], 1)            # a blocked attack: you stall
            seen[a] = k
        else:
            hurt[d] += _ATTACKS[act][2]
            cut[d] = True
            seen[d] = k
            ev.append((k, "hit:%d:%s" % (d, _ATTACKS[act][0])))
    for i in (0, 1):                             # a block that stops nothing
        if acts[i] == "block" and not blocked[i] and not stun[i]:
            stun[i] = 1                              # costs the next turn
            ev.append((DUEL_SUB, "whiff:%d" % i))
    for i in (0, 1):
        if acts[i] == "grab" and not grabbed[i]:
            penalty = 4 if acts[1 - i] == "jab" else 3
            stun[i] = max(stun[i], penalty)
            ev.append((DUEL_SUB, f"grab_fail:{i}:{penalty}"))
    # ---- 3. apply it
    S["round"] += 1
    for i in (0, 1):
        fi = P[i]
        fi["x"] = nx[i]
        fi["hp"] = max(0, fi["hp"] - hurt[i])
        if acts[i] == "stunned":
            fi["stun"] -= 1
        fi["stun"] = max(fi["stun"], stun[i])
        if acts[i] != "stunned" and not grabbed_target[i]:
            fi["stun_grabbed"] = False
            fi["grab_protected"] = False
        if acts[i] == "wind" and not cut[i]:
            fi["move"], fi["t"] = "heavy", 1     # strikes next turn
        elif acts[i] in ("dash", "dash_back") and not cut[i]:
            fi["move"], fi["t"] = acts[i], 1     # one more tile next turn
        else:
            fi["move"], fi["t"] = None, 0
    a, b = P[0]["hp"], P[1]["hp"]
    if a <= 0 or b <= 0:
        S["over"] = True
        S["winner"] = -1 if a <= 0 and b <= 0 else (1 if a <= 0 else 0)
    elif S["round"] >= DUEL_MAX_ROUNDS:
        S["over"] = True
        S["winner"] = -1 if a == b else (0 if a > b else 1)
    # ---- 4. the pictures: DUEL_SUB frames that play the turn out
    flat = [e for (_, e) in sorted(ev, key=lambda p: p[0])]
    frames = [_turn_frame(0, start, acts, hurt, seen, nx, P, ev)]
    frames += [_turn_frame(k, start, acts, hurt, seen, nx, P, ev)
               for k in range(1, DUEL_SUB + 1)]
    return frames, flat


def _turn_frame(k, st, acts, hurt, seen, nx, P, ev):
    """One animation frame (k = 0..DUEL_SUB) of a turn."""
    out = []
    last = k == DUEL_SUB
    for i in (0, 1):
        a_ = acts[i]
        if a_ == "wind":
            am, lo, hi = "heavy", 0, DUEL_MOVES["heavy"]["su"]
        elif a_ == "strike":
            am, lo, hi = "heavy", DUEL_MOVES["heavy"]["su"], \
                _anim_total("heavy")
        elif a_ == "dash_follow":
            am, lo, hi = st[i]["move"], 0, _anim_total(st[i]["move"])
        elif a_ in DUEL_MOVES and a_ != "wait":
            am, lo, hi = a_, 0, _anim_total(a_)
        else:
            am, lo, hi = None, 0, 0
        x = st[i]["x"] + (nx[i] - st[i]["x"]) * k / DUEL_SUB
        hit = seen[i] is not None and k >= seen[i]
        hp = max(0, st[i]["hp"] - (hurt[i] if hit else 0))
        if last:                                 # the state after the turn
            move, t = P[i]["move"], _art_t(P[i])
            hp = P[i]["hp"]
            reeling = P[i]["stun"] > 0
        else:
            move, t = am, lo + (hi - lo) * k // DUEL_SUB
            reeling = a_ == "stunned" or hit
        if reeling:
            move, t = None, 0
        out.append({"x": x, "f": P[i]["f"], "hp": hp, "move": move,
                    "stun": 1 if reeling else 0, "t": t, "ko": hp <= 0,
                    "ev": [], "guard": False, "active": False, "reach": 0})
    fr = {"p": out, "ev": []}
    if k:
        fr["ev"] = [e for (n, e) in ev if n == k]
    return fr


# ------------------------------------------------------------- duel art
# Nidhogg-1 look: flat-colour silhouette fencers (yellow vs orange) on
# posterised skies in front of black scenery. This part draws nothing
# itself: it turns a fight frame into a list of (x, y, w, h, colour)
# pixel rectangles on a small logical canvas, and the window scales them
# up. No Tk in here, so it can be tested by saving pictures.
DUEL_LW, DUEL_LH = 200, 100          # logical canvas, in pixels
DUEL_GY = 76                         # the ground line
DUEL_U = 16                          # logical pixels per space
DUEL_MX = 20                         # left margin
DUEL_COLS = ("#ffd21f", "#ff7a1a")   # yellow, orange
DUEL_STAGES = (
    dict(name="castle", sky=("#3b1f63", "#6f3482", "#c04a7e"), sun="#ffb347",
         sunat=(148, 30, 13), sil="#10081a", edge="#ff9a3c"),
    dict(name="wilds", sky=("#0f3d3b", "#17655c", "#2f9470"), sun="#eaf7a4",
         sunat=(40, 28, 11), sil="#04201e", edge="#b7f36b"),
    dict(name="dusk", sky=("#192a5f", "#2f50a3", "#6c93e6"), sun="#fff1cb",
         sunat=(120, 24, 9), sil="#070c24", edge="#8fd0ff"),
    dict(name="embers", sky=("#4b1016", "#8e1e1e", "#d24a20"), sun="#ffd9a3",
         sunat=(70, 34, 15), sil="#1c0507", edge="#ff6a3a"),
)
_BG_CACHE = {}


def duel_stage_for(gid, rnd):
    """Same stage on both laptops; the scenery changes every 10 rounds."""
    try:
        base = int(gid[:4], 16)
    except (TypeError, ValueError):
        base = 0
    return (base + (rnd - 1) // 10) % len(DUEL_STAGES)


def _lerp(a, b, u):
    return int(round(a + (b - a) * u))


def _line(x0, y0, x1, y1, th=1):
    """Pixels of a thick line (Bresenham with a square brush)."""
    pts = set()
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    for _ in range(600):
        for ox in range(th):
            for oy in range(th):
                pts.add((x0 + ox, y0 + oy))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def _runs(pts, colour):
    """Merge pixels into horizontal runs (fewer rectangles to draw)."""
    out, run = [], None
    for (x, y) in sorted(pts, key=lambda p: (p[1], p[0])):
        if run and run[1] == y and run[0] + run[2] == x:
            run[2] += 1
        else:
            if run:
                out.append((run[0], run[1], run[2], 1, colour))
            run = [x, y, 1]
    if run:
        out.append((run[0], run[1], run[2], 1, colour))
    return out


def _disc(cx, cy, r, colour):
    out = []
    for dy in range(-r, r + 1):
        w = int((r * r - dy * dy) ** 0.5)
        out.append((cx - w, cy + dy, 2 * w + 1, 1, colour))
    return out


def _scenery(stage):
    """Black silhouettes behind the fighters, built once per stage."""
    s = DUEL_STAGES[stage]
    sil, sky = s["sil"], s["sky"][2]
    gy = DUEL_GY
    out = []
    seed = [stage * 7919 + 13]

    def rnd(n):
        seed[0] = (seed[0] * 1103515245 + 12345) & 0x7FFFFFFF
        return (seed[0] >> 8) % n
    if s["name"] == "castle":
        out.append((0, 52, DUEL_LW, gy - 52, sil))
        for x in range(0, DUEL_LW, 10):
            out.append((x, 48, 6, 4, sil))
        for tx, tw, top in ((14, 16, 22), (118, 22, 14), (176, 14, 30)):
            out.append((tx, top, tw, 52 - top, sil))
            for x in range(tx, tx + tw, 4):
                out.append((x, top - 3, 2, 3, sil))
            out.append((tx + tw // 2 - 1, top + 8, 2, 4, sky))      # lit window
    elif s["name"] == "wilds":
        for x in range(0, DUEL_LW, 4):
            h = 54 + rnd(6)
            out.append((x, h, 4, gy - h, sil))
        for tx in (12, 52, 96, 140, 182):
            h = 14 + rnd(10)
            for row in range(h):
                w = 1 + row // 2
                out.append((tx - w // 2, 54 - h + row, w, 1, sil))
            out.append((tx - 1, 54, 2, 4, sil))
    elif s["name"] == "dusk":
        x = 0
        while x < DUEL_LW:
            w, h = 8 + rnd(10), 22 + rnd(24)
            out.append((x, 58 - h + 14, w, gy - (58 - h + 14), sil))
            for wy in range(58 - h + 18, 56, 6):
                if rnd(3) == 0:
                    out.append((x + 2, wy, 2, 3, sky))
            x += w
    else:                                                  # embers: ruins
        out.append((0, 56, DUEL_LW, gy - 56, sil))
        for cx in (10, 44, 80, 128, 160, 188):
            h = 14 + rnd(20)
            out.append((cx, 56 - h, 6, h, sil))
            out.append((cx - 2, 56 - h - 2, 10, 3, sil))
            if rnd(2):
                out.append((cx + 2, 56 - h - 6, 3, 4, sil))
    return out


def duel_bg_rects(stage):
    """Sky, sun, scenery and ground for one stage (cached)."""
    if stage in _BG_CACHE:
        return _BG_CACHE[stage]
    s = DUEL_STAGES[stage]
    out = [(0, 0, DUEL_LW, 26, s["sky"][0]), (0, 26, DUEL_LW, 22, s["sky"][1]),
           (0, 48, DUEL_LW, DUEL_GY - 48, s["sky"][2])]
    out += _disc(*s["sunat"][:2], s["sunat"][2], s["sun"])
    out += _scenery(stage)
    out.append((0, DUEL_GY, DUEL_LW, DUEL_LH - DUEL_GY, s["sil"]))
    out.append((0, DUEL_GY, DUEL_LW, 1, s["edge"]))
    _BG_CACHE[stage] = out
    return out


# ------------------------------------------------------------- fighters
def _phase(move, t):
    """('su'|'act'|'rec', progress 0..1, step inside the active part)."""
    d = DUEL_MOVES[move]
    if d["kind"] == "walk":
        return "walk", min(1.0, t / d["steps"]), t
    su, act, rec = d["su"], d["act"], d["rec"]
    if t <= su:
        return "su", (t / su if su else 1.0), 0
    if t <= su + act:
        return "act", (t - su) / act, t - su - 1
    return "rec", min(1.0, (t - su - act) / rec) if rec else 1.0, 0


def _pose(p, phase):
    """Where every limb goes, in pixels from the fighter's feet, with
    +x toward the opponent and -y up."""
    m = p["move"]
    R = DUEL_MOVES[m]["reach"] * DUEL_U if m and "reach" in DUEL_MOVES[m] else 0
    q = dict(lean=1, ff=5, bf=-4, ffy=0, bfy=0, drop=1 if phase % 8 < 4 else 0,
             hand=(8, -18), tip=(20, -22), bhand=(-4, -17), blade=None,
             two=False)
    if p["stun"] > 0 and m is None:
        q.update(lean=-4, ff=3, bf=-6, drop=1, hand=(1, -9), tip=(8, -2),
                 bhand=(-9, -16))
        return q
    if m is None or m == "wait":
        return q
    kind = DUEL_MOVES[m]["kind"]
    ph, u, k = _phase(m, p["t"])
    if kind == "walk":
        sw = 3 if (p["t"] % 2) else -3
        q.update(ff=5 + sw, bf=-4 - sw, ffy=-1 if sw > 0 else 0,
                 bfy=-1 if sw < 0 else 0, drop=0,
                 lean=2 if m in ("advance", "dash") else -1)
    elif m == "jab":
        if ph == "su":
            hx = _lerp(8, 1, u)
            q.update(lean=_lerp(1, -2, u), ff=_lerp(5, 3, u), hand=(hx, -17),
                     tip=(hx + 9, -17))
        elif ph == "act":
            q.update(lean=4, ff=9, bf=-5, drop=1, hand=(13, -17),
                     tip=(max(R, 20), -17))
        else:
            hx = _lerp(13, 8, u)
            q.update(lean=_lerp(4, 1, u), ff=_lerp(9, 5, u), hand=(hx, -17),
                     tip=(_lerp(R, hx + 12, u), _lerp(-17, -22, u)))
    elif m == "heavy":
        if ph == "su":
            hand = (_lerp(6, 3, u), _lerp(-20, -31, u))
            q.update(lean=_lerp(0, -3, u), ff=4, bf=-5, hand=hand,
                     tip=(hand[0] + 1, hand[1] - 15),
                     bhand=(hand[0] - 2, hand[1] + 3), two=True)
        elif ph == "act":
            s = min(1.0, (k + 1) / DUEL_MOVES[m]["act"])
            hand = (_lerp(5, 9, s), _lerp(-30, -18, s))
            q.update(lean=_lerp(0, 4, s), ff=_lerp(5, 9, s), bf=-5, drop=1,
                     hand=hand, tip=(_lerp(10, R, s), _lerp(-40, -5, s)),
                     bhand=(hand[0] - 2, hand[1] + 2), two=True)
        else:
            q.update(lean=_lerp(4, 1, u), ff=_lerp(9, 5, u),
                     drop=_lerp(2, 0, u), hand=(9, -14),
                     tip=(_lerp(int(R * 0.8), 14, u), _lerp(-4, -16, u)))
    elif m == "grab":
        if ph == "su":
            q.update(lean=_lerp(1, 3, u), ff=6, hand=(_lerp(7, 11, u), -18),
                     tip=None, bhand=(_lerp(2, 8, u), -15))
        elif ph == "act":
            q.update(lean=5, ff=10, bf=-5, drop=1, hand=(R - 1, -17),
                     tip=None, bhand=(R - 3, -14))
        else:
            q.update(lean=_lerp(5, 1, u), ff=_lerp(10, 5, u),
                     drop=_lerp(2, 0, u), hand=(_lerp(R - 1, 8, u), -17),
                     tip=None, bhand=(_lerp(R - 3, -4, u), -15))
    elif m == "block":
        up = {"su": 0.5 + 0.5 * u, "act": 1.0, "rec": 1.0 - u}[ph]
        q.update(lean=0, ff=4, hand=(9, -15), tip=None,
                 blade=((9, -3), (9, -3 - int(31 * up))), bhand=(2, -15))
    return q


def _fighter(p, cx, colour, phase, flash, goal=False):
    """Pixel rectangles of one fencer."""
    gy, f = DUEL_GY, p["f"]

    def X(dx):
        return cx + f * dx

    def Y(dy):
        return gy - 1 + dy
    col = "#ffffff" if flash else colour
    pts, sword = set(), set()
    if p["ko"]:                                     # lying in the blood
        pts |= _line(X(-14), Y(-3), X(-4), Y(-3), 3)
        pts |= _line(X(-4), Y(-2), X(5), Y(-1), 2)
        pts |= _line(X(-12), Y(-5), X(-8), Y(-1), 2)
        for dx in range(-20, -14):
            for dy in range(-6, -1):
                if not (dx in (-20, -19) and dy in (-6, -5)):
                    pts.add((X(dx), Y(dy)))
        sword |= _line(X(7), Y(-1), X(20), Y(-1), 1)
        out = _runs(pts, col) + _runs(sword, col)
        out.append((cx - 14, gy, 28, 1, colour))     # pool
        out.append((cx - 9, gy + 1, 18, 1, colour))
        return out
    q = _pose(p, phase)
    drop = q["drop"]
    hip = (q["lean"] // 2, -12 + drop)
    sho = (q["lean"], -21 + drop)
    head = (q["lean"] + 1, -26 + drop)
    pts |= _line(X(hip[0]), Y(hip[1]), X(sho[0]), Y(sho[1]), 3)
    for (fx_, fy_) in ((q["ff"], q["ffy"]), (q["bf"], q["bfy"])):
        pts |= _line(X(hip[0]), Y(hip[1]), X(fx_), Y(fy_), 2)
        pts.add((X(fx_ + 1), Y(fy_)))
        pts.add((X(fx_ + 2), Y(fy_)))
    pts |= _line(X(sho[0]), Y(sho[1] + 1), X(q["hand"][0]), Y(q["hand"][1]), 2)
    pts |= _line(X(sho[0]), Y(sho[1] + 1), X(q["bhand"][0]),
                 Y(q["bhand"][1]), 2)
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx) + abs(dy) < 4:
                pts.add((X(head[0] + dx), Y(head[1] + dy)))
    if q["blade"]:
        (bx0, by0), (bx1, by1) = q["blade"]
        sword |= _line(X(bx0), Y(by0), X(bx1), Y(by1), 1)
        for dx in (-2, -1, 0, 1, 2):
            sword.add((X(q["hand"][0] + dx), Y(q["hand"][1] - 1)))
    elif q["tip"]:
        sword |= _line(X(q["hand"][0]), Y(q["hand"][1]),
                       X(q["tip"][0]), Y(q["tip"][1]),
                       2 if p["move"] == "heavy" else 1)
        for dy in (-1, 0, 1):
            sword.add((X(q["hand"][0]), Y(q["hand"][1] + dy)))
    out = []
    if p["move"] == "heavy" and _phase("heavy", p["t"])[0] == "act":
        R = DUEL_MOVES["heavy"]["reach"] * DUEL_U     # faint slash trail
        trail = set()
        for j in range(_phase("heavy", p["t"])[2]):
            s_ = (j + 1) / DUEL_MOVES["heavy"]["act"]
            hx, hy = _lerp(5, 9, s_), _lerp(-30, -18, s_)
            tx, ty = _lerp(10, R, s_), _lerp(-40, -5, s_)
            trail |= {pt for n, pt in enumerate(sorted(_line(
                X(hx), Y(hy), X(tx), Y(ty), 1))) if n % 2 == 0}
        out += _runs(trail, "#ffffff")
    out += _runs(pts, col) + _runs(sword, col)
    if q["blade"] and p["move"] == "block" and _phase("block", p["t"])[0] \
            == "act" and phase % 4 < 2:               # parry shimmer
        out += _runs({(X(9 + 1), Y(by1 + 2 + j)) for j in range(0, 20, 3)},
                     "#ffffff")
    return out


# ------------------------------------------------------------- effects
class DuelFx:
    """Blood, sparks, screen shake, white flashes. Only for looks, so
    nothing here has to match between laptops."""

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.parts = []          # [x, y, vx, vy, colour, size]
        self.splats = []         # blood left on the ground (x, y, colour)
        self.shake = 0
        self.flash = [0, 0]
        self.hold = 0            # extra frames of hit-stop
        self.ko_done = [False, False]
        self.stars = []          # [x, y, frames left] white impact flashes

    @staticmethod
    def _cx(p):
        return int(round(DUEL_MX + p["x"] * DUEL_U))

    def _burst(self, x, y, direction, n, colour, speed=2.4):
        for _ in range(n):
            self.parts.append([x + self.rng.uniform(-2, 2),
                               y + self.rng.uniform(-4, 4),
                               direction * self.rng.uniform(0.3, speed)
                               + self.rng.uniform(-0.4, 0.4),
                               -self.rng.uniform(0.2, speed + 0.8),
                               colour, 2 if self.rng.random() < 0.55 else 1])

    def on_frame(self, fr):
        P = fr["p"]
        for e in fr.get("ev", ()):
            b = e.split(":")
            if b[0] == "hit":
                d = int(b[1])
                a = 1 - d
                n = {"heavy": 44}.get(b[2], 20)
                self._burst(self._cx(P[d]), DUEL_GY - 18, P[a]["f"], n,
                            DUEL_COLS[d], 3.0)
                self.stars.append([self._cx(P[d]) - P[a]["f"] * 2,
                                   DUEL_GY - 18, 3])
                self.flash[d] = 3
                self.shake = max(self.shake, 6 if b[2] == "heavy" else 4)
                self.hold = max(self.hold, 3 if b[2] != "heavy" else 5)
            elif b[0] == "grab":
                d = int(b[1])
                self._burst(self._cx(P[d]), DUEL_GY - 18, P[1 - d]["f"], 8,
                            "#ffffff", 2.4)
                self.flash[d] = 3
                self.shake = max(self.shake, 3)
                self.hold = max(self.hold, 3)
            elif b[0] == "counter":
                d = int(b[1])
                self._burst(self._cx(P[d]), DUEL_GY - 22, P[1 - d]["f"], 12,
                            "#ffffff", 3.2)
                self.shake += 2
                self.hold += 2
            elif b[0] == "blocked":
                d = int(b[1])
                x = self._cx(P[d]) + P[d]["f"] * 10
                for c in ("#ffffff", "#ffe98a"):
                    self._burst(x, DUEL_GY - 22, -P[d]["f"], 6, c, 2.6)
                self.shake = max(self.shake, 2)
                self.hold = max(self.hold, 2)
            elif b[0] == "tech":
                x = (self._cx(P[0]) + self._cx(P[1])) / 2
                self._burst(x, DUEL_GY - 18, 1, 6, "#ffffff", 2)
                self._burst(x, DUEL_GY - 18, -1, 6, "#ffffff", 2)
        for i in (0, 1):
            if P[i]["ko"] and not self.ko_done[i]:
                self.ko_done[i] = True
                self._burst(self._cx(P[i]), DUEL_GY - 18, -P[i]["f"], 40,
                            DUEL_COLS[i], 3.2)
                self.shake = 9
                self.hold = 9

    def step(self):
        keep = []
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.28
            if p[1] >= DUEL_GY - 1:
                if len(self.splats) < 500:
                    self.splats.append((int(p[0]), DUEL_GY - 1
                                        - self.rng.randrange(2), p[4]))
            elif -5 < p[0] < DUEL_LW + 5:
                keep.append(p)
        self.parts = keep
        self.flash = [max(0, n - 1) for n in self.flash]
        self.stars = [[x, y, n - 1] for (x, y, n) in self.stars if n > 1]
        if self.shake:
            self.shake -= 1

    def offset(self):
        if not self.shake:
            return 0, 0
        s = 1 if self.shake % 2 else -1
        return s * min(2, 1 + self.shake // 4), (s if self.shake > 3 else 0)


def _hud(fr, goal):
    """Health bars (one block per HP) and the 'GO' arrow."""
    out = []
    for i in (0, 1):
        segs = fr["p"][i]["hp"]
        x0 = 6 if i == 0 else DUEL_LW - 6 - DUEL_HP * 18
        for n in range(DUEL_HP):
            xi = x0 + (n if i == 0 else DUEL_HP - 1 - n) * 18
            out.append((xi, 12, 16, 5, DUEL_COLS[i] if n < segs else "#1a1226"))
    if goal is not None:
        w, loser = goal
        x = 140 if w == 0 else 30
        d = 1 if w == 0 else -1
        pts = set()
        for dx in range(0, 18):
            for dy in range(-1, 2):
                pts.add((x + d * dx, 38 + dy))
        for j in range(0, 6):
            for dy in range(-j, j + 1):
                pts.add((x + d * (18 + 5 - j), 38 + dy))
        out += _runs(pts, DUEL_COLS[w])
    return out


DUEL_TILE_COLS = ("#2c2542", "#1f1a33")      # the two chessboard shades
DUEL_HL = {"attack": "#e8453c", "grab": "#b06bff", "move": "#4a8fe0",
           "guard": "#3fbf6a"}


def duel_tile_rects(hl=None):
    """The row of tiles under the fighters. hl = (tiles, kind) lights some
    of them up (hovering over a move)."""
    on = {}
    if hl:
        for t in hl[0]:
            on[t] = hl[1]
    out = []
    for t in range(DUEL_W + 1):
        x = DUEL_MX + t * DUEL_U - DUEL_U // 2
        kind = on.get(t)
        if kind:
            col = DUEL_HL[kind]
            out.append((x, DUEL_GY + 1, DUEL_U - 1, 8, col))
            out.append((x, DUEL_GY - 3, DUEL_U - 1, 3, col))   # a bar above
        else:
            out.append((x, DUEL_GY + 1, DUEL_U - 1, 8,
                        DUEL_TILE_COLS[t % 2]))
    return out


def duel_fg_rects(fr, fx, phase, goal=None):
    """Everything in front of the backdrop for one frame. goal is
    (winner, loser) once the match is over, to show the GO arrow."""
    out = [(x, y, 1, 1, c) for (x, y, c) in fx.splats]
    for i in (0, 1):
        p = fr["p"][i]
        out += _fighter(p, int(round(DUEL_MX + p["x"] * DUEL_U)),
                        DUEL_COLS[i], phase,
                        fx.flash[i] > 0)
    for (x, y, vx, vy, c, sz) in fx.parts:
        out.append((int(x), int(y), sz, sz, c))
    for (x, y, n) in fx.stars:                     # white impact cross
        r = 2 + n
        out += [(int(x) - r, int(y), 2 * r + 1, 1, "#ffffff"),
                (int(x), int(y) - r, 1, 2 * r + 1, "#ffffff")]
    out += _hud(fr, goal if phase % 6 < 4 else None)
    return out



__all__ = (
    "DUEL_W", "DUEL_HP", "DUEL_START", "DUEL_MAX_ROUNDS", "DUEL_SUB",
    "DUEL_MOVES", "DUEL_ORDER", "DUEL_MOVE_CHOICES", "duel_new",
    "duel_free", "duel_need", "duel_turn_lead", "duel_frame_lead",
    "duel_movement_action", "duel_move_tiles", "duel_frame", "duel_round",
    "DUEL_LW", "DUEL_LH", "DUEL_GY", "DUEL_U", "DUEL_MX",
    "DUEL_COLS", "DUEL_STAGES", "duel_stage_for", "duel_bg_rects",
    "DuelFx", "DUEL_TILE_COLS", "DUEL_HL", "duel_tile_rects",
    "duel_fg_rects",
)
