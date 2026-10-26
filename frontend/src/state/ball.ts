// Who has the ball, and why play has stopped, from the event stream. The pitch rings the
// carrier and shows the stoppage note (spec 3, pitch view).

import { t } from "../i18n";
import type { MatchEvent } from "../protocol";
import { attacksRight, type Roster } from "../roster";

export interface BallState {
  owner: string | null;
  incoming: { id: string; at: number } | null; // receiver of a pass still in the air
  stoppage: string | null;
}

export const initialBall: BallState = { owner: null, incoming: null, stoppage: null };

const OWNS = new Set(["kickoff", "carry", "interception", "save", "throw_in", "corner",
  "goal_kick", "free_kick", "duel"]);
const RELEASES = new Set(["shot", "clearance", "block", "goal", "out_of_play", "offside", "period_end"]);
const RESTARTS = new Set(["kickoff", "throw_in", "corner", "goal_kick", "free_kick", "pass", "carry", "shot"]);

export function nextBall(ball: BallState, e: MatchEvent, roster: Roster): BallState {
  let { owner, incoming, stoppage } = ball;
  if (RESTARTS.has(e.type)) stoppage = null;
  const player = e.player_id;
  if (e.type === "pass") {
    owner = null;
    incoming = null;
    if (e.outcome === "complete" && typeof e.receiver_id === "string") {
      const flight = Number(e.length_m) / Math.max(Number(e.ball_speed_kmh) / 3.6, 1);
      incoming = { id: e.receiver_id, at: e.t + flight };
    }
  } else if (player && (OWNS.has(e.type) || e.type === "possession_change" ||
      (e.type === "tackle" && e.outcome === "won"))) {
    owner = player;
    incoming = null;
  } else if (RELEASES.has(e.type)) {
    owner = null;
    incoming = null;
  }
  const note = stoppageNote(e, roster);
  if (note) stoppage = note;
  return { owner, incoming, stoppage };
}

export function carrierAt(ball: BallState, matchT: number): string | null {
  if (ball.incoming) return matchT >= ball.incoming.at ? ball.incoming.id : null;
  return ball.owner;
}

function stoppageNote(e: MatchEvent, roster: Roster): string | null {
  const other = (id: string | null) => (id === roster.home.id ? roster.away : roster.home);
  switch (e.type) {
    case "out_of_play": {
      const last = String(e.last_touch_team_id);
      if (e.x > 1 && e.x < 104) return t("stop.throw_in", { team: other(last).short_name });
      // Over an end line: the club defending that end gets a goal kick, unless it touched last.
      const defending = attacksRight(roster.home.id, e.period, roster.home.id) === (e.x <= 1)
        ? roster.home : roster.away;
      return last === defending.id
        ? t("stop.corner", { team: other(defending.id).short_name })
        : t("stop.goal_kick", { team: defending.short_name });
    }
    case "foul":
      return e.advantage ? null : t("stop.foul", { team: other(e.team_id).short_name });
    case "offside":
      return t("stop.offside", { team: other(e.team_id).short_name });
    case "goal":
      return t("stop.goal", { team: other(e.team_id).short_name });
    case "period_end":
      return t(e.period === 1 ? "stop.half" : "stop.full");
    default:
      return null;
  }
}
