// "Read it out" on the TV decision card: the browser's own speech (Web Speech API), in the viewer's language.

import type { Locale, Roster } from "./contracts.ts";
import { withNames } from "./derive.ts";

export const SPEECH_LANG: Record<Locale, string> = { en: "en-GB", es: "es-ES" };

/** The line as it is spoken: the headline (which has no full stop on screen) and the reason, with names. */
export function speechText(line: { headline: string; reason: string }, roster: Roster | null): string {
  const headline = withNames(line.headline, roster).trim();
  return `${/[.!?]$/.test(headline) ? headline : `${headline}.`} ${withNames(line.reason, roster).trim()}`;
}
