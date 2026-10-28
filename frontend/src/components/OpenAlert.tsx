// A visible banner for an announced window (spec 3): the open square's question, a big
// countdown and an Answer button. Screen readers get the same words from the live region in App.

import { useNow } from "../hooks";
import { t } from "../i18n";
import type { Square } from "../card/types";

interface Props {
  square: Square | undefined;
  language: string;
  muted: boolean;
  onMute(): void;
  onAnswer(squareId: string): void;
}

export function OpenAlert({ square, language, muted, onMute, onAnswer }: Props) {
  const now = useNow(250);
  if (!square) return null;
  const seconds = square.closes_at === null ? 0 : Math.max(0, Math.ceil((square.closes_at - now) / 1000));
  return (
    <div className="open-alert">
      <span className="open-alert-label">{t("alert.open")}</span>
      <span className="open-alert-question">{square.text[language] ?? square.text.en}</span>
      <span className="open-alert-seconds" aria-hidden="true">{seconds}s</span>
      <button type="button" className="primary" onClick={() => onAnswer(square.id)}>{t("alert.answer")}</button>
      <button type="button" className="ghost" aria-pressed={muted} onClick={onMute}>
        {muted ? t("alert.unmute") : t("alert.mute")}
      </button>
    </div>
  );
}
