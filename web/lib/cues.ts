// Broadcast cue sheet: every graphic the broadcast stage shows, as a timed cue on the feed's
// pos axis. Built from the match log alone, so the same function serves replay, live and the
// exported JSON. Cue data carries ids and numbers as given; the stage formats them.
// Runtime imports carry the .ts extension so Node's test runner can load this file without
// a bundler; clock.ts imports nothing.

import { toPos } from "./clock.ts";
import type { DecisionCard, MatchEvent, TeamCode } from "./contracts";
import type { MatchLog, Timed } from "./datasource";

export type CueKind = "decision" | "fading" | "manager_call" | "goal" | "focus_event" | "whatif";

export interface Cue {
  id: string;
  kind: CueKind;
  in_pos: number;
  out_pos: number;
  data: Record<string, unknown>;
}

export const DECISION_MAX_MS = 180_000;
export const FADING_MS = 30_000;
export const MANAGER_CALL_MS = 25_000;
export const GOAL_MS = 20_000;
export const FOCUS_EVENT_MS = 15_000;
export const WHATIF_MS = 120_000;

const MIN_MS = 60_000;
const LIVE_SUB_WINDOW_MS = 10_000;
const FOCUS_TYPES: readonly MatchEvent["type"][] = ["goal", "shot", "sub", "foul"];

export function buildCues(log: MatchLog, focus: string | null): Cue[] {
  const at = (period: 1 | 2, tMs: number) => toPos(period, tMs, log.firstHalfEnd);
  const cues: Cue[] = [];

  for (const { pos, item } of log.cards) {
    cues.push(...cardCues(pos, item, log.events, at));
  }
  cues.push(...goalCues(log, at));
  if (focus) cues.push(...focusCues(log.events, focus));
  const whatif = whatIfCue(log);
  if (whatif) cues.push(whatif);

  return cues.sort((a, b) => a.in_pos - b.in_pos || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

export function activeCues(cues: readonly Cue[], pos: number): Cue[] {
  return cues.filter((c) => c.in_pos <= pos && pos < c.out_pos);
}

/**
 * The cues to draw at `pos`: the active ones, plus any that started within the last
 * `minWallMs` of wall time, so a graphic stays readable at 20x. `firstSeen` (cue id ->
 * wall ms) is the caller's memory between frames; going back before a cue forgets it.
 */
export function holdCues(cues: readonly Cue[], pos: number, firstSeen: Map<string, number>, now: number,
  minWallMs: number): Cue[] {
  const out: Cue[] = [];
  for (const c of cues) {
    if (pos < c.in_pos) {
      firstSeen.delete(c.id);
      continue;
    }
    const active = pos < c.out_pos;
    if (active && !firstSeen.has(c.id)) firstSeen.set(c.id, now);
    const seen = firstSeen.get(c.id);
    if (active || (seen !== undefined && now - seen < minWallMs)) out.push(c);
  }
  return out;
}

export function cueSheet(log: MatchLog, focus: string | null, source: "replay" | "live") {
  return { match_id: log.events[0]?.item.match_id ?? null, source, cues: buildCues(log, focus) };
}

function cardCues(cardPos: number, card: DecisionCard, events: readonly Timed<MatchEvent>[],
  at: (period: 1 | 2, tMs: number) => number): Cue[] {
  const { payload, closed } = card;
  const id = payload.decision_id;
  const out: Cue[] = [];

  const closedPos = closed ? at(closed.period, closed.t_ms) : Infinity;
  out.push({
    id: `decision:${id}`, kind: "decision", in_pos: cardPos,
    out_pos: Math.min(closedPos, cardPos + DECISION_MAX_MS), data: { decision_id: id },
  });

  if (payload.trigger === "condition_drop") {
    const condition = payload.evidence.find((e) => e.type === "condition");
    if (condition && condition.type === "condition") {
      out.push({
        id: `fading:${id}`, kind: "fading", in_pos: cardPos, out_pos: cardPos + FADING_MS,
        data: { decision_id: id, player_id: condition.player_id, condition: condition.value },
      });
    }
  }

  const action = payload.manager_action;
  if (action) {
    const callPos = Math.max(at(action.period, action.t_ms), cardPos);
    out.push({
      id: `manager_call:${id}`, kind: "manager_call", in_pos: callPos, out_pos: callPos + MANAGER_CALL_MS,
      data: {
        decision_id: id, team: payload.team, subs: action.subs, option_id: action.option_id,
        matched: action.option_id === payload.recommendation.option_id,
        minutes_after: Math.round((callPos - cardPos) / MIN_MS),
      },
    });
  } else if (closed?.reason === "change") {
    // Live: no manager_action, so the change is read from the team's sub events at the closing.
    const subs = events
      .filter((e) => e.item.type === "sub" && e.item.team === payload.team
        && Math.abs(e.pos - closedPos) <= LIVE_SUB_WINDOW_MS)
      .map((e) => ({ off: e.item.player_id, on: e.item.player_in_id ?? null }));
    out.push({
      id: `manager_call:${id}`, kind: "manager_call", in_pos: closedPos, out_pos: closedPos + MANAGER_CALL_MS,
      data: { decision_id: id, team: payload.team, subs, option_id: null, matched: null,
        minutes_after: Math.round((closedPos - cardPos) / MIN_MS) },
    });
  }
  return out;
}

function goalCues(log: MatchLog, at: (period: 1 | 2, tMs: number) => number): Cue[] {
  const score: Record<TeamCode, number> = {};
  if (log.roster) {
    score[log.roster.home] = 0;
    score[log.roster.away] = 0;
  }
  const out: Cue[] = [];
  for (const { item } of log.events) {
    if (item.type !== "goal") continue;
    score[item.team] = (score[item.team] ?? 0) + 1;
    const pos = at(item.period, item.t_ms);
    out.push({
      id: `goal:${item.seq}`, kind: "goal", in_pos: pos, out_pos: pos + GOAL_MS,
      data: { team: item.team, player_id: item.player_id, score: { ...score } },
    });
  }
  return out;
}

function focusCues(events: readonly Timed<MatchEvent>[], focus: string): Cue[] {
  return events
    .filter((e) => FOCUS_TYPES.includes(e.item.type) && (e.item.player_id === focus || e.item.player_in_id === focus))
    .map((e) => ({
      id: `focus_event:${e.item.seq}`, kind: "focus_event" as const, in_pos: e.pos, out_pos: e.pos + FOCUS_EVENT_MS,
      data: { type: e.item.type, player_id: e.item.player_id, player_in_id: e.item.player_in_id ?? null },
    }));
}

function whatIfCue(log: MatchLog): Cue | null {
  const reviewed = log.cards.filter((c) => c.item.review);
  if (!reviewed.length) return null;
  const rows = reviewed.map(({ item }) => ({
    decision_id: item.payload.decision_id,
    minute: Math.floor(item.payload.t_ms / MIN_MS),
    model: item.review!.model,
    manager: item.review!.manager,
    gap_win: item.review!.gap_win,
  }));
  let lead: string | null = null;
  let best = -Infinity;
  for (const row of rows) {
    if (row.gap_win !== null && row.gap_win > best) {
      best = row.gap_win;
      lead = row.decision_id;
    }
  }
  return { id: "whatif", kind: "whatif", in_pos: log.duration, out_pos: log.duration + WHATIF_MS, data: { rows, lead } };
}
