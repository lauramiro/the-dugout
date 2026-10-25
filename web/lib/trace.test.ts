import { test } from "node:test";
import assert from "node:assert/strict";
import { stepLabel } from "./trace.ts";
import type { NarrationStep } from "./contracts.ts";

const step = (over: Partial<NarrationStep>): NarrationStep => ({
  stage: "narrator", attempt: 0, outcome: "passed", text: "", errors: [], locale: "en", mode: "analyst", ...over,
});

test("stepLabel: the narrator's attempts count from one, with the language it wrote in", () => {
  assert.deepEqual(stepLabel(step({ attempt: 1, outcome: "rejected" })),
    { who: "trace_narrator", whoVars: { n: 2, lang: "EN" }, outcome: "trace_rejected" });
});

test("stepLabel: the localizer names the viewer's language and mode", () => {
  assert.deepEqual(stepLabel(step({ stage: "localizer", locale: "es", mode: "casual" })),
    { who: "trace_localizer", whoVars: { n: 1, lang: "ES", mode: "casual" }, outcome: "trace_passed" });
});

test("stepLabel: a timeout, an error and the template each have their own outcome", () => {
  assert.equal(stepLabel(step({ outcome: "timeout" })).outcome, "trace_timeout");
  assert.equal(stepLabel(step({ outcome: "error" })).outcome, "trace_error");
  assert.deepEqual(stepLabel(step({ stage: "template", outcome: "used" })),
    { who: "trace_template", whoVars: {}, outcome: "trace_used" });
});
