// When the live page's Web PubSub connection drops (a network blip, a laptop waking up, the
// service restarting), the page negotiates a fresh URL and connects again on its own.

type Status = "loading" | "ready" | "error";

/** Wait before reconnect attempt `attempt` (0 is the first): 1 s, doubling, at most 30 s. */
export function reconnectDelayMs(attempt: number): number {
  return Math.min(30_000, 1000 * 2 ** attempt);
}

/** The status after a drop: a feed that was showing the match keeps it on screen while it
 *  reconnects; one that never connected shows the error. */
export function statusOnDrop(status: Status): Status {
  return status === "ready" ? "ready" : "error";
}

/** A connection that stayed open this long counts as working, so the next drop starts the backoff again. */
export const STABLE_MS = 10_000;

/** The attempt count after a close: back to 0 only if the connection held for STABLE_MS, so one that
 *  is accepted and closed at once (a quota, a draining service) keeps backing off. */
export function attemptsAfterClose(attempts: number, openForMs: number): number {
  return openForMs >= STABLE_MS ? 0 : attempts;
}
