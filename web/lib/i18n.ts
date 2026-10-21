// UI strings, in English (the project is English only). Narration text comes from the agents
// (or their template fallback); only the chrome around it lives here.

import type { Locale, Strength, Trigger } from "./contracts";

const en = {
  tagline: "Live decision guide",
  replay: "Replay",
  live: "Live",
  demoNote: "Recorded demo: fictional clubs, synthetic data, model estimates.",
  play: "Play",
  pause: "Pause",
  restart: "Replay from kick-off",
  speed: "Speed",
  view: "View",
  casual: "Casual",
  analyst: "Analyst",
  club: "Club",
  half1: "1st half",
  half2: "2nd half",
  fullTime: "Full time",
  loading: "Loading the match",
  loadError: "The match files did not load ({error}). Reload the page to try again.",
  waitingLive: "Waiting for the live feed.",
  pitch: "Pitch: player positions and the ball",
  ticker: "Match events",
  noEvents: "Events appear here as the match plays.",
  goal: "Goal",
  shot_saved: "Shot saved",
  shot_blocked: "Shot blocked",
  shot_off_target: "Shot off target",
  sub: "Substitution",
  subLine: "{off} off, {on} on",
  card: "Card",
  dugout: "Dugout",
  condition: "Condition",
  conditionHelp: "Estimated from minutes on the pitch and in the last 7 days, runs made, and running against each player's own first 20 minutes.",
  na: "n/a",
  subsLeft: "{n} subs left",
  windowsLeft: "{n} windows left",
  belowIn: "{name} below 69% in about {n} min",
  below: "{name} below 69%",
  atLine: "{name} at 69% now",
  decision: "Decision",
  noDecision: "No decision open. A card opens when a player's condition falls well below his team's and under 69%, after a goal from 55', or at a substitution.",
  trigger_condition_drop: "Fading against his team",
  trigger_goal_after_55: "Goal after 55'",
  trigger_manager_sub: "Manager's substitution",
  yourClub: "Your club",
  opponent: "Opponent",
  options: "Options",
  win: "Win",
  draw: "Draw",
  loss: "Loss",
  xpts: "Exp. points",
  gap: "Gap",
  pts: "pts",
  reference: "reference",
  ci90: "90% interval",
  modelPick: "Model's pick",
  strength_strong: "strong",
  strength_lean: "lean",
  strength_toss_up: "toss-up",
  strengthTitle: "Strength",
  opt_no_change: "No change",
  opt_sub_like_for_like: "Like-for-like sub for {name}",
  opt_attacking: "Attacking change",
  opt_defensive: "Defensive change",
  evidence: "Evidence",
  ev_condition: "{name} at {pct}",
  ev_trend: "{v}% per min",
  ev_flank: "{side} flank: {pct} of chances against",
  side_left: "Left",
  side_centre: "Centre",
  side_right: "Right",
  hsr: "High-speed running, last 10 min",
  sprints: "Sprints, last 10 min",
  baseline: "baseline {v}",
  rates: "Scoring rate per 90",
  ratesValue: "{for} for, {against} against",
  narrationSource: "Narration",
  source_model: "model, checked in code",
  source_template: "template",
  timeline: "Win probability",
  timelineTeam: "{team} win probability",
  jumpTo: "Jump to the {minute} decision",
  seekHint: "Click the line to jump; diamonds mark decisions.",
  yourCall: "Your call",
  yourCallPrompt: "What would you do? Lock in a call before the manager does.",
  secondsLeft: "{n} s left",
  timeUp: "Time is up: no call made on this card.",
  lockedIn: "Locked in: {option}",
  waitingManager: "Waiting for the manager's call.",
  theCalls: "The calls at {minute}",
  you: "You",
  model: "Model",
  manager: "Manager",
  noCall: "No call",
  closeCall: "options close",
  managerNoChange: "No change",
  managerLater: "Like-for-like change at {minute}",
  unpriced: "A change the card did not price",
  crowd: "{n} votes on this card",
  voteError: "Your vote did not reach the server ({error}); it still counts on this screen.",
  review: "Full-time review",
  reviewSoFar: "Review so far",
  openReview: "Review",
  close: "Close",
  reviewIntro: "Each decision, the option the model rated highest and the call the manager made. Model estimates on the card's own simulations, not hindsight.",
  colMinute: "Min.",
  colDecision: "Decision",
  colManager: "Manager's call",
  colModel: "Model's call",
  colGap: "Trade-off",
  colRecap: "Recap",
  colYou: "Your call",
  gapValue: "{win} pts win · {xpts} exp. pts",
  gapNone: "no gap to show",
  notYet: "Not known yet",
  iq: "Manager IQ",
  iqValue: "{a} of {n}",
  iqHelp: "Your calls that matched the model's option. Toss-ups are left out.",
  iqNone: "Vote on a card to get a manager IQ.",
  managerIq: "The manager matched the model on {a} of {n}.",
  noDecisionsYet: "No decisions yet.",
  recapTemplate: "template",
} as const;

export type StringKey = keyof typeof en;
type Dict = Record<StringKey, string>;

const DICTS: Record<Locale, Dict> = { en };
export const LOCALES: readonly Locale[] = ["en"];

export type Translate = (key: StringKey, vars?: Record<string, string | number>) => string;

export function translator(locale: Locale): Translate {
  const dict = DICTS[locale];
  return (key, vars) => {
    let text = dict[key] ?? en[key];
    if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
    return text;
  };
}

export const triggerKey = (t: Trigger): StringKey => `trigger_${t}` as StringKey;
export const strengthKey = (s: Strength): StringKey => `strength_${s}` as StringKey;

/** A payload probability (0.818) as a percentage string ("81.8"). */
export function pct(value: number, _locale: Locale, digits = 1): string {
  return (Math.round(value * 100 * 10 ** digits) / 10 ** digits).toFixed(digits);
}

/** A payload gap (0.032) in points with its sign ("+3.2"). */
export function points(value: number, _locale: Locale): string {
  const n = Math.round(value * 1000) / 10;
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}`;
}

export function decimal(value: number, _locale: Locale, digits: number): string {
  return value.toFixed(digits);
}
