import { memo } from "react";
import { formatClock, formatMinute } from "../lib/clock";
import type { MatchEvent, Roster } from "../lib/contracts";
import { SPEEDS, type PlaybackControls, type Speed, type Timed } from "../lib/datasource";
import { playerName } from "../lib/derive";
import type { StringKey, Translate } from "../lib/i18n";

interface ScoreboardProps {
  roster: Roster | null;
  score: Record<string, number>;
  period: 1 | 2;
  tMs: number;
  finished: boolean;
  t: Translate;
}

export function Scoreboard({ roster, score, period, tMs, finished, t }: ScoreboardProps) {
  if (!roster) return <div className="scoreboard placeholder" />;
  const { home, away } = roster;
  return (
    <div className="scoreboard">
      <div className="team home">
        <span className="kit" aria-hidden />
        <span className="name full">{roster.teams[home].name}</span>
        <span className="name code">{home}</span>
      </div>
      <div className="score" aria-live="polite" aria-atomic>
        <span>{score[home] ?? 0}</span>
        <span className="sep" aria-hidden>:</span>
        <span>{score[away] ?? 0}</span>
      </div>
      <div className="team away">
        <span className="name full">{roster.teams[away].name}</span>
        <span className="name code">{away}</span>
        <span className="kit" aria-hidden />
      </div>
      <div className="clock">
        <span className="led">{formatClock(tMs)}</span>
        <span className="half">{finished ? t("fullTime") : t(period === 1 ? "half1" : "half2")}</span>
      </div>
    </div>
  );
}

interface ControlsProps {
  controls: PlaybackControls | null;
  playing: boolean;
  speed: Speed;
  finished: boolean;
  t: Translate;
}

export function Controls({ controls, playing, speed, finished, t }: ControlsProps) {
  if (!controls) {
    return (
      <div className="controls">
        <span className="source-badge live">{t("live")}</span>
      </div>
    );
  }
  return (
    <div className="controls">
      <span className="source-badge">{t("replay")}</span>
      <button
        className="play"
        onClick={playing ? controls.pause : controls.play}
        aria-label={playing ? t("pause") : finished ? t("restart") : t("play")}
      >
        {playing ? (
          <svg viewBox="0 0 16 16" aria-hidden><rect x="3" y="2" width="3.5" height="12" /><rect x="9.5" y="2" width="3.5" height="12" /></svg>
        ) : (
          <svg viewBox="0 0 16 16" aria-hidden><path d="M4 2 L14 8 L4 14 Z" /></svg>
        )}
        <span>{playing ? t("pause") : finished ? t("restart") : t("play")}</span>
      </button>
      <div className="segmented" role="group" aria-label={t("speed")}>
        {SPEEDS.map((s) => (
          <button key={s} aria-pressed={speed === s} onClick={() => controls.setSpeed(s)}>
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
}

interface TickerProps {
  events: Timed<MatchEvent>[];
  roster: Roster | null;
  t: Translate;
}

function describe(e: MatchEvent, roster: Roster | null, t: Translate): { title: string; detail: string } {
  const name = playerName(roster, e.player_id);
  switch (e.type) {
    case "goal":
      return { title: t("goal"), detail: name };
    case "shot":
      return { title: t(`shot_${e.outcome}` as StringKey), detail: name };
    case "sub":
      return { title: t("sub"), detail: t("subLine", { off: name, on: playerName(roster, e.player_in_id) }) };
    default:
      return { title: t("card"), detail: name };
  }
}

export const Ticker = memo(function Ticker({ events, roster, t }: TickerProps) {
  return (
    <section className="ticker" aria-label={t("ticker")}>
      <h2 className="eyebrow">{t("ticker")}</h2>
      {events.length === 0 ? (
        <p className="empty">{t("noEvents")}</p>
      ) : (
        <ol>
          {events.map(({ item: e }) => {
            const { title, detail } = describe(e, roster, t);
            const home = roster ? e.team === roster.home : true;
            return (
              <li key={e.seq} className={`${e.type}${home ? " home" : " away"}`}>
                <span className="minute">{formatMinute(e.period, e.t_ms)}</span>
                <span className="mark" aria-hidden />
                <span className="what">{title}</span>
                <span className="who">
                  {detail}
                  {roster && <span className="team-code"> {e.team}</span>}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
});
