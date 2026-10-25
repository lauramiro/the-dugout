import type { ReactNode } from "react";

/** A 16:9 picture letterboxed in the window. Inside it, sizes use container units (cqw), so
 *  every graphic scales with the picture, as a broadcast overlay does. `chrome` (the page's
 *  links and replay controls) sits over the top of the picture, or under it on a tall screen. `sheet` holds
 *  graphics that a portrait phone shows under the picture instead of over it (lib/sheet.ts). */
export function Stage({ children, label, chrome, sheet, sheetFirst = false }: {
  children: ReactNode; label: string; chrome?: ReactNode; sheet?: ReactNode;
  /** The sheet straight under the picture, before the controls (the guided story, whose caption bar sits at the
   *  bottom of the window). */
  sheetFirst?: boolean;
}) {
  return (
    <div className="bc-wrap">
      <div className="bc-frame">
        <div className="bc-stage" role="region" aria-label={label}>
          {children}
        </div>
        {sheet && <div className={`bc-sheet${sheetFirst ? " first" : ""}`}>{sheet}</div>}
        {chrome}
      </div>
    </div>
  );
}
