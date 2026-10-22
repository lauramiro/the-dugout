import { benchAt } from "../../lib/bench";
import type { Snapshot } from "../../lib/contracts";
import type { MatchLog } from "../../lib/datasource";
import type { Translate } from "../../lib/i18n";

/** Shown by name; the rest of the bench is a count. */
const SHOWN = 4;

/** One strip per club, under the scorebug (home) and under the settings chip (away): who has not
 *  played yet, and the subs and windows left. */
export function Bench({ log, pos, snapshot, t }: { log: MatchLog; pos: number; snapshot: Snapshot | null; t: Translate }) {
  const roster = log.roster;
  if (!roster || !snapshot) return null;
  return (
    <>
      {[roster.home, roster.away].map((club, i) => {
        const bench = benchAt(log, pos, club);
        const more = bench.length - SHOWN;
        return (
          <aside key={club} className={`bc-bench ${i === 0 ? "home" : "away"}`} aria-label={t("benchOf", { team: roster.teams[club]?.name ?? club })}>
            <p className="bc-bench-head">
              <b>{club}</b> {t("onTheBench")}
              <span>{t("subsLeft", { n: snapshot.subs_left[club] ?? 0 })} · {t("windowsLeft", { n: snapshot.windows_left[club] ?? 0 })}</span>
            </p>
            <p className="bc-bench-names">
              {bench.slice(0, SHOWN).map((p) => `${p.name} ${p.role}`).join(", ")}
              {more > 0 && ` ${t("andMore", { n: more })}`}
            </p>
          </aside>
        );
      })}
    </>
  );
}
