export type SourceChoice = { kind: "live" } | { kind: "replay"; minute: number };

/** Where the replay opens with no ?t=: a minute before the first decision card (60:20). */
export const LANDING_MINUTE = 59;

/** The page's data source from its query string: ?source=live for Web PubSub, replay
 *  otherwise; ?t=62 opens the replay at that minute, ?t=0 at kick-off, and no (or an
 *  unreadable) ?t= at LANDING_MINUTE. An empty query is what the static HTML was rendered with. */
export function sourceChoice(search: string): SourceChoice {
  const params = new URLSearchParams(search);
  if (params.get("source") === "live") return { kind: "live" };
  const t = params.get("t");
  const minute = t === null || t.trim() === "" ? NaN : Number(t);
  return { kind: "replay", minute: Number.isFinite(minute) && minute >= 0 ? minute : LANDING_MINUTE };
}
