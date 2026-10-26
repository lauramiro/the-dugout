"use client";

import { useEffect, type ReactNode } from "react";
import { VOTE_SECONDS, type Vote } from "../../lib/calls";
import { formatClock, fromPos } from "../../lib/clock";
import type { DecisionCard, Locale, Mode, Roster, TeamCode } from "../../lib/contracts";
import { scoreAt } from "../../lib/cues";
import type { MatchLog, Timed } from "../../lib/datasource";
import { withNames } from "../../lib/derive";
import { fanMoment, type FanContext } from "../../lib/fan";
import { pct, points, strengthKey, triggerKey, type StringKey, type Translate } from "../../lib/i18n";
import { useVoteTimer } from "../broadcast/LowerThird";
import { optionLabel } from "../DecisionCard";
import { TraceDetails } from "../TraceSteps";

interface Props {
  log: MatchLog;
  playhead: number;
  club: TeamCode;
  locale: Locale;
  mode: Mode;
  votes: Record<string, Vote>;
  onVote: (decisionId: string, option: string | null) => void;
  /** Whether the match clock runs: the vote timer stops while the replay is paused. */
  running: boolean;
  /** The decision to lead the full-time row with (the story's card); else the largest gap. */
  leadId?: string | null;
  /** Controls above the moment (the standalone page's club picker and replay buttons). */
  header?: ReactNode;
  t: Translate;
}

/** The fan's phone: the score, then what the manager is weighing on the club's open card, the
 *  vote, the manager's call when it comes, and the What if at full time. */
export function FanView({ log, playhead, club, locale, mode, votes, onVote, running, leadId = null, header, t }: Props) {
  const { roster } = log;
  const moment = fanMoment(log, playhead, club, locale, mode);
  const goals = scoreAt(log, playhead);
  const { tMs } = fromPos(playhead, log.firstHalfEnd);
  const teams = roster ? [roster.home, roster.away] : [];
  return (
    <main className="fan">
      {header}
      <header className="fan-score">
        {teams.map((team, i) => (
          <span key={team} className={`fan-team ${i === 0 ? "home" : "away"}${team === club ? " mine" : ""}`}>
            {team} <b>{goals[team] ?? 0}</b>
          </span>
        ))}
        <span className="fan-clock">{moment.kind === "full-time" ? t("fullTimeShort") : formatClock(tMs)}</span>
      </header>
      {moment.kind === "waiting" && <p className="fan-waiting">{t("noDecision")}</p>}
      {moment.kind === "decision" && (
        <Decision key={moment.context.decisionId} card={moment.card} c={moment.context} roster={roster} locale={locale}
          mode={mode} vote={votes[moment.context.decisionId]} onVote={onVote} running={running} t={t} />
      )}
      {moment.kind === "call" && (
        <Call card={moment.card.item} c={moment.context} manager={moment.manager} model={moment.model}
          vote={votes[moment.context.decisionId]} roster={roster} t={t} />
      )}
      {moment.kind === "full-time" && <FullTime log={log} club={club} leadId={leadId} locale={locale} mode={mode} t={t} />}
    </main>
  );
}

function Decision({ card, c, roster, locale, mode, vote, onVote, running, t }: {
  card: Timed<DecisionCard>; c: FanContext; roster: Roster | null; locale: Locale; mode: Mode;
  vote: Vote | undefined; onVote: (decisionId: string, option: string | null) => void; running: boolean; t: Translate;
}) {
  const payload = card.item.payload;
  const votable = c.trigger !== "manager_sub";
  const open = votable && !vote;
  const left = useVoteTimer(open && running, () => onVote(c.decisionId, null));
  const teamName = roster?.teams[payload.team]?.name ?? payload.team;
  // keys 1-4 vote here too, as on the TV
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.ctrlKey || e.metaKey || e.altKey || !/^[1-9]$/.test(e.key)) return;
      const option = payload.options[Number(e.key) - 1];
      if (!option) return;
      e.preventDefault();
      onVote(c.decisionId, option.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, payload.options, onVote, c.decisionId]);
  const chosen = vote?.option ? payload.options.find((o) => o.id === vote.option) : undefined;

  return (
    <section className="fan-card" aria-label={t("decision")}>
      <p className="fan-card-head">
        <span className="fan-minute">{c.minute}</span>
        <span>{t(triggerKey(c.trigger))}</span>
        <span className={`fan-strength ${c.strength}`}>{t(strengthKey(c.strength))}</span>
      </p>
      {c.narration && <h2 className="fan-headline">{withNames(c.narration.headline, roster)}</h2>}
      {c.narration && <p className="fan-reason">{withNames(c.narration.reason, roster)}</p>}
      {c.narration && <TraceDetails narration={c.narration} roster={roster} t={t} />}

      {c.player && (
        <div className="fan-block">
          <h3>{t("fanWho")}</h3>
          <p className="fan-big">
            {c.player.name} <b>{pct(c.player.condition, locale, 0)}%</b>
            <span className={`fan-trend ${c.player.trend}`}>{t(`trend_${c.player.trend}` as StringKey)}</span>
          </p>
          {c.player.rank !== null && (
            <p className="fan-note">
              {c.player.rank === 1
                ? t("fanRankLowest", { of: c.player.of, team: teamName })
                : t("fanRank", { rank: c.player.rank, of: c.player.of, team: teamName })}
            </p>
          )}
        </div>
      )}

      <div className="fan-block">
        <h3>{t("fanWhyNow")}</h3>
        <p>{t(triggerKey(c.trigger))}</p>
        {c.flankShare !== null && c.flankSide && (
          <p className="fan-note">{t("ev_flank", { side: t(`side_${c.flankSide}` as StringKey), pct: `${pct(c.flankShare, locale, 0)}%` })}</p>
        )}
      </div>

      <div className="fan-block">
        <h3>{t("fanOptions")}</h3>
        {c.strength === "toss_up" && <p className="fan-note">{t("fanTossUp")}</p>}
        <ol className="fan-options">
          {c.options.map((o, i) => {
            const option = payload.options.find((p) => p.id === o.id)!;
            const ci = option.ci90;
            return (
              <li key={o.id}>
                <button type="button" className={`fan-option${o.pick ? " is-pick" : ""}${vote?.option === o.id ? " is-voted" : ""}`}
                  aria-disabled={!open} aria-pressed={votable ? vote?.option === o.id : undefined} onClick={() => open && onVote(c.decisionId, o.id)}>
                  {open && <kbd>{i + 1}</kbd>}
                  <span className="fan-option-name">
                    {optionLabel(option, card.item, roster, t)}
                    {o.pick && <em>{t("modelPick")}</em>}
                  </span>
                  <span className="fan-option-win">{pct(o.win, locale, mode === "analyst" ? 1 : 0)}%</span>
                  <span className="fan-option-gap">
                    {o.id === "no_change" ? "" : `${points(o.deltaWin, locale)} ${t("pts")}`}
                    {mode === "analyst" && ci && o.id !== "no_change" && (
                      <small> {t("ci90")} {points(ci[0], locale)} / {points(ci[1], locale)}</small>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        {open && <p className="fan-vote-hint">{t("voteKeys", { n: payload.options.length })} <b>{t("secondsLeft", { n: left })}</b></p>}
        {votable && vote && <p className="fan-vote-hint done">{chosen ? t("lockedIn", { option: optionLabel(chosen, card.item, roster, t) }) : t("timeUp")}</p>}
      </div>

      <div className="fan-block">
        <h3>{t("fanBench")}</h3>
        <p>{c.ready.length ? c.ready.map((p) => `${p.name} (${p.role})`).join(", ") : t("fanNoneOnBench")}</p>
        <p className="fan-note">{t("subsLeft", { n: c.subsLeft })} · {t("windowsLeft", { n: c.windowsLeft })}</p>
      </div>
    </section>
  );
}

function Call({ card, c, manager, model, vote, roster, t }: {
  card: DecisionCard; c: FanContext; manager: string | null; model: string; vote: Vote | undefined; roster: Roster | null; t: Translate;
}) {
  const label = (id: string | null | undefined) => {
    const option = id ? card.payload.options.find((o) => o.id === id) : undefined;
    return option ? optionLabel(option, card, roster, t) : t("managerNoChange");
  };
  const subs = card.payload.manager_action?.subs ?? [];
  const names = (id: string) => roster?.players[id]?.name ?? id;
  return (
    <section className="fan-card" aria-label={t("fanCallTitle")}>
      <p className="fan-card-head"><span className="fan-minute">{c.minute}</span><span>{t("fanCallTitle")}</span></p>
      <h2 className="fan-headline">{subs.length ? subs.map((s) => t("subLine", { off: names(s.off), on: names(s.on) })).join("; ") : label(manager)}</h2>
      <dl className="fan-calls">
        <div><dt>{t("manager")}</dt><dd>{label(manager)}</dd></div>
        <div><dt>{t("fanModel")}</dt><dd>{c.strength === "toss_up" ? t("strength_toss_up") : label(model)}</dd></div>
        <div>
          <dt>{t("fanYou")}</dt>
          <dd>
            {vote?.option ? label(vote.option) : t("fanNoVote")}
            {vote?.option && c.strength !== "toss_up" && vote.option === model && <em> {t("fanSame")}</em>}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function FullTime({ log, club, leadId, locale, mode, t }: {
  log: MatchLog; club: TeamCode; leadId: string | null; locale: Locale; mode: Mode; t: Translate;
}) {
  const priced = log.cards
    .map((c) => c.item)
    .filter((c) => c.payload.team === club && c.payload.trigger !== "manager_sub" && c.review && c.review.gap_win !== null);
  const lead = priced.find((c) => c.payload.decision_id === leadId)
    ?? [...priced].sort((a, b) => (b.review!.gap_win ?? 0) - (a.review!.gap_win ?? 0))[0];
  const recap = lead?.review?.recap[locale]?.[mode] ?? lead?.review?.recap.en?.[mode];
  return (
    <section className="fan-card" aria-label={t("whatIf")}>
      <p className="fan-card-head"><span>{t("fanFullTime")}</span><span>{t("whatIf")}</span></p>
      {lead && lead.review ? (
        <>
          <p className="fan-big"><b>{points(lead.review.gap_win ?? 0, locale)} {t("pts")}</b></p>
          {recap && <p className="fan-reason">{withNames(recap, log.roster)}</p>}
        </>
      ) : (
        <p className="fan-waiting">{t("noDecisionsYet")}</p>
      )}
    </section>
  );
}
