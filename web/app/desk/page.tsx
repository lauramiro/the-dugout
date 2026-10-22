"use client";

import { DeskView } from "../../components/desk/DeskView";
import { useDataSource, useFeed } from "../../lib/useFeed";

export default function Page() {
  const source = useDataSource();
  const feed = useFeed(source);
  return <DeskView source={source} feed={feed} />;
}
