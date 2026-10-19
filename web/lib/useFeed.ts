"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import type { DataSource, FeedState } from "./datasource";
import { LiveDataSource } from "./live";
import { ReplayDataSource } from "./replay";

/** One data source for the page's lifetime: ?source=live for Web PubSub, replay otherwise. */
export function useDataSource(): DataSource {
  const source = useMemo<DataSource>(() => {
    const live = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("source") === "live";
    return live ? new LiveDataSource() : new ReplayDataSource();
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
