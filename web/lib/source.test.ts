import { test } from "node:test";
import assert from "node:assert/strict";
import { LANDING_MINUTE, sourceChoice } from "./source.ts";

test("sourceChoice: no query is the replay a minute before the first card, the same as the server-rendered page", () => {
  assert.equal(LANDING_MINUTE, 59);
  assert.deepEqual(sourceChoice(""), { kind: "replay", minute: LANDING_MINUTE });
});

test("sourceChoice: ?source=live picks Web PubSub, ?t= opens the replay at that minute", () => {
  assert.deepEqual(sourceChoice("?source=live"), { kind: "live" });
  assert.deepEqual(sourceChoice("?source=live&t=60"), { kind: "live" });
  assert.deepEqual(sourceChoice("?t=62"), { kind: "replay", minute: 62 });
});

test("sourceChoice: ?t=0 is the full match from kick-off; an unreadable ?t= falls back to the landing minute", () => {
  assert.deepEqual(sourceChoice("?t=0"), { kind: "replay", minute: 0 });
  assert.deepEqual(sourceChoice("?t="), { kind: "replay", minute: LANDING_MINUTE });
  assert.deepEqual(sourceChoice("?t=abc"), { kind: "replay", minute: LANDING_MINUTE });
  assert.deepEqual(sourceChoice("?t=-5"), { kind: "replay", minute: LANDING_MINUTE });
});
