"use client";

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

      {/* Decisions timeline */}
      <div className="space-y-2 border-t border-surface-border pt-4">
        <h3 className="text-sm font-semibold text-ink-muted">Top Decisions</h3>
        <div className="space-y-2">
          {report.top_decisions.slice(0, 3).map((decision, i) => (
            <DecisionMarker key={i} decision={decision} matchDuration={matchDuration} />
          ))}
        </div>
      </div>

      {report.bottom_decisions.length > 0 && (
        <div className="space-y-2 border-t border-surface-border pt-4">
          <h3 className="text-sm font-semibold text-ink-muted">Areas for Improvement</h3>
          <div className="space-y-2">
            {report.bottom_decisions.slice(0, 3).map((decision, i) => (
              <DecisionMarker key={i} decision={decision} matchDuration={matchDuration} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DecisionMarker({
  decision,
  matchDuration,
}: {
  decision: DecisionEvaluationResponse;
  matchDuration: number;
}) {
  const minutes = Math.floor(decision.timestamp_ms / 60000);
  const seconds = Math.floor((decision.timestamp_ms % 60000) / 1000);
  const timestamp = `${minutes}:${seconds.toString().padStart(2, "0")}`;

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
