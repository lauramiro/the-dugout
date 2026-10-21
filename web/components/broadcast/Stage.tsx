import type { ReactNode } from "react";

/** A 16:9 picture letterboxed in the window. Inside it, sizes use container units (cqw), so
 *  every graphic scales with the picture, as a broadcast overlay does. */
export function Stage({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="bc-wrap">
      <div className="bc-stage" role="region" aria-label={label}>
        {children}
      </div>
    </div>
  );
}
