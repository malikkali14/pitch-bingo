// Template feed lines (spec 3, running feed). These show at once and stay until the narrator
// (phase 6) replaces them. Only events a viewer would want called out get a line.

import { minuteLabel } from "../clock";
import { has, t } from "../i18n";
import type { MatchEvent } from "../protocol";
import type { Roster } from "../roster";

export interface FeedEntry {
  entry_id: string;
  minute: string;
  icon: string;
  text: string;
  tag: string;
  ai: boolean;
  tags: string[]; // the event's mask tags, so an open square can hide the line (spec 4.9)
  revealed?: boolean; // posted late, after the window it was held for
}

const ICONS: Record<string, string> = {
  goal: "⚽",
  shot: "🎯",
  card: "🟨",
  foul: "✋",
  advantage: "➜",
  offside: "⚑",
  corner: "⛳",
  substitution: "⇄",
  period: "⏱",
};

function textKey(e: MatchEvent): string | null {
  switch (e.type) {
    case "period_start":
    case "period_end":
      return `feed.${e.type}.${e.period}`;
    case "shot":
      // A goal gets its own line from the goal event.
      return e.outcome === "goal" ? null : `feed.shot.${String(e.outcome)}`;
    case "card":
      return `feed.card.${String(e.card)}`;
    case "goal":
    case "foul":
    case "advantage":
    case "offside":
    case "corner":
    case "substitution":
      return `feed.${e.type}`;
    default:
      return null;
  }
}

/** The icon for an event type, with a plain marker for moments that have no template. */
export function iconFor(type: string): string {
  return ICONS[type.startsWith("period") ? "period" : type] ?? "•";
}

export function feedEntry(e: MatchEvent, roster: Roster): FeedEntry | null {
  const key = textKey(e);
  if (!key || !has(key)) return null;
  const name = (id: unknown) =>
    typeof id === "string" ? (roster.players.get(id)?.surname ?? id) : "";
  const team = roster.team(e.team_id);
  const text = t(key, {
    player: name(e.type === "goal" ? e.scorer_id : e.player_id),
    team: team?.short_name ?? "",
    home: roster.home.short_name,
    away: roster.away.short_name,
    on: name(e.player_on_id),
    off: name(e.player_off_id),
  });
  const kind = e.type.startsWith("period") ? "period" : e.type;
  const icon = e.type === "card" && e.card !== "yellow" ? "🟥" : ICONS[kind];
  return {
    entry_id: e.event_id, minute: minuteLabel(e.clock), icon, text, tag: t(`tag.${kind}`), ai: false,
    tags: [...new Set(e.tags)],
  };
}
