"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { DataSource, FeedState } from "./datasource";
import { LiveDataSource } from "./live";
import { ReplayDataSource } from "./replay";
import { linkedMinute, playOnLoad, sourceChoice } from "./source";

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

/** Start the replay once it has loaded, as a broadcast would (see playOnLoad). */
export function usePlayOnLoad(source: DataSource, feed: FeedState, held = false): void {
  const started = useRef(false);
  useEffect(() => {
    if (!playOnLoad({ started: started.current, ready: feed.status === "ready", controls: !!source.controls, held })) return;
    started.current = true;
    source.controls?.play();
  }, [feed.status, source, held]);
}

/** linkedMinute for this page; null until read in the browser (the static HTML has no query). */
export function useLinkedMinute(): boolean | null {
  const [linked, setLinked] = useState<boolean | null>(null);
  useEffect(() => setLinked(linkedMinute(window.location.search)), []);
  return linked;
}
