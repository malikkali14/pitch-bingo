"""Possession-chain match simulator (spec 6.5).

The simulator works in the attacking frame of the club on the ball: u runs from that club's
own goal (0) to the goal it attacks (105), v across the pitch (0 to 68). Events are written in
the absolute frame of spec 6.3, where the home club attacks x = 105 in the first half.
"""

import math
import random
from collections.abc import Callable
from typing import Any

from app.stats.passes import BASE_LOGIT, completion_probability
from app.stats.xg import shot_xg

LENGTH, WIDTH = 105.0, 68.0
BOX_U, BOX_V0, BOX_V1 = 88.5, 13.85, 54.15
HALF_S = 45 * 60

# Planted-moment segments in match minutes (spec 6.7).
SEGMENTS = [(5, 20), (20, 38), (38, 60), (60, 75), (75, 88)]

ATTACK_GROUP = {"ST", "LW", "RW", "AM"}
MID_GROUP = {"CM", "DM", "AM"}
BACK_GROUP = {"CB", "RB", "LB"}

# Event-type tags used by masks and moments (spec 4).
TYPE_TAGS = {
    "shot": ["shots"], "goal": ["goals"], "save": ["shots"], "foul": ["fouls"],
    "advantage": ["fouls"], "card": ["cards"], "corner": ["corners", "restarts"],
    "throw_in": ["restarts"], "goal_kick": ["restarts"], "free_kick": ["restarts"],
    "offside": ["offsides"], "substitution": ["subs"], "pass": ["passes"],
    "tackle": ["defending"], "interception": ["defending"], "clearance": ["defending"],
    "block": ["defending"], "duel": ["defending"], "pressure": ["defending"],
}


class PossessionOver(Exception):  # noqa: N818 - control flow, not an error
    """Raised inside a possession when the ball is lost or play stops."""


class Sim:
    def __init__(self, meta: dict[str, Any], seed: int):
        self.meta = meta
        self.rng = random.Random(f"sim-{seed}")
        self.home = meta["home_team_id"]
        self.away = meta["away_team_id"]
        self.teams = {t["id"]: t for t in meta["teams"]}
        self.players = {p["id"]: p for t in meta["teams"] for p in t["players"]}
        self.team_of = {p["id"]: t["id"] for t in meta["teams"] for p in t["players"]}
        self.on_pitch = {t["id"]: list(t["lineup"]) for t in meta["teams"]}
        self.bench = {t["id"]: list(t["bench"]) for t in meta["teams"]}
        self.spot = {pid: tuple(xy) for t in meta["teams"] for pid, xy in t["spots"].items()}
        self.strictness = meta["referee"]["strictness"]

        self.events: list[dict[str, Any]] = []
        self.t = 0.0
        self.period = 1
        self.period_start = 0.0
        self.possession_id = 0
        self.team = self.home
        self.carrier = self.on_pitch[self.home][0]
        self.u, self.v = 52.5, 34.0
        self.pressured = False
        self.score = {self.home: 0, self.away: 0}
        self.yellows: set[str] = set()
        self.in_play_s = 0.0
        self.on_ball_s = {self.home: 0.0, self.away: 0.0}
        self.last_pass: dict[str, Any] | None = None
        self.open_pressures: list[dict[str, Any]] = []
        self.pending_subs = self._plan_subs()
        self.plants: dict[int, str] = {}
        self.plant_minutes = [self.rng.uniform(a + 1, b - 4) for a, b in SEGMENTS]
        self.planted: dict[int, dict[str, Any]] = {}

    # ---- frames, clock and output ------------------------------------------------------

    def other(self, team: str) -> str:
        return self.away if team == self.home else self.home

    def attacks_right(self, team: str) -> bool:
        return (team == self.home) == (self.period == 1)

    def to_abs(self, team: str, u: float, v: float) -> tuple[float, float]:
        if self.attacks_right(team):
            return u, v
        return LENGTH - u, WIDTH - v

    def minute(self) -> float:
        elapsed = (self.t - self.period_start) / 60
        return elapsed if self.period == 1 else 45 + elapsed

    def clock(self) -> str:
        elapsed = self.t - self.period_start
        base = 0 if self.period == 1 else HALF_S
        if elapsed <= HALF_S:
            total = int(base + elapsed)
            return f"{total // 60:02d}:{total % 60:02d}"
        extra = int(elapsed - HALF_S)
        return f"{(base + HALF_S) // 60}+{extra // 60}:{extra % 60:02d}"

    def play(self, dt: float) -> None:
        self.t += dt
        self.in_play_s += dt
        self.on_ball_s[self.team] += dt

    def dead(self, dt: float) -> None:
        self.t += dt

    def emit(
        self,
        type_: str,
        team: str | None = None,
        player: str | None = None,
        u: float | None = None,
        v: float | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        team = team if team is not None else self.team
        if u is None or v is None:
            u, v = self.u, self.v
            if team != self.team:
                u, v = LENGTH - u, WIDTH - v
        x, y = self.to_abs(team, clamp(u, 0, LENGTH), clamp(v, 0, WIDTH))
        tags = list(TYPE_TAGS.get(type_, []))
        tags += extra.pop("tags", [])
        event = {
            "event_id": f"e{len(self.events) + 1:06d}",
            "seq": len(self.events) + 1,
            "t": round(self.t, 2),
            "period": self.period,
            "clock": self.clock(),
            "type": type_,
            "team_id": team,
            "player_id": player,
            "x": round(x, 2),
            "y": round(y, 2),
            "possession_id": self.possession_id,
            "under_pressure": bool(extra.pop("under_pressure", False)),
            "tags": tags,
            **extra,
        }
        self.events.append(event)
        return event

    def end_xy(self, team: str, u: float, v: float) -> tuple[float, float]:
        x, y = self.to_abs(team, clamp(u, 0, LENGTH), clamp(v, 0, WIDTH))
        return round(x, 2), round(y, 2)

    # ---- squad helpers -----------------------------------------------------------------

    def pos(self, pid: str) -> str:
        return str(self.players[pid]["position"])

    def attr(self, pid: str, name: str) -> float:
        return float(self.players[pid]["attributes"][name])

    def keeper(self, team: str) -> str:
        return next(p for p in self.on_pitch[team] if self.pos(p) == "GK")

    def outfield(self, team: str) -> list[str]:
        return [p for p in self.on_pitch[team] if self.pos(p) != "GK"]

    def pick(self, team: str, near: tuple[float, float], exclude: str | None = None) -> str:
        """A player of `team` weighted toward those whose spot is near (u, v) in their frame."""
        options = [p for p in self.outfield(team) if p != exclude]
        weights = []
        for p in options:
            su, sv = self.spot.get(p, (52.5, 34.0))
            d = math.hypot(su - near[0], sv - near[1])
            weights.append(1.0 / (8.0 + d) ** 2)
        return self.rng.choices(options, weights)[0]

    def defender_near(self) -> str:
        """The opponent closest to the ball, using the mirrored formation spot."""
        return self.pick(self.other(self.team), (LENGTH - self.u, WIDTH - self.v))

    def style(self, team: str, key: str) -> float:
        value = float(self.teams[team]["style"][key])
        if key in ("tempo", "pressing") and self.minute() >= 60:
            diff = self.score[team] - self.score[self.other(team)]
            value += 0.15 if diff < 0 else -0.1 if diff > 0 else 0.0
        return clamp(value, 0.0, 1.0)

    # ---- possession changes and restarts -----------------------------------------------

    def change_possession(self, cause: str, player: str | None = None) -> None:
        old = self.team
        new = self.other(old)
        self.possession_id += 1
        self.emit("possession_change", team=new, player=player, from_team_id=old,
                  to_team_id=new, cause=cause)
        for p in self.open_pressures:
            if self.t - p["t"] <= 5.0 and p["team_id"] == new:
                p["regained_within_5s"] = True
        self.open_pressures.clear()
        self.team = new
        self.u, self.v = LENGTH - self.u, WIDTH - self.v
        self.carrier = player or self.pick(new, (self.u, self.v))
        self.pressured = False
        self.last_pass = None

    def give_to(self, team: str, cause: str, player: str | None = None) -> None:
        if team != self.team:
            self.change_possession(cause, player)
        elif player:
            self.carrier = player

    def restart(self, kind: str, team: str, u: float, v: float, **extra: Any) -> None:
        """Hand a dead ball to `team` at (u, v) in its frame and emit the restart event."""
        if team != self.team:
            self.u, self.v = LENGTH - u, WIDTH - v
            self.change_possession(extra.pop("cause", "out_of_play"))
        extra.pop("cause", None)
        self.u, self.v = u, v
        self.do_subs()
        if kind == "throw_in":
            taker = self.pick(team, (u, v))
            self.dead(self.rng.uniform(10, 20))
        elif kind == "corner":
            taker = self.pick(team, (95, v))
            self.dead(self.rng.uniform(20, 40))
        elif kind == "goal_kick":
            taker = self.keeper(team)
            self.dead(self.rng.uniform(20, 35))
        else:
            taker = self.pick(team, (u, v))
            self.dead(self.rng.uniform(15, 40))
        self.carrier = taker
        self.emit(kind, team=team, player=taker, **extra)

    def out_of_play(self, last_touch: str, over_end_line: bool, u: float, v: float) -> None:
        """Ball out off `last_touch` at (u, v) in the frame of the club on the ball."""
        self.u, self.v = u, v
        self.emit("out_of_play", player=None, last_touch_team_id=last_touch)
        attacking = self.team
        if over_end_line and u > LENGTH / 2:
            if last_touch == attacking:
                self.restart("goal_kick", self.other(attacking), 5.5, 34)
            else:
                corner_v = 0.5 if v < WIDTH / 2 else WIDTH - 0.5
                self.restart("corner", attacking, LENGTH - 0.5, corner_v, side=side_of(corner_v))
        else:
            side_v = 0.5 if v < WIDTH / 2 else WIDTH - 0.5
            taker_team = self.other(last_touch)
            uu = u if taker_team == attacking else LENGTH - u
            vv = side_v if taker_team == attacking else WIDTH - side_v
            self.restart("throw_in", taker_team, clamp(uu, 1, 104), vv, side=side_of(vv))
        raise PossessionOver

    # ---- substitutions -----------------------------------------------------------------

    def _plan_subs(self) -> dict[str, list[float]]:
        return {
            team: sorted(self.rng.uniform(55, 85) for _ in range(self.rng.randint(3, 5)))
            for team in (self.home, self.away)
        }

    def do_subs(self) -> None:
        for team, times in self.pending_subs.items():
            while times and times[0] <= self.minute() and self.bench[team]:
                times.pop(0)
                off_options = [p for p in self.outfield(team) if self.pos(p) != "CB"]
                weights = [3 if self.pos(p) in ATTACK_GROUP else 2 if self.pos(p) in MID_GROUP
                           else 1 for p in off_options]
                off = self.rng.choices(off_options, weights)[0]
                group = (ATTACK_GROUP if self.pos(off) in ATTACK_GROUP else MID_GROUP
                         if self.pos(off) in MID_GROUP else BACK_GROUP)
                bench = [p for p in self.bench[team] if self.pos(p) != "GK"]
                same = [p for p in bench if self.pos(p) in group] or bench
                on = self.rng.choice(same)
                self.bench[team].remove(on)
                self.on_pitch[team][self.on_pitch[team].index(off)] = on
                self.spot[on] = self.spot[off]
                if self.carrier == off:
                    self.carrier = on
                self.dead(self.rng.uniform(30, 45))
                self.emit("substitution", team=team, player=on, u=self.spot[on][0],
                          v=0.0, player_off_id=off, player_on_id=on)

    # ---- the match ---------------------------------------------------------------------

    def run(self) -> list[dict[str, Any]]:
        for period, kicker in ((1, self.home), (2, self.away)):
            self.period = period
            self.period_start = self.t
            stoppage = self.rng.randint(60, 240) if period == 1 else self.rng.randint(180, 420)
            self.team = kicker
            self.emit("period_start", team=kicker, player=None, u=52.5, v=34.0,
                      stoppage_added_s=None)
            self.kickoff(kicker)
            end = self.period_start + HALF_S + stoppage
            while self.t < end:
                planted = self.due_plant()
                try:
                    if planted is not None:
                        self.run_plant(planted)
                    else:
                        self.step()
                except PossessionOver:
                    pass
            self.emit("period_end", player=None, stoppage_added_s=stoppage)
        return self.events

    def kickoff(self, team: str) -> None:
        if team != self.team:
            self.team = team
        self.u, self.v = 52.5, 34.0
        self.carrier = next(p for p in self.on_pitch[team] if self.pos(p) == "ST") \
            if any(self.pos(p) == "ST" for p in self.on_pitch[team]) else self.pick(team, (60, 34))
        self.emit("kickoff", player=self.carrier)
        self.last_pass = None

    # ---- one action by the player on the ball ------------------------------------------

    def zone(self) -> str:
        if self.u >= BOX_U and BOX_V0 <= self.v <= BOX_V1:
            return "box"
        if self.u >= 70:
            return "final"
        if self.u >= 35:
            return "middle"
        return "defensive"

    def step(self) -> None:
        self.defend()
        zone = self.zone()
        tempo = self.style(self.team, "tempo")
        shot_p = {"box": 0.038, "final": 0.014, "middle": 0.0005, "defensive": 0.0}[zone]
        if self.last_pass and self.last_pass["pass_type"] in ("cross", "cutback") and zone == "box":
            shot_p = 0.22
        r = self.rng.random()
        if r < shot_p:
            self.shoot()
        elif r < shot_p + 0.25 - 0.06 * tempo:
            self.carry()
        else:
            self.pass_ball()

    def defend(self) -> None:
        defending = self.other(self.team)
        pressing = self.style(defending, "pressing")
        zone = self.zone()
        r = self.rng.random()
        foul_p = 0.019 * (0.7 + 0.6 * self.strictness) * (0.7 + 0.6 * pressing)
        tackle_p = 0.024 * (0.6 + 0.8 * pressing)
        duel_p = 0.03
        pressure_p = 0.12 * (0.5 + pressing)
        if zone == "box":
            foul_p *= 0.06
        if r < foul_p:
            self.foul()
        elif r < foul_p + tackle_p:
            self.tackle()
        elif r < foul_p + tackle_p + duel_p:
            self.ground_duel()
        elif r < foul_p + tackle_p + duel_p + pressure_p:
            presser = self.defender_near()
            event = self.emit("pressure", team=defending, player=presser,
                              target_id=self.carrier, duration_s=round(self.rng.uniform(1, 3), 1),
                              regained_within_5s=False)
            self.open_pressures.append(event)
            self.pressured = True
        else:
            self.pressured = self.rng.random() < 0.15

    def tackle(self) -> None:
        defender = self.defender_near()
        won = self.rng.random() < 0.55 + 0.003 * (self.attr(defender, "defending") - 60)
        self.emit("tackle", team=self.other(self.team), player=defender,
                  opponent_id=self.carrier, outcome="won" if won else "lost")
        if won:
            self.change_possession("tackle", defender)
            raise PossessionOver
        self.play(self.rng.uniform(0.5, 1.5))

    def ground_duel(self) -> None:
        defender = self.defender_near()
        won = self.rng.random() < 0.4
        self.emit("duel", player=self.carrier, duel_type="ground", opponent_id=defender,
                  outcome="lost" if won else "won", under_pressure=True)
        self.play(self.rng.uniform(0.5, 2))
        if won:
            self.change_possession("tackle", defender)
            raise PossessionOver

    def foul(self, *, by_attacker: bool | None = None, advantage: bool | None = None,
             severity: float | None = None) -> None:
        if by_attacker is None:
            by_attacker = self.rng.random() < 0.3
        fouled_team = self.other(self.team) if by_attacker else self.team
        offender_team = self.other(fouled_team)
        if by_attacker:
            offender, fouled = self.carrier, self.defender_near()
        else:
            offender, fouled = self.defender_near(), self.carrier
        discipline = self.attr(offender, "discipline")
        if severity is None:
            severity = self.rng.betavariate(2, 5) * (1.25 - discipline / 200)
        severity = round(clamp(severity, 0.0, 1.0), 2)
        if advantage is None:
            advantage = (not by_attacker and self.u > 50 and self.rng.random() < 0.25)
        foul = self.emit("foul", team=offender_team, player=offender, fouled_id=fouled,
                         severity=severity, advantage=advantage)
        if advantage:
            self.emit("advantage", team=fouled_team, player=None, foul_event_id=foul["event_id"],
                      tags=["fouls"])
        self.card(offender, offender_team, severity, foul["event_id"])
        if advantage:
            self.play(self.rng.uniform(0.5, 1.5))
            return
        u, v = self.u, self.v
        if fouled_team != self.team:
            u, v = LENGTH - u, WIDTH - v
        self.restart("free_kick", fouled_team, u, v, cause="foul")
        self.after_free_kick()

    def card(self, player: str, team: str, severity: float, foul_id: str) -> None:
        threshold = 0.43 - 0.12 * self.strictness
        card = None
        if severity > 0.82 and self.rng.random() < 0.3:
            card = "red"
        elif severity > threshold:
            if player in self.yellows:
                # Referees think twice before a second yellow.
                card = "second_yellow" if self.rng.random() < 0.2 else None
            else:
                card = "yellow"
                self.yellows.add(player)
        if card is None:
            return
        self.emit("card", team=team, player=player, card=card, foul_event_id=foul_id)
        if card in ("red", "second_yellow") and player in self.on_pitch[team]:
            self.on_pitch[team].remove(player)
            if self.carrier == player:
                self.carrier = self.pick(team, (self.u, self.v))

    def after_free_kick(self) -> None:
        if self.u >= BOX_U and BOX_V0 <= self.v <= BOX_V1:
            self.u, self.v = LENGTH - 11, 34.0
            self.shoot(shot_type="penalty")
        elif self.u > 75 and 18 < self.v < 50 and self.rng.random() < 0.35:
            self.shoot(shot_type="free_kick")

    # ---- passes and carries ------------------------------------------------------------

    def choose_pass(self) -> tuple[str, float, float]:
        rng, u, v = self.rng, self.u, self.v
        directness = self.style(self.team, "directness")
        wide = v < 15 or v > WIDTH - 15
        r = rng.random()
        if u > 72 and wide and r < 0.28:
            return "cross", rng.uniform(93, 100), rng.uniform(26, 42)
        if self.zone() == "box" and wide and r < 0.35:
            return "cutback", rng.uniform(88, 96), rng.uniform(26, 42)
        if 40 < u < 85 and r < 0.05 + 0.04 * directness:
            return "through_ball", min(u + rng.uniform(15, 30), 97), v + rng.uniform(-10, 10)
        if u < 50 and r < 0.04 + 0.10 * directness:
            return "long_ball", u + rng.uniform(35, 55), v + rng.uniform(-15, 15)
        if r < 0.03:
            target_v = rng.uniform(52, 64) if v < WIDTH / 2 else rng.uniform(4, 16)
            return "switch", u + rng.uniform(-5, 12), target_v
        length = rng.gammavariate(3.0, 5.0) + 3
        forward = rng.gauss(0.35 + 0.3 * directness, 0.55)
        angle = math.atan2(rng.gauss(0, 1), forward if abs(forward) > 0.05 else 0.05)
        return "open_play", min(u + length * math.cos(angle), 97), v + length * math.sin(angle)

    def pass_ball(self, *, forced: tuple[str, float, float] | None = None,
                  outcome: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        pass_type, eu, ev = forced or self.choose_pass()
        eu, ev = clamp(eu, 1, 104), clamp(ev, 1, 67)
        length = math.hypot(eu - self.u, ev - self.v)
        forward_m = eu - self.u
        backward = forward_m < 0
        height = {"cross": self.rng.choice(["high", "high", "low"]), "long_ball": "high",
                  "switch": self.rng.choice(["high", "low"])}.get(pass_type, "ground")
        if pass_type == "open_play" and length > 30:
            height = "high"
        bypassed = 0
        if forward_m > 0:
            bypassed = min(6, int(forward_m / 11 * self.rng.uniform(0.4, 1.4)))
        p = completion_probability(
            length,
            under_pressure=self.pressured,
            opponents_bypassed=bypassed,
            through_ball=pass_type == "through_ball",
            cross=pass_type == "cross",
            high=height == "high",
            backward=backward,
            base=BASE_LOGIT + 0.3 * (self.style(self.team, "possession") - 0.5),
        )
        receiver = self.pick(self.team, (eu, ev), exclude=self.carrier)
        if outcome is None:
            if self.rng.random() < p:
                outcome = "complete"
            elif pass_type in ("through_ball", "long_ball") and eu > 75 \
                    and self.rng.random() < 0.15:
                outcome = "offside"
            elif self.rng.random() < 0.26:
                outcome = "out"
            else:
                outcome = "incomplete"
        speed = 35 + 1.1 * length + (12 if height == "high" else 0) + self.rng.uniform(-6, 6)
        end_x, end_y = self.end_xy(self.team, eu, ev)
        event = self.emit(
            "pass", player=self.carrier, under_pressure=self.pressured, receiver_id=receiver,
            end_x=end_x, end_y=end_y, length_m=round(length, 1), height=height,
            pass_type=pass_type, outcome=outcome, ball_speed_kmh=round(speed, 1),
            opponents_bypassed=bypassed, tags=tags or [],
        )
        tempo = self.style(self.team, "tempo")
        self.play(self.rng.uniform(1.5, 4.0) - 0.8 * (tempo - 0.5))
        self.pressured = False
        if outcome == "complete":
            self.u, self.v, self.carrier = eu, ev, receiver
            self.last_pass = event
            return event
        self.last_pass = None
        if outcome == "offside":
            self.u, self.v = eu, ev
            self.emit("offside", player=receiver)
            self.restart("free_kick", self.other(self.team), LENGTH - eu, WIDTH - ev, cause="foul")
            raise PossessionOver
        if outcome == "out":
            over_end = eu > 100 or (pass_type in ("cross", "long_ball") and eu > 90
                                    and self.rng.random() < 0.6)
            self.out_of_play(self.team, over_end, eu, ev)
        self.u, self.v = eu, ev
        self.lose_loose_ball(height)
        raise PossessionOver

    def lose_loose_ball(self, height: str) -> None:
        defending = self.other(self.team)
        winner = self.pick(defending, (LENGTH - self.u, WIDTH - self.v))
        if height == "high" and self.rng.random() < 0.6:
            self.emit("duel", team=defending, player=winner, duel_type="aerial",
                      opponent_id=self.pick(self.team, (self.u, self.v)), outcome="won")
        elif self.u > 80 and self.rng.random() < 0.35:
            self.emit("clearance", team=defending, player=winner)
            r = self.rng.random()
            if r < 0.25:
                self.out_of_play(defending, False, self.u, self.v)
            if r < 0.45:
                self.out_of_play(defending, True, LENGTH, self.v)
        elif self.rng.random() < 0.26:
            self.emit("interception", team=defending, player=winner)
        self.change_possession("interception", winner)

    def carry(self) -> None:
        duration = self.rng.uniform(1, 5)
        du = self.rng.uniform(2, 4) * duration * (0.6 + 0.4 * self.rng.random())
        eu = clamp(self.u + du, 1, max(self.u, 94))
        ev = clamp(self.v + self.rng.gauss(0, 4) + (0.15 * (34 - self.v) if eu > 80 else 0), 1, 67)
        end_x, end_y = self.end_xy(self.team, eu, ev)
        self.emit("carry", player=self.carrier, under_pressure=self.pressured, end_x=end_x,
                  end_y=end_y, duration_s=round(duration, 1))
        self.play(duration)
        self.u, self.v = eu, ev
        self.last_pass = None

    # ---- shots -------------------------------------------------------------------------

    def shoot(self, *, shot_type: str | None = None, outcome: str | None = None,
              speed: float | None = None, rebound: str | None = None,
              tags: list[str] | None = None) -> None:
        """Take a shot. `rebound` forces what follows a save or block: corner, held, defender."""
        rng = self.rng
        shooter = self.carrier
        crossed = bool(self.last_pass and self.last_pass["pass_type"] == "cross")
        header = shot_type is None and crossed and rng.random() < 0.6
        if shot_type is None:
            shot_type = "header" if header else "open_play"
        assisted = bool(self.last_pass and self.last_pass["pass_type"] in ("through_ball",
                                                                         "cutback"))
        dx, dy = LENGTH - self.u, self.v - WIDTH / 2
        xg = shot_xg(dx, dy, header=header, assisted_chance=assisted,
                     pressure=self.pressured, shot_type=shot_type)
        finishing = 0.7 + 0.3 * self.attr(shooter, "shooting") / 100
        if outcome is None:
            r = rng.random()
            p_goal = xg * finishing
            if r < p_goal:
                outcome = "goal"
            elif r < p_goal + (1 - p_goal) * 0.25:
                outcome = "saved"
            elif r < p_goal + (1 - p_goal) * 0.52:
                outcome = "blocked"
            elif r < p_goal + (1 - p_goal) * 0.56:
                outcome = "post"
            else:
                outcome = "off_target"
        if speed is None:
            base = 55 if header else 85 + 0.3 * (self.attr(shooter, "shooting") - 50)
            speed = base + min(dx, 35) * 0.6 + rng.uniform(-8, 8)
        on_target = outcome in ("goal", "saved")
        goal_v = (WIDTH / 2 + rng.uniform(-3.5, 3.5) if on_target
                  else WIDTH / 2 + rng.choice([-1, 1]) * rng.uniform(3.8, 8))
        goal_y = round(goal_v if self.attacks_right(self.team) else WIDTH - goal_v, 2)
        goal_z = round(rng.uniform(0.1, 2.3) if on_target else rng.uniform(0.2, 4.0), 2)
        body = "head" if header else (
            f"{self.players[shooter]['preferred_foot']}_foot" if rng.random() < 0.8
            else ("left_foot" if self.players[shooter]["preferred_foot"] == "right"
                  else "right_foot"))
        shot = self.emit("shot", player=shooter, under_pressure=self.pressured,
                         shot_type=shot_type, body_part=body, outcome=outcome,
                         ball_speed_kmh=round(speed, 1), goal_y=goal_y, goal_z=goal_z,
                         tags=tags or [])
        self.play(rng.uniform(1, 2))
        assist = self.last_pass["player_id"] if self.last_pass else None
        self.last_pass = None
        defending = self.other(self.team)
        if outcome == "goal":
            self.score[self.team] += 1
            self.emit("goal", player=shooter, u=LENGTH, v=goal_v, scorer_id=shooter,
                      assist_id=assist, shot_event_id=shot["event_id"], own_goal=False)
            self.dead(rng.uniform(45, 75))
            self.change_possession("shot", self.pick(defending, (52.5, 34)))
            self.do_subs()
            self.kickoff(defending)
            raise PossessionOver
        if outcome == "saved":
            keeper = self.keeper(defending)
            self.emit("save", team=defending, player=keeper, u=3, v=WIDTH - goal_v,
                      keeper_id=keeper, shot_event_id=shot["event_id"])
            if rebound == "corner" or (rebound is None and rng.random() < 0.35):
                self.out_of_play(defending, True, LENGTH, goal_v)
            self.change_possession("keeper", keeper)
            self.u, self.v = 6.0, WIDTH / 2
            self.dead(rng.uniform(5, 10))
            raise PossessionOver
        if outcome == "blocked":
            blocker = self.defender_near()
            self.emit("block", team=defending, player=blocker)
            r = {"corner": 0.0, "defender": 0.5, "held": 0.9}.get(rebound or "", rng.random())
            if r < 0.35:
                self.out_of_play(defending, True, LENGTH, self.v)
            if r < 0.70:
                self.change_possession("shot", blocker)
            raise PossessionOver
        self.out_of_play(self.team, True, LENGTH, goal_v)

    # ---- planted moments (spec 6.7) ----------------------------------------------------

    def plant(self, segment: int, scenario: str) -> None:
        """Use `scenario` for live-square segment `segment` (0-4) instead of the default."""
        from app.generator.planted import SCENARIOS

        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
        self.plants[segment] = scenario

    def bridge(self, u: float, v: float) -> None:
        """Move the ball to (u, v) with a completed pass so planted moments start smoothly."""
        if math.hypot(u - self.u, v - self.v) > 3:
            self.pass_ball(forced=("open_play", u, v), outcome="complete")

    def passes_in_possession(self) -> int:
        count = 0
        for event in reversed(self.events):
            if event["possession_id"] != self.possession_id:
                break
            count += event["type"] == "pass"
        return count

    def due_plant(self) -> int | None:
        if self.passes_in_possession() > 3:
            return None
        minute = self.minute()
        for i, target in enumerate(self.plant_minutes):
            if i not in self.planted and minute >= target and minute < SEGMENTS[i][1] - 1:
                return i
        return None

    def run_plant(self, segment: int) -> None:
        from app.generator.planted import DEFAULT_PLANTS, SCENARIOS

        name = self.plants.get(segment, DEFAULT_PLANTS[segment])
        scenario: Callable[[Sim, list[str]], None] = SCENARIOS[name]
        self.planted[segment] = {"segment": segment, "scenario": name, "t": round(self.t, 2),
                                 "clock": self.clock(), "first_seq": len(self.events) + 1}
        first = len(self.events)
        tags = ["planted", f"moment:{name}", f"segment:{segment + 1}"]
        try:
            scenario(self, tags)
        finally:
            for event in self.events[first:]:
                event["tags"] = event["tags"] + [t for t in tags if t not in event["tags"]]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def side_of(v: float) -> str:
    return "left" if v < WIDTH / 2 else "right"
