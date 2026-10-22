"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DataSource, PlaybackControls } from "../../lib/datasource";
import type { StoryStep } from "../../lib/story";
import { INITIAL_STORY, storyReducer, type StoryCommand, type StoryEvent, type StoryState } from "../../lib/storyPlayer";

function apply(command: StoryCommand, controls: PlaybackControls): void {
  if (command.seek !== undefined) controls.seek(command.seek);
  if (command.speed !== undefined) controls.setSpeed(command.speed);
  if (command.play === true) controls.play();
  if (command.play === false) controls.pause();
}

export interface StoryRun {
  state: StoryState;
  step: StoryStep | null;
  /** Whether the guide is driving the page now (playing or paused). */
  active: boolean;
  send: (event: StoryEvent) => void;
  /** The replay controls for the page's own buttons: using them while the story runs leaves it. */
  viewerControls: PlaybackControls | null;
}

/** Drives the replay from the story's steps (lib/storyPlayer.ts); ticks read the playhead from
 *  the source itself. */
export function useStory(steps: StoryStep[] | null, source: DataSource): StoryRun {
  const [state, setState] = useState<StoryState>(INITIAL_STORY);
  const current = useRef<StoryState>(INITIAL_STORY);

  const send = useCallback(
    (event: StoryEvent) => {
      if (!steps) return;
      const { state: next, command } = storyReducer(steps, current.current, event);
      if (next !== current.current) {
        current.current = next;
        setState(next);
      }
      if (command && source.controls) apply(command, source.controls);
    },
    [steps, source],
  );

  // A new step list (the files finished loading, or another club) starts from the intro again.
  useEffect(() => {
    current.current = INITIAL_STORY;
    setState(INITIAL_STORY);
  }, [steps]);

  useEffect(() => {
    if (state.status !== "playing") return;
    let raf = 0;
    const loop = () => {
      send({ type: "tick", now: performance.now(), playhead: source.getState().playhead });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [state.status, send, source]);

  const viewerControls = useMemo<PlaybackControls | null>(() => {
    const controls = source.controls;
    if (!controls) return null;
    return {
      play: () => controls.play(),
      pause: () => controls.pause(),
      setSpeed: (speed) => { send({ type: "viewer-speed" }); controls.setSpeed(speed); },
      seek: (pos) => { send({ type: "viewer-seek" }); controls.seek(pos); },
    };
  }, [source, send]);

  const active = state.status === "playing" || state.status === "paused";
  return { state, step: steps?.[state.index] ?? null, active, send, viewerControls };
}
