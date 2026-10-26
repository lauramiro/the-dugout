// What the fan view shows at a moment: the club's open card with its context (who, why now, the
// options, who is on the bench), the manager's call once it is known, or full time. Pure: the
// numbers are the card's own; nothing is computed that the card does not carry.

import { benchAt, type BenchPlayer } from "./bench.ts";
import { revealPos } from "./calls.ts";
import { formatMinute, lastAtOrBefore, toPos } from "./clock.ts";
import type { DecisionCard, Locale, Mode, Narration, Strength, TeamCode, Trigger } from "./contracts";
import { MANAGER_CALL_MS } from "./cues.ts";
import type { MatchLog, Timed } from "./datasource";
import { trend, type Trend } from "./derive.ts";

export interface FanContext {
  decisionId: string;
  minute: string;
  trigger: Trigger;
  strength: Strength;
  /** The flagged player; rank 1 is the lowest condition among his team's outfielders with an estimate. */
  player: { id: string; name: string; condition: number; trend: Trend; rank: number | null; of: number } | null;
  /** His flank's share of the chances against, when the card carries it, and that channel's side. */
  flankShare: number | null;
  flankSide: "left" | "centre" | "right" | null;
  /** Every option as priced; `pick` only on a strong or lean card (a toss-up picks nothing). */
  options: { id: string; win: number; deltaWin: number; pick: boolean }[];
  /** The bench players in the flagged player's position. */
  ready: BenchPlayer[];
  subsLeft: number;
  windowsLeft: number;
  narration: Narration | null;
}

export type FanMoment =
  | { kind: "waiting" }
  | { kind: "decision"; context: FanContext; card: Timed<DecisionCard> }
  | { kind: "call"; context: FanContext; card: Timed<DecisionCard>; manager: string | null; model: string }
  | { kind: "full-time" };

/** "RFC_left" to "left". */
function channelSide(channel: string): "left" | "centre" | "right" | null {
  const side = channel.split("_").at(-1);
  return side === "left" || side === "centre" || side === "right" ? side : null;
}

function context(log: MatchLog, card: Timed<DecisionCard>, pos: number, club: TeamCode, locale: Locale, mode: Mode): FanContext {
  const { payload } = card.item;
  const condition = payload.evidence.find((e) => e.type === "condition");
  const flank = payload.evidence.find((e) => e.type === "flank_threat");
  const roster = log.roster;
  const cardSnapAt = lastAtOrBefore(log.snapshots, card.pos);
  const cardSnap = cardSnapAt >= 0 ? log.snapshots[cardSnapAt].item : null;
  const nowSnapAt = lastAtOrBefore(log.snapshots, pos);
  const nowSnap = nowSnapAt >= 0 ? log.snapshots[nowSnapAt].item : null;

  let player: FanContext["player"] = null;
  if (condition && condition.type === "condition") {
    const team = roster?.players[condition.player_id]?.team ?? payload.team;
    const mates = (cardSnap?.players ?? [])
      .filter((p) => p.condition_est !== null && (roster?.players[p.id]?.team ?? p.id.split("-")[0]) === team)
      .sort((a, b) => (a.condition_est ?? 0) - (b.condition_est ?? 0));
    const at = mates.findIndex((p) => p.id === condition.player_id);
    player = {
      id: condition.player_id,
      name: roster?.players[condition.player_id]?.name ?? condition.player_id,
      condition: condition.value,
      trend: trend(condition.trend_per_min),
      rank: at >= 0 ? at + 1 : null,
      of: mates.length,
    };
  }
  const role = player ? roster?.players[player.id]?.role : undefined;
  const { recommendation } = payload;
  return {
    decisionId: payload.decision_id,
    minute: formatMinute(card.item.period, payload.t_ms),
    trigger: payload.trigger,
    strength: recommendation.strength,
    player,
    flankShare: flank && flank.type === "flank_threat" ? flank.share : null,
    flankSide: flank && flank.type === "flank_threat" ? channelSide(flank.channel) : null,
    options: payload.options.map((o) => ({
      id: o.id, win: o.win, deltaWin: o.delta_win,
      pick: recommendation.strength !== "toss_up" && o.id === recommendation.option_id,
    })),
    ready: benchAt(log, pos, club).filter((p) => !role || p.role === role),
    subsLeft: nowSnap?.subs_left[club] ?? 0,
    windowsLeft: nowSnap?.windows_left[club] ?? 0,
    narration: card.item.narration[locale]?.[mode] ?? card.item.narration.en?.[mode] ?? card.item.narration.en?.casual ?? null,
  };
}

/** The fan's moment at `pos` for `club`: full time, a manager's call being revealed (the
 *  earliest card when one change answers several), the open card, or nothing. */
export function fanMoment(log: MatchLog, pos: number, club: TeamCode, locale: Locale, mode: Mode,
                          live = false): FanMoment {
  // Live, the playhead is always the end of the log so far, so only a replay can reach full time
  // (as on the TV picture and the desk).
  if (!live && log.duration > 0 && pos >= log.duration) return { kind: "full-time" };
  const cards = log.cards.filter((c) => c.item.payload.team === club);

  const revealed = cards.find((c) => {
    if (c.item.payload.trigger === "manager_sub") return false; // raised by the change itself
    const at = revealPos(c, log.firstHalfEnd);
    return at !== null && at <= pos && pos < at + MANAGER_CALL_MS;
  });
  if (revealed) {
    return {
      kind: "call", card: revealed, context: context(log, revealed, pos, club, locale, mode),
      // the option the manager took, comparable with the fan's vote (the review's "manager_later" is not)
      manager: revealed.item.payload.manager_action?.option_id ?? null, model: revealed.item.payload.recommendation.option_id,
    };
  }

  const open = [...cards].reverse().find((c) => {
    if (c.pos > pos) return false;
    const closed = c.item.closed;
    return !closed || pos < toPos(closed.period, closed.t_ms, log.firstHalfEnd);
  });
  if (open) return { kind: "decision", card: open, context: context(log, open, pos, club, locale, mode) };
  return { kind: "waiting" };
}
