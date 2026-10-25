"""Match aggregates used by validation (spec 6.8 measures)."""

from typing import Any

from app.generator import movement
from app.stats.xg import attacks_right, shot_offsets, shot_xg


def shot_xg_from_log(events: list[dict[str, Any]], index: int, home_team_id: str) -> float:
    """xG of the shot at events[index], using the pass that set it up for assisted_chance."""
    shot = events[index]
    assisted = False
    for prev in reversed(events[:index]):
        if prev["possession_id"] != shot["possession_id"]:
            break
        if prev["type"] == "pass":
            assisted = prev["pass_type"] in ("through_ball", "cutback")
            break
    dx, dy = shot_offsets(shot["x"], shot["y"],
                          attacks_right(shot["team_id"], shot["period"], home_team_id))
    return shot_xg(dx, dy, header=shot["shot_type"] == "header", assisted_chance=assisted,
                   pressure=shot["under_pressure"], shot_type=shot["shot_type"])


def summarize(meta: dict[str, Any], events: list[dict[str, Any]], in_play_s: float,
              on_ball_s: dict[str, float], tracking: dict[str, Any] | None) -> dict[str, Any]:
    home, away = meta["home_team_id"], meta["away_team_id"]

    def count(type_: str, **match: Any) -> int:
        return sum(1 for e in events if e["type"] == type_
                   and all(e.get(k) == v for k, v in match.items()))

    passes = count("pass")
    completed = count("pass", outcome="complete")
    shots = count("shot")
    on_target = sum(1 for e in events if e["type"] == "shot" and e["outcome"] in ("goal", "saved"))
    xg = {home: 0.0, away: 0.0}
    for i, e in enumerate(events):
        if e["type"] == "shot":
            xg[e["team_id"]] += shot_xg_from_log(events, i, home)
    goals = {t: count("goal", team_id=t) for t in (home, away)}
    total_ball = sum(on_ball_s.values()) or 1.0
    summary: dict[str, Any] = {
        "score": goals,
        "passes": passes,
        "pass_completion": round(completed / passes, 4) if passes else 0.0,
        "shots": shots,
        "shots_on_target_pct": round(on_target / shots, 4) if shots else 0.0,
        "goals": sum(goals.values()),
        "xg_total": round(sum(xg.values()), 3),
        "xg": {t: round(v, 3) for t, v in xg.items()},
        "fouls": count("foul"),
        "yellow_cards": count("card", card="yellow"),
        "red_cards": count("card", card="red") + count("card", card="second_yellow"),
        "corners": count("corner"),
        "offsides": count("offside"),
        "throw_ins": count("throw_in"),
        "substitutions": count("substitution"),
        "tackles": count("tackle"),
        "interceptions": count("interception"),
        "possession": {home: round(on_ball_s[home] / total_ball, 4),
                       away: round(on_ball_s[away] / total_ball, 4)},
        "ball_in_play_min": round(in_play_s / 60, 2),
        "duration_s": events[-1]["t"],
        "tracking_model": movement.MODEL,
    }
    if tracking is not None:
        dist = movement.player_distances_km(tracking)
        slots = list(tracking["slot_ids"])
        players = {p["id"]: p for t in meta["teams"] for p in t["players"]}
        outfield = [i for i, pid in enumerate(slots) if players[str(pid)]["position"] != "GK"]
        summary["distance_per_outfield_km"] = round(float(dist[outfield].mean()), 2)
        summary["top_speed_kmh"] = round(movement.top_speed_kmh(tracking), 1)
    return summary
