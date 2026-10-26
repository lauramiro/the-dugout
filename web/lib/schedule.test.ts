import { test } from "node:test";
import assert from "node:assert/strict";
import { CONNECT_WAIT_MS, countdown, GRACE_MS, JOIN_WAIT_MS, kickoff, parseSchedule } from "./schedule.ts";

// As dugout/stream/replay.py writes it for the demo match at 5x, every 30 minutes.
const schedule = { match_id: "rfc-cas-0073", every_min: 30, speed: 5, duration_ms: 1_176_800 };
const slot = Date.UTC(2026, 9, 28, 9, 30);

test("parseSchedule takes replay.py's file and refuses anything else", () => {
  assert.deepEqual(parseSchedule(schedule), schedule);
  assert.equal(parseSchedule(null), null);
  assert.equal(parseSchedule({ ...schedule, every_min: 25 }), null);
  assert.equal(parseSchedule({ ...schedule, duration_ms: 30 * 60_000 }), null); // overruns its slot
  assert.equal(parseSchedule({ every_min: 30 }), null);
});

test("kickoff: a match from the slot until its end plus the grace, then the next slot", () => {
  assert.deepEqual(kickoff(schedule, slot), { kind: "on", since: slot, until: slot + schedule.duration_ms });
  assert.equal(kickoff(schedule, slot + schedule.duration_ms + GRACE_MS - 1).kind, "on");
  assert.deepEqual(kickoff(schedule, slot + schedule.duration_ms + GRACE_MS), { kind: "next", at: slot + 30 * 60_000 });
  assert.deepEqual(kickoff(schedule, slot - 1), { kind: "next", at: slot });
});

test("kickoff: a slot that has sent nothing after JOIN_WAIT_MS is missed, so count down to the next", () => {
  assert.equal(kickoff(schedule, slot + JOIN_WAIT_MS, true).kind, "on");
  assert.deepEqual(kickoff(schedule, slot + JOIN_WAIT_MS + 1, true), { kind: "next", at: slot + 30 * 60_000 });
  assert.equal(kickoff(schedule, slot + JOIN_WAIT_MS + 1, false).kind, "on"); // messages arriving: the match is on
});

test("countdown shows minutes and seconds, hours only when needed", () => {
  assert.equal(countdown(485_000), "8:05");
  assert.equal(countdown(484_001), "8:05");
  assert.equal(countdown(3_729_000), "1:02:09");
  assert.equal(countdown(-5), "0:00");
});

test("kickoff: a page that has just connected mid-match waits for the feed before calling the slot missed", () => {
  const mid = slot + 11 * 60_000;
  assert.equal(kickoff(schedule, mid, true, mid - 3_000).kind, "on", "3 s after connecting: joining, not the next kick-off");
  assert.equal(kickoff(schedule, mid, true, mid - CONNECT_WAIT_MS - 1).kind, "next", "connected a while and still nothing: missed");
  assert.equal(kickoff(schedule, mid, true).kind, "next", "without a connection time, as before");
  const between = slot + schedule.duration_ms + GRACE_MS + 60_000;
  assert.equal(kickoff(schedule, between, true, between - 1_000).kind, "next", "between slots: the countdown at once");
});
