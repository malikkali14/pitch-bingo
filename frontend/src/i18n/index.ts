import en from "./en.json";
import fr from "./fr.json";

// One JSON file per language (spec 5.4). A key missing from a language falls back to English.
export const LANGUAGES = ["en", "fr"] as const;
export type Language = (typeof LANGUAGES)[number];

const tables: Record<Language, Record<string, string>> = { en, fr };
let current: Language = "en";

export function setLanguage(language: string): void {
  current = (LANGUAGES as readonly string[]).includes(language) ? (language as Language) : "en";
  if (typeof document !== "undefined") document.documentElement.lang = current;
}

export function getLanguage(): Language {
  return current;
}

/** Look up a UI string and fill {name} placeholders. Unknown keys come back as the key. */
export function t(key: string, vars: Record<string, string | number> = {}): string {
  const template = tables[current][key] ?? en[key as keyof typeof en] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function has(key: string): boolean {
  return key in tables[current] || key in en;
}
