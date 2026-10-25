import { test } from "node:test";
import assert from "node:assert/strict";
import { SPEECH_LANG, speechText } from "./speech.ts";

test("the spoken line is the headline then the reason, as a sentence each, with names not ids", () => {
  const roster = { home: "RFC", away: "CAS", teams: {}, players: { "RFC-03": { team: "RFC", name: "Leon Varga", role: "FB", side: "left" } } };
  const text = speechText({ headline: "Take RFC-03 off for a fresh player", reason: "RFC-03 is tiring." }, roster as never);
  assert.equal(text, "Take Leon Varga off for a fresh player. Leon Varga is tiring.");
  assert.equal(speechText({ headline: "Done.", reason: "Yes" }, null), "Done. Yes");
});

test("each locale has a speech language", () => {
  assert.equal(SPEECH_LANG.en, "en-GB");
  assert.equal(SPEECH_LANG.es, "es-ES");
});
