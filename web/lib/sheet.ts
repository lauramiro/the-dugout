// A portrait phone shows the 16:9 picture about 220 px tall: the decision card and full time's What if
// do not fit on it, so there they sit in a sheet under the picture (app/broadcast.css, same query).

import { useSyncExternalStore } from "react";

export const PHONE_SHEET_QUERY = "(max-width: 700px) and (orientation: portrait)";

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(PHONE_SHEET_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Whether the graphics go in the sheet under the picture; false while rendering the static HTML. */
export function usePhoneSheet(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(PHONE_SHEET_QUERY).matches, () => false);
}
