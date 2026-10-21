import { memo } from "react";
import type { Locale, Mode, Roster, Snapshot, SnapshotPlayer, TeamCode } from "../lib/contracts";
import { band, CONDITION_LINE, forecasts, playerName, shirt, teamPlayers, trend, type Trend } from "../lib/derive";
import { pct, type Translate } from "../lib/i18n";

const LINE_PCT = Math.round(CONDITION_LINE * 100);

function TrendArrow({ value }: { value: Trend }) {
  // One glyph rotated: steady points right, falling 45 degrees down, steep straight down.
  const angle = { rising: -45, steady: 0, falling: 45, steep: 90 }[value];
  return (
    <svg className={`trend ${value}`} viewBox="0 0 12 12" aria-hidden>
      <path d="M1.5 6 H9.5 M6.5 3 L9.5 6 L6.5 9" transform={`rotate(${angle} 6 6)`} />
    </svg>
  );
}

interface BarsProps {
  snapshot: Snapshot | null;
  roster: Roster | null;
  teams: TeamCode[];
  mode: Mode;
  locale: Locale;
  flagged: string | null;
  t: Translate;
}

function ConditionRow({ p, roster, mode, locale, flagged, t }: { p: SnapshotPlayer } & Omit<BarsProps, "snapshot" | "teams">) {
  const info = roster?.players[p.id];
  const value = p.condition_est;
  const label = `${playerName(roster, p.id)}: ${value === null ? t("na") : `${pct(value, locale, 0)}%`}`;
  return (
    <li className={`cond-row${p.id === flagged ? " flagged" : ""}`} aria-label={label}>
      <span className="shirt">{shirt(p.id)}</span>
      <span className="who">
        <span className="pname">{playerName(roster, p.id)}</span>
        {info && <span className="role">{info.role}</span>}
      </span>
      {value === null ? (
        <span className="cond-na">{t("na")}</span>
      ) : (
        <>
          <span className={`bar ${band(value)}`}>
            {mode === "analyst" && p.condition_band && (
              <span
                className="band"
                style={{ left: `${p.condition_band[0] * 100}%`, width: `${(p.condition_band[1] - p.condition_band[0]) * 100}%` }}
              />
            )}
            <span className="fill" style={{ width: `${value * 100}%` }} />
            <span className="card-line" style={{ left: `${CONDITION_LINE * 100}%` }} />
          </span>
          <span className="cond-val">{pct(value, locale, 0)}%</span>
          <TrendArrow value={trend(p.trend_per_min)} />
        </>
      )}
    </li>
  );
}

export const ConditionBars = memo(function ConditionBars(props: BarsProps) {
  const { snapshot, roster, teams, t } = props;
  return (
    <section className="conditions" aria-label={t("condition")}>
      <div className="section-head">
        <h2 className="eyebrow">{t("condition")}</h2>
        <span className="legend" aria-hidden>
          <i className="high" />80+ <i className="mid" />{LINE_PCT}-80 <i className="low" />&lt;{LINE_PCT}
        </span>
      </div>
      <p className="help">{t("conditionHelp")}</p>
      <div className="cond-teams">
        {teams.map((team) => (
          <div key={team} className={`cond-team ${team === roster?.home ? "home" : "away"}`}>
            <h3>{roster?.teams[team]?.name ?? team}</h3>
            <ul>
              {snapshot &&
                teamPlayers(snapshot, team).map((p) => <ConditionRow key={p.id} p={p} {...props} />)}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
});

interface ChipsProps {
  snapshot: Snapshot | null;
  roster: Roster | null;
  teams: TeamCode[];
  t: Translate;
}

export const WindowChips = memo(function WindowChips({ snapshot, roster, teams, t }: ChipsProps) {
  if (!snapshot) return null;
  return (
    <section className="windows" aria-label={t("dugout")}>
      {teams.map((team) => (
        <div key={team} className={`window-row ${team === roster?.home ? "home" : "away"}`}>
          <span className="team-tag">{team}</span>
          <span className="chip quiet">{t("subsLeft", { n: snapshot.subs_left[team] ?? 0 })}</span>
          <span className="chip quiet">{t("windowsLeft", { n: snapshot.windows_left[team] ?? 0 })}</span>
          {forecasts(snapshot.players, team)
            .slice(0, 3)
            .map((f) => (
              <span key={f.playerId} className={`chip ${f.minutes === null ? "low" : "mid"}`}>
                {f.minutes === null
                  ? t("below", { name: playerName(roster, f.playerId) })
                  : f.minutes === 0
                    ? t("atLine", { name: playerName(roster, f.playerId) })
                    : t("belowIn", { name: playerName(roster, f.playerId), n: f.minutes })}
              </span>
            ))}
        </div>
      ))}
    </section>
  );
});
