import type { ReactNode } from "react";
import type { Cue } from "../../lib/cues";
import type { DecisionCard, Locale, Mode, Roster, TeamCode } from "../../lib/contracts";
import { playerName, withNames } from "../../lib/derive";
import { decimal, pct, points, type StringKey, type Translate } from "../../lib/i18n";
import { managerCall, modelCall } from "../YourCall";

// The short-lived graphics: goal flash, manager's call, focus card and the full-time
// "What if". Each reads one cue's data as given and formats it.

export function GoalFlash({ cue, roster, t }: { cue: Cue; roster: Roster | null; t: Translate }) {
  const team = String(cue.data.team);
  const score = cue.data.score as Record<TeamCode, number>;
  const teams = roster ? [roster.home, roster.away] : Object.keys(score);
  return (
    <div className={`bc-goal ${team === roster?.home ? "home" : "away"}`} role="status">
      <span className="bc-goal-word">{t("goal")}</span>
      <span className="bc-goal-scorer">
        {roster?.teams[team]?.name ?? team} · {playerName(roster, cue.data.player_id as string | null)}
      </span>
      <span className="bc-goal-score">{teams.map((tm) => `${tm} ${score[tm] ?? 0}`).join("  ")}</span>
    </div>
  );
}

interface Sub {
  off: string | null;
  on: string | null;
}

/** `you`: the viewer's own call on the card, when they made one; `agrees` when it was the model's pick. */
export function ManagerCall({ cue, roster, you, t }: {
  cue: Cue; roster: Roster | null; you?: { label: string; agrees: boolean } | null; t: Translate;
}) {
  const subs = (cue.data.subs as Sub[]) ?? [];
  const matched = cue.data.matched as boolean | null;
  const team = String(cue.data.team);
  return (
    <aside className={`bc-call ${team === roster?.home ? "home" : "away"}`} role="status">
      <p className="bc-call-title">{t("managersCall")} · {roster?.teams[team]?.name ?? team}</p>
      {subs.length === 0 && (
        <p className="bc-call-line">{cue.data.no_change ? t("opt_no_change") : t("changeMade")}</p>
      )}
      {subs.map((s, i) => (
        <p key={i} className="bc-call-line">
          {t("subLine", { off: playerName(roster, s.off), on: playerName(roster, s.on) })}
        </p>
      ))}
      {matched !== null && (
        <p className={`bc-call-verdict${matched ? " same" : ""}`}>
          {matched ? t("sameAsModel") : t("differentCall")}
          {" · "}
          {t("minutesAfterCard", { n: Number(cue.data.minutes_after) })}
        </p>
      )}
      {you && <p className={`bc-call-you${you.agrees ? " same" : ""}`}>{t("youCalled", { option: you.label })}</p>}
    </aside>
  );
}

const EVENT_KEYS: Record<string, StringKey> = { goal: "goal", sub: "sub", shot: "shot", foul: "foul" };

export function FocusCard({ cue, focus, roster, t }: { cue: Cue; focus: string; roster: Roster | null; t: Translate }) {
  const type = String(cue.data.type);
  const cameOn = type === "sub" && cue.data.player_in_id === focus;
  return (
    <aside className="bc-focus" role="status">
      <span className="bc-focus-name">{playerName(roster, focus)}</span>
      <span className="bc-focus-event">{cameOn ? t("comesOn") : t(EVENT_KEYS[type] ?? "goal")}</span>
    </aside>
  );
}

interface Passes {
  passes: number;
  avg_m: number;
  longest_m: number;
  forward: number;
}

interface Running {
  sprints: number;
  longest_sprint_m: number;
  fast_m: number;
}

interface Side {
  passes: Passes;
  running: Running;
}

/** Every 15 minutes: the focus player's passing and running, or both teams'. Counts and
 *  distances from the events as given; casual shows the headline rows only. */
export function StatsCard({ cue, roster, locale, mode, t }: {
  cue: Cue; roster: Roster | null; locale: Locale; mode: Mode; t: Translate;
}) {
  const sides: [string, Side][] = cue.data.scope === "player"
    ? [[playerName(roster, cue.data.player_id as string), cue.data as unknown as Side]]
    : Object.entries(cue.data.teams as Record<string, Side>);
  const ht = cue.id === "stats:ht";
  const minute = cue.id.split("-")[1];
  const m = (v: number) => `${decimal(v, locale, 1)} m`;
  const share = (p: Passes) => (p.passes ? `${pct(p.forward / p.passes, locale, 0)}%` : "-");
  const rows: [StringKey, (s: Side) => string, boolean][] = [
    ["statPasses", (s) => String(s.passes.passes), true],
    ["statForward", (s) => share(s.passes), true],
    ["statAvgLength", (s) => m(s.passes.avg_m), false],
    ["statLongest", (s) => m(s.passes.longest_m), false],
    ["statSprints", (s) => String(s.running.sprints), true],
    ["statLongestSprint", (s) => m(s.running.longest_sprint_m), false],
    ["statFast", (s) => `${s.running.fast_m} m`, true],
  ];
  return (
    <aside className="bc-stats" role="status">
      <p className="bc-stats-title">{ht ? t("statsHalfTime") : t("statsAt", { m: minute })}</p>
      <table>
        <thead>
          <tr>
            <th />
            {sides.map(([name]) => <th key={name} scope="col">{name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.filter(([, , casual]) => casual || mode === "analyst").map(([key, value]) => (
            <tr key={key}>
              <th scope="row">{t(key)}</th>
              {sides.map(([name, side]) => <td key={name}>{value(side)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  );
}

const WHATIF_ROWS = 5;

interface Row {
  decision_id: string;
  minute: number;
  label: string;
  gap_win: number | null;
}

/** Full time: each decision the review priced, the largest gap first and large. */
export function WhatIf({ cue, cards, roster, locale, mode, t, next }: {
  cue: Cue; cards: readonly DecisionCard[]; roster: Roster | null; locale: Locale; mode: Mode; t: Translate;
  /** Next steps under the rows. */
  next?: ReactNode;
}) {
  const rows = (cue.data.rows as Row[]) ?? [];
  const lead = cue.data.lead as string | null;
  // The lead first, then the next largest gaps; a TV graphic has room for five lines.
  const ordered = [...rows]
    .sort((a, b) => Number(b.decision_id === lead) - Number(a.decision_id === lead) || (b.gap_win ?? -1) - (a.gap_win ?? -1))
    .slice(0, WHATIF_ROWS);
  return (
    <section className="bc-whatif" aria-label={t("whatIf")}>
      <h2 className="bc-whatif-title">{t("whatIf")}</h2>
      <ol className="bc-whatif-rows">
        {ordered.map((row) => {
          const card = cards.find((c) => c.payload.decision_id === row.decision_id);
          if (!card) return null;
          const model = modelCall(card, roster, t);
          const manager = managerCall(card, roster, t);
          const recap = card.review?.recap[locale]?.[mode] ?? card.review?.recap.en?.[mode];
          return (
            <li key={row.decision_id} className={`bc-whatif-row${row.decision_id === lead ? " lead" : ""}`}>
              <span className="bc-whatif-minute">{row.label}</span>
              <span className="bc-whatif-calls">
                <span><em>{t("model")}</em> {model.label}</span>
                <span><em>{t("manager")}</em> {manager ? manager.label : t("notYet")}</span>
              </span>
              <span className="bc-whatif-gap">
                {row.gap_win === null ? "" : `${points(row.gap_win, locale)} ${t("pts")}`}
              </span>
              {row.decision_id === lead && recap && <p className="bc-whatif-recap">{withNames(recap, roster)}</p>}
            </li>
          );
        })}
      </ol>
      {next}
    </section>
  );
}
