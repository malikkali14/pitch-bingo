import { afterEach, describe, expect, it } from "vitest";
import en from "./i18n/en.json";
import fr from "./i18n/fr.json";
import { getLanguage, setLanguage, t } from "./i18n";
import { initialState, matchReducer } from "./state/match";
import { META, PROFILE } from "./test-fixtures";
import { mockBoard } from "./card/mock";

afterEach(() => setLanguage("en"));

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("French (spec 5.4)", () => {
  it("has every English key, with the same placeholders", () => {
    expect(Object.keys(fr).sort()).toEqual(Object.keys(en).sort());
    for (const [key, text] of Object.entries(en)) {
      expect(placeholders((fr as Record<string, string>)[key]), key).toEqual(placeholders(text));
      expect((fr as Record<string, string>)[key].trim(), key).not.toBe("");
    }
  });

  it("switches the interface language, and unknown languages fall back to English", () => {
    setLanguage("fr");
    expect(getLanguage()).toBe("fr");
    expect(t("feed.corner", { team: "Northbridge" })).toBe("Corner pour Northbridge.");
    expect(t("card.state.too_early")).toBe("Trop tôt");
    setLanguage("de");
    expect(t("card.state.too_early")).toBe("Too early");
  });
});

describe("server template lines", () => {
  it("are not labelled AI", () => {
    let state = matchReducer(initialState, { kind: "message", now: 0, msg: {
      type: "session.ready", t: 0, wall: 0, session_id: "s", match: META, profile: PROFILE,
      card: mockBoard, speed: 1, paused: false, duration: 5900 } });
    state = matchReducer(state, { kind: "message", now: 0, msg: {
      type: "feed.replace", t: 600, wall: 0, entry_id: "focus:600", text: "Arvel so far: 12 touches.",
      ai: false, clock: "10:00", event_type: "focus", held: false } });
    expect(state.feed[0]).toMatchObject({ entry_id: "focus:600", ai: false });
  });
});
