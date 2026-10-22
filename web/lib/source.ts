export type SourceChoice = { kind: "live" } | { kind: "replay"; minute: number };

/** The page's data source from its query string: ?source=live for Web PubSub, replay
 *  otherwise; ?t=62 opens the replay at that minute. An empty query is what the static
 *  HTML was rendered with. */
export function sourceChoice(search: string): SourceChoice {
  const params = new URLSearchParams(search);
  if (params.get("source") === "live") return { kind: "live" };
  const minute = Number(params.get("t"));
  return { kind: "replay", minute: Number.isFinite(minute) && minute > 0 ? minute : 0 };
}
