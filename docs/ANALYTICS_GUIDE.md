# Advanced Analytics Guide

This document describes the three flagship analytics systems: Decision Value Added (DVA), 
Playstyle Awards, and the 3D Circular APM/Attention Radar.

## 1. Decision Value Added (DVA)

**Purpose:** Evaluate the quality of strategic decisions relative to peer baselines.

### What DVA Measures

DVA identifies decisions that moved the match outcome:

1. **Age Advancement** — Timing of transitions to feudal, castle, imperial
2. **Build Order** — Opening choice relative to peer meta
3. **Unit Composition** — Diversity and production pacing vs opponent
4. **Expansion** — Aggressive vs conservative expansion patterns

Each decision gets a value_added score (-1.0 to +1.0) and confidence rating (0.0-1.0).

### Output

```python
DVAReport(
    decisions=[DecisionEvaluation(...)],
    total_value_added=+0.25,  # Aggregate quality score
    decision_quality="good",  # excellent / good / neutral / below-average
    top_decisions=[...],      # Best decisions made
    bottom_decisions=[...]    # Areas for improvement
)
```

---

## 2. Playstyle Awards & Archetypes

**Purpose:** Identify unique strengths and classify players into strategic archetypes.

### Nine Strategic Archetypes

- **Archer Rush** — Early feudal, high military spend
- **Castle Power** — Strong castle age, multi-unit composition
- **Troop Hoard** — Large armies, unit volume focus
- **Ninja Economy** — Low visible army, explosive growth
- **Boom Domination** — Many expansions, map control
- **Turtle Defender** — High production, reactive play
- **Micro Specialist** — High APM, precision unit control
- **Pocket Aggressive** — Team player, aggressive helper
- **Balanced** — No dominant pattern, flexible

### Awards

Recognizes exceptional performance (percentile-based):
- **Legendary** (0-10th): Fastest Feudal, Lightning Castle
- **Rare** (10-20th): Army Hoarder, Economic Virtuoso
- **Uncommon** (20-40th): Expansion Specialist, Micro Master
- **Common** (40-85th): Unit Composition Expert, Steady Eddy

### Output

```python
PlaystyleProfile(
    primary_archetype=PlaystyleArchetype.ARCHER_RUSH,
    archetype_confidence=0.75,
    awards=[PlaystyleAward(...)],
    strengths=["Fastest Feudal (95th percentile)", ...],
    weaknesses=["Economy Efficiency (15th percentile)", ...]
)
```

---

## 3. 3D Circular APM/Attention Radar

**Purpose:** Visualize action distribution, focus patterns, and attention shifts.

### Visualization

A **3D polar plot** where:
- **Circumference:** Time (0° at start, 360° at end)
- **Radial distance:** Action intensity (normalized APM)
- **Color:** Action type (blue=economy, red=military, green=scouting, amber=strategy)
- **3D rotation:** Reveals temporal patterns and spikes

### Data

```python
RadarVisualization(
    samples=[ActionSample(timestamp_ms, intensity, action_type, color_code)],
    sectors=[RadarSector(intensity by type, dominant action, action count)],
    average_apm=85.5,
    peak_apm=145.0,
    focus_distribution={"economy": 0.45, "military": 0.35, ...},
    attention_shifts=7,  # How many times dominant action changed
    playstyle_signature="Early aggression, mid-game economy, late defense"
)
```

### Interpretation

1. **Intensity spikes:** High-action periods
2. **Color transitions:** Build order and strategy shifts
3. **Attention shifts:** Reactive (high shifts) vs committed (low shifts)
4. **Focus distribution:** Pie chart of effort allocation
5. **Playstyle signature:** Early/mid/late phase classification

---

## Complete Analytics Dashboard

All three systems integrated:

```
DashboardView
├── DVA Timeline (decisions over match)
├── Playstyle Profile (archetype + awards + strengths/weaknesses)
├── 3D Radar Visualization (action distribution)
└── Combined Insights (summary recommendations)
```

### API Endpoints

```
GET  /api/v1/analytics/matches/{match_id}/decisions   → DVAReport
GET  /api/v1/analytics/matches/{match_id}/playstyle   → PlaystyleProfile
GET  /api/v1/analytics/matches/{match_id}/radar       → RadarVisualization
GET  /api/v1/analytics/matches/{match_id}/insights    → Combined
```

---

## Next Steps

1. **Database Integration:** Wire endpoints to match/cohort data
2. **Frontend Components:** Implement React/Three.js visualizations
3. **Caching:** Cache results to avoid recomputation
4. **Real-time:** Support live coaching during spectator mode

See `docs/SETUP.md` for database schema and integration roadmap.
