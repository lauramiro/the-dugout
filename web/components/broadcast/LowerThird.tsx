import { useEffect, useRef, useState } from "react";
import { VOTE_SECONDS, type Vote } from "../../lib/calls";
import { formatMinute } from "../../lib/clock";
import type { DecisionCard, Locale, Mode, Narration, Roster } from "../../lib/contracts";
import { withNames } from "../../lib/derive";
import { pct, points, strengthKey, triggerKey, type Translate } from "../../lib/i18n";
import { SPEECH_LANG, narrationLocale, speechText } from "../../lib/speech";
import { optionLabel } from "../DecisionCard";

interface Props {
  card: DecisionCard;
  roster: Roster | null;
  mode: Mode;
  locale: Locale;
  /** The viewer's call on this card; undefined until they vote or the timer runs out. */
  vote: Vote | undefined;
  onVote: (option: string | null) => void;
  /** Whether the match clock is running: the vote timer stops while the replay is paused. */
  running: boolean;
  /** Whether keys 1 to 4 vote here; off while a story screen (tablet, phone) covers the picture. */
  keys?: boolean;
  /** Opens how the line was written (the narration workflow's trace). */
  onTrace?: () => void;
  t: Translate;
}

/** The viewer's version; English of the same mode, then English casual, while the others arrive. */
function narrationFor(card: DecisionCard, locale: Locale, mode: Mode): Narration | undefined {
  return card.narration[locale]?.[mode] ?? card.narration.en?.[mode] ?? card.narration.en?.casual;
}

/** The decision as a lower third: what triggered it, the model's line, the options as bars.
 *  The rows are the viewer's vote too (click, or keys 1 to 4) for VOTE_SECONDS of running
 *  clock. A manager_sub card is raised by the change itself, so there is nothing to call. */
export function LowerThird({ card, roster, mode, locale, vote, onVote, running, keys = true, onTrace, t }: Props) {
  const { payload } = card;
  const narration = narrationFor(card, locale, mode);
  const pick = payload.recommendation.option_id;
  const votable = payload.trigger !== "manager_sub";
  const open = votable && !vote;
  const left = useVoteTimer(open && running, () => onVote(null));

  useEffect(() => {
    if (!open || !keys) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
      if ((e.target as HTMLElement | null)?.closest("input, select, textarea, dialog")) return;
      const option = payload.options[Number(e.key) - 1];
      if (!option || !/^[1-9]$/.test(e.key)) return;
      e.preventDefault();
      onVote(option.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, keys, payload.options, onVote]);

  const chosen = vote?.option ? payload.options.find((o) => o.id === vote.option) : undefined;
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
          <p className="bc-lower-credit">
            {t(narration.source === "model" ? "creditModel" : "creditTemplate")}
            {onTrace && narration.trace && narration.trace.length > 0 && (
              <button type="button" onClick={onTrace}>{t("traceOpen")}</button>
            )}
            <ReadAloud text={speechText(narration, roster)} lang={SPEECH_LANG[narrationLocale(card, locale, mode)]} t={t} />
          </p>
        </div>
      )}
      <ol className={`bc-options${open ? " voting" : ""}`}>
        {payload.options.map((o, i) => (
          <li key={o.id}>
            <button
              type="button"
              className={`bc-option${o.id === pick ? " bc-pick" : ""}${o.id === vote?.option ? " bc-voted" : ""}`}
              // aria-disabled, not disabled: a disabled button drops the focus, so after a vote it would land on the
              // page; this way it stays on the option just chosen
              aria-disabled={!open}
              tabIndex={votable ? undefined : -1}
              aria-pressed={votable ? o.id === vote?.option : undefined}
              aria-keyshortcuts={open ? String(i + 1) : undefined}
              onClick={() => open && onVote(o.id)}
            >
              {open && <kbd className="bc-option-key">{i + 1}</kbd>}
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
                  // label and range on their own lines: the gap column is narrow and does not wrap
                  <span className="bc-option-ci">
                    <span>{t("ci90")}</span> <span>{points(o.ci90[0], locale)} / {points(o.ci90[1], locale)}</span>
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {open && (
        <p className="bc-lower-call">
          <span>{t("voteKeys", { n: payload.options.length })}</span>
          <span className="bc-lower-timer" role="timer" aria-live="off">{t("secondsLeft", { n: left })}</span>
        </p>
      )}
      {votable && vote && (
        <p className="bc-lower-call done" role="status">
          {chosen ? t("lockedIn", { option: optionLabel(chosen, card, roster, t) }) : t("timeUp")}
          {vote.tally && ` · ${t("crowd", { n: vote.tally.total })}`}
        </p>
      )}
    </section>
  );
}

/** Whole seconds left of VOTE_SECONDS, counting only while `running`; calls onDone at zero. */
export function useVoteTimer(running: boolean, onDone: () => void): number {
  const [leftMs, setLeftMs] = useState(VOTE_SECONDS * 1000);
  useEffect(() => {
    if (!running) return;
    let last = performance.now();
    const tick = setInterval(() => {
      const now = performance.now();
      setLeftMs((ms) => Math.max(0, ms - (now - last)));
      last = now;
    }, 250);
    return () => clearInterval(tick);
  }, [running]);
  const done = leftMs === 0;
  useEffect(() => {
    if (running && done) onDone();
  }, [running, done, onDone]);
  return Math.ceil(leftMs / 1000);
}

/** Reads the card's line with the browser's speech, where it has one; stops when the card closes or its line
 *  changes (another language or view). */
function ReadAloud({ text, lang, t }: { text: string; lang: string; t: Translate }) {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  // The utterance in flight: cancel() ends the old one asynchronously, and only the current one may say it is done.
  const current = useRef<SpeechSynthesisUtterance | null>(null);
  useEffect(() => setSupported(typeof window !== "undefined" && "speechSynthesis" in window), []);
  useEffect(() => () => {
    if (current.current) window.speechSynthesis.cancel();
    current.current = null;
    setSpeaking(false);
  }, [text, lang]);
  if (!supported) return null;
  const toggle = () => {
    const synth = window.speechSynthesis;
    synth.cancel();
    if (speaking) {
      current.current = null;
      return setSpeaking(false);
    }
    const line = new SpeechSynthesisUtterance(text);
    line.lang = lang;
    line.onend = line.onerror = () => {
      if (current.current === line) {
        current.current = null;
        setSpeaking(false);
      }
    };
    current.current = line;
    setSpeaking(true);
    synth.speak(line);
  };
  return <button type="button" aria-pressed={speaking} onClick={toggle}>{t(speaking ? "readStop" : "readAloud")}</button>;
}
