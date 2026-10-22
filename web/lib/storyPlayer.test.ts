import { test } from "node:test";
import assert from "node:assert/strict";
import { leaveUrl, storyReducer, INITIAL_STORY, type StoryState } from "./storyPlayer.ts";
import type { StoryStep } from "./story.ts";

const FIRST_HALF_END = 2_870_000;
const pos2 = (tMs: number) => FIRST_HALF_END + 500 + (tMs - 2_700_000);

const steps: StoryStep[] = [
  { id: "tv-open", screen: "tv", startPos: pos2(3_540_000), wait: { kind: "play", untilPos: pos2(3_622_000), speed: 5 },
    caption: { key: "story_open", vars: { team: "Riverside FC" } } },
  { id: "tablet", screen: "tablet", startPos: pos2(3_622_000), wait: { kind: "hold", ms: 12_000 },
    caption: { key: "story_tablet", vars: { player: "Leon Varga" } } },
  { id: "vote", screen: "phone", startPos: pos2(3_622_000), wait: { kind: "vote", ms: 15_000, decisionId: "rfc-60-20" },
    caption: { key: "story_vote", vars: {} } },
  { id: "end", screen: "end", startPos: pos2(5_800_000), wait: { kind: "stay" }, caption: { key: "story_end", vars: {} } },
];

const run = (state: StoryState, ...events: Parameters<typeof storyReducer>[2][]) =>
  events.reduce((s, e) => storyReducer(steps, s, e).state, state);

test("storyReducer: start opens the first step and plays it from its start at its speed", () => {
  const { state, command } = storyReducer(steps, INITIAL_STORY, { type: "start", now: 1000 });
  assert.equal(state.status, "playing");
  assert.equal(state.index, 0);
  assert.deepEqual(command, { seek: steps[0].startPos, speed: 5, play: true });
});

test("storyReducer: a play step advances once the playhead reaches its end, and a held step stops the replay", () => {
  const started = run(INITIAL_STORY, { type: "start", now: 0 });
  assert.equal(storyReducer(steps, started, { type: "tick", now: 100, playhead: pos2(3_621_999) }).state.index, 0);
  const { state, command } = storyReducer(steps, started, { type: "tick", now: 200, playhead: pos2(3_622_000) });
  assert.equal(state.index, 1);
  assert.equal(state.stepStartedAt, 200);
  assert.deepEqual(command, { seek: steps[1].startPos, play: false });
});

test("storyReducer: a held step advances after its time", () => {
  const onTablet = run(INITIAL_STORY, { type: "start", now: 0 }, { type: "next", now: 1000 });
  assert.equal(storyReducer(steps, onTablet, { type: "tick", now: 12_999, playhead: 0 }).state.index, 1);
  assert.equal(storyReducer(steps, onTablet, { type: "tick", now: 13_000, playhead: 0 }).state.index, 2);
});

test("storyReducer: pause on a held step keeps its remaining time", () => {
  const onTablet = run(INITIAL_STORY, { type: "start", now: 0 }, { type: "next", now: 1000 });
  const paused = run(onTablet, { type: "pause", now: 5000 });          // 4 s of 12 s used
  assert.equal(paused.status, "paused");
  assert.equal(storyReducer(steps, paused, { type: "tick", now: 60_000, playhead: 0 }).state.index, 1); // no clock while paused
  const resumed = run(paused, { type: "resume", now: 100_000 });
  assert.equal(storyReducer(steps, resumed, { type: "tick", now: 107_999, playhead: 0 }).state.index, 1);
  assert.equal(storyReducer(steps, resumed, { type: "tick", now: 108_000, playhead: 0 }).state.index, 2);
});

test("storyReducer: pause and resume on a play step stop and restart the replay", () => {
  const started = run(INITIAL_STORY, { type: "start", now: 0 });
  assert.deepEqual(storyReducer(steps, started, { type: "pause", now: 10 }).command, { play: false });
  const paused = run(started, { type: "pause", now: 10 });
  assert.deepEqual(storyReducer(steps, paused, { type: "resume", now: 20 }).command, { play: true });
});

test("storyReducer: the vote step advances on a vote for its card, not another card", () => {
  const onVote = run(INITIAL_STORY, { type: "start", now: 0 }, { type: "next", now: 1 }, { type: "next", now: 2 });
  assert.equal(onVote.index, 2);
  assert.equal(storyReducer(steps, onVote, { type: "vote", decisionId: "cas-69-10", now: 3 }).state.index, 2);
  assert.equal(storyReducer(steps, onVote, { type: "vote", decisionId: "rfc-60-20", now: 3 }).state.index, 3);
});

test("storyReducer: the vote step moves on by itself after its timeout", () => {
  const onVote = run(INITIAL_STORY, { type: "start", now: 0 }, { type: "next", now: 1 }, { type: "next", now: 2 });
  assert.equal(storyReducer(steps, onVote, { type: "tick", now: 15_002, playhead: 0 }).state.index, 3);
});

test("storyReducer: reaching the end finishes the story", () => {
  const done = run(INITIAL_STORY, { type: "start", now: 0 }, { type: "next", now: 1 }, { type: "next", now: 2 }, { type: "next", now: 3 });
  assert.equal(done.status, "done");
  assert.equal(done.index, 3);
  assert.equal(storyReducer(steps, done, { type: "tick", now: 1e9, playhead: 0 }).state.index, 3);
});

test("storyReducer: a chapter click or a speed change during the story leaves it and commands nothing", () => {
  const started = run(INITIAL_STORY, { type: "start", now: 0 });
  for (const type of ["viewer-seek", "viewer-speed"] as const) {
    const { state, command } = storyReducer(steps, started, { type });
    assert.equal(state.status, "left");
    assert.equal(command, null);
  }
});

test("storyReducer: ticks and votes do nothing once the viewer has left or skipped the intro", () => {
  const left = run(INITIAL_STORY, { type: "start", now: 0 }, { type: "leave" });
  assert.deepEqual(storyReducer(steps, left, { type: "tick", now: 1e9, playhead: 1e9 }), { state: left, command: null });
  const skipped = run(INITIAL_STORY, { type: "skip-intro" });
  assert.equal(skipped.status, "left");
});

test("leaveUrl: the step's own screen at the playhead, in hundredths of a minute so a card that just opened is still open", () => {
  assert.equal(leaveUrl(steps[0], pos2(3_600_000), FIRST_HALF_END), "/?t=60");
  assert.equal(leaveUrl(steps[1], pos2(3_622_000), FIRST_HALF_END), "/desk?t=60.36"); // 60:22, after the 60:20 card
  assert.equal(leaveUrl(steps[2], pos2(3_622_000), FIRST_HALF_END), "/fan?t=60.36");
  assert.equal(leaveUrl(steps[0], 1_500_000, FIRST_HALF_END), "/?t=25");
  assert.equal(leaveUrl(steps[3], pos2(5_800_000), FIRST_HALF_END), "/?t=96.66");
});
