import { test } from "node:test";
import assert from "node:assert/strict";
import { reconnectDelayMs, statusOnDrop } from "./reconnect.ts";

test("reconnectDelayMs: one second first, doubling, never more than thirty", () => {
  assert.deepEqual([0, 1, 2, 3, 4].map(reconnectDelayMs), [1000, 2000, 4000, 8000, 16000]);
  assert.equal(reconnectDelayMs(5), 30000);
  assert.equal(reconnectDelayMs(50), 30000);
});

test("statusOnDrop: a feed that was showing the match keeps it on screen; one that never connected says so", () => {
  assert.equal(statusOnDrop("ready"), "ready");
  assert.equal(statusOnDrop("loading"), "error");
  assert.equal(statusOnDrop("error"), "error");
});
