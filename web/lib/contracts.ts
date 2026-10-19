// TypeScript mirrors of docs/data-contracts.md. The UI reads these shapes and never
// derives win probabilities or gaps from them.

export type TeamCode = string;

// 1. Event
export type EventType =
  | "pass" | "carry" | "duel" | "press" | "shot" | "goal" | "foul"
  | "card" | "out" | "restart" | "sub" | "sprint" | "hsr";

export interface MatchEvent {
  match_id: string;
  seq: number;
  t_ms: number;
  period: 1 | 2;
  type: EventType;
  team: TeamCode;
  player_id: string | null;
  channel: "left" | "centre" | "right" | null;
  x: number | null;
  y: number | null;
  end_x: number | null;
  end_y: number | null;
  outcome: string | null;
  xg: number | null;
  dist_m?: number | null;
  player_in_id?: string;
}

// 2. Tracking frame
export interface TrackingFrame {
  match_id: string;
  period: 1 | 2;
  t_ms: number;
  ball: { x: number; y: number };
  players: { id: string; x: number; y: number; v: number }[];
}

// 3. Snapshot
export interface SnapshotPlayer {
  id: string;
  condition_est: number | null;
  condition_band: [number, number] | null;
  trend_per_min: number | null;
  hsr_m_10m: number;
  baseline_hsr_m_10m: number;
  sprints_10m: number;
  baseline_sprints_10m: number;
}

export interface Snapshot {
  t_ms: number;
  score: Record<TeamCode, number>;
  subs_left: Record<TeamCode, number>;
  windows_left: Record<TeamCode, number>;
  rates: Record<TeamCode, { for90: number; against90: number }>;
  players: SnapshotPlayer[];
  threat_by_channel: Record<string, number>;
}

// 4. Decision payload
export type Trigger = "condition_below_60" | "goal_after_55" | "manager_sub";
export type Strength = "strong" | "lean" | "toss_up";

export interface DecisionOption {
  id: string;
  label: string;
  win: number;
  draw: number;
  loss: number;
  xpts: number;
  delta_win: number;
  ci90?: [number, number];
}

export type Evidence =
  | { type: "condition"; player_id: string; value: number; trend_per_min: number }
  | { type: "flank_threat"; channel: string; share: number };

export interface DecisionPayload {
  decision_id: string;
  t_ms: number;
  team: TeamCode;
  trigger: Trigger;
  options: DecisionOption[];
  recommendation: { option_id: string; strength: Strength };
  evidence: Evidence[];
  manager_action: unknown;
}

// Agent output per locale and mode (dugout.agents.pipeline.Card).
export type Locale = "en" | "es" | "ca";
export type Mode = "casual" | "analyst";

export interface Narration {
  headline: string;
  reason: string;
  source: "model" | "template";
}

export interface DecisionCard {
  period: 1 | 2; // the payload's t_ms alone is ambiguous in first-half added time
  payload: DecisionPayload;
  narration: Partial<Record<Locale, Partial<Record<Mode, Narration>>>>;
}

// Home win probability over time. Not one of the four contracts: the fixture
// series comes from the engine's no-change run at each snapshot.
export interface WinProbPoint {
  period: 1 | 2;
  t_ms: number;
  team: TeamCode;
  win: number;
  draw: number;
  loss: number;
}

export interface RosterPlayer {
  team: TeamCode;
  name: string;
  role: "GK" | "CB" | "FB" | "CM" | "W" | "ST";
  side: "left" | "centre" | "right";
}

export interface Roster {
  home: TeamCode;
  away: TeamCode;
  teams: Record<TeamCode, { name: string }>;
  players: Record<string, RosterPlayer>;
}
