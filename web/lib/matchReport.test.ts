import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCues } from "./cues.ts";
import { demoLog } from "./demoLog.testutil.ts";
import { en, es, translator, type StringKey } from "./i18n.ts";
import { matchReport, reportLines, stripMinute, whatIfLead, whatIfRows } from "./matchReport.ts";

const log = demoLog();
const cards = log.cards.map((c) => c.item);
const whatif = buildCues(log, null).find((c) => c.kind === "whatif")!;

test("the match report gives the final score and every goal in order, with its scorer and minute", () => {
  const report = matchReport(log, whatif, cards, null)!;
  assert.deepEqual(report.score, { RFC: 3, CAS: 2 });
  assert.deepEqual(report.goals.map((g) => [g.team, g.player_id, g.label]), [
    ["RFC", "RFC-07", "32'"], ["CAS", "CAS-07", "72'"], ["RFC", "RFC-09", "81'"],
    ["CAS", "CAS-09", "88'"], ["RFC", "RFC-10", "89'"],
  ]);
});

test("the decision of the match is the one What if leads with, in and out of the story", () => {
  assert.equal(matchReport(log, whatif, cards, null)!.lead?.decision_id, whatIfLead(whatif, cards, null));
  assert.equal(matchReport(log, whatif, cards, "rfc-60-20")!.lead?.decision_id, "rfc-60-20");
});

test("report lines name the clubs and scorers and reuse the review's own line, so no number is new", () => {
  const report = matchReport(log, whatif, cards, "rfc-60-20")!;
  const lines = reportLines(report, log.roster, "en", "casual", translator("en"), cards);
  assert.match(lines[0], /Riverside FC 3, Castleton Athletic 2/);
  assert.match(lines.join(" "), /Leon Varga/, "ids in the review line become names");
  assert.ok(lines.some((l) => l.includes("about 3 points better (lean)")));
  assert.ok(!lines.some((l) => /\b[A-Z]{3}-\d{2}\b/.test(l)), "no raw player ids");
  const spanish = reportLines(report, log.roster, "es", "casual", translator("es"), cards);
  assert.notDeepEqual(spanish, lines);
});

test("a goal sent twice is listed once, and a club whose list does not add up to its score gets no list", () => {
  const goals = log.events.filter((e) => e.item.type === "goal");
  const twice = { ...log, events: [...log.events, goals[0]].sort((a, b) => a.pos - b.pos) };
  assert.equal(matchReport(twice, whatif, cards, null)!.goals.length, 5);
  const dropped = { ...log, events: log.events.filter((e) => e !== goals[0]) };
  const report = matchReport(dropped, whatif, cards, null)!;
  assert.equal(report.score.RFC, 3, "the score still comes from the snapshots");
  const lines = reportLines(report, log.roster, "en", "casual", translator("en"), cards);
  assert.ok(!lines.some((l) => l.startsWith("Goals for Riverside FC")), "two scorers under a score of 3 is left out");
  assert.ok(lines.some((l) => l.startsWith("Goals for Castleton Athletic")));
});

test("a goal with no scorer shows the minute only", () => {
  const goals = log.events.filter((e) => e.item.type === "goal");
  const anon = { ...log, events: log.events.map((e) => (e === goals[0] ? { ...e, item: { ...e.item, player_id: null } } : e)) };
  const lines = reportLines(matchReport(anon, whatif, cards, null)!, log.roster, "en", "casual", translator("en"), cards);
  assert.ok(lines.some((l) => l.startsWith("Goals for Riverside FC: 32', Kai Thornton 81'")), lines.join("|"));
});

test("report strings use the same placeholders in both languages", () => {
  const vars = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
  for (const k of Object.keys(en).filter((k) => k.startsWith("report")) as StringKey[]) assert.equal(vars(es[k]), vars(en[k]), k);
});

test("stripMinute drops the review line's own minute, which the row label already shows", () => {
  assert.equal(stripMinute("91': the manager chose no change"), "the manager chose no change");
  assert.equal(stripMinute("The card has no option"), "The card has no option");
  assert.equal(stripMinute("91': the manager chose no change", true), "The manager chose no change",
    "a line that stands alone starts with a capital");
  assert.equal(stripMinute("60': el entrenador eligió", true), "El entrenador eligió");
});

test("every report string exists in both languages, translated, with no long dashes", () => {
  const keys = Object.keys(en).filter((k) => k.startsWith("report")) as StringKey[];
  assert.ok(keys.length >= 4);
  for (const k of keys) {
    assert.ok(es[k], k);
    assert.notEqual(es[k], en[k], k);
    assert.ok(!/[–—]/.test(en[k] + es[k]), k);
  }
});

test("What if drops a later card that prices the same call against the same change of the manager's", () => {
  const ids = whatIfRows(whatif, cards).map((r) => r.decision_id);
  assert.ok(ids.includes("rfc-60-20"));
  assert.ok(!ids.includes("rfc-72-40"), "72': Varga off against the 79' change again, the 60' row already says it");
  assert.ok(ids.includes("rfc-85-10"), "a different call stays");
});
