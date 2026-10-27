"use client";

import { useEffect, useMemo, useState } from "react";
import { KickoffSlate, useLiveSchedule } from "../../components/broadcast/KickoffSlate";
import { FanView } from "../../components/fan/FanView";
import type { Locale, Mode, TeamCode } from "../../lib/contracts";
import { SPEEDS } from "../../lib/datasource";
import { LOCALES, translator } from "../../lib/i18n";
import { useDataSource, useFeed, useLinkedMinute, usePlayOnLoad } from "../../lib/useFeed";
import { useVotes } from "../../lib/useVotes";
import "../fan.css";

// The fan's phone on its own: one club's cards with their context and the vote, on the replay
// (or ?source=live). The guided story on / shows the same view inside a phone.

interface FanPrefs {
  club: TeamCode | null;
  mode: Mode;
  locale: Locale;
}

const PREFS_KEY = "dugout.fan";

function readPrefs(): Partial<FanPrefs> {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Record<string, unknown>;
    const out: Partial<FanPrefs> = {};
    if (typeof raw.club === "string") out.club = raw.club;
    if (raw.mode === "casual" || raw.mode === "analyst") out.mode = raw.mode;
    if (LOCALES.includes(raw.locale as Locale)) out.locale = raw.locale as Locale;
    return out;
  } catch {
    return {};
  }
}

/** ?club= and ?lang= from a link (leaving the story passes the viewer's): they win over storage. */
function fromUrl(): Partial<FanPrefs> {
  const q = new URLSearchParams(window.location.search);
  const out: Partial<FanPrefs> = {};
  const club = q.get("club");
  const lang = q.get("lang");
  if (club) out.club = club;
  if (LOCALES.includes(lang as Locale)) out.locale = lang as Locale;
  return out;
}

function writePrefs(prefs: FanPrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // storage blocked: keep the choice for this visit only
  }
}

export default function FanPage() {
  const source = useDataSource();
  const feed = useFeed(source);
  // Opened on its own it plays like a broadcast; a link to a minute (leaving the story) waits for the viewer.
  usePlayOnLoad(source, feed, useLinkedMinute() !== false);
  const { log, playhead, status } = feed;
  const live = source.kind === "live";
  const schedule = useLiveSchedule(source);
  const { votes, castVote } = useVotes(live);
  const [prefs, setPrefs] = useState<FanPrefs>({ club: null, mode: "casual", locale: "en" });
  useEffect(() => setPrefs((p) => ({ ...p, ...readPrefs(), ...fromUrl() })), []);
  useEffect(() => {
    document.documentElement.lang = prefs.locale;
  }, [prefs.locale]);
  const set = (patch: Partial<FanPrefs>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    writePrefs(next);
  };
  const t = useMemo(() => translator(prefs.locale), [prefs.locale]);
  const roster = log.roster;
  const club = roster && prefs.club && prefs.club in roster.teams ? prefs.club : (roster?.home ?? "");
  const controls = source.controls;

  const header = (
    <nav className="fan-nav" aria-label={t("fanView")}>
      <span className="fan-brand">The Dugout</span>
      <span className="fan-about">{t("fanAbout")}</span>
      {roster && (
        <label className="fan-pick">
          <span>{t("fanClub")}</span>
          <select value={club} onChange={(e) => set({ club: e.target.value })}>
            {[roster.home, roster.away].map((team) => <option key={team} value={team}>{roster.teams[team]?.name ?? team}</option>)}
          </select>
        </label>
      )}
      <span className="fan-toggles">
        {(["casual", "analyst"] as const).map((m) => (
          <button key={m} type="button" aria-pressed={prefs.mode === m} onClick={() => set({ mode: m })}>{t(m)}</button>
        ))}
        {LOCALES.map((l) => (
          <button key={l} type="button" aria-pressed={prefs.locale === l} onClick={() => set({ locale: l })}>{l.toUpperCase()}</button>
        ))}
      </span>
      {controls && status === "ready" && (
        <span className="fan-toggles">
          <button type="button" onClick={() => (feed.playing ? controls.pause() : controls.play())}>
            {feed.playing ? t("pause") : t("play")}
          </button>
          {SPEEDS.map((s) => (
            <button key={s} type="button" aria-pressed={feed.speed === s} onClick={() => controls.setSpeed(s)}>{s}x</button>
          ))}
        </span>
      )}
      <a className="fan-link" href="/">{t("broadcastView")}</a>
    </nav>
  );

  // Live keeps its frame while it connects; a feed that never connected says so (it keeps retrying).
  if (status === "error" || (status !== "ready" && !live)) {
    return (
      <main className="fan">
        {header}
        <p className="fan-waiting" role={status === "error" ? "alert" : "status"}>
          {status === "error" ? t("loadError", { error: feed.error ?? "" }) : t("loading")}
        </p>
      </main>
    );
  }
  const liveEmpty = live && log.events.length === 0 && log.snapshots.length === 0;
  const kickoff = live && schedule
    ? <KickoffSlate schedule={schedule} empty={liveEmpty} locale={prefs.locale} t={t} className="fan-kickoff" replayHref="/fan" />
    : null;
  return (
    <FanView log={log} playhead={playhead} club={club} locale={prefs.locale} mode={prefs.mode} votes={votes}
      onVote={castVote} running={live || feed.playing} header={header} live={live} kickoff={kickoff} t={t} />
  );
}
