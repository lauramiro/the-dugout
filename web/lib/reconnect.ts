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
