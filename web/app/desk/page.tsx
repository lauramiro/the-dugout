"use client";

import { DeskView } from "../../components/desk/DeskView";
import { useDataSource, useFeed, usePlayOnLoad } from "../../lib/useFeed";

export default function Page() {
  const source = useDataSource();
  const feed = useFeed(source);
  usePlayOnLoad(source, feed);
  return <DeskView source={source} feed={feed} />;
}
