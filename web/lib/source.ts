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

/** Whether a replay page should start playing now: a page opened on its own runs like a broadcast, once
 *  it has loaded, and only the first time (a pause after that stays a pause). `held`: something on the
 *  page asks for a wait first, such as the landing's story intro. */
export function playOnLoad(s: { started: boolean; ready: boolean; controls: boolean; held: boolean }): boolean {
  return !s.started && s.ready && s.controls && !s.held;
}

/** Whether a page's query opens a minute of its own (?t=), as leaving the story does: such a page waits
 *  for the viewer instead of playing on, so a card that just opened can be read and called. */
export function linkedMinute(search: string): boolean {
  return new URLSearchParams(search).has("t");
}
