// The how-it-works carousel: native scroll-snap, so it swipes on touch screens and scrolls
// with a trackpad; the buttons and dots do the same for mouse and keyboard users.

import { useRef, useState } from "react";
import { t } from "../i18n";

const SLIDES = [1, 2, 3, 4, 5];

export function HowItWorks() {
  const track = useRef<HTMLUListElement>(null);
  const [index, setIndex] = useState(0);
  const go = (next: number) => {
    const clamped = Math.max(0, Math.min(SLIDES.length - 1, next));
    const el = track.current;
    if (el) el.scrollTo({ left: clamped * el.clientWidth, behavior: "smooth" });
    setIndex(clamped);
  };
  return (
    <section className="how-carousel" aria-roledescription="carousel" aria-labelledby="how-title">
      <h3 id="how-title">{t("setup.how")}</h3>
      <ul className="slides" ref={track}
        onScroll={(e) => setIndex(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}>
        {SLIDES.map((n) => (
          <li key={n} className="slide" aria-roledescription="slide"
            aria-label={`${n} / ${SLIDES.length}`}>
            <strong>{t(`how.${n}.title`)}</strong>
            <span>{t(`how.${n}.text`)}</span>
          </li>
        ))}
      </ul>
      <div className="carousel-nav">
        <button type="button" className="ghost" onClick={() => go(index - 1)} disabled={index === 0}
          aria-label={t("how.prev")}>‹</button>
        <span className="dots">
          {SLIDES.map((n, i) => (
            <button key={n} type="button" className={i === index ? "dot-btn on" : "dot-btn"}
              aria-label={`${n} / ${SLIDES.length}`} aria-current={i === index} onClick={() => go(i)} />
          ))}
        </span>
        <button type="button" className="ghost" onClick={() => go(index + 1)}
          disabled={index === SLIDES.length - 1} aria-label={t("how.next")}>›</button>
      </div>
    </section>
  );
}
