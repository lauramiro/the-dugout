// The UI reads the match only through a DataSource. ReplayDataSource plays the static
// fixture files; LiveDataSource will take the Web PubSub feed. Both expose the same log
// of everything known so far plus a playhead, so the screen never knows which it has.

import type { DecisionCard, MatchEvent, Roster, Snapshot, TrackingFrame, WinProbPoint } from "./contracts";

export interface Timed<T> {
  pos: number;
  item: T;
}

export interface MatchLog {
  roster: Roster | null;
  /** t_ms of the first half's final frame; the second half's pos starts after it. */
  firstHalfEnd: number;
  /** pos of the last moment the feed covers (replay: full time). */
  duration: number;
  events: Timed<MatchEvent>[];
  snapshots: Timed<Snapshot>[];
  cards: Timed<DecisionCard>[];
  winprob: Timed<WinProbPoint>[];
}

export type Speed = 1 | 5 | 20;
export const SPEEDS: readonly Speed[] = [1, 5, 20];

export interface FeedState {
  status: "loading" | "ready" | "error";
  error: string | null;
  log: MatchLog;
  playhead: number;
  playing: boolean;
  speed: Speed;
}

export interface PlaybackControls {
  play(): void;
  pause(): void;
  setSpeed(speed: Speed): void;
  seek(pos: number): void;
}

/** A frame at an exact pos, interpolated between the two nearest tracking frames. */
export interface PitchFrame {
  ball: { x: number; y: number };
  players: { id: string; x: number; y: number }[];
}

export interface DataSource {
  readonly kind: "replay" | "live";
  /** Replay only; a live feed cannot seek or change speed. */
  readonly controls: PlaybackControls | null;
  getState(): FeedState;
  subscribe(listener: () => void): () => void;
  frameAt(pos: number): PitchFrame | null;
  start(): void;
  dispose(): void;
}

export function emptyLog(): MatchLog {
  return { roster: null, firstHalfEnd: 2_700_000, duration: 0, events: [], snapshots: [], cards: [], winprob: [] };
}

/** Interpolate between two frames; players only in one of them are drawn at that frame's spot. */
export function interpolate(a: Timed<TrackingFrame>, b: Timed<TrackingFrame>, pos: number): PitchFrame {
  const span = b.pos - a.pos;
  const k = span > 0 ? Math.min(1, Math.max(0, (pos - a.pos) / span)) : 0;
  const near = k < 0.5 ? a.item : b.item;
  const other = new Map(b.item.players.map((p) => [p.id, p]));
  const players = near.players.map((p) => {
    const from = a.item.players.find((q) => q.id === p.id);
    const to = other.get(p.id);
    if (!from || !to) return { id: p.id, x: p.x, y: p.y };
    return { id: p.id, x: from.x + (to.x - from.x) * k, y: from.y + (to.y - from.y) * k };
  });
  return {
    ball: {
      x: a.item.ball.x + (b.item.ball.x - a.item.ball.x) * k,
      y: a.item.ball.y + (b.item.ball.y - a.item.ball.y) * k,
    },
    players,
  };
}
