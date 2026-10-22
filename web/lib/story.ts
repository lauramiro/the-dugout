// The guided story: one decision seen on three screens. A pure function turns the match log
// into the story's steps, so the minutes, names and captions come from the data and a rebuild
// of the demo files keeps them right. The player in lib/storyPlayer.ts runs the steps.

import { formatMinute } from "./clock.ts";
import { managerPos } from "./calls.ts";
import type { DecisionCard, TeamCode } from "./contracts.ts";
import type { MatchLog, Timed } from "./datasource.ts";
import type { StringKey } from "./i18n.ts";

export type StoryScreen = "tv" | "tablet" | "phone" | "end";

export type StoryWait =
  | { kind: "play"; untilPos: number; speed: 1 | 5 | 20 }
  | { kind: "hold"; ms: number }
  | { kind: "vote"; ms: number; decisionId: string }
  | { kind: "stay" };

export interface StoryStep {
  id: "tv-open" | "tv-decision" | "tablet" | "vote" | "equaliser" | "manager" | "full-time" | "end";
  screen: StoryScreen;
  startPos: number;
  wait: StoryWait;
  caption: { key: StringKey; vars: Record<string, string> };
}

export interface StoryOptions {
  club: TeamCode;
  /** Whether the fan view exists: without it the vote and the manager's call stay on TV. */
  phone: boolean;
}

/** TV opens this long before the card. */
export const STORY_LEAD_MS = 80_000;
export const DECISION_HOLD_MS = 7_000;
export const TABLET_HOLD_MS = 12_000;
export const VOTE_MS = 15_000;
export const FULL_TIME_HOLD_MS = 12_000;
const GOAL_LEAD_MS = 15_000;
const GOAL_TAIL_MS = 6_000;
const MANAGER_LEAD_MS = 3_000;
const MANAGER_TAIL_MS = 6_000;
const CARD_TAIL_MS = 2_000;

const MIRROR: Record<string, string> = { left: "right", right: "left", centre: "centre" };

export function buildStory(log: MatchLog, options: StoryOptions): StoryStep[] | null {
  const { club, phone } = options;
  const found = log.cards.find((c) => c.item.payload.team === club && c.item.payload.trigger === "condition_drop");
  if (!found) return null;
  const card: Timed<DecisionCard> = found;
  const { payload } = card.item;
  const evidence = payload.evidence.find((e) => e.type === "condition");
  const playerId = evidence && "player_id" in evidence ? evidence.player_id : null;
  const roster = log.roster;
  const player = playerId ? roster?.players[playerId] : undefined;
  const playerName = player?.name ?? playerId ?? "";
  const teamName = (code: TeamCode) => roster?.teams[code]?.name ?? code;
  const opponent = roster ? (roster.home === club ? roster.away : roster.home) : null;
  const cardMinute = formatMinute(card.item.period, payload.t_ms);
  const voteScreen = phone ? "phone" : "tv";

  const steps: StoryStep[] = [
    {
      id: "tv-open", screen: "tv", startPos: Math.max(0, card.pos - STORY_LEAD_MS),
      wait: { kind: "play", untilPos: card.pos + CARD_TAIL_MS, speed: 5 },
      caption: { key: "story_open", vars: { team: teamName(club) } },
    },
    {
      id: "tv-decision", screen: "tv", startPos: card.pos + CARD_TAIL_MS, wait: { kind: "hold", ms: DECISION_HOLD_MS },
      caption: { key: "story_decision", vars: { player: playerName } },
    },
    {
      id: "tablet", screen: "tablet", startPos: card.pos + CARD_TAIL_MS, wait: { kind: "hold", ms: TABLET_HOLD_MS },
      caption: { key: "story_tablet", vars: { player: playerName } },
    },
    {
      id: "vote", screen: voteScreen, startPos: card.pos + CARD_TAIL_MS,
      wait: { kind: "vote", ms: VOTE_MS, decisionId: payload.decision_id },
      caption: { key: "story_vote", vars: {} },
    },
  ];

  const goal = log.events.find((e) => e.item.type === "goal" && e.item.team !== club && e.pos > card.pos);
  if (goal && opponent) {
    const down = goal.item.channel ? MIRROR[goal.item.channel] : null;
    const flank = down !== null && player !== undefined && down === player.side;
    steps.push({
      id: "equaliser", screen: "tv", startPos: goal.pos - GOAL_LEAD_MS,
      wait: { kind: "play", untilPos: goal.pos + GOAL_TAIL_MS, speed: 5 },
      caption: flank
        ? { key: "story_equaliser_flank", vars: { team: teamName(goal.item.team), player: playerName } }
        : { key: "story_equaliser", vars: { team: teamName(goal.item.team) } },
    });
  }

  const changedAt = managerPos(card.item, log.firstHalfEnd);
  if (changedAt !== null) {
    steps.push({
      id: "manager", screen: voteScreen, startPos: changedAt - MANAGER_LEAD_MS,
      wait: { kind: "play", untilPos: changedAt + MANAGER_TAIL_MS, speed: 5 },
      caption: { key: "story_manager", vars: { minutes: String(Math.round((changedAt - card.pos) / 60_000)) } },
    });
  }

  steps.push(
    {
      id: "full-time", screen: "tv", startPos: log.duration, wait: { kind: "hold", ms: FULL_TIME_HOLD_MS },
      caption: { key: "story_full_time", vars: { minute: cardMinute } },
    },
    { id: "end", screen: "end", startPos: log.duration, wait: { kind: "stay" }, caption: { key: "story_end", vars: {} } },
  );
  return steps;
}
