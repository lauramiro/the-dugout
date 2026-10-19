import { memo } from "react";
import { formatMinute } from "../lib/clock";
import type { DecisionCard as Card, DecisionOption, Evidence, Locale, Mode, Roster, Snapshot, TeamCode } from "../lib/contracts";
import { playerName, shirt } from "../lib/derive";
import { decimal, pct, points, strengthKey, triggerKey, type StringKey, type Translate } from "../lib/i18n";

interface Props {
  card: Card | null;
  snapshot: Snapshot | null; // the snapshot at the card's moment, for the analyst evidence list
  roster: Roster | null;
  focus: TeamCode;
  mode: Mode;
  locale: Locale;
  t: Translate;
}

function conditionPlayer(card: Card): string | null {
  const ev = card.payload.evidence.find((e) => e.type === "condition");
  return ev && ev.type === "condition" ? ev.player_id : null;
}

function optionLabel(o: DecisionOption, card: Card, roster: Roster | null, t: Translate): string {
  const known: Record<string, StringKey> = {
    no_change: "opt_no_change",
    sub_like_for_like: "opt_sub_like_for_like",
    attacking: "opt_attacking",
    defensive: "opt_defensive",
  };
  const key = known[o.id];
  if (!key) return o.label;
  return t(key, { name: playerName(roster, conditionPlayer(card)) });
}

function channelSide(channel: string): "left" | "centre" | "right" {
  const side = channel.split("_").pop();
  return side === "left" || side === "right" ? side : "centre";
}

function EvidenceChip({ ev, roster, locale, t }: { ev: Evidence; roster: Roster | null; locale: Locale; t: Translate }) {
  if (ev.type === "condition") {
    return (
      <li className="chip evidence">
        {t("ev_condition", { name: playerName(roster, ev.player_id), pct: `${pct(ev.value, locale, 0)}%` })}
        <span className="sub"> · {t("ev_trend", { v: points(ev.trend_per_min, locale) })}</span>
      </li>
    );
  }
  return (
    <li className="chip evidence">
      {t("ev_flank", { side: t(`side_${channelSide(ev.channel)}` as StringKey), pct: `${pct(ev.share, locale, 0)}%` })}
    </li>
  );
}

/** The fourth official's board: minute in amber, the flagged player's number in red. */
function Board({ minute, number, label }: { minute: string; number: string | null; label: string }) {
  return (
    <div className="board" aria-label={label}>
      <span className="led amber">{minute}</span>
      {number && <span className="led red">{number.padStart(2, "0")}</span>}
    </div>
  );
}

export const DecisionCard = memo(function DecisionCard({ card, snapshot, roster, focus, mode, locale, t }: Props) {
  if (!card) {
    return (
      <section className="decision empty" aria-label={t("decision")}>
        <h2 className="eyebrow">{t("decision")}</h2>
        <p>{t("noDecision")}</p>
      </section>
    );
  }
  const { payload } = card;
  const minute = formatMinute(card.period, payload.t_ms);
  const flagged = conditionPlayer(card);
  const narration = card.narration[locale]?.[mode] ?? card.narration.en?.[mode];
  const strength = payload.recommendation.strength;
  const ours = payload.team === focus;
  const best = payload.recommendation.option_id;
  const flaggedStats = flagged ? snapshot?.players.find((p) => p.id === flagged) : undefined;
  const rates = snapshot?.rates[payload.team];

  return (
    <section className={`decision ${payload.team === roster?.home ? "home" : "away"}`} aria-label={t("decision")}>
      <header className="decision-head">
        <Board minute={minute.replace("'", "")} number={flagged ? shirt(flagged) : null} label={`${minute} ${t(triggerKey(payload.trigger))}`} />
        <div className="decision-meta">
          <span className="eyebrow">
            {t("decision")} · {ours ? t("yourClub") : t("opponent")}
          </span>
          <span className="trigger">{t(triggerKey(payload.trigger))}</span>
          <span className="team-name">{roster?.teams[payload.team]?.name ?? payload.team}</span>
        </div>
        <span className={`strength ${strength}`} title={t("strengthTitle")}>
          {t(strengthKey(strength))}
        </span>
      </header>

      {narration && (
        <div className="narration">
          <p className="headline">{narration.headline}</p>
          <p className="reason">{narration.reason}</p>
        </div>
      )}

      <h3 className="eyebrow">{t("options")}</h3>
      <ul className="options">
        {payload.options.map((o) => {
          const ref = o.id === "no_change";
          return (
            <li key={o.id} className={`option${o.id === best ? " best" : ""}`}>
              <div className="option-top">
                <span className="option-label">
                  {optionLabel(o, card, roster, t)}
                  {o.id === best && <span className="pick">{t("modelPick")}</span>}
                </span>
                <span className="option-win">
                  {pct(o.win, locale)}%<span className="unit"> {t("win").toLowerCase()}</span>
                </span>
              </div>
              <div className="option-bar" aria-hidden>
                <span style={{ width: `${o.win * 100}%` }} />
              </div>
              <div className="option-foot">
                <span className={`gap${o.delta_win > 0 ? " up" : o.delta_win < 0 ? " down" : ""}`}>
                  {ref ? t("reference") : `${points(o.delta_win, locale)} ${t("pts")}`}
                </span>
                {mode === "analyst" && (
                  <span className="analyst-nums">
                    {o.ci90 && (
                      <span>
                        {t("ci90")} {points(o.ci90[0], locale)} / {points(o.ci90[1], locale)}
                      </span>
                    )}
                    <span>
                      {t("draw")} {pct(o.draw, locale)}% · {t("loss")} {pct(o.loss, locale)}% · {t("xpts")} {decimal(o.xpts, locale, 2)}
                    </span>
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <h3 className="eyebrow">{t("evidence")}</h3>
      <ul className="chips">
        {payload.evidence.map((ev, i) => (
          <EvidenceChip key={i} ev={ev} roster={roster} locale={locale} t={t} />
        ))}
      </ul>

      {mode === "analyst" && (
        <dl className="evidence-list">
          {flaggedStats && (
            <>
              <dt>{t("hsr")}</dt>
              <dd>
                {flaggedStats.hsr_m_10m} m <span className="sub">({t("baseline", { v: `${flaggedStats.baseline_hsr_m_10m} m` })})</span>
              </dd>
              <dt>{t("sprints")}</dt>
              <dd>
                {flaggedStats.sprints_10m} <span className="sub">({t("baseline", { v: flaggedStats.baseline_sprints_10m })})</span>
              </dd>
            </>
          )}
          {rates && (
            <>
              <dt>{t("rates")}</dt>
              <dd>{t("ratesValue", { for: decimal(rates.for90, locale, 2), against: decimal(rates.against90, locale, 2) })}</dd>
            </>
          )}
          {narration && (
            <>
              <dt>{t("narrationSource")}</dt>
              <dd>{t(narration.source === "model" ? "source_model" : "source_template")}</dd>
            </>
          )}
        </dl>
      )}
    </section>
  );
});
