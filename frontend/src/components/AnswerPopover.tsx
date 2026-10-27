// The answer popover (spec 3, bingo card): the input that fits the square's answer type.
// First-to-happen squares always take an answer, since the card never signals the event.

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { deadlineLabel, type Square } from "../card/types";
import { t } from "../i18n";
import type { Roster } from "../roster";

interface Props {
  square: Square;
  roster: Roster;
  language: string;
  pending: string | undefined;
  correctAnswer: string | null | undefined;
  onAnswer(value: string): void;
  onClose(): void;
}

/** What to show for an answer value: a club, a player, or the option's label. */
export function answerLabel(square: Square, value: string, roster: Roster, language = "en"): string {
  const labels = square.option_labels[language] ?? square.option_labels.en;
  const index = square.options.indexOf(value);
  if (labels && index >= 0) return labels[index];
  if (value === "level") return t("card.level");
  const team = roster.team(value);
  if (team) return team.short_name;
  const player = roster.players.get(value);
  if (player) return player.full_name;
  return value;
}

export function canAnswer(square: Square): boolean {
  if (square.answer) return false;
  return square.state === "open" || (square.kind === "first" && square.state === "waiting");
}

export function AnswerPopover({ square, roster, language, pending, correctAnswer, onAnswer, onClose }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => panel.current?.focus(), [square.id]);
  const question = square.text[language] ?? square.text.en ?? "";
  const answered = square.answer?.value ?? pending;
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  };

  let body;
  if (answered !== undefined) {
    body = <p>{t("card.answered", { answer: answerLabel(square, answered, roster, language) })}</p>;
  } else if (!canAnswer(square)) {
    body = square.kind === "deadline" && square.state === "waiting" && square.deadline_s !== null
      ? <p>{t("card.opens_at", { minute: deadlineLabel(square.deadline_s) })}</p>
      : null;
  } else if (square.answer_type === "player") {
    body = <PlayerPicker roster={roster} onPick={onAnswer} />;
  } else if (square.answer_type === "number" && square.options.length === 0) {
    body = <NumberStepper onAnswer={onAnswer} />;
  } else {
    body = (
      <div className="choices">
        {square.options.map((value, i) => (
          <button key={value} type="button" onClick={() => onAnswer(value)}>
            <span className="key" aria-hidden="true">{i + 1}</span>
            {answerLabel(square, value, roster, language)}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="popover" role="dialog" aria-label={question} tabIndex={-1} ref={panel}
      onKeyDown={(e) => {
        onKey(e);
        // Number keys pick choices (spec 3, accessibility).
        const pick = Number(e.key);
        if (canAnswer(square) && answered === undefined && square.options.length && pick >= 1 &&
            pick <= square.options.length && (e.target as HTMLElement).tagName !== "INPUT") {
          onAnswer(square.options[pick - 1]);
        }
      }}>
      <div className="popover-head">
        <h3>{question}</h3>
        <button type="button" className="ghost" onClick={onClose}>{t("card.close")}</button>
      </div>
      {square.kind === "first" && canAnswer(square) && answered === undefined && (
        <p className="muted small">{t("card.first_hint")}</p>
      )}
      {body}
      {correctAnswer && (
        <p className="correct-answer">
          {t("card.correct_answer", { answer: answerLabel(square, correctAnswer, roster, language) })}
        </p>
      )}
    </div>
  );
}

function NumberStepper({ onAnswer }: { onAnswer(value: string): void }) {
  const [value, setValue] = useState(0);
  return (
    <div className="stepper">
      <div className="choices">
        {[0, 1, 2, 3, 4, 5, 6].map((n) => (
          <button key={n} type="button" onClick={() => onAnswer(String(n))}>{n}</button>
        ))}
      </div>
      <label>
        <span className="visually-hidden">{t("card.answer_title")}</span>
        <button type="button" onClick={() => setValue((v) => Math.max(0, v - 1))} aria-label="−1">−</button>
        <input type="number" min={0} value={value} onChange={(e) => setValue(Math.max(0, Number(e.target.value) || 0))} />
        <button type="button" onClick={() => setValue((v) => v + 1)} aria-label="+1">+</button>
      </label>
      <button type="button" className="primary" onClick={() => onAnswer(String(value))}>{t("card.submit")}</button>
    </div>
  );
}

function PlayerPicker({ roster, onPick }: { roster: Roster; onPick(id: string): void }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  // On-pitch starters first; search reaches the benches too.
  const teams = [roster.home, roster.away].map((team) => ({
    team,
    players: team.players.filter((p) =>
      q ? p.full_name.toLowerCase().includes(q) || String(p.shirt_number) === q : team.lineup.includes(p.id)),
  }));
  return (
    <div className="player-picker">
      <input type="search" placeholder={t("card.search")} aria-label={t("card.search")} value={query}
        onChange={(e) => setQuery(e.target.value)} />
      {teams.map(({ team, players }) => (
        <div key={team.id} className="player-team">
          <h4>{team.short_name}</h4>
          <div className="choices">
            {players.map((p) => (
              <button key={p.id} type="button" onClick={() => onPick(p.id)}>
                {p.shirt_number} {p.surname}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
