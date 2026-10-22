import type { Roster } from "../../lib/contracts";
import type { PitchFrame } from "../../lib/datasource";
import { shirt } from "../../lib/derive";
import { Markings, PITCH_L, PITCH_W, sy } from "../Pitch";

/** A label that follows one player: the focus player always, a fading player while the cue runs. */
export interface PlayerTag {
  id: string;
  label: string;
  /** A line above the name (the focus player's running stats), or null. */
  detail: string | null;
  /** Condition 0..1 for the ring, or null for no ring. */
  ring: number | null;
  tone: "focus" | "fading" | "sprint";
}

interface Props {
  frame: PitchFrame | null;
  roster: Roster | null;
  tags: PlayerTag[];
  label: string;
}

// The pitch fills the 16:9 picture: 128 x 72 units around the 105 x 68 m pitch.
const VIEW_W = 128;
const VIEW_H = 72;
const VIEW = `${(PITCH_L - VIEW_W) / 2} ${(PITCH_W - VIEW_H) / 2} ${VIEW_W} ${VIEW_H}`;

export function FieldView({ frame, roster, tags, label }: Props) {
  const home = roster?.home;
  const byId = new Map(tags.map((tag) => [tag.id, tag]));
  return (
    <svg className="pitch bc-field" viewBox={VIEW} preserveAspectRatio="xMidYMid slice" role="img" aria-label={label}>
      <Markings />
      {frame?.players.map((p) => {
        const info = roster?.players[p.id];
        const team = info?.team ?? p.id.split("-")[0];
        const tag = byId.get(p.id);
        return (
          <g
            key={p.id}
            className={`dot ${team === home ? "home" : "away"}${info?.role === "GK" ? " keeper" : ""}`}
            transform={`translate(${p.x.toFixed(2)} ${sy(p.y).toFixed(2)})`}
          >
            {tag && <TagMark tag={tag} />}
            <circle r={1.75} />
            <text dy={0.62}>{shirt(p.id)}</text>
          </g>
        );
      })}
      {frame && (
        <g className="ball" transform={`translate(${frame.ball.x.toFixed(2)} ${sy(frame.ball.y).toFixed(2)})`}>
          <circle r={0.85} />
        </g>
      )}
    </svg>
  );
}

const RING_R = 3;
const RING_C = 2 * Math.PI * RING_R;

function TagMark({ tag }: { tag: PlayerTag }) {
  const ring = tag.ring === null ? null : Math.min(1, Math.max(0, tag.ring));
  const band = ring === null ? "" : ring >= 0.8 ? "high" : ring >= 0.69 ? "mid" : "low";
  return (
    <g className={`bc-tag ${tag.tone}`}>
      <circle r={RING_R} className="bc-tag-track" />
      {ring !== null && (
        <circle
          r={RING_R}
          className={`bc-tag-ring ${band}`}
          strokeDasharray={`${(ring * RING_C).toFixed(2)} ${RING_C.toFixed(2)}`}
          transform="rotate(-90)"
        />
      )}
      <g className="bc-tag-label" transform={`translate(0 ${-RING_R - 1.4})`}>
        <text textAnchor="middle">{tag.label}</text>
        {tag.detail && (
          <text textAnchor="middle" y={-2.4} className="bc-tag-detail">{tag.detail}</text>
        )}
      </g>
    </g>
  );
}
