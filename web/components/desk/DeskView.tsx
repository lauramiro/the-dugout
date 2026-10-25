"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DecisionCard } from "../DecisionCard";
import { ConditionBars, WindowChips } from "../Dugout";
import { ModeSwitcher, type Settings } from "../ModeSwitcher";
import { Pitch } from "../Pitch";
import { Timeline } from "../Timeline";
import { Controls, Scoreboard, Ticker } from "../MatchZone";
import { Review } from "../Review";
import { YourCall } from "../YourCall";
import type { Vote } from "../../lib/calls";
import { fromPos, lastAtOrBefore } from "../../lib/clock";
import type { DecisionCard as Card, Locale, Mode } from "../../lib/contracts";
import type { DataSource, FeedState, PlaybackControls } from "../../lib/datasource";
import { benchAt } from "../../lib/bench";
import { score, tickerEvents } from "../../lib/derive";
import { LOCALES, translator } from "../../lib/i18n";
import { useVotes } from "../../lib/useVotes";

const TICKER_LENGTH = 8;
const SETTINGS_KEY = "dugout.settings";

// Per-viewer preference only; the page works the same without storage.
function readSettings(): Partial<Settings> {
  try {
    const raw = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? "{}") as Record<string, unknown>;
    const out: Partial<Settings> = {};
    if (raw.mode === "casual" || raw.mode === "analyst") out.mode = raw.mode;
    if (LOCALES.includes(raw.locale as Locale)) out.locale = raw.locale as Locale;
    if (typeof raw.focus === "string") out.focus = raw.focus;
    return out;
  } catch {
    return {};
  }
}

function writeSettings(settings: Settings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // storage blocked: keep the choice for this visit only
  }
}

interface DeskViewProps {
  source: DataSource;
  feed: FeedState;
  /** Picked out in the condition list (the story's flagged player); without it, the open card's. */
  highlight?: string | null;
  /** Inside the story: no page links and no replay controls of its own (the story drives the playhead). */
  embedded?: boolean;
  /** Inside the story: the page's votes, so a call on the tablet is the story's call. */
  votes?: Record<string, Vote>;
  onVote?: (id: string, option: string | null) => void;
  /** Inside the story: the story-aware controls, so a timeline click leaves the story. */
  controls?: PlaybackControls | null;
  /** Inside the story: the TV's language and mode. */
  locale?: Locale;
  mode?: Mode;
}

/** The analyst desk: the match, the decision card, the dugout panel and the timeline, on any data source. */
export function DeskView(props: DeskViewProps) {
  const { source, feed, highlight = null, embedded = false } = props;
  const { log, playhead, status } = feed;
  const { roster } = log;
  const [settings, setSettings] = useState<Settings>({ mode: "casual", focus: "", locale: "en" });
  useEffect(() => {
    // ?lang= and ?club= from a link (leaving the story passes the viewer's) win over storage
    const q = new URLSearchParams(window.location.search);
    const lang = q.get("lang");
    const club = q.get("club");
    setSettings((s) => ({
      ...s, ...readSettings(),
      ...(LOCALES.includes(lang as Locale) ? { locale: lang as Locale } : {}),
      ...(club ? { focus: club } : {}),
    }));
  }, []);
  useEffect(() => {
    if (!embedded) document.documentElement.lang = settings.locale; // embedded: the host page owns <html lang>
  }, [embedded, settings.locale]);
  const changeSettings = (next: Settings) => {
    setSettings(next);
    writeSettings(next);
  };
  const mode = props.mode ?? settings.mode;
  const locale = props.locale ?? settings.locale;
  const t = useMemo(() => translator(locale), [locale]);

  // The focus club is listed first in the dugout panel.
  const teams = useMemo(() => {
    if (!roster) return [];
    return settings.focus === roster.away ? [roster.away, roster.home] : [roster.home, roster.away];
  }, [roster, settings.focus]);
  const { period, tMs } = fromPos(playhead, log.firstHalfEnd);
  const finished = source.kind === "replay" && status === "ready" && playhead >= log.duration;

  const evIdx = lastAtOrBefore(log.events, playhead);
  const goals = useMemo(() => score(log.events, evIdx, teams), [log.events, evIdx, teams]);
  const ticker = useMemo(() => tickerEvents(log.events, evIdx, TICKER_LENGTH), [log.events, evIdx]);

  const snapIdx = lastAtOrBefore(log.snapshots, playhead);
  const snapshot = snapIdx >= 0 ? log.snapshots[snapIdx].item : null;
  const bench = useMemo(
    () => Object.fromEntries(teams.map((team) => [team, benchAt(log, playhead, team)])),
    [log, playhead, teams],
  );

  // One open card at a time: the latest one the playhead has reached.
  const cardIdx = lastAtOrBefore(log.cards, playhead);
  const card: Card | null = cardIdx >= 0 ? log.cards[cardIdx].item : null;
  const cardSnapIdx = cardIdx >= 0 ? lastAtOrBefore(log.snapshots, log.cards[cardIdx].pos) : -1;
  const cardSnapshot = cardSnapIdx >= 0 ? log.snapshots[cardSnapIdx].item : null;
  const flagged = card?.payload.evidence.find((e) => e.type === "condition");
  const flaggedId = highlight ?? (flagged && flagged.type === "condition" ? flagged.player_id : null);
  const focus = roster && settings.focus in roster.teams ? settings.focus : (roster?.home ?? "");
  const allGoals = useMemo(() => log.events.filter((e) => e.item.type === "goal"), [log.events]);

  // Your call: the desk's own votes, or the host page's inside the story.
  const own = useVotes(source.kind === "live");
  const votes = props.votes ?? own.votes;
  const castVote = props.onVote ?? own.castVote;

  // The review opens by itself once at full time, and from its button at any point.
  const [reviewOpen, setReviewOpen] = useState(false);
  const shownAtFullTime = useRef(false);
  useEffect(() => {
    if (finished && !shownAtFullTime.current) {
      shownAtFullTime.current = true;
      setReviewOpen(true);
    }
    if (!finished) shownAtFullTime.current = false;
  }, [finished]);

  // The story picks a player out: bring his row into view once each time it changes.
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    if (highlight) root.current?.querySelector(".cond-row.flagged")?.scrollIntoView({ block: "nearest" });
  }, [highlight, snapshot !== null]);

  return (
    <main ref={root} className={`screen${embedded ? " embedded" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <h1>The Dugout</h1>
          <span className="tagline">{t("tagline")}</span>
        </div>
        <div className="topbar-actions">
          {!embedded && <ModeSwitcher settings={{ ...settings, focus }} roster={roster} onChange={changeSettings} t={t} />}
          {!embedded && (
            <>
              <a className="review-open" href="/" onClick={(e) => { e.currentTarget.href = `/${window.location.search}`; }}>
                {t("broadcastView")}
              </a>
              <button className="review-open" onClick={() => setReviewOpen(true)} disabled={status !== "ready"}>
                {finished ? t("review") : t("openReview")}
              </button>
            </>
          )}
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
        {!embedded && <Controls controls={source.controls} playing={feed.playing} speed={feed.speed} finished={finished} t={t} />}
        <Ticker events={ticker} roster={roster} t={t} />
      </section>

      <aside className="dugout" tabIndex={0} aria-label={t("dugout")}>
        <DecisionCard key={card?.payload.decision_id} card={card} snapshot={cardSnapshot} roster={roster} focus={focus} mode={mode} locale={locale} t={t} />
        <YourCall
          card={cardIdx >= 0 ? log.cards[cardIdx] : null}
          cards={log.cards}
          votes={votes}
          onVote={castVote}
          playhead={playhead}
          firstHalfEnd={log.firstHalfEnd}
          roster={roster}
          t={t}
        />
        <WindowChips snapshot={snapshot} roster={roster} teams={teams} bench={bench} t={t} />
        <ConditionBars snapshot={snapshot} roster={roster} teams={teams} mode={mode} locale={locale} flagged={flaggedId} t={t} />
      </aside>

      <Timeline
        winprob={log.winprob}
        goals={allGoals}
        cards={log.cards}
        playhead={playhead}
        duration={log.duration}
        firstHalfEnd={log.firstHalfEnd}
        roster={roster}
        focus={focus}
        onSeek={(props.controls !== undefined ? props.controls : source.controls)?.seek ?? null}
        t={t}
      />

      <p className="foot">{t("demoNote")}</p>

      <Review
        open={reviewOpen}
        onClose={() => setReviewOpen(false)}
        cards={log.cards}
        votes={votes}
        playhead={playhead}
        firstHalfEnd={log.firstHalfEnd}
        finished={finished}
        roster={roster}
        locale={locale}
        mode={mode}
        t={t}
      />
    </main>
  );
}
