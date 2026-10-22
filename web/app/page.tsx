"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { FieldView, type PlayerTag } from "../components/broadcast/FieldView";
import { FocusCard, GoalFlash, ManagerCall, StatsCard, WhatIf } from "../components/broadcast/Graphics";
import { KickoffSlate, useLiveSchedule } from "../components/broadcast/KickoffSlate";
import {
  AboutPanel, Chrome, GradedPanel, Slate, TitleCard, useTitleCard, type PanelId,
} from "../components/broadcast/Landing";
import { LowerThird } from "../components/broadcast/LowerThird";
import { Worm } from "../components/broadcast/Worm";
import { useHeldCues } from "../components/broadcast/useHeldCues";
import { Scorebug } from "../components/broadcast/Scorebug";
import {
  DEFAULT_PREFS, readPrefs, SettingsChip, writePrefs, type BroadcastPrefs,
} from "../components/broadcast/SettingsChip";
import { Stage } from "../components/broadcast/Stage";
import { DeskView } from "../components/desk/DeskView";
import { FanView } from "../components/fan/FanView";
import { markStorySeen, StoryEnd, StoryIntro, StoryOverlay, StoryScreen, storySeen } from "../components/story/Story";
import { useStory } from "../components/story/useStory";
import { optionLabel } from "../components/DecisionCard";
import type { Vote } from "../lib/calls";
import { aheadPos, fromPos, lastAtOrBefore, toPos } from "../lib/clock";
import type { Locale, Roster, Snapshot } from "../lib/contracts";
import { buildCues, cueSheet, scoreAt, type Cue } from "../lib/cues";
import type { DataSource, FeedState, MatchLog, PitchFrame } from "../lib/datasource";
import { playerName } from "../lib/derive";
import { decimal, translator, type Translate } from "../lib/i18n";
import { ReplayDataSource } from "../lib/replay";
import { buildStory } from "../lib/story";
import { leaveUrl } from "../lib/storyPlayer";
import { useDataSource, useFeed } from "../lib/useFeed";
import { useVotes } from "../lib/useVotes";
import "./broadcast.css";
import "./fan.css";

// The broadcast picture: the match full-bleed from the tracking data, graphics on top, with
// the name, links and chapters around it. The analyst desk is at /desk; /broadcast is kept
// as an alias of this page.

export default function BroadcastPage() {
  const source = useDataSource();
  const feed = useFeed(source);
  const { log, playhead } = feed;
  const live = source.kind === "live";

  const [cuesJson, setCuesJson] = useState(false);
  useEffect(() => setCuesJson(new URLSearchParams(window.location.search).get("cues") === "json"), []);
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
  // The guided story: replay only, and not when the link opens a minute of its own (?t=).
  const [askedMinute, setAskedMinute] = useState(false);
  useEffect(() => setAskedMinute(new URLSearchParams(window.location.search).has("t")), []);
  const steps = useMemo(
    () => (live || askedMinute || feed.status !== "ready" || !log.roster ? null : buildStory(log, { club: log.roster.home, phone: true })),
    [live, askedMinute, feed.status, log],
  );
  const story = useStory(steps, source);
  const [seen, setSeen] = useState(true);
  useEffect(() => setSeen(storySeen()), []);
  const startStory = () => {
    markStorySeen();
    setSeen(true);
    story.send({ type: "start", now: performance.now() });
  };
  const skipStory = () => {
    markStorySeen();
    setSeen(true);
    story.send({ type: "skip-intro" });
  };
  const leaveStory = () => {
    const step = story.step;
    story.send({ type: "leave" });
    source.controls?.pause();
    if (!step) return;
    const url = leaveUrl(step, source.getState().playhead, log.firstHalfEnd);
    if (step.screen === "tv" || step.screen === "end") window.history.replaceState(null, "", url);
    else window.location.assign(url);
  };
  const storyRef = useRef(story);
  useEffect(() => {
    storyRef.current = story;
  });

  useEffect(() => {
    const controls = source.controls;
    if (!controls) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || (e.target as HTMLElement | null)?.closest("button, select, input")) return;
      e.preventDefault();
      const run = storyRef.current;
      if (run.active) run.send({ type: run.state.status === "paused" ? "resume" : "pause", now: performance.now() });
      else if (source.getState().playing) controls.pause();
      else controls.play();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [source]);

  // Your call from the lower third: replay votes stay in the page; live votes also go to the
  // service. A vote during the story moves it on.
  const { votes, castVote: cast } = useVotes(live);
  const castVote = useCallback(
    (id: string, option: string | null) => {
      cast(id, option);
      if (option !== null) storyRef.current.send({ type: "vote", decisionId: id, now: performance.now() });
    },
    [cast],
  );
  const controls = steps ? story.viewerControls : source.controls;
  // The card the story is built around: its vote step names it.
  const storyCardId = steps?.flatMap((s) => (s.wait.kind === "vote" ? [s.wait.decisionId] : []))[0] ?? null;

  // About and How it's graded pause the replay while they are open.
  const [panel, setPanel] = useState<PanelId | null>(null);
  const resume = useRef(false);
  const openPanel = (next: PanelId) => {
    if (panel === null) resume.current = feed.playing;
    if (feed.playing) source.controls?.pause();
    setPanel(next);
  };
  const closePanel = () => {
    setPanel(null);
    if (resume.current) source.controls?.play();
    resume.current = false;
  };

  const pos = useSmoothedPos(playhead, live);
  const recorded = useRecordedTracking(source, log, pos);
  const frame = live ? recorded.frame : source.frameAt(pos);

  const { tMs } = fromPos(pos, log.firstHalfEnd);
  const goals = scoreAt(log, pos);

  const cues = useMemo(() => buildCues(log, prefs.player), [log, prefs.player]);
  const shown = useHeldCues(cues, pos);
  const snapshotAt = lastAtOrBefore(log.snapshots, pos);
  const snapshot = snapshotAt >= 0 ? log.snapshots[snapshotAt].item : null;
  const tags = playerTags(shown, prefs.player, snapshot, frame, log.roster, prefs.locale, t);
  const latest = (kind: Cue["kind"]) => [...shown].reverse().find((c) => c.kind === kind);
  const decision = latest("decision");
  const goalCue = latest("goal");
  const callCue = latest("manager_call");
  const focusCue = latest("focus_event");
  const statsCue = latest("stats");
  // Full time: replay's playhead stops at the end, so the segment shows from there on.
  const whatifCue = cues.find((c) => c.kind === "whatif" && pos >= c.in_pos);
  const decisionCard = decision
    ? log.cards.find((c) => c.item.payload.decision_id === decision.data.decision_id)?.item
    : undefined;
  const fullTime = !live && feed.status === "ready" && playhead >= log.duration;
  const [titleShown, hideTitle] = useTitleCard(!!decision);
  const voteId = decisionCard?.payload.decision_id;
  const onVote = useCallback((option: string | null) => {
    if (voteId) castVote(voteId, option);
  }, [voteId, castVote]);

  // Nothing to draw yet: the files are loading, the live feed has sent nothing, or it failed.
  // Live with a schedule (schedule.json): the kick-off countdown stands in for the waiting slate.
  const schedule = useLiveSchedule(source);
  const liveEmpty = live && log.events.length === 0 && log.snapshots.length === 0;
  const slate = feed.status === "error" ? "error"
    : liveEmpty && !schedule ? "waiting"
    : feed.status === "loading" && !(live && schedule) ? "loading" : null;

  if (cuesJson) return <CueSheetView log={log} focus={prefs.player} source={source.kind} />;

  return (
    <Stage
      label={t("broadcastLabel")}
      chrome={
        <Chrome
          cards={log.cards}
          duration={log.duration}
          feed={feed}
          controls={controls}
          onPanel={openPanel}
          onSeek={hideTitle}
          onStory={steps ? startStory : undefined}
          t={t}
        />
      }
    >
      <FieldView frame={frame} roster={log.roster} tags={tags} label={t("broadcastLabel")} />
      {decisionCard && (
        <LowerThird
          key={decisionCard.payload.decision_id}
          card={decisionCard}
          roster={log.roster}
          mode={prefs.mode}
          locale={prefs.locale}
          vote={votes[decisionCard.payload.decision_id]}
          onVote={onVote}
          running={live || feed.playing}
          t={t}
        />
      )}
      {goalCue && <GoalFlash key={goalCue.id} cue={goalCue} roster={log.roster} t={t} />}
      {callCue && (
        <ManagerCall key={callCue.id} cue={callCue} roster={log.roster} you={viewerCall(callCue, log, votes, t)} t={t} />
      )}
      {statsCue && (
        <StatsCard key={statsCue.id} cue={statsCue} roster={log.roster} locale={prefs.locale} mode={prefs.mode} t={t} />
      )}
      {focusCue && prefs.player && (
        <FocusCard key={focusCue.id} cue={focusCue} focus={prefs.player} roster={log.roster} t={t} />
      )}
      {whatifCue && story.state.status !== "done" && (
        <WhatIf
          leadId={story.active ? storyCardId : null}
          cue={whatifCue}
          cards={log.cards.map((c) => c.item)}
          roster={log.roster}
          locale={prefs.locale}
          mode={prefs.mode}
          t={t}
          next={
            <p className="bc-whatif-next">
              {source.controls && (
                <button type="button" onClick={() => { source.controls?.seek(0); source.controls?.play(); }}>
                  {t("watchAgain")}
                </button>
              )}
              <a href="/desk" onClick={(e) => { e.currentTarget.href = `/desk${window.location.search}`; }}>
                {t("analystDesk")}
              </a>
              <button type="button" onClick={() => openPanel("graded")}>{t("howGraded")}</button>
            </p>
          }
        />
      )}
      <Worm
        winprob={log.winprob}
        cards={log.cards.map((c) => c.pos)}
        playhead={pos}
        duration={log.duration}
        firstHalfEnd={log.firstHalfEnd}
        roster={log.roster}
        club={prefs.club}
        locale={prefs.locale}
        t={t}
      />
      <Scorebug roster={log.roster} score={goals} tMs={tMs} live={live} fullTime={fullTime} club={prefs.club} t={t} />
      {slate && <Slate kind={slate} error={feed.error} t={t} />}
      {live && schedule && feed.status !== "error" && (
        <KickoffSlate schedule={schedule} empty={liveEmpty} locale={prefs.locale} t={t} />
      )}
      {!slate && steps && !seen && story.state.status === "intro" && <StoryIntro onStart={startStory} onSkip={skipStory} t={t} />}
      {!slate && titleShown && !story.active && story.state.status !== "done" && (seen || !steps) && (
        <TitleCard replay={!live} onDone={hideTitle} t={t} />
      )}
      {story.active && story.step?.screen === "tablet" && (
        <StoryScreen device="tablet">
          <DeskView source={source} feed={feed} highlight={story.step.caption.vars.player ? flaggedId(log, story.step) : null} embedded />
        </StoryScreen>
      )}
      {story.active && story.step?.screen === "phone" && log.roster && (
        <StoryScreen device="phone">
          <FanView log={log} playhead={pos} club={log.roster.home} locale={prefs.locale} mode={prefs.mode} votes={votes}
            onVote={castVote} running={feed.playing} leadId={storyCardId} t={t} />
        </StoryScreen>
      )}
      {story.state.status === "done" && (
        <StoryEnd
          onReplay={startStory}
          onClose={() => story.send({ type: "leave" })}
          onPanel={openPanel}
          extra={<a href="/fan">{t("fanView")}</a>}
          t={t}
        />
      )}
      {story.active && story.step && (
        <StoryOverlay step={story.step} state={story.state} total={steps?.length ?? 0} send={story.send} onLeave={leaveStory} t={t} />
      )}
      <SettingsChip
        prefs={prefs}
        onChange={changePrefs}
        roster={log.roster}
        controls={controls}
        feed={feed}
        recordedTracking={recorded.active}
        extra={
          <>
            <button type="button" onClick={() => downloadCueSheet(cueSheet(log, prefs.player, source.kind))}>
              {t("exportCues")}
            </button>
          </>
        }
        t={t}
      />
      {panel === "about" && <AboutPanel onClose={closePanel} onPanel={openPanel} t={t} />}
      {panel === "graded" && <GradedPanel onClose={closePanel} locale={prefs.locale} t={t} />}
    </Stage>
  );
}

/** The story's flagged player: the condition evidence on the card the story is built around. */
function flaggedId(log: MatchLog, step: { startPos: number }): string | null {
  const at = lastAtOrBefore(log.cards, step.startPos);
  const evidence = at >= 0 ? log.cards[at].item.payload.evidence.find((e) => e.type === "condition") : undefined;
  return evidence && evidence.type === "condition" ? evidence.player_id : null;
}

/** The viewer's vote on the card a manager's call cue belongs to, for the reveal; agrees when
 *  it was the model's pick (toss-ups pick nothing). */
function viewerCall(cue: Cue, log: MatchLog, votes: Record<string, Vote>, t: Translate): { label: string; agrees: boolean } | null {
  const id = String(cue.data.decision_id);
  const option = votes[id]?.option;
  const card = log.cards.find((c) => c.item.payload.decision_id === id)?.item;
  const voted = option && card ? card.payload.options.find((o) => o.id === option) : undefined;
  if (!card || !voted) return null;
  const { recommendation } = card.payload;
  return {
    label: optionLabel(voted, card, log.roster, t),
    agrees: recommendation.strength !== "toss_up" && voted.id === recommendation.option_id,
  };
}

/** ?cues=json: the cue sheet as plain JSON instead of the picture, for a graphics system. */
function CueSheetView({ log, focus, source }: { log: MatchLog; focus: string | null; source: "replay" | "live" }) {
  return <pre className="bc-cuesheet">{JSON.stringify(cueSheet(log, focus, source), null, 2)}</pre>;
}

function downloadCueSheet(sheet: ReturnType<typeof cueSheet>): void {
  const blob = new Blob([JSON.stringify(sheet, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cues-${sheet.match_id ?? "match"}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/** The focus player always; a fading player while the cue runs. The ring is the latest
 *  snapshot's condition estimate. */
/** Speed (m/s) above which a tag shows the player's current speed: about 25 km/h. */
const SPEED_SHOW_MS = 7;
/** Speed (m/s) that triggers a tag on any player: 28.8 km/h, about the top 1% of frames. */
const SPEED_TAG_MS = 8;

/** Tags on the pitch, one per player, in this order of precedence: a fading player while the
 *  cue runs, a sprinting player (distance from the sprint event), the focus player always
 *  (running stats from the snapshot), any player above SPEED_TAG_MS. Speed comes from the
 *  tracking frame as given and shows only while the player is fast. */
function playerTags(shown: readonly Cue[], focus: string | null, snapshot: Snapshot | null, frame: PitchFrame | null,
  roster: Roster | null, locale: Locale, t: Translate): PlayerTag[] {
  const stats = (id: string) => snapshot?.players.find((p) => p.id === id);
  const condition = (id: string) => stats(id)?.condition_est ?? null;
  const speed = (id: string) => frame?.players.find((p) => p.id === id)?.v ?? null;
  const kmh = (v: number) => t("speedKmh", { v: decimal(v * 3.6, locale, 1) });
  const tags = new Map<string, PlayerTag>();
  for (const cue of shown) {
    if (cue.kind !== "fading") continue;
    const id = String(cue.data.player_id);
    const value = condition(id) ?? Number(cue.data.condition);
    tags.set(id, { id, label: `${playerName(roster, id)} · ${Math.round(value * 100)}%`, detail: null, ring: value, tone: "fading" });
  }
  for (const cue of shown) {
    if (cue.kind !== "sprint") continue;
    const id = String(cue.data.player_id);
    if (tags.has(id)) continue;
    const v = speed(id);
    const d = Number(cue.data.dist_m);
    tags.set(id, {
      id, label: `${playerName(roster, id)} · ${t("sprintTag", { d: decimal(d, locale, 0) })}`,
      detail: v !== null && v >= SPEED_SHOW_MS ? kmh(v) : null, ring: null, tone: "sprint",
    });
  }
  if (focus && !tags.has(focus)) {
    const p = stats(focus);
    const v = speed(focus);
    const running = p ? t("tagStats", { hsr: p.hsr_m_10m, sprints: p.sprints_10m }) : null;
    const detail = v !== null && v >= SPEED_SHOW_MS ? [kmh(v), running].filter(Boolean).join(" · ") : running;
    tags.set(focus, { id: focus, label: playerName(roster, focus), detail, ring: condition(focus), tone: "focus" });
  }
  for (const p of frame?.players ?? []) {
    if (p.v < SPEED_TAG_MS || tags.has(p.id)) continue;
    tags.set(p.id, { id: p.id, label: `${playerName(roster, p.id)} · ${kmh(p.v)}`, detail: null, ring: null, tone: "sprint" });
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
      setShown(aheadPos(pos, wall, rate, performance.now(), MAX_AHEAD_MS));
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
  const liveMatch = log.snapshots[0]?.item.match_id ?? log.events[0]?.item.match_id;
  const active = !!recorded && !!state && !!liveMatch && liveMatch === state.log.events[0]?.item.match_id;
  return { frame: active ? recorded.frameAt(recPos) : null, active };
}
