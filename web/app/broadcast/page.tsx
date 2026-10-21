"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { FieldView, type PlayerTag } from "../../components/broadcast/FieldView";
import { LowerThird } from "../../components/broadcast/LowerThird";
import { useHeldCues } from "../../components/broadcast/useHeldCues";
import { Scorebug } from "../../components/broadcast/Scorebug";
import {
  DEFAULT_PREFS, readPrefs, SettingsChip, writePrefs, type BroadcastPrefs,
} from "../../components/broadcast/SettingsChip";
import { Stage } from "../../components/broadcast/Stage";
import { fromPos, lastAtOrBefore, toPos } from "../../lib/clock";
import type { Roster, Snapshot } from "../../lib/contracts";
import { buildCues, type Cue } from "../../lib/cues";
import type { DataSource, FeedState, MatchLog, PitchFrame } from "../../lib/datasource";
import { playerName, score } from "../../lib/derive";
import { translator } from "../../lib/i18n";
import { ReplayDataSource } from "../../lib/replay";
import { useDataSource, useFeed } from "../../lib/useFeed";
import "./broadcast.css";

// The broadcast picture: the match full-bleed from the tracking data, graphics on top.
// The analyst desk stays at /.

export default function BroadcastPage() {
  const source = useDataSource();
  const feed = useFeed(source);
  const { log, playhead } = feed;
  const live = source.kind === "live";

  const [prefs, setPrefs] = useState<BroadcastPrefs>(DEFAULT_PREFS);
  useEffect(() => setPrefs((p) => ({ ...p, ...readPrefs() })), []);
  useEffect(() => {
    document.documentElement.lang = prefs.locale;
  }, [prefs.locale]);
  const changePrefs = (next: BroadcastPrefs) => {
    setPrefs(next);
    writePrefs(next);
  };
  const t = useMemo(() => translator(prefs.locale), [prefs.locale]);

  // A broadcast runs on its own: replay starts once loaded; space pauses and resumes.
  const started = useRef(false);
  useEffect(() => {
    if (started.current || feed.status !== "ready" || !source.controls) return;
    started.current = true;
    source.controls.play();
  }, [feed.status, source]);
  useEffect(() => {
    const controls = source.controls;
    if (!controls) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || (e.target as HTMLElement | null)?.closest("button, select, input")) return;
      e.preventDefault();
      if (source.getState().playing) controls.pause();
      else controls.play();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [source]);

  const pos = useSmoothedPos(playhead, live);
  const recorded = useRecordedTracking(source, log, pos);
  const frame = live ? recorded.frame : source.frameAt(pos);

  const { tMs } = fromPos(pos, log.firstHalfEnd);
  const teams = log.roster ? [log.roster.home, log.roster.away] : [];
  const goals = score(log.events, lastAtOrBefore(log.events, pos), teams);

  const cues = useMemo(() => buildCues(log, prefs.player), [log, prefs.player]);
  const shown = useHeldCues(cues, pos);
  const snapshotAt = lastAtOrBefore(log.snapshots, pos);
  const snapshot = snapshotAt >= 0 ? log.snapshots[snapshotAt].item : null;
  const tags = playerTags(shown, prefs.player, snapshot, log.roster);
  const decision = [...shown].reverse().find((c) => c.kind === "decision");
  const decisionCard = decision
    ? log.cards.find((c) => c.item.payload.decision_id === decision.data.decision_id)?.item
    : undefined;

  return (
    <Stage label={t("broadcastLabel")}>
      <FieldView frame={frame} roster={log.roster} tags={tags} label={t("broadcastLabel")} />
      {decisionCard && (
        <LowerThird
          key={decisionCard.payload.decision_id}
          card={decisionCard}
          roster={log.roster}
          mode={prefs.mode}
          locale={prefs.locale}
          t={t}
        />
      )}
      <Scorebug roster={log.roster} score={goals} tMs={tMs} live={live} club={prefs.club} t={t} />
      <SettingsChip
        prefs={prefs}
        onChange={changePrefs}
        roster={log.roster}
        controls={source.controls}
        feed={feed}
        recordedTracking={recorded.active}
        t={t}
      />
    </Stage>
  );
}

/** The focus player always; a fading player while the cue runs. The ring is the latest
 *  snapshot's condition estimate. */
function playerTags(shown: readonly Cue[], focus: string | null, snapshot: Snapshot | null, roster: Roster | null): PlayerTag[] {
  const condition = (id: string) => snapshot?.players.find((p) => p.id === id)?.condition_est ?? null;
  const tags = new Map<string, PlayerTag>();
  for (const cue of shown) {
    if (cue.kind !== "fading") continue;
    const id = String(cue.data.player_id);
    const value = condition(id) ?? Number(cue.data.condition);
    tags.set(id, { id, label: `${playerName(roster, id)} · ${Math.round(value * 100)}%`, ring: value, tone: "fading" });
  }
  if (focus && !tags.has(focus)) {
    tags.set(focus, { id: focus, label: playerName(roster, focus), ring: condition(focus), tone: "focus" });
  }
  return [...tags.values()];
}

const MAX_RATE = 30; // match ms per wall ms: above the fastest replay speed (20x)
const MAX_AHEAD_MS = 3000; // never draw further than this past the last message

/** Replay: the playhead as is. Live: the playhead only moves when a message arrives, so
 *  between messages the picture runs on at the rate the last messages came in. */
function useSmoothedPos(playhead: number, live: boolean): number {
  const last = useRef({ pos: playhead, wall: 0, rate: 0 });
  const [shown, setShown] = useState(playhead);
  useEffect(() => {
    if (!live) return;
    const now = performance.now();
    const prev = last.current;
    const dt = now - prev.wall;
    const rate = prev.wall && dt > 0 ? Math.min(MAX_RATE, Math.max(0, (playhead - prev.pos) / dt)) : prev.rate;
    last.current = { pos: playhead, wall: now, rate: prev.wall ? rate * 0.5 + prev.rate * 0.5 : 0 };
  }, [playhead, live]);
  useEffect(() => {
    if (!live) return;
    let raf = 0;
    const tick = () => {
      const { pos, wall, rate } = last.current;
      setShown(pos + Math.min(rate * (performance.now() - wall), rate * MAX_AHEAD_MS));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [live]);
  return live ? shown : playhead;
}

const noSubscribe = () => () => {};
const noState = () => null;

/** Live: no tracking comes over Web PubSub, so when the live match is the recorded demo match,
 *  draw the recorded tracking at the live clock (and say so in the settings). */
function useRecordedTracking(source: DataSource, log: MatchLog, pos: number): { frame: PitchFrame | null; active: boolean } {
  const recorded = useMemo(() => (source.kind === "live" ? new ReplayDataSource() : null), [source]);
  useEffect(() => {
    if (!recorded) return;
    recorded.start();
    return () => recorded.dispose();
  }, [recorded]);
  const state: FeedState | null = useSyncExternalStore(
    recorded?.subscribe ?? noSubscribe, recorded?.getState ?? noState, recorded?.getState ?? noState,
  );
  // The live log does not know where the first half ended; map through (period, t_ms).
  const { period, tMs } = fromPos(pos, log.firstHalfEnd);
  const recPos = state ? toPos(period, tMs, state.log.firstHalfEnd) : 0;
  const bucket = Math.floor(recPos / 5000);
  useEffect(() => {
    recorded?.controls.seek(bucket * 5000); // load the tracking chunk under the live clock first
  }, [recorded, bucket]);
  const liveMatch = log.events[0]?.item.match_id;
  const active = !!recorded && !!state && !!liveMatch && liveMatch === state.log.events[0]?.item.match_id;
  return { frame: active ? recorded.frameAt(recPos) : null, active };
}
