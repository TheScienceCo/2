"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { DVATimeline } from "@/components/analytics/DVATimeline";
import { PlaystyleProfile } from "@/components/analytics/PlaystyleProfile";
import { RadarVisualization } from "@/components/analytics/RadarVisualization";
import { Card, Disclaimer, ErrorNotice } from "@/components/ui";
import { ApiError, fetchInsights } from "@/lib/api";
import { clock } from "@/lib/format";
import type { MatchInsightsResponse } from "@/lib/types";

/** `params` is a promise in this version of Next; unwrap it with `use`. */
export default function MatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  /** Result carries the id it belongs to, so a changed route reads as loading
   *  without an effect having to reset state synchronously. */
  const [result, setResult] = useState<{
    id: string;
    data?: MatchInsightsResponse;
    error?: string;
  } | null>(null);

  useEffect(() => {
    let live = true;

    fetchInsights(id)
      .then((data) => live && setResult({ id, data }))
      .catch((e) =>
        live &&
        setResult({
          id,
          error: e instanceof ApiError ? e.message : "Something went wrong.",
        }),
      );

    return () => {
      live = false;
    };
  }, [id]);

  if (result?.id !== id) return <MatchSkeleton />;

  const { data: insights, error } = result;

  if (error || !insights) {
    return (
      <div className="space-y-6 py-10">
        <div className="space-y-1">
          <div className="label">Match analysis</div>
          <h1 className="text-3xl font-semibold tracking-tight">
            <span className="font-mono text-2xl text-ink-muted">{id.slice(0, 12)}</span>
          </h1>
        </div>
        <ErrorNotice title="Could not load this match" message={error ?? "No data found."} />
        <p className="text-sm text-ink-muted">
          <Link href="/upload" className="link">
            Analyse a replay
          </Link>{" "}
          to generate one.
        </p>
      </div>
    );
  }

  const players = [
    {
      name: insights.p1_name,
      civ: insights.p1_civ,
      won: insights.winner === 1,
      decisions: insights.p1_decisions,
      playstyle: insights.p1_playstyle,
      radar: insights.p1_radar,
    },
    {
      name: insights.p2_name,
      civ: insights.p2_civ,
      won: insights.winner === 2,
      decisions: insights.p2_decisions,
      playstyle: insights.p2_playstyle,
      radar: insights.p2_radar,
    },
  ];

  return (
    <div className="space-y-10 py-6">
      <header className="space-y-4">
        <div className="space-y-1">
          <div className="label">Match analysis</div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {insights.p1_name} <span className="text-ink-faint">vs</span> {insights.p2_name}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
          <span className="stat">{clock(insights.duration_ms)}</span>
          <span aria-hidden className="text-ink-faint">
            ·
          </span>
          <span>
            {insights.p1_civ} vs {insights.p2_civ}
          </span>
          <span aria-hidden className="text-ink-faint">
            ·
          </span>
          <span className="font-mono text-xs text-ink-faint">{insights.match_id.slice(0, 12)}</span>
        </div>
      </header>

      {/* One column per player, so the two read against each other. */}
      <div className="grid gap-6 lg:grid-cols-2">
        {players.map((p) => (
          <div key={p.name} className="space-y-6">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">{p.name}</h2>
              <span className="text-sm text-ink-muted">{p.civ}</span>
              {p.won && (
                <span className="rounded bg-good/15 px-2 py-0.5 text-xs font-medium text-good">
                  won
                </span>
              )}
            </div>

            <Card title="Decisions">
              {p.decisions ? (
                <DVATimeline report={p.decisions} matchDuration={insights.duration_ms} />
              ) : (
                <p className="text-sm text-ink-faint">
                  Not enough peer data to evaluate decisions.
                </p>
              )}
            </Card>

            <Card title="Playstyle">
              {p.playstyle ? (
                <PlaystyleProfile profile={p.playstyle} />
              ) : (
                <p className="text-sm text-ink-faint">No playstyle classification available.</p>
              )}
            </Card>

            <Card title="Attention radar">
              {p.radar ? (
                <RadarVisualization data={p.radar} />
              ) : (
                <p className="text-sm text-ink-faint">
                  This replay carries no usable command telemetry.
                </p>
              )}
            </Card>
          </div>
        ))}
      </div>

      <Disclaimer>
        Everything above is derived from the replay&rsquo;s command stream — the inputs the
        players sent, not the outcomes the engine produced. Decision values are relative to a
        peer cohort and carry a confidence figure; treat a low-confidence value as a hint, not
        a verdict.
      </Disclaimer>
    </div>
  );
}

function MatchSkeleton() {
  return (
    <div className="space-y-10 py-6" aria-busy="true" aria-label="Loading match analysis">
      <div className="space-y-3">
        <div className="h-3 w-28 animate-pulse rounded bg-surface-raised" />
        <div className="h-9 w-96 max-w-full animate-pulse rounded bg-surface-raised" />
        <div className="h-4 w-64 animate-pulse rounded bg-surface-raised" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {[0, 1].map((col) => (
          <div key={col} className="space-y-6">
            {[0, 1, 2].map((row) => (
              <div
                key={row}
                className="h-56 animate-pulse rounded-xl border border-surface-border bg-surface-raised/50"
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
