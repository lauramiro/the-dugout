// Display helpers over the feed. Counting goals and reading snapshot fields is fine
// here; win probabilities and gaps always come from the payload as given.

import type { MatchEvent, Roster, Snapshot, SnapshotPlayer, TeamCode } from "./contracts";
import type { Timed } from "./datasource";

// The condition_drop trigger's constants (dugout/stream/triggers.py): a card opens when a
// player is CONDITION_MARGIN below his team's outfield median and under CONDITION_LINE.
export const CONDITION_LINE = 0.69;
export const CONDITION_MARGIN = 0.1;
const FORECAST_HORIZON_MIN = 15;

export type Band = "high" | "mid" | "low";

/** Three bands: 80% and up, the card line (69%) to 80, under the line. */
export function band(condition: number): Band {
  if (condition >= 0.8) return "high";
  if (condition >= CONDITION_LINE) return "mid";
  return "low";
}

export type Trend = "steady" | "falling" | "steep" | "rising";

export function trend(perMin: number | null): Trend {
  if (perMin === null) return "steady";
  if (perMin > 0.001) return "rising";
  if (perMin <= -0.008) return "steep";
  if (perMin <= -0.003) return "falling";
  return "steady";
}

export function score(events: readonly Timed<MatchEvent>[], upto: number, teams: TeamCode[]): Record<TeamCode, number> {
  const out: Record<TeamCode, number> = Object.fromEntries(teams.map((t) => [t, 0]));
  for (let i = 0; i <= upto; i++) {
    const e = events[i].item;
    if (e.type === "goal") out[e.team] = (out[e.team] ?? 0) + 1;
  }
  return out;
}

const TICKER_TYPES = new Set(["goal", "shot", "sub", "card"]);

/** The newest notable events, newest first. A goal's shot is folded into the goal. */
export function tickerEvents(events: readonly Timed<MatchEvent>[], upto: number, limit: number): Timed<MatchEvent>[] {
  const out: Timed<MatchEvent>[] = [];
  for (let i = upto; i >= 0 && out.length < limit; i--) {
    const e = events[i].item;
    if (!TICKER_TYPES.has(e.type) || (e.type === "shot" && e.outcome === "goal")) continue;
    out.push(events[i]);
  }
  return out;
}

export function playerName(roster: Roster | null, id: string | null | undefined): string {
  if (!id) return "";
  return roster?.players[id]?.name ?? id;
}

// The agents name players by id only, since the grounding check verifies ids
// (dugout.agents.grounding.PLAYER_ID); the screen shows names.
const PLAYER_ID = /\b[A-Z]{2,4}-\d{2,3}\b/g;

/** Narration or recap text with every known player id replaced by his roster name. */
export function withNames(text: string, roster: Roster | null): string {
  return roster ? text.replace(PLAYER_ID, (id) => roster.players[id]?.name ?? id) : text;
}

export function shirt(id: string): string {
  return String(Number(id.split("-").pop()));
}

export interface WindowForecast {
  playerId: string;
  minutes: number | null; // null: already below the line
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/**
 * Substitution windows, on the card's own rule: players at least 10 points below their
 * team's outfield median who are under the 69% line, or heading there within 15 minutes
 * on their current trend (the snapshot's own condition_est and trend_per_min).
 */
export function forecasts(players: readonly SnapshotPlayer[], team: TeamCode): WindowForecast[] {
  const out: WindowForecast[] = [];
  const ests = players.flatMap((p) => (p.id.startsWith(`${team}-`) && p.condition_est !== null ? [p.condition_est] : []));
  if (ests.length === 0) return out;
  const teamMedian = median(ests);
  for (const p of players) {
    if (!p.id.startsWith(`${team}-`) || p.condition_est === null) continue;
    if (p.condition_est > teamMedian - CONDITION_MARGIN) continue;
    if (p.condition_est < CONDITION_LINE) {
      out.push({ playerId: p.id, minutes: null });
    } else if (p.trend_per_min !== null && p.trend_per_min < 0) {
      const minutes = Math.round((p.condition_est - CONDITION_LINE) / -p.trend_per_min);
      if (minutes <= FORECAST_HORIZON_MIN) out.push({ playerId: p.id, minutes });
    }
  }
  return out.sort((a, b) => (a.minutes ?? -1) - (b.minutes ?? -1));
}

export function teamPlayers(snapshot: Snapshot, team: TeamCode): SnapshotPlayer[] {
  return snapshot.players.filter((p) => p.id.startsWith(`${team}-`));
}
