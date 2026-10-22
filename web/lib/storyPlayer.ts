// Runs the guided story: what the guide does on each tick, vote or viewer action. Pure, so the
// rules (advance, pause keeps the held time, a viewer who takes the controls leaves the story)
// are tested without a browser; components/story/useStory.ts applies the commands.

import { fromPos } from "./clock.ts";
import type { StoryStep } from "./story.ts";

export interface StoryState {
  status: "intro" | "playing" | "paused" | "left" | "done";
  index: number;
  /** Wall time the current step's clock last started. */
  stepStartedAt: number;
  /** Wall time already spent on the current step before the last pause. */
  elapsedMs: number;
  /** Cards the viewer has voted on during this run: their vote steps are passed over. */
  voted: readonly string[];
}

export type StoryEvent =
  | { type: "start"; now: number }
  | { type: "skip-intro" }
  | { type: "tick"; now: number; playhead: number }
  | { type: "vote"; decisionId: string; now: number }
  | { type: "pause"; now: number }
  | { type: "resume"; now: number }
  | { type: "next"; now: number }
  | { type: "viewer-seek" }
  | { type: "viewer-speed" }
  /** The page's own Play and Pause buttons (and the panels, which pause the replay). */
  | { type: "viewer-play"; now: number }
  | { type: "viewer-pause"; now: number }
  | { type: "leave" };

/** What the replay should do: seek, change speed, play or pause. */
export type StoryCommand = { seek?: number; speed?: 1 | 5 | 20; play?: boolean };

export const INITIAL_STORY: StoryState = { status: "intro", index: 0, stepStartedAt: 0, elapsedMs: 0, voted: [] };

type Result = { state: StoryState; command: StoryCommand | null };

function enter(step: StoryStep): StoryCommand {
  return step.wait.kind === "play"
    ? { seek: step.startPos, speed: step.wait.speed, play: true }
    : { seek: step.startPos, play: false };
}

function goTo(steps: readonly StoryStep[], index: number, now: number, voted: readonly string[]): Result {
  // A vote step for a card the viewer has already called has nothing left to ask.
  while (index + 1 < steps.length) {
    const wait = steps[index].wait;
    if (wait.kind !== "vote" || !voted.includes(wait.decisionId)) break;
    index += 1;
  }
  const step = steps[index];
  const status = step.wait.kind === "stay" ? "done" : "playing";
  return { state: { status, index, stepStartedAt: now, elapsedMs: 0, voted }, command: enter(step) };
}

export function storyReducer(steps: readonly StoryStep[], state: StoryState, event: StoryEvent): Result {
  const same: Result = { state, command: null };
  const active = state.status === "playing" || state.status === "paused";
  const step = steps[state.index];
  const advance = (now: number, voted = state.voted) => (state.index + 1 < steps.length ? goTo(steps, state.index + 1, now, voted) : same);

  switch (event.type) {
    case "start":
      return steps.length ? goTo(steps, 0, event.now, []) : same;
    case "skip-intro":
    case "leave":
      return { state: { ...state, status: "left" }, command: null };
    case "viewer-seek":
    case "viewer-speed":
      return active ? { state: { ...state, status: "left" }, command: null } : same;
    case "next":
      return active ? advance(event.now) : same;
    case "viewer-pause":
    case "pause":
      if (state.status !== "playing") return same;
      return {
        state: { ...state, status: "paused", elapsedMs: state.elapsedMs + (event.now - state.stepStartedAt) },
        command: { play: false },
      };
    case "resume":
      if (state.status !== "paused") return same;
      return {
        state: { ...state, status: "playing", stepStartedAt: event.now },
        command: step.wait.kind === "play" ? { play: true } : null,
      };
    case "viewer-play":
      if (state.status === "paused") return storyReducer(steps, state, { type: "resume", now: event.now });
      if (state.status !== "playing" || step.wait.kind === "play") return same;
      // a held step keeps the replay still: the viewer who plays it takes over
      return { state: { ...state, status: "left" }, command: { play: true } };
    case "vote": {
      if (!active) return same;
      const voted = state.voted.includes(event.decisionId) ? state.voted : [...state.voted, event.decisionId];
      if (step.wait.kind !== "vote" || step.wait.decisionId !== event.decisionId) return { state: { ...state, voted }, command: null };
      return advance(event.now, voted);
    }
    case "tick": {
      if (state.status !== "playing") return same;
      const wait = step.wait;
      if (wait.kind === "play") return event.playhead >= wait.untilPos ? advance(event.now) : same;
      if (wait.kind === "hold" || wait.kind === "vote") {
        return state.elapsedMs + (event.now - state.stepStartedAt) >= wait.ms ? advance(event.now) : same;
      }
      return same;
    }
  }
}

const PATHS = { tv: "/", tablet: "/desk", phone: "/fan", end: "/" } as const;

/** Where leaving the story takes the viewer: the step's own screen at the playhead, in
 *  hundredths of a minute (?t= takes decimals), so a card that opened seconds ago is still open,
 *  with the viewer's club and language so the screen opens as they left it. */
export function leaveUrl(step: StoryStep, playhead: number, firstHalfEnd: number,
  keep: { club?: string; lang?: string } = {}): string {
  const { tMs } = fromPos(playhead, firstHalfEnd);
  const params = new URLSearchParams({ t: String(Math.floor(tMs / 600) / 100) });
  if (keep.club) params.set("club", keep.club);
  if (keep.lang) params.set("lang", keep.lang);
  return `${PATHS[step.screen]}?${params}`;
}
