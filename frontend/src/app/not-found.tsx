import Link from "next/link";

import { EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <EmptyState
      title="Not found"
      action={
        <Link href="/upload" className="link text-sm">
          Analyse a replay
        </Link>
      }
    >
      That page isn’t here. If you were looking for an analysis, it may have been
      removed — upload the replay again.
    </EmptyState>
  );
}
