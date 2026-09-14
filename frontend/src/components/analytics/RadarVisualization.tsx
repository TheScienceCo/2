"use client";

import { clock } from "@/lib/format";
import type { RadarSectorResponse, RadarVisualizationResponse } from "@/lib/types";

interface RadarVisualizationProps {
  data: RadarVisualizationResponse;
}

const ACTION_LABEL: Record<string, string> = {
  economy: "Economy",
  military: "Military",
  scouting: "Scouting",
  strategy: "Strategy",
};

/** Four categorical hues, separated for colour-vision deficiency and legible on
 *  the dark surface. Colour follows the action type, never its rank. */
const ACTION_COLOR: Record<string, string> = {
  economy: "#4c9aff",
  military: "#eb6834",
  scouting: "#3fb950",
  strategy: "#a371f7",
};

const FALLBACK_COLOR = "#6b7785";

const SIZE = 240;
const CENTER = SIZE / 2;
const R_INNER = 26;
const R_OUTER = 108;
/** Breathing room in the viewBox so the outer time labels aren't clipped. */
const PAD = 24;

function polar(angle: number, radius: number): [number, number] {
  return [CENTER + radius * Math.cos(angle), CENTER + radius * Math.sin(angle)];
}

/** An annular wedge between two angles, from `R_INNER` out to `radius`. */
function wedgePath(a0: number, a1: number, radius: number): string {
  const [x0, y0] = polar(a0, R_INNER);
  const [x1, y1] = polar(a0, radius);
  const [x2, y2] = polar(a1, radius);
  const [x3, y3] = polar(a1, R_INNER);
  const large = a1 - a0 > Math.PI ? 1 : 0;

  return [
    `M ${x0} ${y0}`,
    `L ${x1} ${y1}`,
    `A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2}`,
    `L ${x3} ${y3}`,
    `A ${R_INNER} ${R_INNER} 0 ${large} 0 ${x0} ${y0}`,
    "Z",
  ].join(" ");
}

export function RadarVisualization({ data }: RadarVisualizationProps) {
  return (
    <div className="space-y-5">
      {data.playstyle_signature && (
        <p className="text-sm text-ink-muted">{data.playstyle_signature}</p>
      )}

      <div className="grid gap-5 sm:grid-cols-[auto,1fr] sm:items-center">
        <PolarRadar sectors={data.sectors} duration={data.match_duration_ms} />

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-1">
          <div>
            <dt className="label">Average APM</dt>
            <dd className="stat text-xl">{data.average_apm.toFixed(0)}</dd>
          </div>
          <div>
            <dt className="label">Peak APM</dt>
            <dd className="stat text-xl">{data.peak_apm.toFixed(0)}</dd>
          </div>
          <div>
            <dt className="label">Attention shifts</dt>
            <dd className="stat text-xl">{data.attention_shifts}</dd>
          </div>
        </dl>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {Object.keys(ACTION_LABEL).map((type) => (
          <span key={type} className="flex items-center gap-1.5 text-xs text-ink-muted">
            <span
              aria-hidden
              className="h-2 w-2 rounded-sm"
              style={{ background: ACTION_COLOR[type] }}
            />
            {ACTION_LABEL[type]}
          </span>
        ))}
      </div>

      <div className="space-y-2.5 border-t border-surface-border pt-4">
        <h3 className="text-sm font-semibold">Where attention went</h3>
        {Object.entries(data.focus_distribution)
          .sort(([, a], [, b]) => b - a)
          .map(([type, share]) => (
            <div key={type} className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-ink-muted">{ACTION_LABEL[type] ?? type}</span>
                <span className="stat font-semibold">{(share * 100).toFixed(0)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-overlay">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.max(0, Math.min(1, share)) * 100}%`,
                    background: ACTION_COLOR[type] ?? FALLBACK_COLOR,
                  }}
                />
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

/**
 * Time runs clockwise around the circumference, action intensity is the radius
 * and the dominant action type is the colour — the match read as one shape.
 */
function PolarRadar({
  sectors,
  duration,
}: {
  sectors: RadarSectorResponse[];
  duration: number;
}) {
  if (sectors.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-surface-border text-xs text-ink-faint"
        style={{ width: SIZE, height: SIZE }}
      >
        No command telemetry
      </div>
    );
  }

  const peak = Math.max(...sectors.map((s) => s.total_action_count), 1);
  const span = duration || sectors[sectors.length - 1]?.time_end_ms || 1;

  // Start at 12 o'clock and run clockwise.
  const angleAt = (ms: number) => (ms / span) * Math.PI * 2 - Math.PI / 2;

  return (
    <figure className="space-y-1.5">
      <svg
        viewBox={`${-PAD} ${-PAD} ${SIZE + PAD * 2} ${SIZE + PAD * 2}`}
        width={SIZE}
        height={SIZE}
        role="img"
        aria-label={`Action intensity around ${clock(span)} of match time, coloured by action type`}
        className="max-w-full"
      >
        {/* Scale rings at 25 / 50 / 75 / 100% of peak intensity. */}
        {[0.25, 0.5, 0.75, 1].map((step) => (
          <circle
            key={step}
            cx={CENTER}
            cy={CENTER}
            r={R_INNER + (R_OUTER - R_INNER) * step}
            fill="none"
            stroke="#262d38"
            strokeWidth={1}
            strokeDasharray={step === 1 ? undefined : "2 4"}
          />
        ))}

        {sectors.map((s, i) => {
          const radius =
            R_INNER + (R_OUTER - R_INNER) * Math.sqrt(s.total_action_count / peak);
          const a0 = angleAt(s.time_start_ms);
          const a1 = angleAt(s.time_end_ms);
          if (a1 <= a0) return null;

          return (
            <path
              key={i}
              d={wedgePath(a0, a1, radius)}
              fill={ACTION_COLOR[s.dominant_action_type] ?? FALLBACK_COLOR}
              fillOpacity={0.85}
              stroke="#0d1117"
              strokeWidth={0.5}
            >
              <title>
                {`${clock(s.time_start_ms)}–${clock(s.time_end_ms)} · ${s.total_action_count} actions · ${
                  ACTION_LABEL[s.dominant_action_type] ?? s.dominant_action_type
                }`}
              </title>
            </path>
          );
        })}

        {/* Quarter marks, so the ring reads as elapsed time. */}
        {[0, 0.25, 0.5, 0.75].map((frac) => {
          const [x, y] = polar(frac * Math.PI * 2 - Math.PI / 2, R_OUTER + 12);
          return (
            <text
              key={frac}
              x={x}
              y={y}
              fill="#6b7785"
              fontSize={9}
              textAnchor="middle"
              dominantBaseline="middle"
            >
              {clock(span * frac)}
            </text>
          );
        })}
      </svg>
      <figcaption className="text-[11px] leading-snug text-ink-faint">
        Time clockwise from the top · radius is action intensity
      </figcaption>
    </figure>
  );
}
