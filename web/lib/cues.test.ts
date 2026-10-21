import { test } from "node:test";
import assert from "node:assert/strict";
import { activeCues, buildCues, cueSheet, holdCues, scoreAt, type Cue } from "./cues.ts";
import type { DecisionCard, MatchEvent, Review } from "./contracts.ts";
import type { MatchLog, Timed } from "./datasource.ts";

const FIRST_HALF_END = 2_870_000;
const HALF_MS = 2_700_000;
const pos = (period: 1 | 2, tMs: number) => (period === 1 ? tMs : FIRST_HALF_END + 500 + (tMs - HALF_MS));

function card(over: {
  id: string;
  period?: 1 | 2;
  t_ms: number;
  team?: string;
  trigger?: DecisionCard["payload"]["trigger"];
  closed?: DecisionCard["closed"];
  manager_action?: DecisionCard["payload"]["manager_action"];
  review?: Review;
}): Timed<DecisionCard> {
  const period = over.period ?? 2;
  const item: DecisionCard = {
    period,
    payload: {
      decision_id: over.id,
      t_ms: over.t_ms,
      team: over.team ?? "RFC",
      trigger: over.trigger ?? "condition_drop",
      options: [],
      recommendation: { option_id: "sub_like_for_like", strength: "strong" },
      evidence: [{ type: "condition", player_id: "RFC-03", value: 0.689, trend_per_min: -0.003 }],
      manager_action: over.manager_action ?? null,
    },
    narration: {},
    closed: over.closed,
    review: over.review,
  };
  return { pos: pos(period, over.t_ms), item };
}

function event(seq: number, period: 1 | 2, tMs: number, type: MatchEvent["type"], team: string, player: string,
  extra: Partial<MatchEvent> = {}): Timed<MatchEvent> {
  const item: MatchEvent = {
    match_id: "rfc-cas-0073", seq, t_ms: tMs, period, type, team, player_id: player, channel: null,
    x: null, y: null, end_x: null, end_y: null, outcome: null, xg: null, ...extra,
  };
  return { pos: pos(period, tMs), item };
}

function log(cards: Timed<DecisionCard>[] = [], events: Timed<MatchEvent>[] = []): MatchLog {
  return {
    roster: {
      home: "RFC", away: "CAS", teams: { RFC: { name: "Riverside" }, CAS: { name: "Castleton" } },
      players: {
        "RFC-03": { team: "RFC", name: "Leon Varga", role: "FB", side: "left" },
        "RFC-15": { team: "RFC", name: "Sub", role: "FB", side: "left" },
      },
    },
    firstHalfEnd: FIRST_HALF_END,
    duration: pos(2, 5_800_000),
    events, snapshots: [], cards, winprob: [],
  };
}

const ofKind = (cues: Cue[], kind: Cue["kind"]) => cues.filter((c) => c.kind === kind);
const review = (gap: number | null): Review => ({
  model: { id: "sub_like_for_like", win: 0.78, xpts: 2.5 }, manager: { id: "manager_later", minute: 79, win: 0.75, xpts: 2.4 },
  gap_win: gap, gap_xpts: null, recap: {}, recap_source: "template",
});

test("decision cue runs from the card to its closing", () => {
  const c = card({ id: "rfc-60-01", t_ms: 3_600_000, closed: { period: 2, t_ms: 3_780_000, reason: "timeout" } });
  const [cue] = ofKind(buildCues(log([c]), null), "decision");
  assert.equal(cue.id, "decision:rfc-60-01");
  assert.equal(cue.in_pos, pos(2, 3_600_000));
  assert.equal(cue.out_pos, pos(2, 3_780_000));
});

test("an open card's decision cue ends after DECISION_MAX_MS", () => {
  const c = card({ id: "rfc-60-01", t_ms: 3_600_000 });
  const [cue] = ofKind(buildCues(log([c]), null), "decision");
  assert.equal(cue.out_pos, cue.in_pos + 180_000);
});

test("a condition_drop card adds a fading cue with the evidence player", () => {
  const cues = buildCues(log([card({ id: "a", t_ms: 3_600_000 }), card({ id: "b", t_ms: 4_300_000, trigger: "goal_after_55" })]), null);
  const fading = ofKind(cues, "fading");
  assert.equal(fading.length, 1);
  assert.equal(fading[0].data.player_id, "RFC-03");
  assert.equal(fading[0].data.condition, 0.689);
  assert.equal(fading[0].out_pos, fading[0].in_pos + 30_000);
});

test("manager call from manager_action says whether it matched", () => {
  const c = card({
    id: "rfc-60-01", t_ms: 3_600_000,
    manager_action: { period: 2, t_ms: 4_740_000, subs: [{ off: "RFC-03", on: "RFC-15" }], option_id: "sub_like_for_like" },
  });
  const [cue] = ofKind(buildCues(log([c]), null), "manager_call");
  assert.equal(cue.data.matched, true);
  assert.equal(cue.data.minutes_after, 19);
  assert.equal(cue.in_pos, pos(2, 4_740_000));
  assert.equal(cue.out_pos, cue.in_pos + 25_000);
});

test("live manager call comes from the closing and the sub events", () => {
  const closed = { period: 2 as const, t_ms: 4_740_000, reason: "change" as const };
  const sub = event(900, 2, 4_744_000, "sub", "RFC", "RFC-03", { player_in_id: "RFC-15" });
  const [cue] = ofKind(buildCues(log([card({ id: "x", t_ms: 4_300_000, closed })], [sub]), null), "manager_call");
  assert.deepEqual(cue.data.subs, [{ off: "RFC-03", on: "RFC-15" }]);
  assert.equal(cue.data.matched, null);
  assert.equal(cue.data.option_id, null);
  const [empty] = ofKind(buildCues(log([card({ id: "x", t_ms: 4_300_000, closed })]), null), "manager_call");
  assert.deepEqual(empty.data.subs, []);
});

test("goal cues carry the score after the goal", () => {
  const goals = [event(1, 1, 600_000, "goal", "RFC", "RFC-09"), event(2, 2, 3_000_000, "goal", "CAS", "CAS-09")];
  const cues = ofKind(buildCues(log([], goals), null), "goal");
  assert.equal(cues.length, 2);
  assert.deepEqual(cues[1].data.score, { RFC: 1, CAS: 1 });
  assert.equal(cues[1].out_pos, cues[1].in_pos + 20_000);
});

test("focus cues only for the focused player", () => {
  const sub = event(900, 2, 4_744_000, "sub", "RFC", "RFC-03", { player_in_id: "RFC-15" });
  const shot = event(901, 2, 4_800_000, "shot", "CAS", "CAS-09");
  assert.equal(ofKind(buildCues(log([], [sub, shot]), "RFC-15"), "focus_event").length, 1);
  assert.equal(ofKind(buildCues(log([], [sub, shot]), "RFC-99"), "focus_event").length, 0);
  assert.equal(ofKind(buildCues(log([], [sub, shot]), null), "focus_event").length, 0);
});

test("what-if cue at full time leads with the largest gap", () => {
  const l = log([card({ id: "a", t_ms: 3_600_000, review: review(0.031) }), card({ id: "b", t_ms: 4_300_000, review: review(0.004) })]);
  const [cue] = ofKind(buildCues(l, null), "whatif");
  assert.equal(cue.data.lead, "a");
  assert.equal(cue.in_pos, l.duration);
  assert.equal((cue.data.rows as unknown[]).length, 2);
  assert.equal(ofKind(buildCues(log([card({ id: "a", t_ms: 3_600_000 })]), null), "whatif").length, 0);
});

test("cues sort by pos across half-time", () => {
  const late = card({ id: "late-first", period: 1, t_ms: 2_820_000 });
  const early = card({ id: "early-second", period: 2, t_ms: 2_760_000 });
  const ids = ofKind(buildCues(log([early, late]), null), "decision").map((c) => c.id);
  assert.deepEqual(ids, ["decision:late-first", "decision:early-second"]);
});

test("activeCues is half-open", () => {
  const cue: Cue = { id: "x", kind: "goal", in_pos: 10, out_pos: 20, data: {} };
  assert.equal(activeCues([cue], 10).length, 1);
  assert.equal(activeCues([cue], 19).length, 1);
  assert.equal(activeCues([cue], 20).length, 0);
});

test("cueSheet names the match from the first event", () => {
  const sheet = cueSheet(log([], [event(1, 1, 600_000, "goal", "RFC", "RFC-09")]), null, "replay");
  assert.equal(sheet.match_id, "rfc-cas-0073");
  assert.equal(sheet.source, "replay");
  assert.equal(cueSheet(log(), null, "live").match_id, null);
});

test("holdCues keeps a cue on screen for a minimum wall time", () => {
  const cue: Cue = { id: "g", kind: "goal", in_pos: 100, out_pos: 200, data: {} };
  const seen = new Map<string, number>();
  assert.deepEqual(holdCues([cue], 150, seen, 1000, 4000).map((c) => c.id), ["g"]);
  assert.deepEqual(holdCues([cue], 900, seen, 3000, 4000).map((c) => c.id), ["g"], "ended in match time, held on wall time");
  assert.deepEqual(holdCues([cue], 900, seen, 5001, 4000), [], "dropped once the minimum has passed");
});

test("holdCues forgets a cue when the playhead goes back before it", () => {
  const cue: Cue = { id: "g", kind: "goal", in_pos: 100, out_pos: 200, data: {} };
  const seen = new Map<string, number>();
  holdCues([cue], 150, seen, 1000, 4000);
  assert.deepEqual(holdCues([cue], 50, seen, 1500, 4000), []);
  assert.equal(seen.has("g"), false);
});

test("a card raised by the manager's own substitution gets no manager-call cue", () => {
  const action = { period: 2 as const, t_ms: 4_740_000, subs: [{ off: "RFC-03", on: "RFC-15" }], option_id: null };
  const raised = card({ id: "rfc-79-00", t_ms: 4_740_000, trigger: "manager_sub", manager_action: action });
  const fading = card({ id: "rfc-60-20", t_ms: 3_620_000,
    manager_action: { ...action, option_id: "sub_like_for_like" } });
  const calls = ofKind(buildCues(log([fading, raised]), null), "manager_call");
  assert.deepEqual(calls.map((c) => c.id), ["manager_call:rfc-60-20"]);
});

test("a manager action with no subs is a settled no-change call", () => {
  const settled = card({ id: "cas-75-40", t_ms: 4_500_000, team: "CAS",
    manager_action: { period: 2, t_ms: 4_900_000, subs: [], option_id: "no_change" } });
  const [cue] = ofKind(buildCues(log([settled]), null), "manager_call");
  assert.equal(cue.data.no_change, true);
  const closed = { period: 2 as const, t_ms: 4_740_000, reason: "change" as const };
  const [live] = ofKind(buildCues(log([card({ id: "x", t_ms: 4_300_000, closed })]), null), "manager_call");
  assert.equal(live.data.no_change, false, "live: a change happened, the subs just did not arrive");
});

test("scoreAt starts from the latest snapshot's score and adds only later goals", () => {
  const goals = [event(1, 1, 600_000, "goal", "RFC", "RFC-09"), event(2, 2, 3_000_000, "goal", "CAS", "CAS-09"),
    event(2, 2, 3_000_000, "goal", "CAS", "CAS-09")];
  const l = log([], goals);
  const snap = { pos: pos(2, 3_010_000), item: { t_ms: 3_010_000, score: { RFC: 1, CAS: 1 } } };
  l.snapshots = [snap as unknown as MatchLog["snapshots"][number]];
  assert.deepEqual(scoreAt(l, pos(2, 3_020_000)), { RFC: 1, CAS: 1 }, "a goal sent twice does not count twice");
  assert.deepEqual(scoreAt({ ...l, snapshots: [] }, pos(2, 3_020_000)), { RFC: 1, CAS: 2 }, "without snapshots, goals are counted");
  const late = event(3, 2, 3_015_000, "goal", "RFC", "RFC-10");
  assert.deepEqual(scoreAt({ ...l, events: [...goals, late] }, pos(2, 3_020_000)), { RFC: 2, CAS: 1 });
});
