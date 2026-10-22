import type { ReactNode } from "react";

/** A 16:9 picture letterboxed in the window. Inside it, sizes use container units (cqw), so
 *  every graphic scales with the picture, as a broadcast overlay does. `chrome` (the page's
 *  links and replay controls) sits over the top of the picture, or under it on a tall screen. */
export function Stage({ children, label, chrome }: { children: ReactNode; label: string; chrome?: ReactNode }) {
  return (
    <div className="bc-wrap">
      <div className="bc-frame">
        <div className="bc-stage" role="region" aria-label={label}>
          {children}
        </div>
        {chrome}
      </div>
    </div>
  );
}
