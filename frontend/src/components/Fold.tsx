// A section that collapses to its title (spec 3): keeps the page short once you know the panels.

import type { ReactNode } from "react";

interface Props {
  id: string;
  title: string;
  hint?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function Fold({ id, title, hint, defaultOpen = true, children }: Props) {
  return (
    <details className="fold" open={defaultOpen} aria-labelledby={`${id}-fold`}>
      <summary id={`${id}-fold`}>{title}</summary>
      {hint && <p className="hint">{hint}</p>}
      {children}
    </details>
  );
}
