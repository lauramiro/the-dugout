import { test } from "node:test";
import assert from "node:assert/strict";
import { fanMoment, type FanContext } from "./fan.ts";
import type { MatchLog } from "./datasource.ts";
import { demoLog, demoPos } from "./demoLog.testutil.ts";

const context = (m: ReturnType<typeof fanMoment>): FanContext => {
  assert.ok(m.kind === "decision" || m.kind === "call", `expected a card, got ${m.kind}`);
  return m.context;
};

test("fanMoment: at 60:30 the Riverside fan sees Varga's card, his rank on the team and the options", () => {
  const c = context(fanMoment(demoLog(), demoPos(2, 3_630_000), "RFC", "en", "casual"));
  assert.equal(c.decisionId, "rfc-60-20");
  assert.equal(c.minute, "60'");
  assert.equal(c.trigger, "condition_drop");
  assert.equal(c.strength, "strong");
  assert.equal(c.player!.name, "Leon Varga");
  assert.equal(c.player!.condition, 0.689);
  assert.equal(c.player!.rank, 1); // the lowest condition on Riverside
  assert.equal(c.player!.of, 10); // ten outfielders with an estimate
  assert.equal(c.flankShare, 0.137);
  assert.equal(c.flankSide, "left"); // the card's channel RFC_left
  assert.deepEqual(c.options.filter((o) => o.pick).map((o) => o.id), ["sub_like_for_like"]);
  assert.equal(c.options.length, 4);
  assert.ok(c.ready.some((p) => p.name === "Femi Osei"));
  assert.ok(c.ready.every((p) => p.role === "FB"));
  assert.equal(c.subsLeft, 5);
  assert.equal(c.windowsLeft, 3);
  assert.equal(c.narration?.source, "model");
});

test("fanMoment: a Castleton card is not shown to a Riverside fan", () => {
  assert.equal(fanMoment(demoLog(), demoPos(2, 4_160_000), "RFC", "en", "casual").kind, "waiting");
});

test("fanMoment: just after the manager's 79' change the fan sees the call on the 60' card", () => {
  const m = fanMoment(demoLog(), demoPos(2, 4_745_000), "RFC", "en", "casual");
  assert.equal(m.kind, "call");
  assert.equal(context(m).decisionId, "rfc-60-20"); // the 72' card reveals the same change; the earlier one leads
  assert.equal(m.kind === "call" && m.manager, "sub_like_for_like");
  assert.equal(m.kind === "call" && m.model, "sub_like_for_like");
});

test("fanMoment: after the call has shown, the card opened by the change takes over", () => {
  const c = context(fanMoment(demoLog(), demoPos(2, 4_780_000), "RFC", "en", "casual"));
  assert.equal(c.decisionId, "rfc-79-10");
});

test("fanMoment: a toss-up lists every option and marks none as the pick", () => {
  const c = context(fanMoment(demoLog(), demoPos(2, 4_160_000), "CAS", "en", "casual"));
  assert.equal(c.strength, "toss_up");
  assert.equal(c.options.length, 4);
  assert.equal(c.options.some((o) => o.pick), false);
});

test("fanMoment: a card with no flank evidence has flankShare null, not 0", () => {
  const log = demoLog();
  const cards = log.cards.map((c) => ({ ...c, item: { ...c.item, payload: { ...c.item.payload,
    evidence: c.item.payload.evidence.filter((e) => e.type !== "flank_threat") } } }));
  const c = context(fanMoment({ ...log, cards } as MatchLog, demoPos(2, 3_630_000), "RFC", "en", "casual"));
  assert.equal(c.flankShare, null);
});

test("fanMoment: Spanish analyst text when the viewer asks for it", () => {
  const c = context(fanMoment(demoLog(), demoPos(2, 3_630_000), "RFC", "es", "analyst"));
  assert.match(c.narration!.reason, /intervalo/);
});

test("fanMoment: at full time the moment is full-time, and before the first card it is waiting", () => {
  const log = demoLog();
  assert.equal(fanMoment(log, log.duration, "RFC", "en", "casual").kind, "full-time");
  assert.equal(fanMoment(log, demoPos(1, 600_000), "RFC", "en", "casual").kind, "waiting");
});

test("fanMoment: live, the log ends where the feed has got to, which is not full time", () => {
  // Live, every message moves the playhead and the log's duration together, so the card open
  // at 60:30 must still show; only the replay knows where the match ends.
  const pos = demoPos(2, 3_630_000);
  const live = { ...demoLog(), duration: pos };
  assert.equal(fanMoment(live, pos, "RFC", "en", "casual", true).kind, "decision");
  assert.equal(fanMoment(live, pos, "RFC", "en", "casual").kind, "full-time"); // a replay that ends there
});

test("fanMoment: a queued card whose call was settled before it opened shows the card, not the call", () => {
  // rfc-91-10 opens at 91' with the manager's no change dated 89' (the next goal came first).
  const log = demoLog();
  const card = log.cards.find((c) => c.item.payload.decision_id === "rfc-91-10")!;
  const m = fanMoment(log, card.pos + 5_000, "RFC", "en", "casual");
  assert.equal(m.kind, "decision");
});
