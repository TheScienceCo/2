"use client";

import { useState } from "react";

import { ResourceCurveChart } from "@/components/charts";
import { ApiError, uploadReplay } from "@/lib/api";
import { clock, metricValue, signedClock } from "@/lib/format";
import type { MatchAnalysis, Metric, PlayerAnalysis } from "@/lib/types";

const ACCEPT = ".aoe2record,.mgz,.mgx,.aoe2mpgame";

/** Metrics shown in the summary table, in reading order. */
const SUMMARY_KEYS = [
  "feudal_time",
  "castle_time",
  "imperial_time",
  "float_mean",
  "float_peak",
  "time_floating",
  "villagers_queued",
  "max_production_gap",
  "buildings_placed",
  "technologies_researched",
  "eapm",
];

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MatchAnalysis | null>(null);
  const [dragging, setDragging] = useState(false);

  async function submit(chosen: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await uploadReplay(chosen));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function choose(chosen: File | undefined) {
    if (!chosen) return;
    setFile(chosen);
    setError(null);
    void submit(chosen);
  }

  return (
    <div className="space-y-8 py-10">
      <header className={`space-y-2 ${result ? "" : "mx-auto max-w-2xl text-center"}`}>
        <h1 className="text-3xl font-semibold tracking-tight">Analyse a replay</h1>
        <p className="text-ink-muted">
          Drop an <code className="font-mono text-sm">.aoe2record</code> file in. Nothing
          is kept beyond the analysis itself.
        </p>
      </header>

      {/* Until there's a result this is the whole page, so give it room. */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          choose(e.dataTransfer.files[0]);
        }}
        className={`mx-auto flex max-w-2xl flex-col items-center justify-center rounded-xl border-2 border-dashed text-center transition-colors ${
          result ? "px-6 py-8" : "px-6 py-16"
        } ${
          dragging
            ? "border-accent bg-accent/5"
            : "border-surface-border bg-surface-raised/40 hover:border-ink-faint"
        }`}
      >
        <svg
          aria-hidden
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`mb-3 h-8 w-8 transition-colors ${dragging ? "text-accent" : "text-ink-faint"}`}
        >
          <path d="M12 16V4m0 0L8 8m4-4 4 4" />
          <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
        </svg>

        <p className="font-medium">Drag a replay here</p>
        <p className="mt-1 text-sm text-ink-muted">
          or{" "}
          <label className="cursor-pointer text-accent underline-offset-2 hover:underline">
            choose a file
            <input
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => choose(e.target.files?.[0])}
            />
          </label>
        </p>
        <p className="mt-3 font-mono text-[11px] text-ink-faint">
          .aoe2record · .mgz · .mgx · .aoe2mpgame
        </p>
        {file && (
          <p className="mt-3 text-xs text-ink-faint">
            {file.name} · {(file.size / 1_048_576).toFixed(1)} MB
          </p>
        )}
        {busy && (
          <p className="mt-3 flex items-center gap-2 text-sm text-ink-muted">
            <span
              aria-hidden
              className="h-3 w-3 animate-spin rounded-full border-2 border-surface-border border-t-accent"
            />
            Parsing and analysing…
          </p>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          {error}
        </div>
      )}

      {result && <Analysis result={result} />}
    </div>
  );
}

function Analysis({ result }: { result: MatchAnalysis }) {
  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-2xl font-semibold">{result.map_name ?? "Unknown map"}</h2>
        <span className="text-ink-muted">{clock(result.duration_ms)}</span>
        {result.version && <span className="text-xs text-ink-faint">{result.version}</span>}
      </div>

      {result.warnings.length > 0 && (
        <div className="space-y-1 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <p className="font-medium">Some metrics are unavailable for this replay</p>
          <ul className="list-inside list-disc">
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <ResourceCurveChart players={result.players} />

      <div className="grid gap-6 lg:grid-cols-2">
        {result.players.map((p) => (
          <PlayerCard key={p.player_number} player={p} />
        ))}
      </div>
    </section>
  );
}

function PlayerCard({ player }: { player: PlayerAnalysis }) {
  return (
    <article className="space-y-4 rounded-lg border border-surface-border bg-surface-raised p-5">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold">{player.name}</h3>
          {player.winner && (
            <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent">
              won
            </span>
          )}
        </div>
        <p className="text-sm text-ink-muted">
          {player.civilization}
          {player.opening && player.opening !== "unclassified" && ` · ${player.opening}`}
        </p>
      </header>

      {player.insights.length > 0 && (
        <ul className="space-y-2 text-sm">
          {player.insights.map((line) => (
            <li key={line} className="border-l-2 border-surface-border pl-3 text-ink-muted">
              {line}
            </li>
          ))}
        </ul>
      )}

      <table className="w-full text-sm">
        <caption className="sr-only">Derived metrics for {player.name}</caption>
        <tbody>
          {SUMMARY_KEYS.flatMap((key) => {
            const m = player.metrics[key];
            return m ? [<MetricRow key={m.key} metric={m} />] : [];
          })}
          {["feudal", "castle", "imperial"].map((age) => {
            const m = player.metrics[`${age}_delta`];
            if (!m || m.value === null) return null;
            return (
              <tr key={m.key} className="border-t border-surface-border/60">
                <th scope="row" className="py-1.5 text-left font-normal text-ink-muted">
                  {m.label}
                </th>
                <td className="py-1.5 text-right font-mono tabular-nums">
                  {signedClock(m.value)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </article>
  );
}

function MetricRow({ metric }: { metric: Metric }) {
  const unavailable = metric.availability === "unavailable";
  return (
    <tr className="border-t border-surface-border/60">
      <th scope="row" className="py-1.5 text-left font-normal text-ink-muted">
        {metric.label}
        {/* Provenance is part of the number: an inferred figure must not read as measured. */}
        {!unavailable && metric.availability !== "observed" && (
          <span className="ml-1.5 text-xs text-ink-faint">({metric.availability})</span>
        )}
      </th>
      <td
        className={`py-1.5 text-right font-mono tabular-nums ${unavailable ? "text-ink-faint" : ""}`}
        title={metric.note ?? undefined}
      >
        {unavailable ? "unavailable" : metricValue(metric.value, metric.unit)}
      </td>
    </tr>
  );
}
