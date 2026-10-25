import type { Narration, Roster } from "../lib/contracts";
import { withNames } from "../lib/derive";
import type { Translate } from "../lib/i18n";
import { stepLabel } from "../lib/trace";

/** Each agent step that wrote a line and what the code check made of it (the narration workflow's trace). */
export function TraceSteps({ narration, roster, t }: { narration: Narration | undefined; roster: Roster | null; t: Translate }) {
  const steps = narration?.trace ?? [];
  if (steps.length === 0) return <p>{t("traceNone")}</p>;
  return (
    <ol className="bc-trace">
      {steps.map((step, i) => {
        const label = stepLabel(step);
        return (
          <li key={i} className={`bc-trace-step ${step.outcome}`}>
            <p className="bc-trace-head">
              <span>{t(label.who, label.whoVars)}</span>
              <b>{t(label.outcome)}</b>
            </p>
            {step.text && <p className="bc-trace-text">{withNames(step.text, roster)}</p>}
            {step.errors.length > 0 && (
              <>
                <p className="bc-trace-label">{t("traceChecks")}</p>
                <ul className="bc-trace-errors">{step.errors.map((e, j) => <li key={j}>{e}</li>)}</ul>
              </>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** The card's provenance where there is no room for a panel (the desk, the fan's phone): the credit, and the
 *  steps behind it on request. */
export function TraceDetails({ narration, roster, t }: { narration: Narration; roster: Roster | null; t: Translate }) {
  const credit = t(narration.source === "model" ? "creditModel" : "creditTemplate");
  if (!narration.trace?.length) return <p className="trace-credit">{credit}</p>;
  return (
    <details className="trace-details">
      <summary><span className="trace-credit">{credit}</span> <span className="trace-open">{t("traceOpen")}</span></summary>
      <p className="trace-lead">{t("traceLead")}</p>
      <TraceSteps narration={narration} roster={roster} t={t} />
    </details>
  );
}
