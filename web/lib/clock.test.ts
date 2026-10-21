import { test } from "node:test";
import assert from "node:assert/strict";
import { aheadPos, liveHalf, type LiveHalf } from "./clock.ts";

test("aheadPos caps the run-on at maxAheadMs of match time, whatever the rate", () => {
  // 20x: 10 s of wall time since the last message would be 200 s of match time.
  assert.equal(aheadPos(1_000_000, 0, 20, 10_000, 3000), 1_003_000);
  assert.equal(aheadPos(1_000_000, 0, 20, 100, 3000), 1_002_000);
  assert.equal(aheadPos(1_000_000, 0, 0, 10_000, 3000), 1_000_000);
});

test("liveHalf learns where the first half ended from period-1 messages", () => {
  let half: LiveHalf = { firstHalfEnd: 2_700_000, secondHalf: false };
  let r = liveHalf(half, 1, 2_870_000);
  assert.equal(r.period, 1);
  assert.equal(r.half.firstHalfEnd, 2_870_000);
  half = r.half;
  r = liveHalf(half, 2, 2_700_000);
  assert.equal(r.period, 2);
  assert.equal(r.half.secondHalf, true);
  assert.equal(r.half.firstHalfEnd, 2_870_000, "a second-half message does not move the first half's end");
});

test("liveHalf infers the period when a message has none", () => {
  const first: LiveHalf = { firstHalfEnd: 2_800_000, secondHalf: false };
  assert.equal(liveHalf(first, undefined, 2_790_000).period, 1, "added time before the second half has started");
  const second: LiveHalf = { firstHalfEnd: 2_870_000, secondHalf: true };
  assert.equal(liveHalf(second, undefined, 2_790_000).period, 2);
  assert.equal(liveHalf(second, undefined, 1_000_000).period, 1, "a first-half t_ms below 45' is always period 1");
});
