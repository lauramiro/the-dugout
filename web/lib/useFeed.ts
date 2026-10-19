"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import type { DataSource, FeedState } from "./datasource";
import { LiveDataSource } from "./live";
import { ReplayDataSource } from "./replay";

/**
 * One data source for the page's lifetime: ?source=live for Web PubSub, replay
 * otherwise; ?t=62 opens the replay at that minute.
 */
export function useDataSource(): DataSource {
  const source = useMemo<DataSource>(() => {
    const params = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
    if (params.get("source") === "live") return new LiveDataSource();
    const minute = Number(params.get("t"));
    return new ReplayDataSource(Number.isFinite(minute) && minute > 0 ? minute : 0);
  }, []);
  useEffect(() => {
    source.start();
    return () => source.dispose();
  }, [source]);
  return source;
}

export function useFeed(source: DataSource): FeedState {
  return useSyncExternalStore(source.subscribe, source.getState, source.getState);
}
