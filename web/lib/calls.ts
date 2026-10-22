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

/** Reveal once the manager has acted, and never before the card itself opened. */
export function revealPos(card: Timed<DecisionCard>, firstHalfEnd: number): number | null {
  const at = managerPos(card.item, firstHalfEnd);
  return at === null ? null : Math.max(at, card.pos);
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
