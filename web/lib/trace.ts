// Labels for one step of how a card's line was written (NarrationStep, from the narration
// workflow's trace): which agent, which attempt, and what the code check made of it.

import type { NarrationStep } from "./contracts";
import type { StringKey } from "./i18n";

export interface StepLabel {
  who: StringKey;
  whoVars: Record<string, string | number>;
  outcome: StringKey;
}

const OUTCOME: Record<NarrationStep["outcome"], StringKey> = {
  passed: "trace_passed",
  rejected: "trace_rejected",
  timeout: "trace_timeout",
  error: "trace_error",
  used: "trace_used",
};

export function stepLabel(step: NarrationStep): StepLabel {
  const outcome = OUTCOME[step.outcome];
  if (step.stage === "template") return { who: "trace_template", whoVars: {}, outcome };
  const lang = step.locale.toUpperCase();
  if (step.stage === "narrator") return { who: "trace_narrator", whoVars: { n: step.attempt + 1, lang }, outcome };
  return { who: "trace_localizer", whoVars: { n: step.attempt + 1, lang, mode: step.mode }, outcome };
}
