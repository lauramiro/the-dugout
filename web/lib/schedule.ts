// When the live demo match kicks off. infra/deploy.sh writes public/schedule.json from
// dugout/stream/replay.py (`--write-schedule`): a scheduled job replays the recorded match every
// `every_min` minutes from midnight UTC, and each replay runs `duration_ms` of wall time.

export interface Schedule {
  match_id: string | null;
  every_min: number;
  speed: number;
  duration_ms: number;
}

export type Kickoff =
  | { kind: "on"; since: number; until: number }
  | { kind: "next"; at: number };

/** Time after a replay's planned end still counted as the match: the pipeline runs a few
 *  seconds behind the replay, and the last cards are narrated after the final whistle. */
export const GRACE_MS = 60_000;

/** The schedule from schedule.json, or null when it is missing or malformed. */
export function parseSchedule(json: unknown): Schedule | null {
  if (typeof json !== "object" || json === null) return null;
  const s = json as Record<string, unknown>;
  const every = s.every_min;
  const duration = s.duration_ms;
  if (typeof every !== "number" || !(every > 0) || 60 % every !== 0) return null;
  if (typeof duration !== "number" || !(duration > 0) || duration >= every * 60_000) return null;
  return {
    match_id: typeof s.match_id === "string" ? s.match_id : null,
    every_min: every,
    speed: typeof s.speed === "number" ? s.speed : 1,
    duration_ms: duration,
  };
}

/** How long after a kick-off the page waits for the first message before it takes the slot as
 *  missed (the job did not run, for example on the deploy that created it) and counts down to the
 *  next one instead of saying the match is under way. */
export const JOIN_WAIT_MS = 120_000;

/** The match on now (epoch ms, from the latest slot), or the next kick-off. `empty`: nothing has
 *  arrived from the feed; a slot that has sent nothing by JOIN_WAIT_MS counts as missed. */
export function kickoff(schedule: Schedule, now: number, empty = false): Kickoff {
  const period = schedule.every_min * 60_000;
  const last = Math.floor(now / period) * period;
  const missed = empty && now - last > JOIN_WAIT_MS;
  if (!missed && now < last + schedule.duration_ms + GRACE_MS) return { kind: "on", since: last, until: last + schedule.duration_ms };
  return { kind: "next", at: last + period };
}

/** "8:05" or "1:02:09" until a moment; "0:00" once it has passed. */
export function countdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
