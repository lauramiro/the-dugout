import { test } from "node:test";
import assert from "node:assert/strict";
import { benchAt } from "./bench.ts";
import { demoLog, demoPos } from "./demoLog.testutil.ts";

test("benchAt: at 60:00 Riverside's bench is the seven players who have not played, Femi Osei among them", () => {
  const bench = benchAt(demoLog(), demoPos(2, 3_600_000), "RFC");
  assert.equal(bench.length, 7);
  assert.ok(bench.some((p) => p.name === "Femi Osei" && p.role === "FB"));
});

test("benchAt: after the 79' change Femi Osei is on and Leon Varga, subbed off, is not on the bench", () => {
  const names = benchAt(demoLog(), demoPos(2, 4_800_000), "RFC").map((p) => p.name);
  assert.equal(names.includes("Femi Osei"), false);
  assert.equal(names.includes("Leon Varga"), false);
  assert.equal(names.length, 6);
});

test("benchAt: at kick-off, before the first snapshot, the first snapshot's players are the ones on the pitch", () => {
  const bench = benchAt(demoLog(), 0, "CAS");
  assert.equal(bench.length, 7);
  assert.ok(bench.every((p) => p.id.startsWith("CAS-")));
});

test("benchAt: with no snapshot at all nobody is known to be on the pitch, so the list is empty rather than wrong", () => {
  assert.deepEqual(benchAt({ ...demoLog(), snapshots: [] }, 0, "CAS"), []);
});
