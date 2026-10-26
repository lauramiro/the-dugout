import { test } from "node:test";
import assert from "node:assert/strict";
import { activeCues, buildCues, cueSheet, holdCues, holdExpiresInMs, passStats, pickCall, scoreAt, type Cue } from "./cues.ts";
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

test("holdCues drops a held cue when the playhead jumps far past it", () => {
  const cue: Cue = { id: "d", kind: "decision", in_pos: 100, out_pos: 30_000, data: {} };
  const seen = new Map<string, number>();
  holdCues([cue], 1_000, seen, 1000, 4000, 120_000);
  assert.deepEqual(holdCues([cue], 100_000, seen, 2000, 4000, 120_000).map((c) => c.id), ["d"],
    "fast play: still inside the hold");
  assert.deepEqual(holdCues([cue], 2_000_000, seen, 2500, 4000, 120_000), [],
    "a seek to full time does not leave the card on screen");
});

test("holdCues keeps a cue lagging just under the limit and drops one just over", () => {
  const cue: Cue = { id: "d", kind: "decision", in_pos: 0, out_pos: 10_000, data: {} };
  const seen = new Map<string, number>([["d", 1000]]);
  assert.equal(holdCues([cue], 10_000 + 80_000, seen, 2000, 4000, 120_000).length, 1);
  assert.equal(holdCues([cue], 10_000 + 121_000, seen, 2000, 4000, 120_000).length, 0);
});

test("holdExpiresInMs is the wall time until the first held cue goes, so a paused page can re-render then", () => {
  const ended: Cue = { id: "g", kind: "goal", in_pos: 0, out_pos: 100, data: {} };
  const later: Cue = { id: "s", kind: "stats", in_pos: 0, out_pos: 150, data: {} };
  const active: Cue = { id: "d", kind: "decision", in_pos: 0, out_pos: 10_000, data: {} };
  const seen = new Map<string, number>([["g", 1000], ["s", 2500], ["d", 1000]]);
  assert.equal(holdExpiresInMs([ended, later, active], 200, seen, 3000, 4000), 2000);
  assert.equal(holdExpiresInMs([active], 200, seen, 3000, 4000), null, "nothing held, nothing to wait for");
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

// --- sprint tags and stat graphics ---

function pass(seq: number, period: 1 | 2, tMs: number, team: string, player: string, x: number, endX: number) {
  return event(seq, period, tMs, "pass", team, player, { x, y: 30, end_x: endX, end_y: 30, outcome: "complete" });
}

test("long sprints get a sprint cue; the focus player's sprints always do", () => {
  const sprints = [event(1, 1, 60_000, "sprint", "RFC", "RFC-07", { dist_m: 34.5 }),
    event(2, 1, 70_000, "sprint", "RFC", "RFC-03", { dist_m: 12.0 }),
    event(3, 1, 80_000, "sprint", "CAS", "CAS-09", { dist_m: 29.9 })];
  const plain = ofKind(buildCues(log([], sprints), null), "sprint");
  assert.deepEqual(plain.map((c) => c.data.player_id), ["RFC-07"]);
  assert.equal(plain[0].data.dist_m, 34.5);
  assert.equal(plain[0].out_pos, plain[0].in_pos + 6_000);
  const focused = ofKind(buildCues(log([], sprints), "RFC-03"), "sprint");
  assert.deepEqual(focused.map((c) => c.data.player_id), ["RFC-07", "RFC-03"]);
});

test("passStats measures passes from their start and end points", () => {
  // RFC is home: attacks towards x = 105 in the first half, towards 0 in the second.
  const events = [pass(1, 1, 60_000, "RFC", "RFC-04", 20, 50), pass(2, 1, 70_000, "RFC", "RFC-04", 50, 40),
    pass(3, 2, 2_800_000, "RFC", "RFC-04", 80, 40), pass(4, 1, 80_000, "CAS", "CAS-10", 64, 30.2)];
  const l = log([], events);
  const rfc4 = passStats(l, pos(2, 3_000_000), (e) => e.player_id === "RFC-04");
  assert.equal(rfc4.passes, 3);
  assert.equal(rfc4.longest_m, 40);
  assert.equal(rfc4.avg_m, 26.7);
  assert.equal(rfc4.forward, 2, "30 m up in the first half and 40 m down in the second are forward");
  const cas = passStats(l, pos(2, 3_000_000), (e) => e.team === "CAS");
  assert.equal(cas.forward, 1, "the away side attacks towards x = 0 in the first half");
  assert.equal(passStats(l, 65_000, () => true).passes, 1, "only passes up to pos");
});

test("stat cues every 15 minutes: the focus player's, or both teams'", () => {
  const events = [pass(1, 1, 60_000, "RFC", "RFC-04", 20, 50),
    event(2, 1, 61_000, "sprint", "RFC", "RFC-04", { dist_m: 31 }), event(3, 1, 62_000, "hsr", "RFC", "RFC-04", { dist_m: 12 })];
  const teams = ofKind(buildCues(log([], events), null), "stats");
  assert.deepEqual(teams.map((c) => c.id), ["stats:1-15", "stats:1-30", "stats:ht", "stats:2-60", "stats:2-75", "stats:2-90"]);
  assert.equal(teams[0].in_pos, 900_000);
  assert.equal(teams[2].in_pos, FIRST_HALF_END);
  assert.equal(teams[0].out_pos, teams[0].in_pos + 12_000);
  assert.equal(teams[0].data.scope, "teams");
  const rfc = (teams[0].data.teams as Record<string, { passes: { passes: number } }>).RFC;
  assert.equal(rfc.passes.passes, 1);
  const player = ofKind(buildCues(log([], events), "RFC-04"), "stats")[0];
  assert.equal(player.data.scope, "player");
  assert.equal(player.data.player_id, "RFC-04");
  assert.deepEqual(player.data.running, { sprints: 1, longest_sprint_m: 31, fast_m: 43 });
});

test("passStats skips a pass sent without its coordinates", () => {
  const bare = event(1, 1, 60_000, "pass", "RFC", "RFC-04");
  delete (bare.item as Partial<MatchEvent>).x;
  delete (bare.item as Partial<MatchEvent>).end_x;
  assert.equal(passStats(log([], [bare]), 100_000, () => true).passes, 0);
});

test("what-if rows label added time the way the lower third does", () => {
  const l = log([card({ id: "a", period: 1, t_ms: 2_820_000, review: review(0.031) }), card({ id: "b", t_ms: 3_600_000, review: review(0.004) })]);
  const rows = ofKind(buildCues(l, null), "whatif")[0].data.rows as { decision_id: string; label: string }[];
  assert.deepEqual(rows.map((r) => r.label), ["45+3'", "60'"]);
});

test("pickCall prefers the manager's call on a card the viewer voted on when two calls share one change", () => {
  const call = (id: string): Cue => ({ id: `manager_call:${id}`, kind: "manager_call", in_pos: 0, out_pos: 10, data: { decision_id: id } });
  const shown = [call("rfc-60-20"), call("rfc-72-40")];
  assert.equal(pickCall(shown, { "rfc-60-20": { option: "sub_like_for_like" } })?.id, "manager_call:rfc-60-20");
  assert.equal(pickCall(shown, {})?.id, "manager_call:rfc-72-40", "no vote: the latest, as before");
  assert.equal(pickCall([], {}), undefined);
  assert.equal(pickCall(shown, { "rfc-60-20": { option: null } })?.id, "manager_call:rfc-72-40", "a timed-out vote is no vote");
  assert.equal(pickCall(shown, { "rfc-60-20": { option: "a" }, "rfc-72-40": { option: "b" } })?.id, "manager_call:rfc-72-40");
});

test("no manager call graphic for a card whose call was known before it opened", () => {
  // A goal card queued behind another opens at 91', but the next goal (89') already settled it.
  const c = card({
    id: "rfc-91-10", t_ms: 5_460_000, trigger: "goal_after_55",
    manager_action: { period: 2, t_ms: 5_340_000, subs: [], option_id: "no_change" },
  });
  assert.equal(ofKind(buildCues(log([c]), null), "manager_call").length, 0);
});
