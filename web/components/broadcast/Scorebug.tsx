import { formatClock } from "../../lib/clock";
import type { Roster, TeamCode } from "../../lib/contracts";
import type { Translate } from "../../lib/i18n";

interface Props {
  roster: Roster | null;
  score: Record<TeamCode, number>;
  tMs: number;
  live: boolean;
  club: TeamCode | null;
  t: Translate;
}

/** Top-left scorebug: clubs, score and the running clock, always on. */
export function Scorebug({ roster, score, tMs, live, club, t }: Props) {
  const teams = roster ? [roster.home, roster.away] : [];
  return (
    <div className="bc-scorebug" aria-live="off">
      {teams.length === 0 && <span className="bc-sb-team">—</span>}
      {teams.map((team, i) => (
        <span key={team} className={`bc-sb-side ${i === 0 ? "home" : "away"}${club === team ? " fav" : ""}`}>
          <span className="bc-sb-team" title={roster?.teams[team]?.name}>{team}</span>
          <span className="bc-sb-goals">{score[team] ?? 0}</span>
        </span>
      ))}
      <span className="bc-sb-clock">{formatClock(tMs)}</span>
      <span className={`bc-sb-source${live ? " live" : ""}`}>{live ? t("live") : t("replay")}</span>
    </div>
  );
}
