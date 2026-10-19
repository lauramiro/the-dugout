"use client";

import { useMemo } from "react";
import { Pitch } from "../components/Pitch";
import { Controls, Scoreboard, Ticker } from "../components/MatchZone";
import { fromPos, lastAtOrBefore } from "../lib/clock";
import { score, tickerEvents } from "../lib/derive";
import { translator } from "../lib/i18n";
import { useDataSource, useFeed } from "../lib/useFeed";

const TICKER_LENGTH = 8;

export default function Page() {
  const source = useDataSource();
  const feed = useFeed(source);
  const { log, playhead, status } = feed;
  const { roster } = log;
  const t = translator("en");

  const teams = useMemo(() => (roster ? [roster.home, roster.away] : []), [roster]);
  const { period, tMs } = fromPos(playhead, log.firstHalfEnd);
  const finished = source.kind === "replay" && status === "ready" && playhead >= log.duration;

  const evIdx = lastAtOrBefore(log.events, playhead);
  const goals = useMemo(() => score(log.events, evIdx, teams), [log.events, evIdx, teams]);
  const ticker = useMemo(() => tickerEvents(log.events, evIdx, TICKER_LENGTH), [log.events, evIdx]);

  return (
    <main className="screen">
      <header className="topbar">
        <div className="brand">
          <h1>The Dugout</h1>
          <span className="tagline">{t("tagline")}</span>
        </div>
      </header>

      <section className="match" aria-label={roster ? `${roster.teams[roster.home].name} v ${roster.teams[roster.away].name}` : undefined}>
        <Scoreboard roster={roster} score={goals} period={period} tMs={tMs} finished={finished} t={t} />
        <div className="pitch-wrap">
          <Pitch frame={source.frameAt(playhead)} roster={roster} highlight={null} label={t("pitch")} />
          {status !== "ready" && (
            <div className="pitch-status" role="status">
              {status === "error" ? t("loadError", { error: feed.error ?? "" }) : source.kind === "live" ? t("waitingLive") : t("loading")}
            </div>
          )}
        </div>
        <Controls controls={source.controls} playing={feed.playing} speed={feed.speed} finished={finished} t={t} />
        <Ticker events={ticker} roster={roster} t={t} />
      </section>

      <p className="foot">{t("demoNote")}</p>
    </main>
  );
}
