import type { FeedEntry } from "../feed/templates";
import { t } from "../i18n";

// Newest first, about four entries visible, the rest scrolls. A polite live region, so screen
// readers announce new lines (spec 3, running feed). While a window is open, older lines it
// depends on collapse to "Hidden while a square is open" (spec 3, 4.9).
export function Feed({ entries, masked = new Set() }: { entries: FeedEntry[]; masked?: Set<string> }) {
  return (
    <section className="feed" aria-labelledby="feed-title">
      <h2 id="feed-title">{t("feed.title")}</h2>
      <ol className="feed-list" role="log" aria-live="polite" aria-relevant="additions">
        {entries.length === 0 && <li className="feed-empty">{t("feed.empty")}</li>}
        {entries.map((e) => {
          const hidden = e.tags.some((tag) => masked.has(tag));
          return (
          <li key={e.entry_id} className={`feed-entry${hidden ? " hidden" : ""}${e.revealed ? " revealed" : ""}`}>
            <span className="minute">{e.minute}</span>
            <span className="icon" aria-hidden="true">
              {hidden ? "·" : e.icon}
            </span>
            <span className="text">{hidden ? t("feed.hidden") : e.text}</span>
            <span className="tag">{hidden ? "" : e.tag}</span>
            {e.ai && <span className="ai">{t("feed.ai")}</span>}
          </li>
          );
        })}
      </ol>
    </section>
  );
}
