import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";

import { Nav } from "@/components/nav";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: {
    default: "AoE2 Analytics — Replay analysis & coaching",
    template: "%s · AoE2 Analytics",
  },
  description:
    "Post-game Age of Empires II analytics: economy, military, scouting metrics, peer comparison, and coaching insights from replay analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-40 border-b border-surface-border bg-surface/80 backdrop-blur-md">
          {/* Wraps to a second row rather than overflowing on a phone. */}
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link
              href="/"
              className="flex items-center gap-2.5 font-semibold tracking-tight transition-opacity hover:opacity-80"
            >
              <span
                aria-hidden
                className="inline-block h-5 w-5 rounded bg-gradient-to-br from-accent to-accent-soft"
              />
              AoE2 Analytics
            </Link>

            <div className="ml-auto flex items-center gap-1">
              <Nav />
              <a
                href="https://github.com/thescienceco/league"
                className="rounded-md px-2.5 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink"
              >
                GitHub
              </a>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4">{children}</main>

        <footer className="border-t border-surface-border">
          <div className="mx-auto max-w-7xl px-4 py-6 text-xs leading-relaxed text-ink-faint">
            <p className="max-w-3xl">
              Analysis is derived from replay files, which record player commands rather than
              game outcomes. Figures marked <em>inferred</em> or <em>reconstructed</em> are
              estimates, not measurements. Not endorsed by or affiliated with Microsoft or Xbox
              Game Studios.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
