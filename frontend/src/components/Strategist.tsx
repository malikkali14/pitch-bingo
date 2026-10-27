// Strategist strip under the card (spec 3): a suggestion with Apply in suggest mode, or the
// reason for a move it just made in auto mode. Suggested cells are outlined on the card.

import { t } from "../i18n";
import type { StrategyAdviceMessage } from "../protocol";

interface Props {
  advice: StrategyAdviceMessage | null;
  note: string | null;
  onApply(adviceId: string): void;
}

const pct = (x: number) => Math.round(x * 100);

export function Strategist({ advice, note, onApply }: Props) {
  if (!advice && !note) return null;
  return (
    <section className="strategist" aria-labelledby="strategist-title" aria-live="polite">
      <h2 id="strategist-title">{t("strategist.title")}</h2>
      {advice ? (
        <>
          <p>{advice.reason}</p>
          <p className="muted small">
            {t("strategist.chance", { before: pct(advice.before), after: pct(advice.after) })}
          </p>
          <button type="button" className="primary" onClick={() => onApply(advice.advice_id)}>
            {t("strategist.apply")}
          </button>
        </>
      ) : (
        <p>{t("strategist.moved", { reason: note ?? "" })}</p>
      )}
    </section>
  );
}
