"use client";

import { PlaystyleProfileResponse } from "@/lib/types";

interface PlaystyleProfileProps {
  profile: PlaystyleProfileResponse;
}

const archetypeDescriptions: Record<string, string> = {
  archer_rush: "Early feudal aggression with high military investment",
  castle_power: "Strong castle age with flexible unit composition",
  troop_hoard: "Large armies, overwhelming unit volume",
  ninja_economy: "Low visible army, explosive growth",
  boom_domination: "Aggressive expansion, map control focus",
  turtle_defender: "Defensive production, reactive playstyle",
  micro_specialist: "High APM, precision unit control",
  pocket_aggressive: "Team player, aggressive helper",
  balanced: "No dominant pattern, flexible approach",
};

export function PlaystyleProfile({ profile }: PlaystyleProfileProps) {
  const archetypeName = profile.primary_archetype.replace(/_/g, " ").toLowerCase();
  const description = archetypeDescriptions[profile.primary_archetype] || "";

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold capitalize">{archetypeName}</h2>
        <p className="text-sm text-ink-muted">{description}</p>

        <div className="flex items-center gap-2 text-xs">
          <div className="h-2 rounded-full bg-surface-border flex-1">
            <div
              className="h-2 rounded-full bg-accent"
              style={{ width: `${profile.archetype_confidence * 100}%` }}
            />
          </div>
          <span className="text-ink-muted">{Math.round(profile.archetype_confidence * 100)}% confidence</span>
        </div>
      </div>

      {/* Awards */}
      {profile.awards.length > 0 && (
        <div className="space-y-2 border-t border-surface-border pt-4">
          <h3 className="text-sm font-semibold">Achievements</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {profile.awards.map((award) => {
              const rarityColors = {
                legendary: "bg-amber-500/10 border-amber-500 text-amber-500",
                rare: "bg-purple-500/10 border-purple-500 text-purple-500",
                uncommon: "bg-blue-500/10 border-blue-500 text-blue-500",
                common: "bg-slate-500/10 border-slate-500 text-slate-500",
              };

              return (
                <div
                  key={award.award}
                  className={`rounded border p-2 text-xs font-semibold ${rarityColors[award.rarity as keyof typeof rarityColors]}`}
                >
                  🏆 {award.award}
                  <div className="mt-0.5 text-xs font-normal text-ink-muted">{award.percentile}th percentile</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Strengths */}
      {profile.strengths.length > 0 && (
        <div className="space-y-2 border-t border-surface-border pt-4">
          <h3 className="text-sm font-semibold">Strengths</h3>
          <ul className="space-y-1">
            {profile.strengths.map((strength, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-ink-muted">
                <span className="mt-0.5 text-emerald-500">✓</span>
                <span>{strength}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Weaknesses */}
      {profile.weaknesses.length > 0 && (
        <div className="space-y-2 border-t border-surface-border pt-4">
          <h3 className="text-sm font-semibold">Areas to Improve</h3>
          <ul className="space-y-1">
            {profile.weaknesses.map((weakness, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-ink-muted">
                <span className="mt-0.5 text-red-500">→</span>
                <span>{weakness}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
