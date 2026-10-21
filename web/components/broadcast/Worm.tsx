import { toPos } from "../../lib/clock";
import type { Locale, Roster, TeamCode, WinProbPoint } from "../../lib/contracts";
import type { Timed } from "../../lib/datasource";
import { pct, type Translate } from "../../lib/i18n";

interface Props {
  winprob: readonly Timed<WinProbPoint>[];
  cards: readonly number[];
  playhead: number;
  duration: number;
  firstHalfEnd: number;
  roster: Roster | null;
  club: TeamCode | null;
  locale: Locale;
  t: Translate;
}

const FULL_MATCH_MS = 96 * 60_000;

/** Win probability along the bottom edge, for the favourite club or else the home club. The
 *  points are the home side's; the away side's win is the point's `loss`, as given. */
export function Worm({ winprob, cards, playhead, duration, firstHalfEnd, roster, club, locale, t }: Props) {
  if (!roster || winprob.length === 0) return null;
  const team = club === roster.away ? roster.away : roster.home;
  const value = (p: WinProbPoint) => (team === roster.home ? p.win : p.loss);
  const span = Math.max(duration, toPos(2, FULL_MATCH_MS, firstHalfEnd));
  const shown = winprob.filter((w) => w.pos <= playhead);
  if (shown.length === 0) return null;
  const x = (pos: number) => (pos / span) * 100;
  const y = (v: number) => (1 - v) * 20;
  const path = shown.map((w, i) => `${i ? "L" : "M"}${x(w.pos).toFixed(2)} ${y(value(w.item)).toFixed(2)}`).join(" ");
  const now = value(shown[shown.length - 1].item);
  return (
    <div className={`bc-worm ${team === roster.home ? "home" : "away"}`}>
      <span className="bc-worm-label">
        {team} {t("win").toLowerCase()} <strong>{pct(now, locale, 0)}%</strong>
      </span>
      <svg viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">
        <line x1="0" y1="10" x2="100" y2="10" className="bc-worm-mid" />
        {cards.filter((c) => c <= playhead).map((c) => (
          <line key={c} x1={x(c)} y1="0" x2={x(c)} y2="20" className="bc-worm-card" />
        ))}
        <path d={path} className="bc-worm-line" />
      </svg>
    </div>
  );
}
