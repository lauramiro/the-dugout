// Who is on the bench: the club's roster players who have not played by a moment. The data has
// no "ready" flag, so this claims no more than "has not played yet".

import { lastAtOrBefore } from "./clock.ts";
import type { TeamCode } from "./contracts";
import type { MatchLog } from "./datasource";

export interface BenchPlayer {
  id: string;
  name: string;
  role: string;
}

/** The club's roster players not on the pitch in the latest snapshot at or before `pos` (the
 *  first snapshot before any) and never subbed off by then. Empty when no snapshot exists. */
export function benchAt(log: MatchLog, pos: number, club: TeamCode): BenchPlayer[] {
  if (!log.roster || log.snapshots.length === 0) return [];
  const at = lastAtOrBefore(log.snapshots, pos);
  const onPitch = new Set(log.snapshots[Math.max(0, at)].item.players.map((p) => p.id));
  const subbedOff = new Set(
    log.events.filter((e) => e.pos <= pos && e.item.type === "sub" && e.item.player_id).map((e) => e.item.player_id as string),
  );
  return Object.entries(log.roster.players)
    .filter(([id, p]) => p.team === club && !onPitch.has(id) && !subbedOff.has(id))
    .map(([id, p]) => ({ id, name: p.name, role: p.role }));
}
