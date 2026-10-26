// The three calls on a decision: the viewer's vote, the model's pick and the manager's
// action. Only ids and counts are handled here; every number shown comes from the payload
// or the review block as given.

import { toPos } from "./clock.ts";
import type { DecisionCard } from "./contracts";
import type { Timed } from "./datasource";
import type { Tally } from "./votes";

export const VOTE_SECONDS = 20;

export interface Vote {
  /** The option voted for, or null when the timer ran out first. */
  option: string | null;
  tally: Tally | null;
  error: string | null;
}

/** The pos at which the manager's call is known, or null while it is not (live). */
export function managerPos(card: DecisionCard, firstHalfEnd: number): number | null {
  const action = card.payload.manager_action;
  return action ? toPos(action.period, action.t_ms, firstHalfEnd) : null;
}

/** Where a manager's call shows, from the positions of the call, the card's opening and its
 *  closing (null when not known). After the opening; a call settled at or before it (a queued
 *  card that a later goal overtook) waits for the card to close, so the fresh card shows first. */
export function callPos(managerAt: number, cardAt: number, closedAt: number | null): number {
  if (managerAt > cardAt) return managerAt;
  return closedAt === null ? cardAt : Math.max(closedAt, cardAt);
}

/** Reveal once the manager has acted (see callPos). A manager_sub card is raised by the change
 *  itself, so its call is known as it opens. */
export function revealPos(card: Timed<DecisionCard>, firstHalfEnd: number): number | null {
  const at = managerPos(card.item, firstHalfEnd);
  if (at === null) return null;
  if (card.item.payload.trigger === "manager_sub") return Math.max(at, card.pos);
  const closed = card.item.closed;
  return callPos(at, card.pos, closed ? toPos(closed.period, closed.t_ms, firstHalfEnd) : null);
}

/** The option id the manager's call stands for in the review, if any. */
export function managerOption(card: DecisionCard): string | null {
  return card.review?.manager?.id ?? card.payload.manager_action?.option_id ?? null;
}

export interface Agreement {
  agreed: number;
  counted: number;
}

/**
 * How often a call matched the model's pick. Toss-ups are left out: the card itself
 * says those options are close rather than picking one.
 */
export function agreement(cards: readonly DecisionCard[], pick: (c: DecisionCard) => string | null): Agreement {
  let agreed = 0;
  let counted = 0;
  for (const c of cards) {
    const call = pick(c);
    if (call === null || c.payload.recommendation.strength === "toss_up") continue;
    counted++;
    if (call === c.payload.recommendation.option_id) agreed++;
  }
  return { agreed, counted };
}
