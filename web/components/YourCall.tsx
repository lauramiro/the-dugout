import { useEffect, useState } from "react";
import { formatMinute } from "../lib/clock";
import type { DecisionCard as Card, Roster } from "../lib/contracts";
import type { Timed } from "../lib/datasource";
import { VOTE_SECONDS, revealPos, type Vote } from "../lib/calls";
import { playerName } from "../lib/derive";
import type { Translate } from "../lib/i18n";
import { optionLabel } from "./DecisionCard";

const REVEALS_SHOWN = 2;

interface Props {
  card: Timed<Card> | null; // the open card
  cards: Timed<Card>[];
  votes: Record<string, Vote>;
  onVote: (decisionId: string, option: string | null) => void;
  playhead: number;
  firstHalfEnd: number;
  roster: Roster | null;
  t: Translate;
}

/** The model's pick as words; a toss-up says the options are close. */
export function modelCall(card: Card, roster: Roster | null, t: Translate): { label: string; close: boolean } {
  const { recommendation, options } = card.payload;
  const pick = options.find((o) => o.id === recommendation.option_id);
  return {
    label: pick ? optionLabel(pick, card, roster, t) : recommendation.option_id,
    close: recommendation.strength === "toss_up",
  };
}

/** The manager's call as words: the change itself, plus which card option it stands for. */
export function managerCall(card: Card, roster: Roster | null, t: Translate): { label: string; detail: string | null } | null {
  const action = card.payload.manager_action;
  if (!action) return null;
  if (action.subs.length === 0) return { label: t("managerNoChange"), detail: null };
  const label = action.subs
    .map((s) => t("subLine", { off: playerName(roster, s.off), on: playerName(roster, s.on) }))
    .join("; ");
  const later = card.review?.manager?.id === "manager_later" ? card.review.manager.minute : undefined;
  const option = card.payload.options.find((o) => o.id === action.option_id);
  let detail: string | null = null;
  if (later !== undefined) detail = t("managerLater", { minute: `${later}'` });
  else if (option) detail = optionLabel(option, card, roster, t);
  else if (card.payload.trigger !== "manager_sub") detail = t("unpriced");
  return { label, detail };
}

/** You, the model and the manager side by side, once the manager has acted. */
export function CallsBoard({ card, vote, roster, t }: { card: Card; vote: Vote | undefined; roster: Roster | null; t: Translate }) {
  const minute = formatMinute(card.period, card.payload.t_ms);
  const model = modelCall(card, roster, t);
  const manager = managerCall(card, roster, t);
  const voted = vote?.option ? card.payload.options.find((o) => o.id === vote.option) : undefined;
  const agrees = !!voted && !model.close && voted.id === card.payload.recommendation.option_id;
  return (
    <div className="calls" role="group" aria-label={t("theCalls", { minute })}>
      <h3 className="eyebrow">{t("theCalls", { minute })}</h3>
      <div className="calls-row">
        <div className={`call you${agrees ? " agrees" : ""}`}>
          <span className="call-who">{t("you")}</span>
          <span className="call-what">{voted ? optionLabel(voted, card, roster, t) : t("noCall")}</span>
          {vote?.tally && <span className="call-note">{t("crowd", { n: vote.tally.total })}</span>}
        </div>
        <div className="call model">
          <span className="call-who">{t("model")}</span>
          <span className="call-what">{model.label}</span>
          {model.close && <span className="call-note">{t("closeCall")}</span>}
        </div>
        <div className="call manager">
          <span className="call-who">{t("manager")}</span>
          <span className="call-what">{manager ? manager.label : t("notYet")}</span>
          {manager?.detail && <span className="call-note">{manager.detail}</span>}
        </div>
      </div>
    </div>
  );
}

function Countdown({ seconds, t }: { seconds: number; t: Translate }) {
  return (
    <div className="countdown" role="timer" aria-label={t("secondsLeft", { n: seconds })}>
      <span className="led amber">{String(seconds).padStart(2, "0")}</span>
      <span className="countdown-bar" aria-hidden>
        <span style={{ width: `${(seconds / VOTE_SECONDS) * 100}%` }} />
      </span>
    </div>
  );
}

export function YourCall({ card, cards, votes, onVote, playhead, firstHalfEnd, roster, t }: Props) {
  const id = card?.item.payload.decision_id ?? null;
  const vote = id ? votes[id] : undefined;
  // The deadline belongs to one card, so a card that just opened never sees the last one's.
  const [timer, setTimer] = useState<{ id: string; at: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // A fresh 20 s each time a card the viewer has not answered opens; only a new card
  // restarts the timer, so the vote itself is left out of the dependencies.
  useEffect(() => {
    setTimer(id && !vote ? { id, at: Date.now() + VOTE_SECONDS * 1000 } : null);
    setNow(Date.now());
  }, [id]);

  const deadline = timer && timer.id === id ? timer.at : null;
  useEffect(() => {
    if (deadline === null || vote) return;
    const tick = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(tick);
  }, [deadline, vote]);

  const left = deadline === null ? VOTE_SECONDS : Math.max(0, Math.ceil((deadline - now) / 1000));
  useEffect(() => {
    if (id && deadline !== null && !vote && left === 0) onVote(id, null);
  }, [id, deadline, vote, left, onVote]);

  // The newest cards whose calls are all known, among those the viewer answered.
  const reveals = cards
    .map((c) => ({ c, at: revealPos(c, firstHalfEnd) }))
    .filter(({ c, at }) => at !== null && at <= playhead && c.item.payload.decision_id in votes)
    .sort((a, b) => (b.at ?? 0) - (a.at ?? 0) || b.c.pos - a.c.pos)
    .slice(0, REVEALS_SHOWN)
    .map(({ c }) => c);

  if (!card && reveals.length === 0) return null;
  const open = card && !vote;
  const currentRevealed = reveals.some((c) => c.item.payload.decision_id === id);

  return (
    <section className="your-call" aria-label={t("yourCall")}>
      <div className="section-head">
        <h2 className="eyebrow">{t("yourCall")}</h2>
        {open && deadline !== null && <Countdown seconds={left} t={t} />}
      </div>
      {card && open && (
        <>
          <p className="help">{t("yourCallPrompt")}</p>
          <div className="vote-buttons">
            {card.item.payload.options.map((o) => (
              <button key={o.id} className="vote" onClick={() => onVote(card.item.payload.decision_id, o.id)}>
                {optionLabel(o, card.item, roster, t)}
              </button>
            ))}
          </div>
        </>
      )}
      {card && vote && !currentRevealed && (
        <p className="locked" role="status">
          {vote.option === null
            ? t("timeUp")
            : t("lockedIn", {
                option: optionLabel(
                  card.item.payload.options.find((o) => o.id === vote.option) ?? { id: vote.option, label: vote.option },
                  card.item,
                  roster,
                  t,
                ),
              })}{" "}
          <span className="sub">{t("waitingManager")}</span>
        </p>
      )}
      {vote?.error && <p className="help vote-error">{t("voteError", { error: vote.error })}</p>}
      {reveals.map((c) => (
        <CallsBoard key={c.item.payload.decision_id} card={c.item} vote={votes[c.item.payload.decision_id]} roster={roster} t={t} />
      ))}
    </section>
  );
}
