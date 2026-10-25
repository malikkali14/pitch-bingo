"""Player and ball tracking at 10 Hz (spec 6.6).

This is the simple version: the ball follows the events, and every player drifts toward a
target spot (their formation spot shifted toward the ball) at no more than their top speed.
It covers steps 1, 2 and the speed cap of step 4. Still to do, by the movement-model owner:
step 3 (passer, receiver, carrier and chasers in the action), acceleration and smooth noise
(step 4), and rewriting each event's x and y to the tracked position (the 0.5 m test in 6.9).

Output arrays, saved to tracking.npz:
  positions  int16 (frames, 23, 2) in decimetres; slots 0-10 home, 11-21 away, 22 the ball.
             A slot reads -1, -1 after its player is sent off.
  slot_ids   the 22 starting player ids; a substitution hands the slot to player_on_id.
  hz         frames per second (10).
"""

from typing import Any

import numpy as np

HZ = 10
LENGTH, WIDTH = 105.0, 68.0
MODEL = "fallback"


def ball_keyframes(events: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ts, xs, ys = [], [], []
    for e in events:
        ts.append(e["t"])
        xs.append(e["x"])
        ys.append(e["y"])
        if e["type"] == "pass":
            flight = e["length_m"] / max(e["ball_speed_kmh"] / 3.6, 1.0)
            ts.append(e["t"] + flight)
            xs.append(e["end_x"])
            ys.append(e["end_y"])
        elif e["type"] == "carry":
            ts.append(e["t"] + e["duration_s"])
            xs.append(e["end_x"])
            ys.append(e["end_y"])
    order = np.argsort(np.asarray(ts), kind="stable")
    return np.asarray(ts)[order], np.asarray(xs)[order], np.asarray(ys)[order]


def simulate_tracking(meta: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    home = meta["home_team_id"]
    teams = {t["id"]: t for t in meta["teams"]}
    players = {p["id"]: p for t in meta["teams"] for p in t["players"]}
    slot_ids = list(teams[home]["lineup"]) + list(teams[meta["away_team_id"]]["lineup"])
    slot_team = [home] * 11 + [meta["away_team_id"]] * 11
    spots = np.array([teams[slot_team[i]]["spots"][pid] for i, pid in enumerate(slot_ids)],
                     dtype=float)

    duration = events[-1]["t"]
    n = int(duration * HZ) + 1
    frame_t = np.arange(n) / HZ
    kt, kx, ky = ball_keyframes(events)
    ball = np.stack([np.interp(frame_t, kt, kx), np.interp(frame_t, kt, ky)], axis=1)

    # Per-frame state that changes at events: period, team in possession, active slots.
    period = np.ones(n, dtype=np.int8)
    in_possession = np.zeros(n, dtype=bool)  # True when the home club has the ball
    max_step = np.empty(22)
    for i, pid in enumerate(slot_ids):
        max_step[i] = players[pid]["top_speed_kmh"] / 3.6 / HZ
    active = np.ones((n, 22), dtype=bool)
    owner = home
    slot_of = {pid: i for i, pid in enumerate(slot_ids)}
    for e in events:
        f = min(int(e["t"] * HZ), n - 1)
        if e["type"] == "period_start":
            period[f:] = e["period"]
        if e["type"] == "possession_change":
            owner = e["to_team_id"]
        if e["type"] in ("kickoff", "possession_change"):
            in_possession[f:] = owner == home
        if e["type"] == "substitution" and e["player_off_id"] in slot_of:
            slot = slot_of.pop(e["player_off_id"])
            slot_of[e["player_on_id"]] = slot
            max_step[slot] = players[e["player_on_id"]]["top_speed_kmh"] / 3.6 / HZ
        if e["type"] == "card" and e["card"] in ("red", "second_yellow"):
            sent_off = slot_of.get(e["player_id"])
            if sent_off is not None:
                active[f:, sent_off] = False

    positions = np.zeros((n, 23, 2))
    current = np.empty((22, 2))
    home_right = period == 1
    for f in range(n):
        right = home_right[f]
        # Each slot's attacking direction this frame, then the ball in that frame.
        team_right = np.where(np.arange(22) < 11, right, not right)
        bu = np.where(team_right, ball[f, 0], LENGTH - ball[f, 0])
        bv = np.where(team_right, ball[f, 1], WIDTH - ball[f, 1])
        has_ball = np.where(np.arange(22) < 11, in_possession[f], not in_possession[f])
        spread = np.where(has_ball, 1.0, 0.8)
        tu = 45 + (spots[:, 0] - 45) * spread + 0.5 * (bu - 45)
        tv = 34 + (spots[:, 1] - 34) * spread + 0.35 * (bv - 34)
        tu = np.clip(tu, 1, LENGTH - 1)
        tv = np.clip(tv, 1, WIDTH - 1)
        tx = np.where(team_right, tu, LENGTH - tu)
        ty = np.where(team_right, tv, WIDTH - tv)
        target = np.stack([tx, ty], axis=1)
        if f == 0:
            current = target.copy()
        else:
            delta = target - current
            dist = np.hypot(delta[:, 0], delta[:, 1])
            scale = np.minimum(1.0, max_step / np.maximum(dist, 1e-9))
            current = current + delta * scale[:, None]
        positions[f, :22] = current
    positions[:, 22] = ball
    positions = np.round(positions * 10).astype(np.int16)
    positions[:, :22][~active] = -1
    return {"positions": positions, "slot_ids": np.array(slot_ids), "hz": np.array(HZ)}


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
