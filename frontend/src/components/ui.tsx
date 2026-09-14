import type { ReactNode } from "react";

import type { Availability } from "@/lib/types";

export function Card({
  title,
  aside,
  children,
  className = "",
}: {
  title?: ReactNode;
  /** Right-aligned slot in the header rule — a count, a timing, a tag. */
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-surface-border bg-surface-raised/70 ${className}`}
    >
      {title && (
        <header className="flex items-baseline justify-between gap-3 border-b border-surface-border px-5 py-3">
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {aside && <div className="text-xs text-ink-faint">{aside}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/**
 * A standing caveat about what the numbers above are. Deliberately quiet —
 * it sits under content rather than interrupting it.
 */
export function Disclaimer({ children }: { children: ReactNode }) {
  return (
    <p className="border-l-2 border-surface-border pl-3 text-xs leading-relaxed text-ink-faint">
      {children}
    </p>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-surface-border px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNotice({ title, message }: { title: string; message: string }) {
  return (
    <div role="alert" className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3">
      <p className="text-sm font-medium text-bad">{title}</p>
      <p className="mt-1 text-sm text-ink-muted">{message}</p>
    </div>
  );
}

const PROVENANCE_STYLE: Record<Availability | string, string> = {
  observed: "bg-good/15 text-good",
  reconstructed: "bg-accent/15 text-accent",
  inferred: "bg-warn/15 text-warn",
  derived: "bg-violet-500/15 text-violet-400",
  unavailable: "bg-surface-overlay text-ink-faint",
};

/** Provenance travels with the number it describes. */
export function ProvenanceTag({ kind }: { kind: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
        PROVENANCE_STYLE[kind] ?? PROVENANCE_STYLE.unavailable
      }`}
    >
      {kind}
    </span>
  );
}

/** A single figure with its label. Monospaced so columns of them line up. */
export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="label">{label}</div>
      <div className="stat text-xl">{value}</div>
      {hint && <div className="text-xs text-ink-faint">{hint}</div>}
    </div>
  );
}

/** A 0–1 proportion drawn as a rule. `tone` picks the fill colour. */
export function Meter({
  value,
  tone = "accent",
}: {
  value: number;
  tone?: "accent" | "good" | "warn" | "bad";
}) {
  const fill = {
    accent: "bg-accent",
    good: "bg-good",
    warn: "bg-warn",
    bad: "bg-bad",
  }[tone];

  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-overlay">
      <div
        className={`h-full rounded-full ${fill} transition-[width] duration-500`}
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  );
}
