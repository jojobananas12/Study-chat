#!/usr/bin/env python3
"""
CASTLE MACRO - the strategy layer of a co-op "defend the keep" game.

Run it:
    python castle_macro.py              open the game window (hot-seat: one
                                        computer plays every seat; any seat
                                        can be a bot)
    python castle_macro.py --sim 200    play 200 bot games per player count
                                        and print balance + message numbers
    python castle_macro.py --test       run the built-in self checks

Needs only the Python standard library (the window needs Tk, which comes
with the normal python.org installers).

THE GAME IN SHORT
  2-5 players defend a keep against waves that walk in along six
  lanes (N, NE, SE, S, SW, NW). Each lane has 3 cells; cell 1 is next to
  the wall. Survive the boss on round 12. Each player owns one or more
  ROLES (Steward, Engineer, Slayer, Smith, Mage) and has a personal VAULT.

  Every round:
    1 income        the shared pool gets gold from the economy
    2 bank          players who don't petition get a guaranteed deposit
    3 petition      the rotating TREASURER splits the pool among requests
    4 vault         now that everyone sees what the pool paid for, players
                    put vault gold into their OWN projects (never refunded)
    5 map           heroes move / pick targets
    6 combat        spells, attacks, towers, enemies; then builds are placed
                    (map items exist from the next round)
  Personal upgrades (spells, weapons, build skill) work the moment they are
  fully funded. Map items (walls, towers, farms...) are paid into a budget
  and then BUILT by their owner during combat, so they appear next round.

  A real game would play a short mini-game per role in step 6; here a
  "band" (poor / okay / great) stands in for the mini-game score.
"""
import sys
import json
import math
import random
import hashlib
import argparse
import collections

# ======================================================================
#  DATA
# ======================================================================
# six lanes around a hexagonal keep, clockwise from the top
QUADS = ("N", "NE", "SE", "S", "SW", "NW")
BANDS = ("poor", "okay", "great")
LAST_ROUND = 12
KEEP_MAX = 20
START_POOL = 12
BASE_INCOME = 2                  # + INCOME_PER_PLAYER * players
INCOME_PER_PLAYER = 2
DEPOSIT_RATIO = 0.5              # bank deposit = this share of a fair share
VAULT_CAP_BASE = 18              # + VAULT_CAP_EXTRA per extra role owned
VAULT_CAP_EXTRA = 6
BUDGET_MAX = 30
PETITION_FALLBACK_DEPOSIT = True  # a petitioner who gets nothing keeps the deposit
MAX_WALL, MAX_PLATING, MAX_TIER = 3, 2, 2
CELL_MAX = 3                     # buildings per lane cell (3 cells per lane)
WALL_HP, PLATING_HP = 6, 6
STRUCT_HP = {"farm": 4, "mine": 6, "tower": 8}   # buildings sit in lane cells
TIER_HP = 2                                       # a tower upgrade adds this
MANA_BASE = 3
SIZE_ADJ = {2: 0.90, 3: 0.88, 4: 0.92, 5: 0.89}   # evens out win rates by table size (six lanes)

SEATS = {
    2: [("Steward", "Engineer", "Smith"), ("Slayer", "Mage")],
    3: [("Steward", "Smith"), ("Engineer", "Slayer"), ("Mage",)],
    4: [("Steward", "Smith"), ("Engineer",), ("Slayer",), ("Mage",)],
    5: [("Steward",), ("Engineer",), ("Slayer",), ("Smith",), ("Mage",)],
}
BUILDERS = ("Steward", "Engineer", "Smith")
START_POS = {"Steward": "N", "Engineer": "SE", "Slayer": "S", "Smith": "NW"}

ENEMIES = {
    "goblin": dict(hp=2, spd=1, dmg=1, wall=1, ranged=False, threat=1, ch="g"),
    "runner": dict(hp=1, spd=2, dmg=1, wall=1, ranged=False, threat=1, ch="r"),
    "archer": dict(hp=2, spd=1, dmg=1, wall=1, ranged=True, threat=2, ch="a"),
    "troll":  dict(hp=6, spd=1, dmg=2, wall=2, ranged=False, threat=3, ch="T"),
    "boss":   dict(hp=24, spd=1, dmg=4, wall=2, ranged=False, threat=10, ch="B"),
}

SPELLS = {"bolt": 1, "frost": 2, "fire": 2, "ward": 2, "lightning": 3}
SPELL_HELP = {
    "bolt": "1 mana: hits the nearest enemy (2 + band damage)",
    "frost": "2 mana: freezes the nearest 2/4/all enemies in a lane",
    "fire": "2 mana: 1 + band damage to EVERY enemy in a lane",
    "ward": "2 mana: poor halves wall/building damage, okay stops it, "
            "great also stops keep damage from that lane",
    "lightning": "3 mana: 2 + band damage to the 3 nearest enemies",
}

PROJECTS = {}      # id -> dict(role, kind, name, cost, req, desc)
ITEMS = {}         # id -> dict(budget, cost, name)


def _personal(pid, role, name, cost, desc, req=None):
    PROJECTS[pid] = dict(role=role, kind="personal", name=name, cost=cost,
                         req=req, desc=desc)


def _budget(pid, role, name, desc):
    PROJECTS[pid] = dict(role=role, kind="budget", name=name, cost=0,
                         req=None, desc=desc)


def _item(iid, budget, cost, name):
    ITEMS[iid] = dict(budget=budget, cost=cost, name=name)


_personal("clerks1", "Steward", "Clerks", 8, "+1 build point for the Steward")
_personal("trade1", "Steward", "Trade Routes I", 7, "+1 income every round")
_personal("trade2", "Steward", "Trade Routes II", 11,
          "+2 more income every round", "trade1")
_personal("hammer1", "Engineer", "Efficient Builders I", 8,
          "+1 build point for the Engineer")
_personal("hammer2", "Engineer", "Efficient Builders II", 12,
          "+1 more build point", "hammer1")
_personal("sword1", "Slayer", "Steel Sword", 7, "+2 damage per attack")
_personal("sword2", "Slayer", "Runed Blade", 12, "+3 more damage", "sword1")
_personal("smith1", "Smith", "Master's Tools I", 8,
          "+1 build point for the Smith")
_personal("smith2", "Smith", "Master's Tools II", 12,
          "+1 more build point", "smith1")
_personal("whet", "Smith", "Whetstones", 7,
          "+1 damage for every tower AND for the Slayer")
_personal("frost", "Mage", "Spell: Frost", 9, SPELL_HELP["frost"])
_personal("fire", "Mage", "Spell: Fire", 9, SPELL_HELP["fire"])
_personal("ward", "Mage", "Spell: Ward", 8, SPELL_HELP["ward"])
_personal("lightning", "Mage", "Spell: Lightning", 12, SPELL_HELP["lightning"])
_personal("mana1", "Mage", "Mana Well I", 8, "+1 mana per round")
_personal("mana2", "Mage", "Mana Well II", 12, "+1 more mana", "mana1")

_budget("b_econ", "Steward", "Economy budget", "pays for farms and mines")
_budget("b_wall", "Engineer", "Wall budget",
        "pays for wall sections, wall repair, keep repair")
_budget("b_tower", "Engineer", "Tower budget", "pays for towers")
_budget("b_forge", "Smith", "Forge budget",
        "pays for tower upgrades and wall plating")
_budget("b_tonic", "Slayer", "Tonic budget",
        "pays for tonics (+3 damage, up to 2 per round)")

_item("farm", "b_econ", 5, "Farm (+2 income)")
_item("mine", "b_econ", 9, "Mine (+4 income)")
_item("wall", "b_wall", 4, "Wall section (+6 hp)")
_item("repair", "b_wall", 2, "Repair wall (+4 hp)")
_item("keep_repair", "b_wall", 3, "Repair keep (+2)")
_item("tower", "b_tower", 6, "Tower")
_item("tower_up", "b_forge", 7, "Tower upgrade (+1 dmg)")
_item("plating", "b_forge", 6, "Wall plating (+6 hp cap)")
_item("tonic", "b_tonic", 3, "Tonic (+3 damage)")

ROLE_PERSONAL = {}
ROLE_BUDGETS = {}
for _pid, _p in PROJECTS.items():
    (ROLE_PERSONAL if _p["kind"] == "personal" else ROLE_BUDGETS) \
        .setdefault(_p["role"], []).append(_pid)
BUILD_ITEMS = {"Steward": ("farm", "mine"),
               "Engineer": ("wall", "repair", "keep_repair", "tower"),
               "Smith": ("tower_up", "plating")}
BUILD_UPGRADES = {"Steward": ("clerks1",), "Engineer": ("hammer1", "hammer2"),
                  "Smith": ("smith1", "smith2")}


# ======================================================================
#  THE GAME (pure rules, no window, no network)
# ======================================================================
class Game:
    def __init__(self, n=4, seed=1, diff=1.7, treasurer="draft"):
        if n not in SEATS:
            raise ValueError("2 to 5 players")
        self.n, self.seed, self.diff = n, seed, diff
        self.treasurer_style = treasurer
        self.seats = [list(s) for s in SEATS[n]]
        self.owner = {r: p for p, rs in enumerate(self.seats) for r in rs}
        self.cap = [VAULT_CAP_BASE + VAULT_CAP_EXTRA * (len(rs) - 1)
                    for rs in self.seats]
        self.round = 0
        self.phase = "new"
        self.over = False
        self.won = None
        self.keep = KEEP_MAX
        self.pool = START_POOL
        self.vault = [0] * n
        self.progress = collections.defaultdict(int)
        self.done = set()
        self.budget = {b: 0 for b in PROJECTS if PROJECTS[b]["kind"] == "budget"}
        # slots[0..2] are lane cells 1..3 (cell 1 is next to the wall). A cell
        # is a list of up to CELL_MAX buildings, each
        # {"t": farm|mine|tower, "hp": n, "tier": n, "by": seat, "role": r}.
        self.map = {q: dict(wall=1, wall_hp=WALL_HP, plating=0,
                            slots=[[], [], []]) for q in QUADS}
        self.hcell = {r: 1 for r in START_POS}   # which lane cell a hero is in
        self.fx = []               # this round's combat events (for animation)
        self.anim = None           # {"before": snapshot, "events": [...]}
        self.income_srcs = []
        self.pos = dict(START_POS)
        self.enemies = []
        self.next_id = 1
        self.waves = self._make_waves()
        self.noise = self._make_noise()
        self.who = {}               # actor tags for this round's events
        self.treasurer = 0
        self.income = 0
        self.income_parts = {}
        self.pet = {}
        self.reserve = {}
        self.deposit = 0
        self.funded = []           # [(player, pid, amount, completed)]
        self.ev = []               # this round's log lines
        self.history = []          # all log lines
        self.msgs = collections.Counter()      # this round
        self.stat = collections.Counter()      # whole game

    # ------------------------------------------------------------ setup
    def roles_of(self, p):
        return self.seats[p]

    def _make_waves(self):
        r = random.Random(self.seed * 7919 + 17)
        scale = (0.65 + 0.14 * self.n) * self.diff * SIZE_ADJ[self.n]
        waves = {}
        for rd in range(1, LAST_ROUND + 1):
            budget = int(round((1.5 + 1.1 * rd) * scale))
            types = ["goblin"]
            if rd >= 3:
                types.append("runner")
            if rd >= 4:
                types.append("archer")
            if rd >= 6:
                types.append("troll")
            k = 1 if rd <= 2 else (2 if rd <= 6 else 3)
            qs = r.sample(QUADS, k)
            lst, i = [], 0
            while budget > 0:
                t = r.choice(types)
                if ENEMIES[t]["threat"] > budget:
                    t = "goblin"
                lst.append((qs[i % k], t))
                budget -= ENEMIES[t]["threat"]
                i += 1
            if rd == LAST_ROUND:
                lst.append((r.choice(QUADS), "boss"))
            waves[rd] = lst
        return waves

    def _make_noise(self):
        """A small fixed random nudge per wave group and lane, so lanes that
        look equally tempting do not all attract the same group."""
        r = random.Random(self.seed * 104729 + 3)
        return {rd: [{q: r.randrange(0, 3) for q in QUADS} for _ in range(8)]
                for rd in self.waves}

    def appeal(self, q):
        """How tempting a lane is to enemies. Farms and mines (things to
        wreck, no way of hitting back) raise it; towers (which shoot back)
        lower it."""
        a = 0
        for cell in self.map[q]["slots"]:
            for b in cell:
                a += 3 if b["t"] in ("farm", "mine") else -(3 + b["tier"])
        return a

    def plan_lanes(self, rd):
        """[(lane, type)] for a round's wave, with every group sent to the
        lane that looks best to enemies right now: the fewest towers and the
        most farms. Groups never share a lane while a free one exists."""
        wave = self.waves.get(rd, [])
        groups, order = {}, []
        for hint, t in wave:
            if hint not in groups:
                groups[hint] = []
                order.append(hint)
            groups[hint].append(t)
        used, lane_of = set(), {}
        nz = self.noise.get(rd) or [{q: 0 for q in QUADS}] * 8
        for gi, hint in enumerate(order):
            free = [q for q in QUADS if q not in used] or list(QUADS)
            q = max(free, key=lambda x: (self.appeal(x) + nz[gi % 8][x],
                                         -QUADS.index(x)))
            used.add(q)
            lane_of[hint] = q
        return [(lane_of[h], t) for h, t in wave]

    def forecast(self, ahead=3):
        """{round: {lane: Counter(type)}} for this round and the next. Lanes
        are where enemies would go if they picked a lane right now."""
        out = {}
        for rd in range(max(1, self.round), self.round + ahead):
            if rd in self.waves:
                d = {}
                for q, t in self.plan_lanes(rd):
                    d.setdefault(q, collections.Counter())[t] += 1
                out[rd] = d
        return out

    # ------------------------------------------------------- bookkeeping
    def can_fund(self, p, pid):
        pr = PROJECTS.get(pid)
        if not pr or pr["role"] not in self.seats[p]:
            return False
        if pr["kind"] == "budget":
            return True
        return pid not in self.done and (pr["req"] is None
                                         or pr["req"] in self.done)

    def need(self, pid):
        """How much more gold this project can take."""
        pr = PROJECTS[pid]
        if pr["kind"] == "budget":
            return BUDGET_MAX - self.budget[pid]
        if pid in self.done:
            return 0
        return pr["cost"] - self.progress[pid]

    def fundable(self, p):
        return [pid for pid in PROJECTS if self.can_fund(p, pid)
                and self.need(pid) > 0]

    def build_points(self, role, band=0):
        return 1 + band + sum(1 for u in BUILD_UPGRADES.get(role, ())
                              if u in self.done)

    def mana(self):
        return MANA_BASE + ("mana1" in self.done) + ("mana2" in self.done)

    def known_spells(self):
        return [s for s in SPELLS if s == "bolt" or s in self.done]

    def wall_cap(self, q):
        m = self.map[q]
        return (WALL_HP * m["wall"] + PLATING_HP * m["plating"]
                if m["wall"] > 0 else 0)

    # lane cells ---------------------------------------------------------
    def slot_count(self, q, t):
        return sum(1 for c in self.map[q]["slots"] for s in c if s["t"] == t)

    def econ_count(self, q):
        return self.slot_count(q, "farm") + self.slot_count(q, "mine")

    def free_cells(self, q):
        """Cells that still have room (a cell holds up to CELL_MAX)."""
        return [k for k in (1, 2, 3)
                if len(self.map[q]["slots"][k - 1]) < CELL_MAX]

    def upgradable(self, q):
        return [k for k in (1, 2, 3)
                if any(b["t"] == "tower" and b["tier"] < MAX_TIER
                       for b in self.map[q]["slots"][k - 1])]

    def can_place(self, q, item):
        return bool(self.free_cells(q))

    def auto_cell(self, q, item):
        """Where a building goes when its owner did not pick a cell:
        economy close to the wall (safest), towers one cell out. The emptiest
        of the preferred cells wins a tie."""
        free = self.free_cells(q)
        if not free:
            return None
        pref = (1, 2, 3) if item in ("farm", "mine") else (2, 3, 1)
        return min(free, key=lambda k: (len(self.map[q]["slots"][k - 1]),
                                        pref.index(k)))

    def bank_amount(self, p):
        """Gold banking would secure for seat p from the pool right now."""
        dep = max(1, int(round(DEPOSIT_RATIO * self.income / self.n)))
        return max(0, min(dep, self.cap[p] - self.vault[p], self.pool))

    def _fx(self, *e):
        self.fx.append(e)

    def snapshot(self):
        return dict(round=self.round, keep=self.keep, pool=self.pool,
                    map=json.loads(json.dumps(self.map)),
                    enemies=[dict(e) for e in self.enemies],
                    pos=dict(self.pos), hcell=dict(self.hcell))

    def say(self, text):
        self.ev.append(text)
        self.history.append("R%d  %s" % (self.round, text))

    def danger(self):
        """A rough 'how much trouble is each lane in' score (for bots
        and for the little red bars in the window)."""
        d = {q: 0.0 for q in QUADS}
        for e in self.enemies:
            t = ENEMIES[e["type"]]
            d[e["q"]] += t["dmg"] * (4 - e["cell"]) * (1.5 if e["hp"] > 3 else 1)
        for rd, w in ((self.round, 0.6), (self.round + 1, 0.4)):
            for q, t in self.plan_lanes(rd):
                d[q] += w * ENEMIES[t]["threat"]
        return d

    def state_hash(self):
        blob = json.dumps([self.round, self.keep, self.pool, self.vault,
                           sorted((k, v) for k, v in self.progress.items() if v),
                           sorted(self.done),
                           sorted(self.budget.items()), self.map, self.pos,
                           self.hcell,
                           self.enemies], sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()[:8]

    # ------------------------------------------------- step 1: income
    def start_round(self):
        if self.over:
            return
        self.round += 1
        self.ev = []
        self.msgs = collections.Counter()
        farms = sum(self.slot_count(q, "farm") for q in QUADS)
        mines = sum(self.slot_count(q, "mine") for q in QUADS)
        trade = (1 if "trade1" in self.done else 0) + \
                (2 if "trade2" in self.done else 0)
        base = BASE_INCOME + INCOME_PER_PLAYER * self.n
        self.income_parts = dict(base=base, farms=2 * farms, mines=4 * mines,
                                 trade=trade)
        self.income = sum(self.income_parts.values())
        srcs = [dict(kind="base", q=None, cell=None, amt=base)]
        for q in QUADS:
            for k in (1, 2, 3):
                for bi, sl in enumerate(self.map[q]["slots"][k - 1]):
                    if sl["t"] in ("farm", "mine"):
                        srcs.append(dict(kind=sl["t"], q=q, cell=k, bi=bi,
                                         by=sl.get("by"), role=sl.get("role"),
                                         amt=2 if sl["t"] == "farm" else 4))
        if trade:
            srcs.append(dict(kind="trade", q=None, cell=None, amt=trade))
        self.income_srcs = srcs
        self.pool += self.income
        self.treasurer = (self.round - 1) % self.n
        self.pet, self.reserve, self.funded = {}, {}, []
        self.phase = "petition"
        self.say("Income +%d (pool %d). Treasurer: seat %d."
                 % (self.income, self.pool, self.treasurer + 1))

    # ------------------------------------- steps 2-3a: bank and petitions
    def _clean_items(self, p, items):
        out, seen = [], set()
        for it in items or []:
            try:
                pid, amt = it
                amt = int(amt)
            except (TypeError, ValueError):
                continue
            if pid in seen or not self.can_fund(p, pid):
                continue
            amt = min(amt, self.need(pid))
            if amt <= 0:
                continue
            out.append((pid, amt))
            seen.add(pid)
            if len(out) == 2:
                break
        return out

    def petition(self, orders):
        """orders: {player: {"items": [(project, amount), ...],
        "must": project or None}}. A player who is missing, or whose
        request is empty, banks instead."""
        assert self.phase == "petition", self.phase
        pet = {}
        for p, o in (orders or {}).items():
            if not isinstance(o, dict) or not 0 <= p < self.n:
                continue
            items = self._clean_items(p, o.get("items"))
            if items:
                must = o.get("must")
                pet[p] = dict(items=items,
                              must=must if must in [i for i, _ in items] else None)
        self.pet = pet
        self.deposit = max(1, int(round(DEPOSIT_RATIO * self.income / self.n)))
        for p in range(self.n):
            if p in pet:
                continue
            pay = max(0, min(self.deposit, self.cap[p] - self.vault[p], self.pool))
            if pay:
                self.vault[p] += pay
                self.pool -= pay
                self.stat["banked"] += 1
                self.say("Seat %d banks %d." % (p + 1, pay))
            else:
                self.say("Seat %d can't bank (vault full)." % (p + 1))
        left = self.pool
        for p in pet:                      # hold a deposit for each petitioner
            hold = max(0, min(self.deposit, self.cap[p] - self.vault[p], left))
            self.reserve[p] = hold
            left -= hold
        self.pool = left
        # the treasurer's own request travels inside their decision message,
        # so nobody ever sends more than 2 messages in a round
        self.msgs["petition"] = len([p for p in pet if p != self.treasurer])
        self.stat["petitioned"] += len(pet)
        self.phase = "decision"

    # ----------------------------------------- step 3b: the treasurer
    def decide(self, alloc=None):
        """alloc: {(player, project): amount} from the treasurer, or None to
        use the automatic draft (a missing treasurer)."""
        assert self.phase == "decision", self.phase
        if self.pet:
            if alloc is None:
                alloc = allocate(self, self.treasurer_style)
            else:
                self.msgs["decision"] = 1
            asked = {(p, pid): a for p, d in self.pet.items()
                     for pid, a in d["items"]}
            got = collections.Counter()
            for (p, pid), amt in sorted(alloc.items()):
                amt = min(int(amt), asked.get((p, pid), 0), self.pool)
                if amt <= 0:
                    continue
                used = self._fund(pid, amt)
                self.pool -= used
                got[p] += used
                self.stat["pool_funded"] += used
                self.funded.append((p, pid, used, pid in self.done))
            for p, hold in self.reserve.items():
                if got[p] == 0 and PETITION_FALLBACK_DEPOSIT and hold:
                    self.vault[p] += hold
                    self.say("Seat %d got nothing, keeps the deposit (%d)."
                             % (p + 1, hold))
                    self.stat["fallback_deposit"] += 1
                else:
                    self.pool += hold
            self.reserve = {}
        for p, pid, amt, comp in self.funded:
            self.say("Pool: seat %d +%d to %s%s" % (
                p + 1, amt, PROJECTS[pid]["name"], "  DONE" if comp else ""))
        self.phase = "vault"

    def _fund(self, pid, amount):
        """Put gold into a project. Returns how much it really took."""
        a = min(amount, self.need(pid))
        if a <= 0:
            return 0
        if PROJECTS[pid]["kind"] == "budget":
            self.budget[pid] += a
        else:
            self.progress[pid] += a
            if self.progress[pid] >= PROJECTS[pid]["cost"]:
                self.done.add(pid)
                self.stat["done_" + pid] += 1
        return a

    # ------------------------------------- steps 4-6: vault, map, combat
    def final(self, orders):
        """orders: {player: {"vault": {project: amount},
        "roles": {role: {...}}}}  (see the bots for the role fields)."""
        assert self.phase == "vault", self.phase
        orders = orders or {}
        sends = 0
        ro = {}
        for p in sorted(orders):
            o = orders[p] or {}
            acts = False
            for pid, amt in sorted((o.get("vault") or {}).items()):
                if self.can_fund(p, pid):
                    try:
                        amt = int(amt)
                    except (TypeError, ValueError):
                        continue
                    a = min(amt, self.vault[p], self.need(pid))
                    if a > 0:
                        self.vault[p] -= a
                        self._fund(pid, a)
                        self.stat["vault_funded"] += a
                        acts = True
                        self.say("Vault: seat %d +%d to %s%s" % (
                            p + 1, a, PROJECTS[pid]["name"],
                            "  DONE" if pid in self.done else ""))
            for role, r in (o.get("roles") or {}).items():
                if self.owner.get(role) == p and isinstance(r, dict):
                    ro[role] = r
                    if self._is_action(role, r):
                        acts = True
            sends += acts
        self.msgs["final"] = sends
        self._old_pos = dict(self.pos)
        for role, r in ro.items():
            if role in self.pos and r.get("q") in QUADS:
                self.pos[role] = r["q"]
        self._combat(ro)
        self.stat["msgs"] += sum(self.msgs.values())
        self.stat["rounds"] += 1
        if self.keep <= 0:
            self.over, self.won = True, False
            self.say("The keep has fallen.")
        elif self.round >= LAST_ROUND and not self.enemies:
            self.over, self.won = True, True
            self.say("The last enemy is dead. The keep stands!")
        elif self.round >= LAST_ROUND + 10:
            self.over, self.won = True, False
        self.phase = "idle"
        return self.ev

    @staticmethod
    def _is_action(role, r):
        if role == "Slayer":
            return True
        if role == "Mage":
            return bool(r.get("casts"))
        return bool(r.get("build"))

    # ------------------------------------------------------------ combat
    @staticmethod
    def _band(r):
        b = r.get("band", 0)
        return b if b in (0, 1, 2) else 0

    def _in(self, q, key=None):
        es = [e for e in self.enemies if e["q"] == q]
        es.sort(key=key or (lambda e: (e["cell"], e["id"])))
        return es

    def _hit(self, e, dmg):
        if dmg <= 0 or e["hp"] <= 0 or e not in self.enemies:
            return 0
        dealt = min(dmg, e["hp"])
        e["hp"] -= dealt
        kind, role, who = self.actor
        self._fx("dmg", e["id"], e["q"], e["cell"], dealt, e["hp"],
                 kind, role, who)
        if e["hp"] <= 0:
            self._fx("kill", e["id"], e["q"], e["cell"], e["type"],
                     kind, role, who)
            self.enemies.remove(e)
            self.kills += 5 if e["type"] == "boss" else 1
            self.say("%s %s falls." % (e["q"], e["type"]))
        return dealt

    def _combat(self, ro):
        """Order of a round: everyone builds first, then the Mage and Slayer
        act, towers fire, surviving enemies attack or advance, and finally
        the new wave appears at the far end of its lanes."""
        self.fx = []
        before = self.snapshot()
        before["pos"] = dict(getattr(self, "_old_pos", self.pos))
        self.kills = 0
        self.frozen = set()
        self.ward = {q: 0 for q in QUADS}
        self.actor = ("", "", None)
        for role in BUILDERS:               # builders walk to their lane
            if role in ro and before["pos"][role] != self.pos[role]:
                self._hero(role, self.pos[role], self.hcell[role])
        self._builds(ro)
        if "Mage" in ro:
            self._mage(ro["Mage"])
        if "Slayer" in ro:
            self._slayer(ro["Slayer"])
        self._towers()
        self._enemies_act()
        wave = self.plan_lanes(self.round)
        for q, t in wave:
            hp = ENEMIES[t]["hp"] + (4 * self.n - 8 if t == "boss" else 0)
            self.enemies.append(dict(id=self.next_id, type=t, q=q, cell=3,
                                     hp=hp))
            self._fx("spawn", self.next_id, t, q, 3, hp)
            self.next_id += 1
        if wave:
            self.say("Enemies appear: " + ", ".join(
                "%s %s" % (q, t) for q, t in wave))
        if self.kills:
            self.pool += self.kills
            self._fx("loot", self.kills)
            self.stat["kills"] += self.kills
            self.say("Kills pay +%d to the pool." % self.kills)
        self.anim = dict(before=before, events=list(self.fx))

    def _mage(self, r):
        mana, b = self.mana(), self._band(r)
        known = self.known_spells()
        self.actor = ("Mage", "Mage", self.owner.get("Mage"))
        for spell, q in (r.get("casts") or [])[:4]:
            cost = SPELLS.get(spell)
            if cost is None or spell not in known or q not in QUADS \
                    or cost > mana:
                continue
            mana -= cost
            es = self._in(q)
            self.stat["cast_" + spell] += 1
            self._fx("cast", spell, q, self.owner.get("Mage"))
            if spell == "bolt" and es:
                self._hit(es[0], 2 + b)
            elif spell == "fire":
                for e in es:
                    self._hit(e, 1 + b)
            elif spell == "lightning":
                for e in es[:3]:
                    self._hit(e, 2 + b)
            elif spell == "frost":
                for e in es[:(2, 4, 99)[b]]:
                    self.frozen.add(e["id"])
                    self._fx("freeze", e["id"])
            elif spell == "ward":
                self.ward[q] = max(self.ward[q], b + 1)
            self.say("Mage casts %s on %s (%s)." % (spell, q, BANDS[b]))

    def _hero(self, role, q, cell):
        """The hero walks to the lane cell where they are working."""
        self.hcell[role] = cell
        self._fx("hero", role, q, cell)

    def _slayer(self, r):
        q, b = self.pos["Slayer"], self._band(r)
        self.actor = ("Slayer", "Slayer", self.owner.get("Slayer"))
        pts = (2, 3, 5)[b] + (2 if "sword1" in self.done else 0) + \
              (3 if "sword2" in self.done else 0) + \
              (1 if "whet" in self.done else 0)
        try:
            want = int(r.get("tonics", 0) or 0)
        except (TypeError, ValueError):
            want = 0
        t = max(0, min(want, 2, self.budget["b_tonic"] // ITEMS["tonic"]["cost"]))
        self.budget["b_tonic"] -= t * ITEMS["tonic"]["cost"]
        pts += 3 * t
        key = (lambda e: (-e["hp"], e["cell"], e["id"])) \
            if r.get("prio") == "strongest" else None
        targets = self._in(q, key)
        self._hero("Slayer", q, targets[0]["cell"] if targets
                   else self.hcell["Slayer"])
        self._fx("slash", q, self.owner.get("Slayer"))
        for e in targets:
            if pts <= 0:
                break
            if e["cell"] != self.hcell["Slayer"]:
                self._hero("Slayer", q, e["cell"])
            pts -= self._hit(e, pts)
        self.say("Slayer fights in %s (%s%s)." % (
            q, BANDS[b], ", %d tonic" % t if t else ""))

    def _towers(self):
        for q in QUADS:
            for k in (1, 2, 3):
                for sl in list(self.map[q]["slots"][k - 1]):
                    if sl["t"] != "tower":
                        continue
                    es = self._in(q)
                    if not es:
                        break
                    self.actor = ("tower", sl.get("role"), sl.get("by"))
                    self._fx("shot", q, k, es[0]["id"], sl.get("by"))
                    self._hit(es[0], 1 + sl["tier"] + (1 if "whet" in self.done else 0))

    def _keep_dmg(self, d, q):
        if self.ward[q] >= 3:
            d = 0
        self.keep = max(0, self.keep - d)
        if d:
            self._fx("keep", q, d, self.keep)
            self.say("%s enemy hits the keep for %d." % (q, d))

    def _enemies_act(self):
        """Each enemy, nearest the wall first: if a building stands in its
        cell it attacks the weakest one there; otherwise it shoots (archers),
        hits the wall or keep (cell 1), or walks forward, stopping in any cell
        that holds a building so it can attack it next round."""
        for q in QUADS:
            m = self.map[q]
            w = self.ward[q]
            for e in self._in(q):
                if e["id"] in self.frozen or e not in self.enemies:
                    continue
                t = ENEMIES[e["type"]]
                cellb = m["slots"][e["cell"] - 1]
                if cellb:
                    bi = min(range(len(cellb)), key=lambda i: cellb[i]["hp"])
                    sl = cellb[bi]
                    d = t["dmg"] * t["wall"]
                    d = d // 2 if w == 1 else (0 if w >= 2 else d)
                    sl["hp"] = max(0, sl["hp"] - d)
                    self._fx("sattack", q, e["cell"], e["id"], d, sl["hp"], bi)
                    if sl["hp"] <= 0:
                        cellb.pop(bi)
                        self._fx("sdestroy", q, e["cell"], sl["t"], bi,
                                 sl.get("by"), sl.get("role"))
                        self.say("The %s in %s cell %d is destroyed!"
                                 % (sl["t"], q, e["cell"]))
                elif t["ranged"] and e["cell"] <= 2:
                    self._keep_dmg(t["dmg"], q)
                elif e["cell"] == 1:
                    if m["wall_hp"] > 0:
                        d = t["dmg"] * t["wall"]
                        d = d // 2 if w == 1 else (0 if w >= 2 else d)
                        m["wall_hp"] = max(0, m["wall_hp"] - d)
                        self._fx("wall", q, e["id"], d, m["wall_hp"])
                        if m["wall_hp"] == 0:
                            m["wall"], m["plating"] = 0, 0
                            self._fx("walldown", q)
                            self.say("The %s wall is destroyed!" % q)
                    else:
                        self._keep_dmg(t["dmg"], q)
                else:
                    c0, c = e["cell"], e["cell"]
                    for _ in range(t["spd"]):
                        if c <= 1:
                            break
                        c -= 1
                        if m["slots"][c - 1]:
                            break
                    e["cell"] = c
                    if c != c0:
                        self._fx("move", e["id"], q, c0, c)

    def _builds(self, ro):
        for role in BUILDERS:
            r = ro.get(role)
            if not r or not isinstance(r.get("build"), (list, tuple)):
                continue
            q, pts = self.pos[role], self.build_points(role, self._band(r))
            for ent in r["build"]:
                if pts <= 0:
                    break
                if isinstance(ent, str):
                    item, cell = ent, None
                elif isinstance(ent, (list, tuple)) and ent \
                        and isinstance(ent[0], str):
                    item, cell = ent[0], (ent[1] if len(ent) > 1 else None)
                else:
                    continue
                if self._build(role, item, q, cell):
                    pts -= 1

    def _build(self, role, item, q, cell=None):
        it = ITEMS.get(item)
        if not it or item not in BUILD_ITEMS.get(role, ()):
            return False
        b, m = it["budget"], self.map[q]
        if self.budget[b] < it["cost"]:
            return False
        who = self.owner.get(role)
        bi = None
        if item in ("farm", "mine", "tower"):
            if not self.can_place(q, item):
                return False
            if cell not in (1, 2, 3) or len(m["slots"][cell - 1]) >= CELL_MAX:
                cell = self.auto_cell(q, item)
            if cell is None:
                return False
            m["slots"][cell - 1].append(dict(t=item, hp=STRUCT_HP[item], tier=0,
                                             by=who, role=role))
            bi = len(m["slots"][cell - 1]) - 1
        elif item == "wall":
            if m["wall"] >= MAX_WALL:
                return False
            m["wall"] += 1
            m["wall_hp"] += WALL_HP
        elif item == "repair":
            if m["wall"] == 0 or m["wall_hp"] >= self.wall_cap(q):
                return False
            m["wall_hp"] = min(self.wall_cap(q), m["wall_hp"] + 4)
        elif item == "keep_repair":
            if self.keep >= KEEP_MAX:
                return False
            self.keep = min(KEEP_MAX, self.keep + 2)
        elif item == "tower_up":
            ups = self.upgradable(q)
            if not ups:
                return False
            if cell not in ups:
                cell = ups[0]
            cands = [i for i, x in enumerate(m["slots"][cell - 1])
                     if x["t"] == "tower" and x["tier"] < MAX_TIER]
            bi = min(cands, key=lambda i: m["slots"][cell - 1][i]["tier"])
            sl = m["slots"][cell - 1][bi]
            sl["tier"] += 1
            sl["hp"] += TIER_HP
        elif item == "plating":
            if m["wall"] == 0 or m["plating"] >= MAX_PLATING:
                return False
            m["plating"] += 1
            m["wall_hp"] += PLATING_HP
        self.budget[b] -= it["cost"]
        self.stat["built_" + item] += 1
        self._hero(role, q, cell or 1)
        self._fx("build", item, q, cell, json.loads(json.dumps(m)), self.keep,
                 role, who, bi)
        self.say("%s builds: %s in %s%s." % (
            role, it["name"], q, " (cell %d)" % cell if cell else ""))
        return True


# ======================================================================
#  THE TREASURER'S SPLIT (used for a missing treasurer and by bots)
# ======================================================================
def allocate(g, style="draft"):
    """Split g.pool among g.pet. Returns {(player, project): amount}."""
    order = [(g.treasurer + i) % g.n for i in range(g.n)]
    pool, out = g.pool, {}

    def give(p, pid, amt):
        nonlocal pool
        a = min(amt, pool)
        if a > 0:
            out[(p, pid)] = out.get((p, pid), 0) + a
            pool -= a
        return a
    req = {(p, pid): a for p, d in g.pet.items() for pid, a in d["items"]}
    if style == "selfish" and g.treasurer in g.pet:
        for pid, a in g.pet[g.treasurer]["items"]:
            give(g.treasurer, pid, a)
    for p in order:                            # must-haves first
        d = g.pet.get(p)
        if d and d["must"]:
            give(p, d["must"], req[(p, d["must"])] - out.get((p, d["must"]), 0))
    if style == "prorata":
        rest = {k: a - out.get(k, 0) for k, a in req.items()
                if a - out.get(k, 0) > 0}
        tot = sum(rest.values())
        if tot and tot > pool:
            share = pool
            for k in sorted(rest):
                give(k[0], k[1], rest[k] * share // tot)
            for k in sorted(rest):             # leftovers, one gold at a time
                while pool > 0 and out.get(k, 0) < req[k]:
                    give(k[0], k[1], 1)
                    break
        else:
            for k in sorted(rest):
                give(k[0], k[1], rest[k])
    else:                                       # draft: round-robin picks
        for slot in range(2):
            for p in order:
                d = g.pet.get(p)
                if d and slot < len(d["items"]):
                    pid, a = d["items"][slot]
                    give(p, pid, a - out.get((p, pid), 0))
    return {k: v for k, v in out.items() if v > 0}


# ======================================================================
#  BOTS (for the simulator, and for empty seats when you play)
# ======================================================================
PERSONAL_ORDER = {
    "Steward": ("trade1", "clerks1", "trade2"),
    "Engineer": ("hammer1", "hammer2"),
    "Slayer": ("sword1", "sword2"),
    "Smith": ("whet", "smith1", "smith2"),
    "Mage": ("fire", "mana1", "ward", "lightning", "frost", "mana2"),
}


def _free_econ_q(g):
    best = None
    for q in QUADS:
        if g.can_place(q, "farm"):
            k = (g.danger()[q], g.econ_count(q))
            if best is None or k < best[0]:
                best = (k, q)
    return best[1] if best else None


def wanted_builds(g, role):
    """[(item, lane)] a sensible player would build, best first."""
    d = g.danger()
    qs = sorted(QUADS, key=lambda q: -d[q])
    out = []
    left = LAST_ROUND - g.round
    if role == "Steward":
        n_econ = sum(g.econ_count(q) for q in QUADS)
        q = _free_econ_q(g)
        if q and left >= 3:
            out.append(("farm" if n_econ < 2 else "mine", q))
    elif role == "Engineer":
        for q in qs:
            m = g.map[q]
            if m["wall"] == 0:
                out.append(("wall", q))
        for q in qs:
            m = g.map[q]
            if m["wall"] and m["wall_hp"] <= g.wall_cap(q) - 3 and d[q] > 0:
                out.append(("repair", q))
        if g.keep <= KEEP_MAX - 4:
            out.append(("keep_repair", qs[0]))
        for q in qs[:2]:
            if g.slot_count(q, "tower") < 1 and g.can_place(q, "tower"):
                out.append(("tower", q))
        for q in qs:
            if g.map[q]["wall"] < 2:
                out.append(("wall", q))
        for q in qs:
            if g.can_place(q, "tower"):
                out.append(("tower", q))
    elif role == "Smith":
        for q in qs:
            if g.upgradable(q):
                out.append(("tower_up", q))
        for q in qs:
            if g.map[q]["wall"] >= 2 and g.map[q]["plating"] < MAX_PLATING:
                out.append(("plating", q))
    return out


def wishes(g, p):
    """[(project, amount)] this player would like to fund, best first."""
    out = []
    for role in g.seats[p]:
        bud = None
        wb = wanted_builds(g, role)
        if wb:
            item = wb[0][0]
            b = ITEMS[item]["budget"]
            short = ITEMS[item]["cost"] - g.budget[b]
            if short > 0:
                bud = (b, min(short, g.need(b)))
        elif role == "Slayer" and g.round >= 3 and max(g.danger().values()) > 6:
            short = ITEMS["tonic"]["cost"] * 2 - g.budget["b_tonic"]
            if short > 0:
                bud = ("b_tonic", short)
        pers = None
        for pid in PERSONAL_ORDER.get(role, ()):
            if pid not in g.done and g.can_fund(p, pid):
                pers = (pid, g.need(pid))
                break
        late = g.round >= LAST_ROUND - 2
        seq = (bud, pers) if (bud and (g.round <= 8 or not pers) and not late) \
            else (pers, bud)
        out += [w for w in seq if w and w[1] > 0]
    return out


class Bot:
    """style: 'balanced', 'saver' or 'spender' (how they use the vault)."""

    def __init__(self, style="balanced"):
        self.style = style

    def petition(self, g, p):
        ws = wishes(g, p)
        if not ws:
            return None
        top_pid, top_need = ws[0]
        personal = PROJECTS[top_pid]["kind"] == "personal"
        if self.style == "saver" and personal and top_need >= 5 \
                and g.vault[p] < top_need:
            return None
        if self.style == "balanced" and personal and top_need > 3 * g.deposit_estimate():
            return None
        return dict(items=ws[:2], must=ws[0][0])

    def vault(self, g, p):
        out, left = {}, g.vault[p]
        for pid, need in wishes(g, p):
            if left <= 0:
                break
            bud = PROJECTS[pid]["kind"] == "budget"
            can_finish = left >= need
            near_cap = g.vault[p] >= g.cap[p] - 2
            if bud or can_finish or self.style == "spender" or near_cap:
                a = min(left, need)
                out[pid] = out.get(pid, 0) + a
                left -= a
        return out

    def allocate(self, g):
        return allocate(g, g.treasurer_style)

    def roles(self, g, p, roll):
        res = {}
        d = g.danger()
        qs = sorted(QUADS, key=lambda q: -d[q])
        for role in g.seats[p]:
            if role in BUILDERS:
                wb = wanted_builds(g, role)
                q, plan = g.pos[role], []
                if wb:
                    q = wb[0][1]
                    plan = [i for i, qq in wb if qq == q]
                avail = dict(g.budget)
                chosen = []
                for it in plan:
                    c = ITEMS[it]["cost"]
                    if avail[ITEMS[it]["budget"]] >= c:
                        avail[ITEMS[it]["budget"]] -= c
                        chosen.append(it)
                res[role] = dict(q=q, build=chosen, band=roll(role))
            elif role == "Slayer":
                res[role] = dict(q=qs[0], prio="nearest", band=roll(role),
                                 tonics=2 if d[qs[0]] > 6 else 0)
            elif role == "Mage":
                res[role] = dict(casts=self._casts(g, qs, d), band=roll(role))
        return res

    @staticmethod
    def _casts(g, qs, d):
        mana, known, casts = g.mana(), g.known_spells(), []
        for q in qs[:3]:
            n = len(g._in(q))
            if not n:
                continue
            front = g._in(q)[0]["cell"]
            for s in ("lightning", "fire", "frost", "ward", "bolt"):
                c = SPELLS[s]
                if s not in known or c > mana:
                    continue
                ok = ((s == "fire" and n >= 2) or (s == "lightning" and n >= 2) or
                      (s == "frost" and front <= 2 and n >= 2) or
                      (s == "ward" and front == 1 and g.map[q]["wall_hp"] <= 6) or
                      s == "bolt")
                if ok:
                    casts.append((s, q))
                    mana -= c
                    break
        return casts


def _deposit_estimate(self):
    return max(1, int(round(DEPOSIT_RATIO * self.income / self.n)))


Game.deposit_estimate = _deposit_estimate


def roll_band(rng, skill=1.0):
    """Stand-in for a mini-game: poor 25% / okay 50% / great 25%."""
    x = rng.random()
    lo, hi = 0.25 / skill, 1 - 0.25 * skill
    return 0 if x < lo else (2 if x > hi else 1)


def bot_round(g, bots, rng, human_orders=None):
    """Play one whole round for bots (every seat), return the log."""
    g.start_round()
    pet = {}
    for p in range(g.n):
        o = bots[p].petition(g, p)
        if o:
            pet[p] = o
    g.petition(pet)
    g.decide(bots[g.treasurer].allocate(g) if g.pet else None)
    bands = {}

    def roll(role):
        if role not in bands:
            bands[role] = roll_band(rng)
        return bands[role]
    orders = {}
    for p in range(g.n):
        orders[p] = dict(vault=bots[p].vault(g, p),
                         roles=bots[p].roles(g, p, roll))
    return g.final(orders)


# ======================================================================
#  SIMULATOR
# ======================================================================
def play_game(n, seed, styles=None, treasurer="draft", diff=1.7):
    g = Game(n, seed, diff, treasurer)
    styles = styles or ["balanced"] * n
    bots = [Bot(styles[i % len(styles)]) for i in range(n)]
    rng = random.Random(seed * 31 + 5)
    while not g.over:
        bot_round(g, bots, rng)
        check_invariants(g)
    return g


def check_invariants(g):
    assert g.pool >= 0, "pool negative"
    assert all(0 <= v <= g.cap[i] for i, v in enumerate(g.vault)), g.vault
    assert 0 <= g.keep <= KEEP_MAX
    assert all(v >= 0 for v in g.budget.values())
    for q in QUADS:
        m = g.map[q]
        assert 0 <= m["wall"] <= MAX_WALL and 0 <= m["plating"] <= MAX_PLATING
        assert 0 <= m["wall_hp"] <= max(g.wall_cap(q), 0) or m["wall"] == 0
        assert len(m["slots"]) == 3
        assert all(len(c) <= CELL_MAX for c in m["slots"])
        assert all(sl["hp"] > 0 for c in m["slots"] for sl in c)
    for pid in g.done:
        assert g.progress[pid] >= PROJECTS[pid]["cost"]
    for pid, a in g.progress.items():
        assert a <= PROJECTS[pid]["cost"], (pid, a)


def simulate(games=100, sizes=(2, 3, 4, 5), seed0=1000, out=print):
    out("Castle Macro simulator: %d bot games per setup" % games)
    out("%-26s %6s %6s %6s %7s %7s %7s" % (
        "setup", "win%", "round", "keep", "msg/rnd", "msg/pl", "banked%"))
    mixes = [("balanced", ["balanced"]), ("saver", ["saver"]),
             ("spender", ["spender"]),
             ("mixed", ["balanced", "saver", "spender"])]
    for n in sizes:
        for name, styles in mixes:
            r = _batch(n, games, seed0, styles)
            out("%-26s %5.0f%% %6.1f %6.1f %7.1f %7.2f %6.0f%%" % (
                "%d players, %s" % (n, name), r["win"], r["rounds"], r["keep"],
                r["msgs"], r["msgs"] / n, r["bank"]))
    out("")
    out("Treasurer rule (4 players, mixed bots):")
    for t in ("draft", "prorata", "selfish"):
        r = _batch(4, games, seed0, ["balanced", "saver", "spender"], t)
        out("  %-9s win %3.0f%%  round %.1f" % (t, r["win"], r["rounds"]))
    return None


def _batch(n, games, seed0, styles, treasurer="draft"):
    wins = rounds = keep = msgs = bank = pet = 0
    for i in range(games):
        g = play_game(n, seed0 + i, styles, treasurer)
        wins += bool(g.won)
        rounds += g.round
        keep += g.keep
        msgs += g.stat["msgs"] / max(1, g.stat["rounds"])
        bank += g.stat["banked"]
        pet += g.stat["petitioned"]
    return dict(win=100 * wins / games, rounds=rounds / games,
                keep=keep / games, msgs=msgs / games,
                bank=100 * bank / max(1, bank + pet))


def self_test():
    """Quick checks: python castle_macro.py --test"""
    for n in (2, 3, 4, 5):
        for seed in range(30):
            g = play_game(n, seed)
            assert g.over and g.round <= LAST_ROUND + 10
    a, b = play_game(4, 9), play_game(4, 9)
    assert a.state_hash() == b.state_hash(), "not deterministic"
    print("castle_macro: 120 bot games ok, deterministic")


if __name__ == "__main__" and "--test" in sys.argv:
    self_test()
    sys.exit(0)

if __name__ == "__main__" and "--sim" in sys.argv:
    simulate(int(sys.argv[sys.argv.index("--sim") + 1])
             if len(sys.argv) > sys.argv.index("--sim") + 1 and
             sys.argv[sys.argv.index("--sim") + 1].isdigit() else 100)
    sys.exit(0)
