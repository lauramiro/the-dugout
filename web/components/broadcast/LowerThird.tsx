import { formatMinute } from "../../lib/clock";
import type { DecisionCard, Locale, Mode, Narration, Roster } from "../../lib/contracts";
import { withNames } from "../../lib/derive";
import { pct, points, strengthKey, triggerKey, type Translate } from "../../lib/i18n";
import { optionLabel } from "../DecisionCard";

interface Props {
  card: DecisionCard;
  roster: Roster | null;
  mode: Mode;
  locale: Locale;
  t: Translate;
}

/** The viewer's version; English of the same mode, then English casual, while the others arrive. */
function narrationFor(card: DecisionCard, locale: Locale, mode: Mode): Narration | undefined {
  return card.narration[locale]?.[mode] ?? card.narration.en?.[mode] ?? card.narration.en?.casual;
}

/** The decision as a lower third: what triggered it, the model's line, the options as bars. */
export function LowerThird({ card, roster, mode, locale, t }: Props) {
  const { payload } = card;
  const narration = narrationFor(card, locale, mode);
  const pick = payload.recommendation.option_id;
  const side = payload.team === roster?.home ? "home" : "away";
  const teamName = roster?.teams[payload.team]?.name ?? payload.team;
  return (
    <section className={`bc-lower ${side}`} aria-live="polite" aria-label={t("decision")}>
      <header className="bc-lower-head">
        <span className="bc-lower-minute">{formatMinute(card.period, payload.t_ms)}</span>
        <span className="bc-lower-title">{t(triggerKey(payload.trigger))}</span>
        <span className="bc-lower-team">{teamName}</span>
        <span className={`bc-lower-strength ${payload.recommendation.strength}`}>{t(strengthKey(payload.recommendation.strength))}</span>
      </header>
      {narration && (
        <div className="bc-lower-text">
          <p className="bc-lower-headline">{withNames(narration.headline, roster)}</p>
          <p className="bc-lower-reason">{withNames(narration.reason, roster)}</p>
        </div>
      )}
      <ol className="bc-options">
        {payload.options.map((o) => (
          <li key={o.id} className={`bc-option${o.id === pick ? " bc-pick" : ""}`}>
            <span className="bc-option-label">
              <span className="bc-option-name">{optionLabel(o, card, roster, t)}</span>
              {o.id === pick && <span className="bc-option-badge">{t("modelPick")}</span>}
            </span>
            <span className="bc-option-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(0, Math.min(1, o.win)) * 100}%` }} />
            </span>
            <span className="bc-option-win">{pct(o.win, locale)}%</span>
            <span className="bc-option-gap">
              {o.id === "no_change" ? "" : `${points(o.delta_win, locale)} ${t("pts")}`}
              {mode === "analyst" && o.ci90 && o.id !== "no_change" && (
                <span className="bc-option-ci"> {t("ci90")} {points(o.ci90[0], locale)} / {points(o.ci90[1], locale)}</span>
              )}
            </span>
          </li>
        ))}
      </ol>
      <p className="bc-lower-call">{t("yourCallPrompt")}</p>
    </section>
  );
}
