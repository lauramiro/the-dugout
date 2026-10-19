"use client";

import { useMemo } from "react";
import { DecisionCard } from "../components/DecisionCard";
import { ConditionBars, WindowChips } from "../components/Dugout";
import { Pitch } from "../components/Pitch";
import { Controls, Scoreboard, Ticker } from "../components/MatchZone";
import { fromPos, lastAtOrBefore } from "../lib/clock";
import type { DecisionCard as Card, Locale, Mode } from "../lib/contracts";
import { score, tickerEvents } from "../lib/derive";
import { translator } from "../lib/i18n";
import { useDataSource, useFeed } from "../lib/useFeed";

const TICKER_LENGTH = 8;

export default function Page() {
  const source = useDataSource();
  const feed = useFeed(source);
  const { log, playhead, status } = feed;
  const { roster } = log;
  const locale: Locale = "en";
  const mode: Mode = "casual";
  const t = translator(locale);

  const teams = useMemo(() => (roster ? [roster.home, roster.away] : []), [roster]);
  const { period, tMs } = fromPos(playhead, log.firstHalfEnd);
  const finished = source.kind === "replay" && status === "ready" && playhead >= log.duration;

  const evIdx = lastAtOrBefore(log.events, playhead);
  const goals = useMemo(() => score(log.events, evIdx, teams), [log.events, evIdx, teams]);
  const ticker = useMemo(() => tickerEvents(log.events, evIdx, TICKER_LENGTH), [log.events, evIdx]);

  const snapIdx = lastAtOrBefore(log.snapshots, playhead);
  const snapshot = snapIdx >= 0 ? log.snapshots[snapIdx].item : null;

  // One open card at a time: the latest one the playhead has reached.
  const cardIdx = lastAtOrBefore(log.cards, playhead);
  const card: Card | null = cardIdx >= 0 ? log.cards[cardIdx].item : null;
  const cardSnapIdx = cardIdx >= 0 ? lastAtOrBefore(log.snapshots, log.cards[cardIdx].pos) : -1;
  const cardSnapshot = cardSnapIdx >= 0 ? log.snapshots[cardSnapIdx].item : null;
  const flagged = card?.payload.evidence.find((e) => e.type === "condition");
  const flaggedId = flagged && flagged.type === "condition" ? flagged.player_id : null;
  const focus = roster?.home ?? "";

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
          <Pitch frame={source.frameAt(playhead)} roster={roster} highlight={flaggedId} label={t("pitch")} />
          {status !== "ready" && (
            <div className="pitch-status" role="status">
              {status === "error" ? t("loadError", { error: feed.error ?? "" }) : source.kind === "live" ? t("waitingLive") : t("loading")}
            </div>
          )}
        </div>
        <Controls controls={source.controls} playing={feed.playing} speed={feed.speed} finished={finished} t={t} />
        <Ticker events={ticker} roster={roster} t={t} />
      </section>

      <aside className="dugout" aria-label={t("dugout")}>
        <DecisionCard card={card} snapshot={cardSnapshot} roster={roster} focus={focus} mode={mode} locale={locale} t={t} />
        <WindowChips snapshot={snapshot} roster={roster} teams={teams} t={t} />
        <ConditionBars snapshot={snapshot} roster={roster} teams={teams} mode={mode} locale={locale} flagged={flaggedId} t={t} />
      </aside>

      <p className="foot">{t("demoNote")}</p>
    </main>
  );
}
