import { useState } from "react";
import { mockBoard } from "./card/mock";
import { Card } from "./components/Card";
import { Feed } from "./components/Feed";
import { Metrics } from "./components/Metrics";
import { Pitch } from "./components/Pitch";
import { TopBar, type Mode } from "./components/TopBar";
import { usePrefersReducedMotion } from "./hooks";
import { t } from "./i18n";
import { useMatchSession } from "./state/session";

// One screen (spec 3): pitch and feed on the left, metrics and card on the right.
export default function App() {
  const { state, frames, setSpeed } = useMatchSession();
  const [mode, setMode] = useState<Mode>("normal");
  const reducedMotion = usePrefersReducedMotion();
  const { roster } = state;

  if (!roster) {
    return (
      <main className="status-screen">
        <h1>{t("app.title")}</h1>
        <p role="status">{state.status === "error" ? t("app.error") : t("app.connecting")}</p>
      </main>
    );
  }

  return (
    <div className="app">
      <TopBar roster={roster} score={state.stats?.score} anchor={state.anchor} fullTime={state.fullTime}
        frames={frames} speed={state.speed} onSpeed={setSpeed} mode={mode} onMode={setMode} />
      {state.status === "error" && <p className="banner" role="alert">{t("app.error")}</p>}
      <main className="layout">
        <div className="left">
          <Pitch roster={roster} frames={frames} cues={state.cues} cards={state.cards} ball={state.ball}
            reducedMotion={reducedMotion} />
          <Feed entries={state.feed} />
        </div>
        <div className="right">
          <Metrics roster={roster} stats={state.stats} xg={state.xg} mode={mode} />
          <Card board={mockBoard} note={t("card.mock")} />
        </div>
      </main>
    </div>
  );
}
