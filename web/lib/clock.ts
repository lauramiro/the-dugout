// Match clock helpers. The feed orders everything on one "pos" axis: elapsed playing
// time, with the second half starting just after the first half's final frame, so
// first-half added time never collides with second-half t_ms.

export const HALF_MS = 2_700_000;
const MIN_MS = 60_000;
const HALF_TIME_GAP_MS = 500;

export function toPos(period: 1 | 2, tMs: number, firstHalfEnd: number): number {
  return period === 1 ? tMs : firstHalfEnd + HALF_TIME_GAP_MS + (tMs - HALF_MS);
}

/** Where a ?t= minute opens the replay: in its half (the second from 45), at most at full time. */
export function minutePos(minute: number, firstHalfEnd: number, duration: number): number {
  return Math.min(minute > 0 ? toPos(minute >= 45 ? 2 : 1, minute * MIN_MS, firstHalfEnd) : 0, duration);
}

export function fromPos(pos: number, firstHalfEnd: number): { period: 1 | 2; tMs: number } {
  if (pos <= firstHalfEnd) return { period: 1, tMs: Math.max(0, pos) };
  return { period: 2, tMs: Math.max(HALF_MS, pos - firstHalfEnd - HALF_TIME_GAP_MS + HALF_MS) };
}

/** Live: where to draw between messages. The last message's pos run on at `rate` (match ms
 *  per wall ms) since `wall`, never more than `maxAheadMs` of match time past it. */
export function aheadPos(pos: number, wall: number, rate: number, now: number, maxAheadMs: number): number {
  return pos + Math.min(rate * Math.max(0, now - wall), maxAheadMs);
}

/** Live: what the feed has shown about the halves so far. */
export interface LiveHalf {
  /** The last period-1 t_ms seen (at least 45:00): the first half's final moment. */
  firstHalfEnd: number;
  /** Whether any period-2 message has arrived. */
  secondHalf: boolean;
}

/** Live: a message's period (its own, or inferred) and the halves after it. Messages arrive in
 *  match order, so every period-1 message comes before the first period-2 one. */
export function liveHalf(half: LiveHalf, period: 1 | 2 | undefined, tMs: number): { period: 1 | 2; half: LiveHalf } {
  const p: 1 | 2 = period ?? (tMs >= HALF_MS && half.secondHalf ? 2 : 1);
  if (p === 2) return { period: 2, half: half.secondHalf ? half : { ...half, secondHalf: true } };
  return { period: 1, half: tMs > half.firstHalfEnd ? { ...half, firstHalfEnd: tMs } : half };
}

/** Running clock, e.g. "62:14" (first-half added time keeps counting, "47:57"). */
export function formatClock(tMs: number): string {
  const s = Math.floor(tMs / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Minute as the engine counts it (t_ms // 60000, "62'"); added time as "45+3'". */
export function formatMinute(period: 1 | 2, tMs: number): string {
  const regular = period === 1 ? 45 : 90;
  const minute = Math.floor(tMs / MIN_MS);
  if (minute >= regular && tMs > regular * MIN_MS) return `${regular}+${minute - regular + 1}'`;
  return `${minute}'`;
}

/** Index of the last item with pos <= at, or -1. Items must be sorted by pos. */
export function lastAtOrBefore<T extends { pos: number }>(items: readonly T[], at: number): number {
  let lo = 0;
  let hi = items.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (items[mid].pos <= at) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}
