import { test } from "node:test";
import assert from "node:assert/strict";
import { sourceChoice } from "./source.ts";

test("sourceChoice: no query is the replay from kick-off, the same as the server-rendered page", () => {
  assert.deepEqual(sourceChoice(""), { kind: "replay", minute: 0 });
});

test("sourceChoice: ?source=live picks Web PubSub, ?t= opens the replay at that minute", () => {
  assert.deepEqual(sourceChoice("?source=live"), { kind: "live" });
  assert.deepEqual(sourceChoice("?source=live&t=60"), { kind: "live" });
  assert.deepEqual(sourceChoice("?t=62"), { kind: "replay", minute: 62 });
  assert.deepEqual(sourceChoice("?t=abc"), { kind: "replay", minute: 0 });
  assert.deepEqual(sourceChoice("?t=-5"), { kind: "replay", minute: 0 });
});
