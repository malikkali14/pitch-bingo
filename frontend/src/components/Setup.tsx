// Pre-match setup (spec 3): mode, favorite club, focus player, then a three-step how-to-play
// and "Kick off". Language arrives with French in phase 7.

import { useEffect, useState, type FormEvent } from "react";
import { LANGUAGES, getLanguage, setLanguage, t, type Language } from "../i18n";
import { HowItWorks } from "./HowItWorks";
import type { MatchMeta, Mode } from "../protocol";
import type { Kickoff } from "../state/session";

interface Props {
  onKickoff(kickoff: Kickoff): void;
  /** For tests: skip fetching. */
  meta?: MatchMeta;
  seed?: number;
}

async function loadMatch(): Promise<{ seed: number; meta: MatchMeta }> {
  const list = (await (await fetch("/api/matches")).json()) as { default: number };
  const meta = (await (await fetch(`/api/matches/${list.default}`)).json()) as MatchMeta;
  return { seed: list.default, meta };
}

export function Setup({ onKickoff, meta: given, seed: givenSeed }: Props) {
  const [match, setMatch] = useState(given ? { seed: givenSeed ?? 0, meta: given } : null);
  const [failed, setFailed] = useState(false);
  const [mode, setMode] = useState<Mode>("normal");
  const [club, setClub] = useState("neutral");
  const [focus, setFocus] = useState("");
  const [handle, setHandle] = useState("You");
  const [language, chooseLanguage] = useState<Language>(getLanguage());
  const pickLanguage = (next: Language) => {
    setLanguage(next);
    chooseLanguage(next);       // re-render this screen in the new language
  };

  useEffect(() => {
    if (match) return;
    loadMatch().then(setMatch, () => setFailed(true));
  }, [match]);

  if (!match) {
    return (
      <main className="status-screen">
        <h1>{t("app.title")}</h1>
        <p role="status">{failed ? t("app.error") : t("setup.loading")}</p>
      </main>
    );
  }
  const { meta, seed } = match;
  const home = meta.teams.find((team) => team.id === meta.home_team_id)!;
  const away = meta.teams.find((team) => team.id === meta.away_team_id)!;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onKickoff({
      seed: seed || undefined,
      profile: { mode, club, focus_player_id: focus || null, handle: handle.trim() || "You",
        language },
    });
  };

  return (
    <main className="setup">
      <h1>{t("app.title")}</h1>
      <p className="setup-match">{t("setup.match", { home: home.name, away: away.name })}</p>
      <form onSubmit={submit} aria-labelledby="setup-title">
        <h2 id="setup-title">{t("setup.title")}</h2>
        <fieldset>
          <legend>{t("setup.language")}</legend>
          {LANGUAGES.map((l) => (
            <label key={l} className="choice">
              <input type="radio" name="language" value={l} checked={language === l}
                onChange={() => pickLanguage(l)} />
              {t(`setup.language.${l}`)}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>{t("setup.mode")}</legend>
          {(["normal", "advanced"] as const).map((m) => (
            <label key={m} className="choice">
              <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
              {t(`setup.mode.${m}`)}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>{t("setup.club")}</legend>
          {[home, away].map((team) => (
            <label key={team.id} className="choice">
              <input type="radio" name="club" value={team.id} checked={club === team.id}
                onChange={() => setClub(team.id)} />
              {team.name}
            </label>
          ))}
          <label className="choice">
            <input type="radio" name="club" value="neutral" checked={club === "neutral"}
              onChange={() => setClub("neutral")} />
            {t("setup.neutral")}
          </label>
        </fieldset>
        <label className="field">
          {t("setup.focus")}
          <select value={focus} onChange={(e) => setFocus(e.target.value)}>
            <option value="">{t("setup.no_focus")}</option>
            {[home, away].map((team) => (
              <optgroup key={team.id} label={team.name}>
                {team.players.map((p) => (
                  <option key={p.id} value={p.id}>{`${p.shirt_number} ${p.full_name} (${p.position})`}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="field">
          {t("setup.handle")}
          <input type="text" value={handle} maxLength={24} onChange={(e) => setHandle(e.target.value)} />
        </label>
        <HowItWorks />
        <button type="submit" className="primary">{t("setup.kickoff")}</button>
      </form>
    </main>
  );
}
