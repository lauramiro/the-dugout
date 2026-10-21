import { useRef } from "react";
import { holdCues, type Cue } from "../../lib/cues";

/** Cues to draw at the playhead, each held at least `minWallMs` of wall time once it showed. */
export function useHeldCues(cues: readonly Cue[], playhead: number, minWallMs = 4000): Cue[] {
  const firstSeen = useRef(new Map<string, number>());
  return holdCues(cues, playhead, firstSeen.current, performance.now(), minWallMs);
}
