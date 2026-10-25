"use client";

import { DeskView } from "../../components/desk/DeskView";
import { useDataSource, useFeed, useLinkedMinute, usePlayOnLoad } from "../../lib/useFeed";

export default function Page() {
  const source = useDataSource();
  const feed = useFeed(source);
  // Opened on its own it plays like a broadcast; a link to a minute (leaving the story) waits for the viewer.
  usePlayOnLoad(source, feed, useLinkedMinute() !== false);
  return <DeskView source={source} feed={feed} />;
}
