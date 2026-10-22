import { test } from "node:test";
import assert from "node:assert/strict";
import { buildStory, STORY_LEAD_MS } from "./story.ts";
import type { DecisionCard, MatchEvent } from "./contracts.ts";
import type { MatchLog, Timed } from "./datasource.ts";
import { demoLog, demoPos } from "./demoLog.testutil.ts";

const FIRST_HALF_END = 2_870_000;
const HALF_MS = 2_700_000;
const pos = (period: 1 | 2, tMs: number) => (period === 1 ? tMs : FIRST_HALF_END + 500 + (tMs - HALF_MS));

function card(id: string, period: 1 | 2, tMs: number, over: Partial<DecisionCard["payload"]> = {}): Timed<DecisionCard> {
  const item: DecisionCard = {
    period,
    payload: {
      decision_id: id, t_ms: tMs, team: "RFC", trigger: "condition_drop", options: [],
      recommendation: { option_id: "sub_like_for_like", strength: "strong" },
      evidence: [{ type: "condition", player_id: "RFC-03", value: 0.689, trend_per_min: -0.003 }],
      manager_action: { period: 2, t_ms: 4_740_000, subs: [{ off: "RFC-03", on: "RFC-15" }], option_id: "sub_like_for_like" },
      ...over,
    },
    narration: {},
  };
  return { pos: pos(period, tMs), item };
}

function goal(seq: number, tMs: number, team: string, channel: MatchEvent["channel"]): Timed<MatchEvent> {
  const item: MatchEvent = {
    match_id: "m", seq, t_ms: tMs, period: 2, type: "goal", team, player_id: `${team}-07`, channel,
    x: null, y: null, end_x: null, end_y: null, outcome: null, xg: null,
  };
  return { pos: pos(2, tMs), item };
}

function logWith(cards: Timed<DecisionCard>[], events: Timed<MatchEvent>[] = []): MatchLog {
  return {
    roster: {
      home: "RFC", away: "CAS", teams: { RFC: { name: "Riverside FC" }, CAS: { name: "Castleton Athletic" } },
      players: { "RFC-03": { team: "RFC", name: "Leon Varga", role: "FB", side: "left" } },
    },
    firstHalfEnd: FIRST_HALF_END,
    duration: pos(2, 5_800_000),
    events, snapshots: [], cards, winprob: [],
  };
}

test("buildStory: no condition card for the club means no story", () => {
  const goalCard = card("rfc-72-40", 2, 4_360_000, { trigger: "goal_after_55" });
  assert.equal(buildStory(logWith([goalCard]), { club: "RFC", phone: true }), null);
  assert.equal(buildStory(logWith([card("rfc-60-20", 2, 3_620_000)]), { club: "CAS", phone: true }), null);
});

test("buildStory: the demo match tells the 60' Varga story in eight steps", () => {
  const steps = buildStory(demoLog(), { club: "RFC", phone: true })!;
  assert.deepEqual(steps.map((s) => s.id),
    ["tv-open", "tv-decision", "tablet", "vote", "equaliser", "manager", "full-time", "end"]);
  assert.deepEqual(steps.map((s) => s.screen), ["tv", "tv", "tablet", "phone", "tv", "phone", "tv", "end"]);
  assert.equal(steps[1].caption.vars.player, "Leon Varga");
  assert.equal(steps[4].caption.key, "story_equaliser_flank"); // CAS-07 scored down the right; Varga plays left
  assert.equal(steps[5].caption.vars.minutes, "19");            // card 60:20, change 79:00
  assert.equal(steps[6].caption.vars.minute, "60'");
  assert.equal(steps[0].startPos, demoPos(2, 3_620_000) - STORY_LEAD_MS);
  assert.deepEqual(steps[0].wait, { kind: "play", untilPos: demoPos(2, 3_620_000) + 2_000, speed: 5 });
  assert.equal(steps[3].wait.kind, "vote");
  assert.equal(steps[6].startPos, demoLog().duration);
  assert.deepEqual(steps[7].wait, { kind: "stay" });
});

test("buildStory: without a phone the vote and the manager's call stay on TV", () => {
  const steps = buildStory(demoLog(), { club: "RFC", phone: false })!;
  assert.equal(steps.find((s) => s.id === "vote")!.screen, "tv");
  assert.equal(steps.find((s) => s.id === "manager")!.screen, "tv");
});

test("buildStory: no goal by the opponent after the card leaves out the equaliser step", () => {
  const early = goal(1, 3_000_000, "CAS", "right"); // before the card
  const own = goal(2, 4_000_000, "RFC", "left");    // the club's own goal
  const steps = buildStory(logWith([card("rfc-60-20", 2, 3_620_000)], [early, own]), { club: "RFC", phone: true })!;
  assert.equal(steps.some((s) => s.id === "equaliser"), false);
  assert.equal(steps.at(-1)!.id, "end");
});

test("buildStory: a manager who never acts leaves out the manager step", () => {
  const steps = buildStory(logWith([card("rfc-60-20", 2, 3_620_000, { manager_action: null })]), { club: "RFC", phone: true })!;
  assert.equal(steps.some((s) => s.id === "manager"), false);
  assert.deepEqual(steps.slice(-2).map((s) => s.id), ["full-time", "end"]);
});

test("buildStory: a goal on the other flank gets the plain equaliser caption", () => {
  const steps = buildStory(logWith([card("rfc-60-20", 2, 3_620_000)], [goal(1, 4_355_000, "CAS", "left")]),
    { club: "RFC", phone: true })!;
  const eq = steps.find((s) => s.id === "equaliser")!;
  assert.equal(eq.caption.key, "story_equaliser");
  assert.equal(eq.caption.vars.team, "Castleton Athletic");
  assert.equal(eq.startPos, pos(2, 4_355_000) - 8_000);
});

test("buildStory: the equaliser and the manager's change play at 1x, slow enough to read", () => {
  const steps = buildStory(demoLog(), { club: "RFC", phone: true })!;
  for (const id of ["equaliser", "manager"] as const) {
    const wait = steps.find((s) => s.id === id)!.wait;
    assert.equal(wait.kind === "play" && wait.speed, 1);
  }
});

test("buildStory: a card in the first two minutes opens the story at kick-off, not before it", () => {
  const steps = buildStory(logWith([card("rfc-1-00", 1, 60_000)]), { club: "RFC", phone: true })!;
  assert.equal(steps[0].startPos, 0);
});
