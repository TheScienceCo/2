import Link from "next/link";

import { Card } from "@/components/ui";

export const dynamic = "force-dynamic";

export default function AnalysisPage() {
  return (
    <div className="space-y-8">
      <section className="pt-6">
        <h1 className="text-3xl font-semibold tracking-tight">Match Analysis</h1>
        <p className="mt-3 max-w-2xl text-ink-muted">
          Load a replay to see comprehensive analytics: decision quality, playstyle
          classification, and APM/attention patterns.
        </p>
      </section>

      <Card title="Analysis Features">
        <div className="space-y-4 text-sm">
          <div>
            <h3 className="font-semibold">Decision Value Added (DVA)</h3>
            <p className="mt-1 text-ink-muted">
              Evaluates the quality of strategic decisions: age advancement timing,
              build order choices, unit composition, and expansion patterns relative
              to peer baselines.
            </p>
          </div>

          <div>
            <h3 className="font-semibold">Playstyle Archetypes & Awards</h3>
            <p className="mt-1 text-ink-muted">
              Classifies players into 9 strategic archetypes and recognizes exceptional
              performance with achievements ranging from legendary to common.
            </p>
          </div>

          <div>
            <h3 className="font-semibold">3D Circular APM Radar</h3>
            <p className="mt-1 text-ink-muted">
              3D polar visualization of action intensity over time, color-coded by action
              type (economy/military/scouting/strategy). Shows attention shifts and playstyle
              signatures.
            </p>
          </div>
        </div>
      </Card>

      <Card title="Getting Started">
        <p className="text-sm text-ink-muted">
          Upload a replay from the <Link href="/upload" className="font-semibold hover:text-ink">
            replay upload page
          </Link> to begin analysis.
        </p>
      </Card>
    </div>
  );
}
