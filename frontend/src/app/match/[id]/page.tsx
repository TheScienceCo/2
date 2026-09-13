"use client";

import { useEffect, useState } from "react";

import { Card, Disclaimer } from "@/components/ui";
import { DVATimeline } from "@/components/analytics/DVATimeline";
import { PlaystyleProfile } from "@/components/analytics/PlaystyleProfile";
import { RadarVisualization } from "@/components/analytics/RadarVisualization";
import type { MatchInsightsResponse } from "@/lib/types";

interface MatchPageProps {
  params: {
    id: string;
  };
}

export default function MatchPage({ params }: MatchPageProps) {
  const [insights, setInsights] = useState<MatchInsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadInsights = async () => {
      try {
        const response = await fetch(
          `/api/v1/analytics/matches/${params.id}/insights`
        );
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        setInsights(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    loadInsights();
  }, [params.id]);

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="h-32 rounded border border-surface-border bg-surface-raised/50 animate-pulse" />
        <div className="h-96 rounded border border-surface-border bg-surface-raised/50 animate-pulse" />
      </div>
    );
  }

  if (error || !insights) {
    return (
      <Disclaimer>
        Failed to load match analysis: {error || "No data found"}
      </Disclaimer>
    );
  }

  const minutes = Math.floor(insights.duration_ms / 60000);
  const seconds = Math.floor((insights.duration_ms % 60000) / 1000);
  const duration = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight">Match Analysis</h1>

        <div className="grid gap-4 sm:grid-cols-2">
          <Card title={`${insights.p1_name} (${insights.p1_civ})`}>
            <div className="space-y-2 text-sm">
              {insights.winner === 1 && (
                <div className="inline-block rounded bg-emerald-500/10 px-2 py-1 font-semibold text-emerald-500">
                  Victory
                </div>
              )}
            </div>
          </Card>

          <Card title={`${insights.p2_name} (${insights.p2_civ})`}>
            <div className="space-y-2 text-sm">
              {insights.winner === 2 && (
                <div className="inline-block rounded bg-emerald-500/10 px-2 py-1 font-semibold text-emerald-500">
                  Victory
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="text-sm text-ink-muted">
          Duration: {duration} | Match ID: {insights.match_id}
        </div>
      </section>

      <section className="space-y-8">
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title={`${insights.p1_name} - Decisions`}>
            {insights.p1_decisions ? (
              <DVATimeline
                report={insights.p1_decisions}
                matchDuration={insights.duration_ms}
              />
            ) : (
              <div className="text-sm text-ink-muted">Analysis unavailable</div>
            )}
          </Card>

          <Card title={`${insights.p2_name} - Decisions`}>
            {insights.p2_decisions ? (
              <DVATimeline
                report={insights.p2_decisions}
                matchDuration={insights.duration_ms}
              />
            ) : (
              <div className="text-sm text-ink-muted">Analysis unavailable</div>
            )}
          </Card>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Card title={`${insights.p1_name} - Playstyle`}>
            {insights.p1_playstyle ? (
              <PlaystyleProfile profile={insights.p1_playstyle} />
            ) : (
              <div className="text-sm text-ink-muted">Playstyle analysis unavailable</div>
            )}
          </Card>

          <Card title={`${insights.p2_name} - Playstyle`}>
            {insights.p2_playstyle ? (
              <PlaystyleProfile profile={insights.p2_playstyle} />
            ) : (
              <div className="text-sm text-ink-muted">Playstyle analysis unavailable</div>
            )}
          </Card>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {insights.p1_radar && (
            <Card title={`${insights.p1_name} - APM Radar`}>
              <RadarVisualization data={insights.p1_radar} />
            </Card>
          )}

          {insights.p2_radar && (
            <Card title={`${insights.p2_name} - APM Radar`}>
              <RadarVisualization data={insights.p2_radar} />
            </Card>
          )}
        </div>
      </section>

      <Disclaimer>
        These analytics are derived from the replay's command stream.
      </Disclaimer>
    </div>
  );
}
