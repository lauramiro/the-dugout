import { test } from "node:test";
import assert from "node:assert/strict";
import { LANDING_MINUTE, linkedMinute, playOnLoad, sourceChoice } from "./source.ts";

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

test("playOnLoad: a replay page opened on its own starts once it has loaded, once, and not while something holds it", () => {
  const base = { started: false, ready: true, controls: true, held: false, atEnd: false };
  assert.equal(playOnLoad(base), true);
  assert.equal(playOnLoad({ ...base, atEnd: true }), false, "opened at full time (?t=95): play would start the match again");
  assert.equal(playOnLoad({ ...base, started: true }), false, "only once: a pause stays a pause");
  assert.equal(playOnLoad({ ...base, ready: false }), false);
  assert.equal(playOnLoad({ ...base, controls: false }), false, "live has no controls");
  assert.equal(playOnLoad({ ...base, held: true }), false, "the landing's intro holds it");
});

test("linkedMinute: a link that opens a minute of its own (leaving the story) waits for the viewer", () => {
  assert.equal(linkedMinute("?t=60.37&club=RFC&lang=en"), true);
  assert.equal(linkedMinute(""), false);
  assert.equal(linkedMinute("?club=RFC"), false);
});
