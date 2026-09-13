"use client";

import { RadarVisualizationResponse } from "@/lib/types";

interface RadarVisualizationProps {
  data: RadarVisualizationResponse;
}

export function RadarVisualization({ data }: RadarVisualizationProps) {
  const actionTypeLabels = {
    economy: "Economy",
    military: "Military",
    scouting: "Scouting",
    strategy: "Strategy",
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">APM & Attention Radar</h2>
        <p className="text-sm text-ink-muted">{data.playstyle_signature}</p>
      </div>

      {/* 3D Radar placeholder - would use Three.js in production */}
      <div className="rounded border border-surface-border bg-surface-raised p-8 text-center">
        <div className="space-y-2">
          <div className="text-sm text-ink-muted">3D Polar Visualization</div>
          <div className="text-lg font-semibold">
            {data.average_apm.toFixed(0)} APM (avg) / {data.peak_apm.toFixed(0)} (peak)
          </div>
          <div className="text-xs text-ink-muted">
            {data.attention_shifts} attention shifts during match
          </div>
        </div>
      </div>

      {/* Focus distribution */}
      <div className="space-y-2 border-t border-surface-border pt-4">
        <h3 className="text-sm font-semibold">Action Distribution</h3>
        <div className="space-y-2">
          {Object.entries(data.focus_distribution).map(([type, percentage]) => (
            <div key={type} className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="capitalize text-ink-muted">{actionTypeLabels[type as keyof typeof actionTypeLabels]}</span>
                <span className="font-semibold">{(percentage * 100).toFixed(0)}%</span>
              </div>
              <div className="h-2 rounded-full bg-surface-border">
                <div
                  className="h-2 rounded-full bg-accent transition-all"
                  style={{ width: `${percentage * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Timeline */}
      <div className="space-y-2 border-t border-surface-border pt-4">
        <h3 className="text-sm font-semibold">Intensity Timeline (by minute)</h3>
        <div className="flex items-end gap-1 overflow-x-auto pb-2">
          {data.sectors.map((sector, i) => {
            const height = Math.max(2, sector.total_action_count * 2);
            const colors = {
              economy: "bg-blue-500",
              military: "bg-red-500",
              scouting: "bg-green-500",
              strategy: "bg-amber-500",
            };

            return (
              <div
                key={i}
                className="flex flex-col items-center gap-1"
                title={`${i}:00 - ${i + 1}:00\n${sector.total_action_count} actions\nDominant: ${sector.dominant_action_type}`}
              >
                <div
                  className={`w-1 rounded-sm transition-all hover:w-2 ${colors[sector.dominant_action_type as keyof typeof colors]}`}
                  style={{ height: `${height}px` }}
                />
                <span className="text-xs text-ink-muted">{i}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Note about 3D rendering */}
      <div className="rounded border border-surface-border bg-surface-raised/50 p-3 text-xs text-ink-muted">
        <p>
          🎯 Full 3D radar visualization uses Three.js for interactive rotation and zoom. 
          This view shows the summary statistics and 1-minute timeline.
        </p>
      </div>
    </div>
  );
}
