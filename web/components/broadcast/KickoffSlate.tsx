import { useEffect, useState, useSyncExternalStore } from "react";
import type { Locale } from "../../lib/contracts";
import type { DataSource } from "../../lib/datasource";
import type { Translate } from "../../lib/i18n";
import { LiveDataSource } from "../../lib/live";
import { countdown, kickoff, type Schedule } from "../../lib/schedule";

// Live only: between scheduled replays of the demo match, the next kick-off and a countdown;
// after a kick-off, until the first message arrives, that the match is under way. Nothing when
// the deployment has no schedule.json (the page shows its plain waiting slate instead).

const noSubscribe = () => () => {};
const noSchedule = () => null;

/** The live source's schedule once schedule.json has loaded; null for a replay or without one. */
export function useLiveSchedule(source: DataSource): Schedule | null {
  const live = source instanceof LiveDataSource ? source : null;
  return useSyncExternalStore(live?.subscribe ?? noSubscribe, () => live?.schedule ?? null, noSchedule);
}

export function KickoffSlate({ schedule, empty, locale, t }: {
  schedule: Schedule;
  /** Nothing has arrived from this match yet. */
  empty: boolean;
  locale: Locale;
  t: Translate;
}) {
  const [now, setNow] = useState<number | null>(null);
  // When this page started listening: a judge who arrives mid-match is joining until the first message lands.
  const [connectedAt] = useState(() => Date.now());
  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [schedule]);
  if (now === null) return null;

  const k = kickoff(schedule, now, empty, connectedAt);
  if (k.kind === "on" && !empty) return null;
  const time = (ms: number) => new Date(ms).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return (
    <div className="bc-kickoff" role="status">
      {k.kind === "next" ? (
        <>
          <p className="bc-kickoff-label">{t("nextKickoff")}</p>
          <p className="bc-kickoff-time">{time(k.at)}</p>
          <p className="bc-kickoff-in">{t("kickoffIn", { countdown: countdown(k.at - now) })}</p>
        </>
      ) : (
        <p className="bc-kickoff-label">{t("kickoffJoining", { time: time(k.since) })}</p>
      )}
      <p className="bc-kickoff-note">{t("liveSchedule", { n: schedule.every_min, speed: schedule.speed })}</p>
      <a className="bc-kickoff-replay" href="/">{t("watchReplay")}</a>
    </div>
  );
}
