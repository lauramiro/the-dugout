import { useRef } from "react";
import { holdCues, type Cue } from "../../lib/cues";
import { SPEEDS } from "../../lib/datasource";

/** Cues to draw at the playhead, each held at least `minWallMs` of wall time once it showed. A hold lags the
 *  playhead by at most what the fastest speed covers in that time (with a margin); further than that is a seek. */
export function useHeldCues(cues: readonly Cue[], playhead: number, minWallMs = 4000): Cue[] {
  const firstSeen = useRef(new Map<string, number>());
  const maxLagMs = 1.5 * minWallMs * Math.max(...SPEEDS);
  return holdCues(cues, playhead, firstSeen.current, performance.now(), minWallMs, maxLagMs);
}
