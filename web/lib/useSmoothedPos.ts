"use client";

import { useEffect, useRef, useState } from "react";
import { aheadPos } from "./clock";

const MAX_RATE = 30; // match ms per wall ms: above the fastest replay speed (20x)
const MAX_AHEAD_MS = 3000; // never draw further than this past the last message

/** Replay: the playhead as is. Live: the playhead only moves when a message arrives, so
 *  between messages the picture runs on at the rate the last messages came in. Live, this
 *  re-renders on every animation frame: call it in the component that draws the picture. */
export function useSmoothedPos(playhead: number, live: boolean): number {
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
