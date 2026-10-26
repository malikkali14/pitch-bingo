import type { FeedEntry } from "../feed/templates";
import { t } from "../i18n";

// Newest first, about four entries visible, the rest scrolls. A polite live region, so screen
// readers announce new lines (spec 3, running feed).
export function Feed({ entries }: { entries: FeedEntry[] }) {
  return (
    <section className="feed" aria-labelledby="feed-title">
      <h2 id="feed-title">{t("feed.title")}</h2>
      <ol className="feed-list" role="log" aria-live="polite" aria-relevant="additions">
        {entries.length === 0 && <li className="feed-empty">{t("feed.empty")}</li>}
        {entries.map((e) => (
          <li key={e.entry_id} className="feed-entry">
            <span className="minute">{e.minute}</span>
            <span className="icon" aria-hidden="true">
              {e.icon}
            </span>
            <span className="text">{e.text}</span>
            <span className="tag">{e.tag}</span>
            {e.ai && <span className="ai">{t("feed.ai")}</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
