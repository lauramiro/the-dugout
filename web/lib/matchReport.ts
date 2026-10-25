// The full-time match report: the result, the goals and the decision of the match, built from the
// match data and the review's own checked line, so it adds no number the rest of the page does not show.

import { formatMinute } from "./clock.ts";
import type { Cue } from "./cues.ts";
import { scoreAt } from "./cues.ts";
import type { DecisionCard, Locale, Mode, Roster, TeamCode } from "./contracts.ts";
import type { MatchLog } from "./datasource.ts";
import { playerName, withNames } from "./derive.ts";
import type { Translate } from "./i18n.ts";

export interface WhatIfRow {
  decision_id: string;
  minute: number;
  label: string;
  gap_win: number | null;
}

export interface MatchReport {
  home: TeamCode;
  away: TeamCode;
  score: Record<TeamCode, number>;
  goals: { team: TeamCode; player_id: string | null; label: string }[];
  /** The decision What if leads with, or null when no decision was reviewed. */
  lead: { decision_id: string; label: string } | null;
}

/** What if's rows. A manager_sub card was raised by the manager's own change, so it has no call of his to
 *  price against the model's: leave it out rather than count that change twice. */
export function whatIfRows(cue: Cue, cards: readonly DecisionCard[]): WhatIfRow[] {
  const trigger = (id: string) => cards.find((c) => c.payload.decision_id === id)?.payload.trigger;
  return ((cue.data.rows as WhatIfRow[]) ?? []).filter((row) => trigger(row.decision_id) !== "manager_sub");
}

/** The decision What if leads with: `leadId` (the story's own card) or the cue's lead when it is a row,
 *  else the largest gap. */
export function whatIfLead(cue: Cue, cards: readonly DecisionCard[], leadId: string | null): string | null {
  const rows = whatIfRows(cue, cards);
  const cueLead = leadId ?? (cue.data.lead as string | null);
  if (rows.some((row) => row.decision_id === cueLead)) return cueLead;
  return rows.reduce<WhatIfRow | null>((best, row) =>
    (row.gap_win !== null && row.gap_win > (best?.gap_win ?? -Infinity) ? row : best), null)?.decision_id ?? null;
}

export function matchReport(log: MatchLog, whatif: Cue, cards: readonly DecisionCard[],
  leadId: string | null): MatchReport | null {
  if (!log.roster) return null;
  // Live, a goal message can arrive twice: one per seq.
  const seqs = new Set<number>();
  const goals = log.events
    .filter(({ item }) => item.type === "goal" && !seqs.has(item.seq) && seqs.add(item.seq))
    .map(({ item }) => ({ team: item.team, player_id: item.player_id, label: formatMinute(item.period, item.t_ms) }));
  const leadCard = cards.find((c) => c.payload.decision_id === whatIfLead(whatif, cards, leadId));
  return {
    home: log.roster.home,
    away: log.roster.away,
    score: scoreAt(log, log.duration),
    goals,
    lead: leadCard
      ? { decision_id: leadCard.payload.decision_id, label: formatMinute(leadCard.period, leadCard.payload.t_ms) }
      : null,
  };
}

/** The review line without its own leading minute ("91': ..."), which a row label or the report already
 *  gives; `standalone` capitalises what is left, for a line shown on its own. */
export function stripMinute(line: string, standalone = false): string {
  const rest = line.replace(/^\d+(\+\d+)?':\s*/, "");
  return standalone && rest !== line ? rest.charAt(0).toUpperCase() + rest.slice(1) : rest;
}

/** The report as sentences in the viewer's language and mode. */
export function reportLines(report: MatchReport, roster: Roster | null, locale: Locale, mode: Mode, t: Translate,
  cards: readonly DecisionCard[] = []): string[] {
  const club = (team: TeamCode) => roster?.teams[team]?.name ?? team;
  const lines = [t("reportResult", {
    home: club(report.home), homeGoals: report.score[report.home] ?? 0,
    away: club(report.away), awayGoals: report.score[report.away] ?? 0,
  })];
  for (const team of [report.home, report.away]) {
    const scored = report.goals.filter((g) => g.team === team);
    // A dropped goal message would list fewer scorers than the score says: leave the list out then.
    if (!scored.length || scored.length !== report.score[team]) continue;
    const list = scored.map((g) => (g.player_id ? `${playerName(roster, g.player_id)} ${g.label}` : g.label)).join(", ");
    lines.push(t("reportGoals", { club: club(team), list }));
  }
  if (report.lead) {
    const card = cards.find((c) => c.payload.decision_id === report.lead!.decision_id);
    const line = card?.review?.recap[locale]?.[mode] ?? card?.review?.recap.en?.[mode];
    if (line) lines.push(t("reportDecision", { minute: report.lead.label, line: withNames(stripMinute(line), roster) }));
  }
  return lines;
}
