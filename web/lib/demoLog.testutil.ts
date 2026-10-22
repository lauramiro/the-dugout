// Test-only: the recorded demo match from public/demo as a MatchLog, built the way
// ReplayDataSource.load builds it (no tracking frames).

import { readFileSync } from "node:fs";
import { toPos } from "./clock.ts";
import type { DecisionCard, MatchEvent, Roster, Snapshot } from "./contracts.ts";
import type { MatchLog } from "./datasource.ts";

const DEMO = new URL("../public/demo/", import.meta.url);
const json = <T>(name: string): T => JSON.parse(readFileSync(new URL(name, DEMO), "utf8")) as T;
const jsonl = <T>(name: string): T[] =>
  readFileSync(new URL(name, DEMO), "utf8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l) as T);

let cached: MatchLog | null = null;

export function demoLog(): MatchLog {
  if (cached) return cached;
  const index = json<{ period_end_t_ms: Record<"1" | "2", number> }>("tracking/index.json");
  const end1 = index.period_end_t_ms["1"];
  const pos = (period: 1 | 2, tMs: number) => toPos(period, tMs, end1);
  const byPos = <T extends { pos: number }>(a: T, b: T) => a.pos - b.pos;
  cached = {
    roster: json<Roster>("roster.json"),
    firstHalfEnd: end1,
    duration: pos(2, index.period_end_t_ms["2"]),
    events: jsonl<MatchEvent>("match.jsonl").sort((a, b) => a.seq - b.seq).map((e) => ({ pos: pos(e.period, e.t_ms), item: e })),
    snapshots: jsonl<Snapshot>("snapshots.jsonl").map((s) => ({ pos: pos(s.period ?? 1, s.t_ms), item: s })).sort(byPos),
    cards: json<{ cards: DecisionCard[] }>("cards.json").cards.map((c) => ({ pos: pos(c.period, c.payload.t_ms), item: c })).sort(byPos),
    winprob: [],
  };
  return cached;
}

export function demoPos(period: 1 | 2, tMs: number): number {
  return toPos(period, tMs, demoLog().firstHalfEnd);
}
