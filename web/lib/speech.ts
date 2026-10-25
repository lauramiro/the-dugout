// "Read it out" on the TV decision card: the browser's own speech (Web Speech API), in the viewer's language.

import type { DecisionCard, Locale, Mode, Roster } from "./contracts.ts";
import { withNames } from "./derive.ts";

export const SPEECH_LANG: Record<Locale, string> = { en: "en-GB", es: "es-ES" };

/** The line as it is spoken: the headline (which has no full stop on screen) and the reason, with names. */
export function speechText(line: { headline: string; reason: string }, roster: Roster | null): string {
  const headline = withNames(line.headline, roster).trim();
  return `${/[.!?]$/.test(headline) ? headline : `${headline}.`} ${withNames(line.reason, roster).trim()}`;
}

/** The language of the line a card shows for `locale` and `mode`: the card's own, or English, which is what
 *  the lower third falls back to (LowerThird narrationFor). */
export function narrationLocale(card: DecisionCard, locale: Locale, mode: Mode): Locale {
  return card.narration[locale]?.[mode] ? locale : "en";
}
