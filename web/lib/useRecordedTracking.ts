"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { fromPos, toPos } from "./clock";
import type { DataSource, FeedState, MatchLog, PitchFrame } from "./datasource";
import { ReplayDataSource } from "./replay";

const noSubscribe = () => () => {};
const noState = () => null;

/** Live: no tracking comes over Web PubSub, so when the live match is the recorded demo match,
 *  draw the recorded tracking at the live clock (the TV picture says so in its settings). Used by
 *  the TV picture and the analyst desk. */
export function useRecordedTracking(source: DataSource, log: MatchLog, pos: number): { frame: PitchFrame | null; active: boolean } {
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
