import { useEffect, useReducer, useRef } from "react";
import { holdCues, holdExpiresInMs, type Cue } from "../../lib/cues";
import { SPEEDS } from "../../lib/datasource";

/** Cues to draw at the playhead, each held at least `minWallMs` of wall time once it showed. A hold lags the
 *  playhead by at most what the fastest speed covers in that time (with a margin); further than that is a seek.
 *  When a hold ends, the hook re-renders, so a paused replay does not keep an ended cue on screen. */
export function useHeldCues(cues: readonly Cue[], playhead: number, minWallMs = 4000): Cue[] {
  const firstSeen = useRef(new Map<string, number>());
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const maxLagMs = 1.5 * minWallMs * Math.max(...SPEEDS);
  const now = performance.now();
  const shown = holdCues(cues, playhead, firstSeen.current, now, minWallMs, maxLagMs);
  const expiresIn = holdExpiresInMs(shown, playhead, firstSeen.current, now, minWallMs);
  useEffect(() => {
    if (expiresIn === null) return;
    const timer = setTimeout(rerender, expiresIn + 50);
    return () => clearTimeout(timer);
  });
  return shown;
}
