import type { ReactNode } from "react";

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
    <div className="rounded-lg border border-dashed border-surface-border px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNotice({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-bad/40 bg-bad/10 px-4 py-3">
      <p className="text-sm font-medium text-bad">{title}</p>
      <p className="mt-1 text-sm text-ink-muted">{message}</p>
    </div>
  );
}
