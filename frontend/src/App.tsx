import { useEffect, useState } from "react";
import { announcedOpen } from "./card/rules";
import { canAnswer } from "./components/AnswerPopover";
import { Card } from "./components/Card";
import { DevPanel } from "./components/DevPanel";
import { Feed } from "./components/Feed";
import { FullTime } from "./components/FullTime";
import { Leaderboard } from "./components/Leaderboard";
import { Metrics } from "./components/Metrics";
import { OpenAlert } from "./components/OpenAlert";
import { Pitch } from "./components/Pitch";
import { Setup } from "./components/Setup";
import { Strategist } from "./components/Strategist";
import { TopBar, type Mode } from "./components/TopBar";
import { useChime, usePrefersReducedMotion } from "./hooks";
import { t } from "./i18n";
import { maskedTags } from "./state/match";
import { useMatchSession, type Kickoff } from "./state/session";

const NOTICE_MS = 4000;

// Setup first, then one screen (spec 3): pitch and feed on the left; metrics, card,
// strategist and leaderboard on the right; the full-time screen over it at the end.
export default function App() {
  const [kickoff, setKickoff] = useState<Kickoff | null>(null);
  const session = useMatchSession(kickoff);
  if (!kickoff) return <Setup onKickoff={setKickoff} />;
  return <Match session={session} />;
}

function Match({ session }: { session: ReturnType<typeof useMatchSession> }) {
  const { state, frames, setSpeed, answer, move, applyAdvice, catchUp, define, dev } = session;
  const [devOpen, setDevOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("normal");
  const [selected, setSelected] = useState<string | null>(null);
  const [fullTimeClosed, setFullTimeClosed] = useState(false);
  const [noticeShown, setNoticeShown] = useState(false);
  const [muted, setMuted] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  const { roster, board, profile } = state;
  useChime(state.announcement, muted);

  useEffect(() => {
    if (profile) setMode(profile.mode);
  }, [profile]);
  useEffect(() => {
    if (!state.notice) return;
    setNoticeShown(true);
    const id = setTimeout(() => setNoticeShown(false), NOTICE_MS);
    return () => clearTimeout(id);
  }, [state.notice]);

  if (!roster || !board || !profile) {
    return (
      <main className="status-screen">
        <h1>{t("app.title")}</h1>
        <p role="status">{state.status === "error" ? t("app.error") : t("app.connecting")}</p>
      </main>
    );
  }

  const masked = maskedTags(state);
  const language = profile.language;
  const square = board.squares.find((s) => s.id === selected);
  const openSquare = board.squares.find((s) => s.state === "open");
  const focusPlayer = profile.focus_player_id ? roster.players.get(profile.focus_player_id) : undefined;
  const picking = square?.answer_type === "player" && canAnswer(square) && !state.pending[square.id];
  const showFullTime = state.fullTime && !fullTimeClosed && !announcedOpen(board);

  return (
    <div className="app">
      <TopBar roster={roster} score={state.stats?.score} anchor={state.anchor} fullTime={state.fullTime}
        frames={frames} speed={state.speed} onSpeed={setSpeed} mode={mode} onMode={setMode}
        devOpen={devOpen} onDev={() => setDevOpen((o) => !o)}
        following={focusPlayer?.surname} language={language} />
      {devOpen && (
        <DevPanel health={state.health} paused={state.paused} narratorDown={state.narratorDown}
          onPause={dev.pause} onJump={dev.jump} onNarratorDown={dev.narratorDown} />
      )}
      {state.status === "error" && <p className="banner" role="alert">{t("app.error")}</p>}
      <p className="visually-hidden" aria-live="assertive">{state.announcement}</p>
      {noticeShown && state.notice && (
        <p className={`toast ${state.notice.kind}`} role="status">{state.notice.text}</p>
      )}
      <OpenAlert square={openSquare} language={language} muted={muted}
        onMute={() => setMuted((m) => !m)} onAnswer={setSelected} />
      <main className="layout">
        <div className="left">
          <Pitch roster={roster} frames={frames} cues={state.cues}
            cards={masked.has("cards") ? {} : state.cards} ball={state.ball} reducedMotion={reducedMotion}
            focusId={profile.focus_player_id}
            onPick={picking && square ? (id) => answer(square.id, id) : undefined} />
          <Feed entries={state.feed} masked={masked} onCatchUp={catchUp} />
        </div>
        <div className="right">
          <Card board={board} roster={roster} language={language} pending={state.pending}
            answers={state.answers} advice={state.advice} selected={selected} onSelect={setSelected}
            onAnswer={answer} onMove={move} />
          <Strategist advice={state.advice} note={state.strategistNote} onApply={applyAdvice} />
          <Metrics roster={roster} stats={state.stats} xg={state.xg} mode={mode}
            definition={state.definition} onDefine={define} />
          <Leaderboard rows={state.leaderboard} mode={profile.mode} />
        </div>
      </main>
      {showFullTime && (
        <FullTime roster={roster} score={state.stats?.score} board={board} moments={state.moments}
          leaderboard={state.leaderboard} total={state.ranked} mode={profile.mode}
          recap={state.recaps.full_time}
          onClose={() => setFullTimeClosed(true)} />
      )}
    </div>
  );
}
