"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import type { DataSource, FeedState } from "./datasource";
import { LiveDataSource } from "./live";
import { ReplayDataSource } from "./replay";
import { sourceChoice } from "./source";

const noSubscribe = () => () => {};
const clientSearch = () => window.location.search;
// The static HTML is rendered without a query string. Hydrating with "" keeps the first
// client render identical to it (no React #418); React then re-renders with the real query.
const serverSearch = () => "";

/** One data source for the page's lifetime, chosen from the query string (see sourceChoice). */
export function useDataSource(): DataSource {
  const search = useSyncExternalStore(noSubscribe, clientSearch, serverSearch);
  const source = useMemo<DataSource>(() => {
    const choice = sourceChoice(search);
    return choice.kind === "live" ? new LiveDataSource() : new ReplayDataSource(choice.minute);
  }, [search]);
  useEffect(() => {
    source.start();
    return () => source.dispose();
  }, [source]);
  return source;
}

export function useFeed(source: DataSource): FeedState {
  return useSyncExternalStore(source.subscribe, source.getState, source.getState);
}
