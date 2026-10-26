import en from "./en.json";

// French (fr.json) and the language setting arrive in phase 7 (spec 5.4).
const strings: Record<string, string> = en;

/** Look up a UI string and fill {name} placeholders. Unknown keys come back as the key. */
export function t(key: string, vars: Record<string, string | number> = {}): string {
  const template = strings[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function has(key: string): boolean {
  return key in strings;
}
