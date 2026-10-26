// Broadcast cue sheet: every graphic the broadcast stage shows, as a timed cue on the feed's
// pos axis. Built from the match log alone, so the same function serves replay, live and the
// exported JSON. Cue data carries ids and numbers as given; the stage formats them.
// Runtime imports carry the .ts extension so Node's test runner can load this file without
// a bundler; clock.ts imports nothing.

import { callPos } from "./calls.ts";
import { formatMinute, toPos } from "./clock.ts";
import type { DecisionCard, MatchEvent, TeamCode } from "./contracts";
import type { MatchLog, Timed } from "./datasource";

export type CueKind = "decision" | "fading" | "manager_call" | "goal" | "focus_event" | "whatif" | "sprint" | "stats";

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
export const SPRINT_MS = 6_000;
export const STATS_MS = 12_000;
/** A sprint this long (about the longest tenth) gets a tag; the focus player's always do. */
export const SPRINT_TAG_M = 30;
/** Stat graphics: these minutes of each half, plus half-time. */
const STATS_AT: readonly [1 | 2, number][] = [[1, 15], [1, 30], [2, 60], [2, 75], [2, 90]];

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
  cues.push(...sprintCues(log.events, focus));
  cues.push(...statsCues(log, focus, at));
  const whatif = whatIfCue(log);
  if (whatif) cues.push(whatif);

  return cues.sort((a, b) => a.in_pos - b.in_pos || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

export function activeCues(cues: readonly Cue[], pos: number): Cue[] {
  return cues.filter((c) => c.in_pos <= pos && pos < c.out_pos);
}

/** The score at `pos`: the latest snapshot's score as given, plus goals after it (a snapshot
 *  corrects a goal message that was dropped or sent twice). Without snapshots, goals counted. */
export function scoreAt(log: MatchLog, pos: number): Record<TeamCode, number> {
  const teams = log.roster ? [log.roster.home, log.roster.away] : [];
  let base: Record<TeamCode, number> = Object.fromEntries(teams.map((t) => [t, 0]));
  let from = -Infinity;
  for (const s of log.snapshots) {
    if (s.pos > pos) break;
    base = { ...base, ...s.item.score };
    from = s.pos;
  }
  const out = { ...base };
  for (const { pos: at, item } of log.events) {
    if (at > pos) break;
    if (item.type === "goal" && at > from) out[item.team] = (out[item.team] ?? 0) + 1;
  }
  return out;
}

/**
 * The cues to draw at `pos`: the active ones, plus any that started within the last
 * `minWallMs` of wall time, so a graphic stays readable at 20x. `firstSeen` (cue id ->
 * wall ms) is the caller's memory between frames; going back before a cue forgets it.
 */
export function holdCues(cues: readonly Cue[], pos: number, firstSeen: Map<string, number>, now: number,
  minWallMs: number, maxLagMs = Infinity): Cue[] {
  const out: Cue[] = [];
  for (const c of cues) {
    if (pos < c.in_pos) {
      firstSeen.delete(c.id);
      continue;
    }
    const active = pos < c.out_pos;
    if (active && !firstSeen.has(c.id)) firstSeen.set(c.id, now);
    const seen = firstSeen.get(c.id);
    // A seek far past the cue ends the hold: the hold is for fast play, not for a jump to another minute.
    const held = seen !== undefined && now - seen < minWallMs && pos - c.out_pos <= maxLagMs;
    if (active || held) out.push(c);
  }
  return out;
}

/** Wall time until the first held cue (ended in match time, kept by `holdCues`) expires, or null if none is held.
 *  A paused page renders nothing on its own, so the caller re-renders then. */
export function holdExpiresInMs(shown: readonly Cue[], pos: number, firstSeen: Map<string, number>, now: number,
  minWallMs: number): number | null {
  let soonest: number | null = null;
  for (const c of shown) {
    const seen = firstSeen.get(c.id);
    if (pos < c.out_pos || seen === undefined) continue;
    const left = Math.max(0, minWallMs - (now - seen));
    if (soonest === null || left < soonest) soonest = left;
  }
  return soonest;
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

  // A manager_sub card is raised by the change itself: that change is not a call on it.
  if (payload.trigger === "manager_sub") return out;
  const action = payload.manager_action;
  if (action) {
    const actedAt = at(action.period, action.t_ms);
    const shownAt = callPos(actedAt, cardPos, closed ? closedPos : null) ?? cardPos;
    out.push({
      id: `manager_call:${id}`, kind: "manager_call", in_pos: shownAt, out_pos: shownAt + MANAGER_CALL_MS,
      data: {
        decision_id: id, team: payload.team, subs: action.subs, no_change: action.subs.length === 0,
        option_id: action.option_id,
        matched: action.option_id === payload.recommendation.option_id,
        // a call settled before the card opened is not "minutes after" it
        minutes_after: actedAt > cardPos ? Math.round((actedAt - cardPos) / MIN_MS) : null,
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
      data: { decision_id: id, team: payload.team, subs, no_change: false, option_id: null, matched: null,
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

function sprintCues(events: readonly Timed<MatchEvent>[], focus: string | null): Cue[] {
  return events
    .filter((e) => e.item.type === "sprint" && ((e.item.dist_m ?? 0) >= SPRINT_TAG_M || e.item.player_id === focus))
    .map((e) => ({
      id: `sprint:${e.item.seq}`, kind: "sprint" as const, in_pos: e.pos, out_pos: e.pos + SPRINT_MS,
      data: { player_id: e.item.player_id, team: e.item.team, dist_m: e.item.dist_m ?? null },
    }));
}

export interface PassStats {
  passes: number;
  /** Mean length in metres, one decimal; 0 with no passes. */
  avg_m: number;
  longest_m: number;
  /** Passes that end nearer the opponents' goal than they started. */
  forward: number;
}

const round1 = (v: number) => Math.round(v * 10) / 10;

/** Passes up to `upto` that `keep` selects, measured from their start and end points.
 *  Every simulated pass is complete, so there is no accuracy to report. */
export function passStats(log: MatchLog, upto: number, keep: (e: MatchEvent) => boolean): PassStats {
  const home = log.roster?.home;
  let passes = 0;
  let total = 0;
  let longest = 0;
  let forward = 0;
  for (const { pos, item } of log.events) {
    if (pos > upto) break;
    if (item.type !== "pass" || item.x == null || item.end_x == null || !keep(item)) continue;
    const length = Math.hypot(item.end_x - item.x, (item.end_y ?? 0) - (item.y ?? 0));
    passes += 1;
    total += length;
    longest = Math.max(longest, length);
    // The home side attacks towards x = 105 in the first half (contract: docs/data-contracts.md).
    const towards105 = (item.team === home) === (item.period === 1);
    if ((item.end_x - item.x) * (towards105 ? 1 : -1) > 0) forward += 1;
  }
  return { passes, avg_m: passes ? round1(total / passes) : 0, longest_m: round1(longest), forward };
}

/** Sprints and high-speed running up to `upto`, from the running events' own distances. */
function running(log: MatchLog, upto: number, keep: (e: MatchEvent) => boolean) {
  let sprints = 0;
  let longest = 0;
  let fast = 0;
  for (const { pos, item } of log.events) {
    if (pos > upto) break;
    if ((item.type !== "sprint" && item.type !== "hsr") || !keep(item)) continue;
    const d = item.dist_m ?? 0;
    fast += d;
    if (item.type === "sprint") {
      sprints += 1;
      longest = Math.max(longest, d);
    }
  }
  return { sprints, longest_sprint_m: round1(longest), fast_m: Math.round(fast) };
}

function statsCues(log: MatchLog, focus: string | null, at: (period: 1 | 2, tMs: number) => number): Cue[] {
  const moments: { id: string; pos: number }[] = [
    ...STATS_AT.filter(([p]) => p === 1).map(([p, m]) => ({ id: `stats:${p}-${m}`, pos: at(p, m * MIN_MS) })),
    { id: "stats:ht", pos: log.firstHalfEnd },
    ...STATS_AT.filter(([p]) => p === 2).map(([p, m]) => ({ id: `stats:${p}-${m}`, pos: at(p, m * MIN_MS) })),
  ];
  const teams = log.roster ? [log.roster.home, log.roster.away] : [];
  return moments
    .filter((m) => m.pos <= log.duration)
    .map(({ id, pos }) => {
      const data: Record<string, unknown> = focus
        ? {
            scope: "player", player_id: focus,
            passes: passStats(log, pos, (e) => e.player_id === focus),
            running: running(log, pos, (e) => e.player_id === focus),
          }
        : {
            scope: "teams",
            teams: Object.fromEntries(teams.map((team) => [team, {
              passes: passStats(log, pos, (e) => e.team === team),
              running: running(log, pos, (e) => e.team === team),
            }])),
          };
      return { id, kind: "stats" as const, in_pos: pos, out_pos: pos + STATS_MS, data };
    });
}

function whatIfCue(log: MatchLog): Cue | null {
  const reviewed = log.cards.filter((c) => c.item.review);
  if (!reviewed.length) return null;
  const rows = reviewed.map(({ item }) => ({
    decision_id: item.payload.decision_id,
    minute: Math.floor(item.payload.t_ms / MIN_MS),
    label: formatMinute(item.period, item.payload.t_ms),
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

/** The manager's call to draw among the shown cues: two cards can close on one change of his (60' and 72' both
 *  priced taking Varga off, done at 79'), so prefer the call on a card the viewer voted on, which carries the
 *  viewer's own call beside his; otherwise the latest, as for every other kind. */
export function pickCall(shown: readonly Cue[], votes: Readonly<Record<string, { option?: string | null }>>): Cue | undefined {
  const calls = shown.filter((c) => c.kind === "manager_call");
  return [...calls].reverse().find((c) => votes[String(c.data.decision_id)]?.option) ?? calls[calls.length - 1];
}
