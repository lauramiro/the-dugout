import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCues } from "./cues.ts";
import { demoLog } from "./demoLog.testutil.ts";
import { en, es, translator, type StringKey } from "./i18n.ts";
import { matchReport, reportLines, stripMinute, whatIfLead } from "./matchReport.ts";

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
