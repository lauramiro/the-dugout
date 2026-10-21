import { memo } from "react";
import type { Roster } from "../lib/contracts";
import type { PitchFrame } from "../lib/datasource";
import { shirt } from "../lib/derive";

export const PITCH_L = 105;
const L = PITCH_L;
export const PITCH_W = 68;
const W = PITCH_W;
const STRIPES = 12;

// Contract coordinates: y grows towards the left touchline of a team attacking x = 105,
// so it points up the screen.
export const sy = (y: number) => W - y;

export const Markings = memo(function Markings() {
  const box = (x: number, dir: 1 | -1, depth: number, width: number) => (
    <rect x={dir === 1 ? x : x - depth} y={(W - width) / 2} width={depth} height={width} />
  );
  return (
    <g className="pitch-lines">
      {Array.from({ length: STRIPES }, (_, i) => (
        <rect key={i} className={i % 2 ? "stripe" : "stripe alt"} x={(L / STRIPES) * i} y={0} width={L / STRIPES} height={W} />
      ))}
      <rect x={0} y={0} width={L} height={W} />
      <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
      <circle cx={L / 2} cy={W / 2} r={9.15} />
      <circle cx={L / 2} cy={W / 2} r={0.35} className="spot" />
      {box(0, 1, 16.5, 40.32)}
      {box(0, 1, 5.5, 18.32)}
      {box(L, -1, 16.5, 40.32)}
      {box(L, -1, 5.5, 18.32)}
      <circle cx={11} cy={W / 2} r={0.35} className="spot" />
      <circle cx={L - 11} cy={W / 2} r={0.35} className="spot" />
      {/* Penalty arcs: the part of the 9.15 m circle outside the box. */}
      <path d={`M 16.5 ${W / 2 - 7.31} A 9.15 9.15 0 0 1 16.5 ${W / 2 + 7.31}`} />
      <path d={`M ${L - 16.5} ${W / 2 - 7.31} A 9.15 9.15 0 0 0 ${L - 16.5} ${W / 2 + 7.31}`} />
      <rect x={-1.6} y={W / 2 - 3.66} width={1.6} height={7.32} className="goal" />
      <rect x={L} y={W / 2 - 3.66} width={1.6} height={7.32} className="goal" />
    </g>
  );
});

interface Props {
  frame: PitchFrame | null;
  roster: Roster | null;
  highlight: string | null;
  label: string;
}

export function Pitch({ frame, roster, highlight, label }: Props) {
  const home = roster?.home;
  return (
    <svg className="pitch" viewBox={`-3 -2 ${L + 6} ${W + 4}`} role="img" aria-label={label}>
      <Markings />
      {frame?.players.map((p) => {
        const team = roster?.players[p.id]?.team ?? p.id.split("-")[0];
        const keeper = roster?.players[p.id]?.role === "GK";
        return (
          <g
            key={p.id}
            className={`dot ${team === home ? "home" : "away"}${keeper ? " keeper" : ""}`}
            transform={`translate(${p.x.toFixed(2)} ${sy(p.y).toFixed(2)})`}
          >
            {p.id === highlight && <circle r={3.2} className="flag-ring" />}
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
