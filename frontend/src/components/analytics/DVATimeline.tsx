"use client";

import { clock } from "@/lib/format";
import { DVAReportResponse, DecisionEvaluationResponse } from "@/lib/types";

interface DVATimelineProps {
  report: DVAReportResponse;
  matchDuration: number;
}

export function DVATimeline({ report, matchDuration }: DVATimelineProps) {
  const qualityColors = {
    excellent: "bg-emerald-500",
    good: "bg-blue-500",
    neutral: "bg-slate-500",
    "below-average": "bg-red-500",
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Decision Value Added</h2>
        <div className="flex items-center gap-2">
          <div className={`h-3 w-3 rounded-full ${qualityColors[report.decision_quality as keyof typeof qualityColors]}`} />
          <span className="text-sm font-medium capitalize">{report.decision_quality}</span>
        </div>
      </div>

      {/* Quality meter */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-ink-muted">
          <span>Poor</span>
          <span>Neutral</span>
          <span>Excellent</span>
        </div>
        <div className="h-2 rounded-full bg-surface-border">
          <div
            className={`h-2 rounded-full transition-all ${qualityColors[report.decision_quality as keyof typeof qualityColors]}`}
            style={{
              width: `${((report.total_value_added + 1) / 2) * 100}%`,
            }}
          />
        </div>
      </div>

      {/* Every evaluated decision, placed where in the match it happened. */}
      {report.decisions.length > 0 && matchDuration > 0 && (
        <MatchTrack decisions={report.decisions} matchDuration={matchDuration} />
      )}

      <div className="space-y-2 border-t border-surface-border pt-4">
        <h3 className="text-sm font-semibold text-ink-muted">Top Decisions</h3>
        <div className="space-y-2">
          {report.top_decisions.slice(0, 3).map((decision, i) => (
            <DecisionMarker key={i} decision={decision} />
          ))}
        </div>
      </div>

      {report.bottom_decisions.length > 0 && (
        <div className="space-y-2 border-t border-surface-border pt-4">
          <h3 className="text-sm font-semibold text-ink-muted">Areas for Improvement</h3>
          <div className="space-y-2">
            {report.bottom_decisions.slice(0, 3).map((decision, i) => (
              <DecisionMarker key={i} decision={decision} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Each evaluated decision as a dot on the match's timeline. Position is when it
 * happened, colour is whether it helped, opacity is how confident the figure is.
 */
function MatchTrack({
  decisions,
  matchDuration,
}: {
  decisions: DecisionEvaluationResponse[];
  matchDuration: number;
}) {
  return (
    <div className="space-y-1.5 border-t border-surface-border pt-4">
      <div className="relative h-6">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-surface-border" />
        {decisions.map((d, i) => (
          <span
            key={i}
            title={`${clock(d.timestamp_ms)} · ${d.decision_type} · ${d.value_added > 0 ? "+" : ""}${d.value_added.toFixed(2)}`}
            className={`absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface-raised ${
              d.value_added >= 0 ? "bg-emerald-500" : "bg-red-500"
            }`}
            style={{
              left: `${Math.min(100, Math.max(0, (d.timestamp_ms / matchDuration) * 100))}%`,
              opacity: 0.35 + d.confidence * 0.65,
            }}
          />
        ))}
      </div>
      <div className="flex justify-between text-[11px] text-ink-faint">
        <span>0:00</span>
        <span>{clock(matchDuration)}</span>
      </div>
    </div>
  );
}

function DecisionMarker({ decision }: { decision: DecisionEvaluationResponse }) {
  const timestamp = clock(decision.timestamp_ms);
  const valueColor = decision.value_added > 0 ? "text-emerald-500" : "text-red-500";

  return (
    <div className="flex items-start gap-2 rounded border border-surface-border p-2 text-sm">
      <div className="mt-0.5 flex-shrink-0 text-xs text-ink-muted">{timestamp}</div>
      <div className="flex-1 space-y-1">
        <div className="flex items-center justify-between">
          <span className="font-semibold capitalize">{decision.decision_type.replace(/_/g, " ")}</span>
          <span className={`font-semibold ${valueColor}`}>{decision.value_added > 0 ? "+" : ""}{decision.value_added.toFixed(2)}</span>
        </div>
        <p className="text-xs text-ink-muted">{decision.explanation}</p>
        <div className="flex items-center gap-1 text-xs text-ink-muted">
          <div className="h-1.5 w-12 rounded-full bg-surface-border">
            <div
              className="h-1.5 rounded-full bg-accent"
              style={{ width: `${Math.max(1, decision.confidence * 100)}%` }}
            />
          </div>
          <span>{Math.round(decision.confidence * 100)}% confidence</span>
        </div>
      </div>
    </div>
  );
}
