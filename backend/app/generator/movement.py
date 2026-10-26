"""Player and ball tracking at 10 Hz (spec 6.6).

The movement runs after the events, in four passes:

1. First touch. While a player holds the ball between actions, they nudge it forward, so the
   ball doesn't sit dead on one spot. Their next action's x, y moves with it.
2. Ball. Straight lines between ball events: at ball speed during passes, with the carrier
   during carries, still at the restart spot during stoppages.
3. Players. Each player chases a target with a top speed and an acceleration cap of about
   3.5 m/s². The target is their formation spot shifted toward the ball, with per-player
   shift factors and smooth noise, unless they are in the action: the player on the ball
   runs with it, the receiver runs to the pass end point, a player about to act (tackle,
   pressure, interception) runs to where it happens, and the nearest opponents chase the
   carrier.
4. Rewrite. Every event's x, y becomes its player's tracked position at that moment, so events
   and tracking agree within 0.5 m (spec 6.9).

Output arrays, saved to tracking.npz:
  positions  int16 (frames, 23, 2) in decimetres; slots 0-10 home, 11-21 away, 22 the ball.
             A slot reads -1, -1 after its player is sent off.
  slot_ids   the 22 starting player ids; a substitution hands the slot to player_on_id.
  hz         frames per second (10).
"""

import math
from typing import Any

import numpy as np

HZ = 10
LENGTH, WIDTH = 105.0, 68.0
MODEL = "full"

ACCEL = 3.5               # m/s², everyone off the ball
OWNER_ACCEL = 8.0         # the player on the ball closing on it
ATTACH_M = 1.0            # within this, the player on the ball moves with it
OWNER_OFFSET_M = 0.3      # and stands just behind it
LOOKAHEAD_S = 4.0         # a player about to act starts running this early
RUN_EARLY_S = 5.0         # a receiver starts their run this long before the pass
CHASERS = 2
CHASE_RADIUS_M = 25.0
TOUCH_SPEED = 1.3         # m/s the ball drifts while a player holds it
TOUCH_MAX_M = 3.0
SETTLE_S = 1.2            # how quickly off-ball players close on their spot

# Events whose x, y is where the ball is. The others mark an off-ball player.
OFF_BALL = {"pressure", "card", "substitution"}
# The player in these events has the ball at that moment.
OWNS = {"kickoff", "pass", "carry", "shot", "clearance", "interception", "save", "throw_in",
        "corner", "goal_kick", "free_kick", "duel", "block"}
# After these the ball leaves the player (it flies, or play stops).
RELEASES = {"pass", "shot", "clearance", "block"}
STOPS = {"goal", "out_of_play", "offside", "period_end"}
RESTART_TYPES = {"kickoff", "throw_in", "corner", "goal_kick", "free_kick"}
TO_SPOT_S = 2.0           # after a stoppage the ball reaches the restart spot this fast


def attacks_right(team: str, period: int, home: str) -> bool:
    return (team == home) == (period == 1)


def _frame(t: float, n: int) -> int:
    return min(max(int(round(t * HZ)), 0), n - 1)


def _flight(e: dict[str, Any]) -> float:
    return float(e["length_m"]) / max(float(e["ball_speed_kmh"]) / 3.6, 1.0)


# ---- 1. first touch -------------------------------------------------------------------

def first_touch(events: list[dict[str, Any]], home: str, rng: np.random.Generator) -> None:
    """Move ball events that sit on a held ball's spot along a slow forward drift.

    A hold that ends in a shot stays put: the shot's outcome was sampled from the xG at its
    exact spot, so the shot must not move.
    """
    chains: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    hold: dict[str, Any] | None = None  # spot, drifted position, time, direction, distance
    chain: list[dict[str, Any]] = []
    for e in events:
        kind = e["type"]
        if kind in OFF_BALL:
            continue
        if hold is not None and math.dist((e["x"], e["y"]), hold["spot"]) <= 0.5:
            chain.append(e)
        else:
            hold = None
        if kind in RELEASES or kind in STOPS or kind == "carry" or (
                kind == "foul" and not e["advantage"]):
            hold = None
        if kind == "pass" and e["outcome"] == "complete":
            hold = _new_hold(e, e["t"] + _flight(e), home, rng)
        elif kind == "carry":
            hold = _new_hold(e, e["t"] + float(e["duration_s"]), home, rng)
        if hold is not None and (not chains or chains[-1][0] is not hold):
            chain = []
            chains.append((hold, chain))
    for hold, held in chains:
        if any(e["type"] == "shot" for e in held):
            continue
        for e in held:
            step = min(TOUCH_SPEED * max(0.0, e["t"] - hold["t"]), TOUCH_MAX_M - hold["moved"])
            x = min(max(hold["at"][0] + hold["dir"][0] * step, 0.5), LENGTH - 0.5)
            y = min(max(hold["at"][1] + hold["dir"][1] * step, 0.5), WIDTH - 0.5)
            e["x"], e["y"] = round(x, 2), round(y, 2)
            hold.update(at=(x, y), t=e["t"], moved=hold["moved"] + step)


def _new_hold(e: dict[str, Any], t: float, home: str, rng: np.random.Generator) -> dict[str, Any]:
    sign = 1.0 if attacks_right(e["team_id"], e["period"], home) else -1.0
    angle = rng.uniform(-0.6, 0.6)
    spot = (float(e["end_x"]), float(e["end_y"]))
    return {"spot": spot, "at": spot, "t": t, "moved": 0.0,
            "dir": (sign * math.cos(angle), math.sin(angle))}


# ---- 2. ball --------------------------------------------------------------------------

def _stops_play(e: dict[str, Any]) -> bool:
    return e["type"] in STOPS or (e["type"] == "foul" and not e["advantage"])


def ball_keyframes(events: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ball positions at event times, plus where passes and carries end.

    An end point that comes after the next ball event is dropped: the ball was cut out (an
    interception, a block) before it got there, so it goes straight to the next event.
    """
    on_ball = [e for e in events if e["type"] not in OFF_BALL]
    ts, xs, ys = [], [], []
    for i, e in enumerate(on_ball):
        ts.append(e["t"])
        xs.append(e["x"])
        ys.append(e["y"])
        nxt = on_ball[i + 1] if i + 1 < len(on_ball) else None
        if _stops_play(e) and nxt is not None and nxt["type"] in RESTART_TYPES \
                and nxt["t"] - e["t"] > TO_SPOT_S:
            # Play stopped: the ball is fetched and placed at the restart spot (spec 6.6).
            ts.append(e["t"] + TO_SPOT_S)
            xs.append(nxt["x"])
            ys.append(nxt["y"])
        if e["type"] not in ("pass", "carry"):
            continue
        end = e["t"] + (_flight(e) if e["type"] == "pass" else float(e["duration_s"]))
        next_t = on_ball[i + 1]["t"] if i + 1 < len(on_ball) else math.inf
        if end <= next_t:
            ts.append(end)
            xs.append(e["end_x"])
            ys.append(e["end_y"])
    order = np.argsort(np.asarray(ts), kind="stable")
    return np.asarray(ts)[order], np.asarray(xs)[order], np.asarray(ys)[order]


# ---- 3. players -----------------------------------------------------------------------

class Plan:
    """Per-frame facts from the events: who has the ball, and who must be where by when."""

    def __init__(self, n: int, slot_ids: list[str]) -> None:
        self.n = n
        self.owner = np.full(n, -1, dtype=np.int16)
        self.target = np.full((n, 22, 2), np.nan)
        self.eta = np.full((n, 22), np.inf)
        self.period = np.ones(n, dtype=np.int8)
        self.home_ball = np.zeros(n, dtype=bool)
        self.active = np.ones((n, 22), dtype=bool)
        self.top_mps = np.zeros((n, 22))
        self.slot_ids = slot_ids

    def aim(self, slot: int, t_from: float, t_at: float, x: float, y: float) -> None:
        """Slot must reach (x, y) by t_at, starting from t_from."""
        f0, f1 = _frame(t_from, self.n), _frame(t_at, self.n)
        for f in range(f0, f1 + 1):
            eta = t_at - f / HZ
            if eta < self.eta[f, slot]:
                self.eta[f, slot] = max(eta, 0.0)
                self.target[f, slot] = (x, y)


def build_plan(meta: dict[str, Any], events: list[dict[str, Any]], n: int) -> Plan:
    home = meta["home_team_id"]
    teams = {t["id"]: t for t in meta["teams"]}
    players = {p["id"]: p for t in meta["teams"] for p in t["players"]}
    slot_ids = list(teams[home]["lineup"]) + list(teams[meta["away_team_id"]]["lineup"])
    plan = Plan(n, slot_ids)
    slot_of = {pid: i for i, pid in enumerate(slot_ids)}
    for i, pid in enumerate(slot_ids):
        plan.top_mps[:, i] = players[pid]["top_speed_kmh"] / 3.6

    changes: list[tuple[int, int]] = []    # (frame, owner slot or -1)
    in_play_owner = home
    stopped_at = math.inf
    for e in events:
        t, kind = e["t"], e["type"]
        f = _frame(t, n)
        if kind == "period_start":
            plan.period[f:] = e["period"]
        if kind == "possession_change":
            in_play_owner = e["to_team_id"]
        if kind in ("kickoff", "possession_change"):
            plan.home_ball[f:] = in_play_owner == home
        if kind == "substitution" and e["player_off_id"] in slot_of:
            slot = slot_of.pop(e["player_off_id"])
            slot_of[e["player_on_id"]] = slot
            plan.top_mps[f:, slot] = players[e["player_on_id"]]["top_speed_kmh"] / 3.6
        if kind == "card" and e["card"] in ("red", "second_yellow") and e["player_id"] in slot_of:
            plan.active[f:, slot_of[e["player_id"]]] = False

        actor = slot_of.get(e["player_id"] or "")
        if actor is not None and kind not in ("substitution", "card"):
            # A set-piece taker walks to the spot as soon as play stops.
            start = min(t - LOOKAHEAD_S, stopped_at) if kind in RESTART_TYPES else t - LOOKAHEAD_S
            plan.aim(actor, start, t, e["x"], e["y"])
        if _stops_play(e):
            stopped_at = t
        elif kind in RESTART_TYPES:
            stopped_at = math.inf
        for key in ("opponent_id", "fouled_id"):
            other = slot_of.get(e.get(key) or "")
            if other is not None:
                plan.aim(other, t - LOOKAHEAD_S, t, e["x"], e["y"])

        if actor is not None and (kind in OWNS or (kind == "possession_change" and e["player_id"])
                                  or (kind == "tackle" and e["outcome"] == "won")):
            changes.append((f, actor))
        if kind in STOPS or kind in RELEASES:
            changes.append((f + 1, -1))
        if kind == "pass" and e["outcome"] == "complete":
            receiver = slot_of.get(e["receiver_id"] or "")
            if receiver is not None:
                arrive = t + _flight(e)
                plan.aim(receiver, t - RUN_EARLY_S, arrive, e["end_x"], e["end_y"])
                changes.append((_frame(arrive, n), receiver))

    changes.sort(key=lambda c: c[0])
    current, last = -1, 0
    for f, slot in changes:
        plan.owner[last:f] = current
        current, last = slot, f
    plan.owner[last:] = current
    return plan


def simulate_tracking(meta: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    rng = np.random.default_rng(int(meta["seed"]) * 7919 + 17)
    home = meta["home_team_id"]
    teams = {t["id"]: t for t in meta["teams"]}
    first_touch(events, home, rng)

    duration = events[-1]["t"]
    n = int(duration * HZ) + 1
    frame_t = np.arange(n) / HZ
    kt, kx, ky = ball_keyframes(events)
    ball = np.stack([np.interp(frame_t, kt, kx), np.interp(frame_t, kt, ky)], axis=1)
    plan = build_plan(meta, events, n)
    slot_ids = plan.slot_ids
    slot_team = [home] * 11 + [meta["away_team_id"]] * 11
    spots = np.array([teams[slot_team[i]]["spots"][pid] for i, pid in enumerate(slot_ids)],
                     dtype=float)
    is_home = np.arange(22) < 11

    # Per-player character, so the team doesn't move as one block.
    shift_u = rng.uniform(0.35, 0.65, 22)
    shift_v = rng.uniform(0.2, 0.5, 22)
    amp = rng.uniform(0.5, 1.5, (22, 2, 2))
    freq = 2 * math.pi / rng.uniform(9.0, 26.0, (22, 2, 2))
    phase = rng.uniform(0, 2 * math.pi, (22, 2, 2))
    keeper = np.array([spots[i, 0] < 10 for i in range(22)])
    amp[keeper] *= 0.4

    positions = np.zeros((n, 23, 2))
    pos = np.empty((22, 2))
    vel = np.zeros((22, 2))
    for f in range(n):
        t = f / HZ
        right = plan.period[f] == 1
        team_right = np.where(is_home, right, not right)
        bu = np.where(team_right, ball[f, 0], LENGTH - ball[f, 0])
        bv = np.where(team_right, ball[f, 1], WIDTH - ball[f, 1])
        has_ball = np.where(is_home, plan.home_ball[f], not plan.home_ball[f])
        spread = np.where(has_ball, 1.0, 0.8)
        noise = (amp * np.sin(freq * t + phase)).sum(axis=2)
        tu = 45 + (spots[:, 0] - 45) * spread + shift_u * (bu - 45) + noise[:, 0]
        tv = 34 + (spots[:, 1] - 34) * spread + shift_v * (bv - 34) + noise[:, 1]
        tu = np.clip(tu, 1, LENGTH - 1)
        tv = np.clip(tv, 1, WIDTH - 1)
        target = np.stack([np.where(team_right, tu, LENGTH - tu),
                           np.where(team_right, tv, WIDTH - tv)], axis=1)
        if f == 0:
            pos = target.copy()

        top = plan.top_mps[f]
        desired = (target - pos) / SETTLE_S
        cap = top * 0.75
        accel = np.full(22, ACCEL)

        aimed = ~np.isnan(plan.target[f, :, 0])
        if aimed.any():
            gap = plan.target[f, aimed] - pos[aimed]
            dist = np.linalg.norm(gap, axis=1)
            speed = np.minimum(dist / np.maximum(plan.eta[f, aimed], 0.3) + 0.5, top[aimed])
            desired[aimed] = gap / np.maximum(dist, 1e-6)[:, None] * speed[:, None]
            cap = np.where(aimed, top, cap)
            accel[aimed] = ACCEL * 1.4

        owner = int(plan.owner[f])
        if owner >= 0:
            _chase(pos, desired, owner, ball[f], is_home, team_right, aimed, top)
            gap = ball[f] - pos[owner]
            desired[owner] = gap / max(float(np.linalg.norm(gap)), 1e-6) * top[owner]
            cap = np.where(np.arange(22) == owner, top, cap)
            accel[owner] = OWNER_ACCEL

        speed = np.linalg.norm(desired, axis=1)
        desired *= (np.minimum(speed, cap) / np.maximum(speed, 1e-6))[:, None]
        dv = desired - vel
        dv_len = np.linalg.norm(dv, axis=1)
        dv *= (np.minimum(dv_len, accel / HZ) / np.maximum(dv_len, 1e-6))[:, None]
        vel = vel + dv
        before = pos
        pos = pos + vel / HZ
        if owner >= 0:
            _attach(pos, vel, before[owner], owner, ball, f, bool(team_right[owner]),
                    float(top[owner]))
        np.clip(pos[:, 0], 0, LENGTH, out=pos[:, 0])
        np.clip(pos[:, 1], 0, WIDTH, out=pos[:, 1])
        positions[f, :22] = pos
    positions[:, 22] = ball
    positions = np.round(positions * 10).astype(np.int16)
    positions[:, :22][~plan.active] = -1
    rewrite_events(events, positions, slot_ids)
    return {"positions": positions, "slot_ids": np.array(slot_ids), "hz": np.array(HZ)}


def _chase(pos: np.ndarray, desired: np.ndarray, owner: int, ball: np.ndarray,
           is_home: np.ndarray, team_right: np.ndarray, aimed: np.ndarray,
           top: np.ndarray) -> None:
    """The nearest opponents not already in the action close down the carrier, goal side."""
    opponents = np.flatnonzero((is_home != is_home[owner]) & ~aimed)
    dist = np.linalg.norm(pos[opponents] - ball, axis=1)
    for i in opponents[np.argsort(dist)][:CHASERS]:
        if np.linalg.norm(pos[i] - ball) > CHASE_RADIUS_M:
            break
        own_goal_x = 0.0 if team_right[i] else LENGTH
        goal_side = np.array([own_goal_x - ball[0], WIDTH / 2 - ball[1]])
        spot = ball + goal_side / max(float(np.linalg.norm(goal_side)), 1e-6) * 1.8
        gap = spot - pos[i]
        desired[i] = gap / max(float(np.linalg.norm(gap)), 1e-6) * min(
            float(np.linalg.norm(gap)) / 0.6, top[i] * 0.9)


def _attach(pos: np.ndarray, vel: np.ndarray, before: np.ndarray, owner: int, ball: np.ndarray,
            f: int, right: bool, top: float) -> None:
    """Close enough, the player on the ball moves with it, just behind it."""
    prev = ball[f - 1] if f > 0 else ball[f]
    ball_vel = (ball[f] - prev) * HZ
    if np.linalg.norm(ball[f] - pos[owner]) > ATTACH_M or np.linalg.norm(ball_vel) > top:
        return
    back = -OWNER_OFFSET_M if right else OWNER_OFFSET_M
    step = ball[f] + (back, 0.0) - before
    length = float(np.linalg.norm(step))
    if length > top / HZ:   # this frame's move replaces the run, never faster than top speed
        step *= top / HZ / length
    pos[owner] = before + step
    vel[owner] = ball_vel


# ---- 4. rewrite -----------------------------------------------------------------------

def rewrite_events(events: list[dict[str, Any]], positions: np.ndarray,
                   slot_ids: list[str]) -> None:
    """Put every event on its player's tracked position (spec 6.6)."""
    n = len(positions)
    slot_of = {pid: i for i, pid in enumerate(slot_ids)}
    for e in events:
        if e["type"] == "substitution" and e["player_off_id"] in slot_of:
            slot_of[e["player_on_id"]] = slot_of.pop(e["player_off_id"])
        slot = slot_of.get(e["player_id"] or "")
        if slot is None:
            continue
        x, y = positions[_frame(e["t"], n), slot]
        if x >= 0:
            e["x"], e["y"] = round(float(x) / 10, 2), round(float(y) / 10, 2)


def player_distances_km(tracking: dict[str, Any]) -> np.ndarray:
    pos = tracking["positions"][:, :22].astype(float) / 10
    step = np.hypot(*np.diff(pos, axis=0).transpose(2, 0, 1))
    valid = (tracking["positions"][1:, :22, 0] >= 0) & (tracking["positions"][:-1, :22, 0] >= 0)
    return np.asarray((step * valid).sum(axis=0) / 1000)


def top_speed_kmh(tracking: dict[str, Any]) -> float:
    """Fastest 0.5 s average speed of any player (spec 7.8)."""
    pos = tracking["positions"][:, :22].astype(float) / 10
    hz = int(tracking["hz"])
    window = hz // 2
    moved = np.hypot(*(pos[window:] - pos[:-window]).transpose(2, 0, 1))
    valid = (tracking["positions"][window:, :22, 0] >= 0) & \
        (tracking["positions"][:-window, :22, 0] >= 0)
    return float((moved * valid).max() / (window / hz) * 3.6)
