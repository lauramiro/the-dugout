"use client";

import { fromPos, formatClock, lastAtOrBefore } from "../lib/clock";
import { SPEEDS } from "../lib/datasource";
import { useDataSource, useFeed } from "../lib/useFeed";

export default function Page() {
  const source = useDataSource();
  const feed = useFeed(source);
  const { log, playhead } = feed;
  const { tMs } = fromPos(playhead, log.firstHalfEnd);
  const goals = log.events.slice(0, lastAtOrBefore(log.events, playhead) + 1).filter((e) => e.item.type === "goal");
  const score = (team: string) => goals.filter((g) => g.item.team === team).length;

  return (
    <main>
      <h1>The Dugout</h1>
      <p>
        {feed.status} {formatClock(tMs)} RFC {score("RFC")} - {score("CAS")} CAS
      </p>
      {source.controls && (
        <p>
          <button onClick={feed.playing ? source.controls.pause : source.controls.play}>{feed.playing ? "Pause" : "Play"}</button>
          {SPEEDS.map((s) => (
            <button key={s} aria-pressed={feed.speed === s} onClick={() => source.controls?.setSpeed(s)}>
              {s}x
            </button>
          ))}
        </p>
      )}
    </main>
  );
}
