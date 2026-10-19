import { useEffect, useRef } from "react";
import { formatMinute } from "../lib/clock";
import type { DecisionCard as Card, Locale, Roster } from "../lib/contracts";
import type { Timed } from "../lib/datasource";
import { agreement, managerOption, revealPos, type Vote } from "../lib/calls";
import { decimal, points, triggerKey, type Translate } from "../lib/i18n";
import { optionLabel } from "./DecisionCard";
import { managerCall, modelCall } from "./YourCall";

interface Props {
  open: boolean;
  onClose: () => void;
  cards: Timed<Card>[];
  votes: Record<string, Vote>;
  playhead: number;
  firstHalfEnd: number;
  finished: boolean;
  roster: Roster | null;
  locale: Locale;
  t: Translate;
}

/** The viewer's "manager IQ": how many of their calls matched the model's pick. */
function Iq({ cards, votes, t }: { cards: Card[]; votes: Record<string, Vote>; t: Translate }) {
  const viewer = agreement(cards, (c) => votes[c.payload.decision_id]?.option ?? null);
  const manager = agreement(cards, managerOption);
  return (
    <div className="iq">
      <div className="iq-board" aria-label={`${t("iq")}: ${t("iqValue", { a: viewer.agreed, n: viewer.counted })}`}>
        <span className="iq-label">{t("iq")}</span>
        <span className="led amber">{viewer.counted ? `${viewer.agreed}/${viewer.counted}` : "--"}</span>
      </div>
      <div className="iq-text">
        <p>{viewer.counted ? t("iqHelp") : t("iqNone")}</p>
        {manager.counted > 0 && <p className="sub">{t("managerIq", { a: manager.agreed, n: manager.counted })}</p>}
      </div>
    </div>
  );
}

export function Review({ open, onClose, cards, votes, playhead, firstHalfEnd, finished, roster, locale, t }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  // Mid-match, only the decisions reached so far, and a manager's call only once he made it.
  const reached = cards.filter((c) => c.pos <= playhead);
  const title = finished ? t("review") : t("reviewSoFar");

  return (
    <dialog ref={ref} className="review" aria-labelledby="review-title" onClose={onClose} onCancel={onClose}>
      <header className="review-head">
        <h2 id="review-title">{title}</h2>
        <button className="close" onClick={onClose}>
          {t("close")}
        </button>
      </header>
      <p className="help">{t("reviewIntro")}</p>
      <Iq cards={reached.filter((c) => (revealPos(c, firstHalfEnd) ?? Infinity) <= playhead).map((c) => c.item)} votes={votes} t={t} />
      {reached.length === 0 ? (
        <p className="help">{t("noDecisionsYet")}</p>
      ) : (
        <ol className="review-rows">
          <li className="review-row head" aria-hidden>
            <span>{t("colMinute")}</span>
            <span>{t("colDecision")}</span>
            <span>{t("colYou")}</span>
            <span>{t("colModel")}</span>
            <span>{t("colManager")}</span>
            <span>{t("colGap")}</span>
          </li>
          {reached.map(({ item: card, pos }) => {
            const { payload, review } = card;
            const at = revealPos({ item: card, pos }, firstHalfEnd);
            const known = at !== null && at <= playhead;
            const model = modelCall(card, roster, t);
            const manager = known ? managerCall(card, roster, t) : null;
            const vote = votes[payload.decision_id];
            const voted = vote?.option ? payload.options.find((o) => o.id === vote.option) : undefined;
            const recap = review?.recap[locale] ?? review?.recap.en;
            return (
              <li key={payload.decision_id} className={`review-row ${payload.team === roster?.home ? "home" : "away"}`}>
                <span className="r-minute led amber">{formatMinute(card.period, payload.t_ms).replace("'", "")}</span>
                <span className="r-decision">
                  <span className="team-tag">{payload.team}</span> {t(triggerKey(payload.trigger))}
                </span>
                <span className="r-you" data-label={t("colYou")}>
                  {voted ? optionLabel(voted, card, roster, t) : vote ? t("noCall") : "-"}
                </span>
                <span className="r-model" data-label={t("colModel")}>
                  {model.label}
                  {model.close && <span className="sub"> ({t("closeCall")})</span>}
                </span>
                <span className="r-manager" data-label={t("colManager")}>
                  {manager ? (
                    <>
                      {manager.label}
                      {manager.detail && <span className="sub"> ({manager.detail})</span>}
                    </>
                  ) : (
                    <span className="sub">{t("notYet")}</span>
                  )}
                </span>
                <span className="r-gap" data-label={t("colGap")}>
                  {!known || !review
                    ? "-"
                    : review.gap_win === null || review.gap_xpts === null
                      ? t("gapNone")
                      : t("gapValue", {
                          win: points(review.gap_win, locale),
                          xpts: `${review.gap_xpts > 0 ? "+" : ""}${decimal(review.gap_xpts, locale, 2)}`,
                        })}
                </span>
                {known && recap && <p className="r-recap">{recap}</p>}
              </li>
            );
          })}
        </ol>
      )}
    </dialog>
  );
}
