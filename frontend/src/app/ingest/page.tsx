"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import { Card, Disclaimer } from "@/components/ui";
import { REPLAY_ENDPOINT } from "@/lib/api";
import { clock } from "@/lib/format";
import type { MatchAnalysis } from "@/lib/types";

const ACCEPT = ".aoe2record,.mgz,.mgx,.aoe2mpgame";

type Status = "queued" | "running" | "done" | "failed";

interface Job {
  id: string;
  file: File;
  status: Status;
  result?: MatchAnalysis;
  error?: string;
  /** Wall-clock ms the request took, so slow replays are visible. */
  elapsedMs?: number;
}

const STATUS_STYLE: Record<Status, string> = {
  queued: "bg-surface-overlay text-ink-faint",
  running: "bg-accent/15 text-accent",
  done: "bg-good/15 text-good",
  failed: "bg-bad/15 text-bad",
};

/**
 * Internal batch ingest. Files are sent to the same single-upload endpoint,
 * strictly one at a time: replay parsing is CPU-bound, and firing a folder of
 * them at once would just queue in the server's threadpool while making
 * failures harder to attribute. This moves to a backend worker later.
 */
export default function IngestPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [running, setRunning] = useState(false);
  const [dragging, setDragging] = useState(false);
  const cancelled = useRef(false);

  const add = useCallback((files: FileList | File[] | null) => {
    if (!files) return;
    const incoming = Array.from(files).map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 7)}`,
      file,
      status: "queued" as Status,
    }));
    if (incoming.length) setJobs((prev) => [...prev, ...incoming]);
  }, []);

  async function run() {
    setRunning(true);
    cancelled.current = false;

    // Snapshot ids up front; anything added mid-run waits for the next pass.
    const pending = jobs.filter((j) => j.status === "queued" || j.status === "failed");

    for (const job of pending) {
      if (cancelled.current) break;

      setJobs((prev) =>
        prev.map((j) => (j.id === job.id ? { ...j, status: "running", error: undefined } : j)),
      );

      const startedAt = performance.now();
      try {
        const body = new FormData();
        body.append("file", job.file);
        const response = await fetch(REPLAY_ENDPOINT, { method: "POST", body });
        const elapsedMs = Math.round(performance.now() - startedAt);

        if (!response.ok) {
          const detail = await response
            .json()
            .then((b) => b?.detail)
            .catch(() => null);
          throw new Error(detail ?? `HTTP ${response.status}`);
        }

        const result: MatchAnalysis = await response.json();
        setJobs((prev) =>
          prev.map((j) => (j.id === job.id ? { ...j, status: "done", result, elapsedMs } : j)),
        );
      } catch (e) {
        const elapsedMs = Math.round(performance.now() - startedAt);
        setJobs((prev) =>
          prev.map((j) =>
            j.id === job.id
              ? {
                  ...j,
                  status: "failed",
                  elapsedMs,
                  error: e instanceof Error ? e.message : "Upload failed.",
                }
              : j,
          ),
        );
      }
    }

    setRunning(false);
  }

  const counts = {
    queued: jobs.filter((j) => j.status === "queued").length,
    done: jobs.filter((j) => j.status === "done").length,
    failed: jobs.filter((j) => j.status === "failed").length,
  };
  const pendingCount = counts.queued + counts.failed;

  return (
    <div className="space-y-8 py-10">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="rounded bg-warn/15 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-warn">
            Internal
          </span>
          <span className="text-xs text-ink-faint">not a player-facing page</span>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">Batch ingest</h1>
        <p className="max-w-2xl text-ink-muted">
          Drop a folder&rsquo;s worth of replays in. They are parsed one at a time against
          the same endpoint a single upload uses, so a failure is attributable to one file.
        </p>
      </header>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(e.dataTransfer.files);
        }}
        className={`rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging
            ? "border-accent bg-accent/5"
            : "border-surface-border bg-surface-raised/40 hover:border-ink-faint"
        }`}
      >
        <p className="font-medium">Drop replays here</p>
        <p className="mt-1 text-sm text-ink-muted">
          or{" "}
          <label className="cursor-pointer text-accent underline-offset-2 hover:underline">
            choose files
            <input
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                add(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        </p>
        <p className="mt-3 font-mono text-[11px] text-ink-faint">{ACCEPT.replace(/,/g, " · ")}</p>
      </div>

      {jobs.length > 0 && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={run}
              disabled={running || pendingCount === 0}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running
                ? "Processing…"
                : counts.failed && !counts.queued
                  ? `Retry ${counts.failed} failed`
                  : `Process ${pendingCount} file${pendingCount === 1 ? "" : "s"}`}
            </button>

            {running && (
              <button
                type="button"
                onClick={() => {
                  cancelled.current = true;
                }}
                className="rounded-lg border border-surface-border px-4 py-2 text-sm font-medium transition hover:bg-surface-raised"
              >
                Stop after current
              </button>
            )}

            <button
              type="button"
              onClick={() => setJobs([])}
              disabled={running}
              className="rounded-lg border border-surface-border px-4 py-2 text-sm font-medium transition hover:bg-surface-raised disabled:opacity-40"
            >
              Clear
            </button>

            <div className="ml-auto flex items-center gap-4 text-sm text-ink-muted">
              <span>
                <span className="stat text-ink">{counts.done}</span> done
              </span>
              <span>
                <span className="stat text-ink">{counts.queued}</span> queued
              </span>
              <span className={counts.failed ? "text-bad" : undefined}>
                <span className="stat">{counts.failed}</span> failed
              </span>
            </div>
          </div>

          <Card title="Queue" aside={`${jobs.length} file${jobs.length === 1 ? "" : "s"}`}>
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Match</th>
                    <th className="text-right">Time</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td className="max-w-[18rem]">
                        <div className="truncate font-medium">{job.file.name}</div>
                        <div className="text-xs text-ink-faint">
                          {(job.file.size / 1_048_576).toFixed(1)} MB
                        </div>
                      </td>
                      <td>
                        <span
                          className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLE[job.status]}`}
                        >
                          {job.status}
                        </span>
                        {job.error && (
                          <div className="mt-1 max-w-[22rem] text-xs text-bad">{job.error}</div>
                        )}
                      </td>
                      <td>
                        {job.result ? (
                          <div className="space-y-0.5">
                            <div>
                              {job.result.map_name ?? "Unknown map"}{" "}
                              <span className="text-ink-faint">
                                · {clock(job.result.duration_ms)}
                              </span>
                            </div>
                            <div className="text-xs text-ink-muted">
                              {job.result.players.map((p) => p.name).join(" vs ")}
                            </div>
                            {job.result.warnings.length > 0 && (
                              <div className="text-xs text-warn">
                                {job.result.warnings.length} warning
                                {job.result.warnings.length === 1 ? "" : "s"}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-ink-faint">—</span>
                        )}
                      </td>
                      <td className="text-right stat text-xs text-ink-muted">
                        {job.elapsedMs ? `${(job.elapsedMs / 1000).toFixed(1)}s` : "—"}
                      </td>
                      <td className="text-right">
                        {job.result && (
                          <Link href={`/match/${job.result.replay_id}`} className="link text-sm">
                            Analysis
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <Disclaimer>
        Re-uploading a file already ingested returns the stored analysis rather than parsing
        it again — the replay id is a hash of the file&rsquo;s bytes. A file that fails here
        is usually from a game version the parser does not support; the error column carries
        the server&rsquo;s reason.
      </Disclaimer>
    </div>
  );
}
