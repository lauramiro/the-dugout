import { test } from "node:test";
import assert from "node:assert/strict";
import { countdown, GRACE_MS, kickoff, parseSchedule } from "./schedule.ts";

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

test("countdown shows minutes and seconds, hours only when needed", () => {
  assert.equal(countdown(485_000), "8:05");
  assert.equal(countdown(484_001), "8:05");
  assert.equal(countdown(3_729_000), "1:02:09");
  assert.equal(countdown(-5), "0:00");
});
