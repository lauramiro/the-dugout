import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type RefObject } from "react";
import { formatMinute, toPos } from "../lib/clock";
import type { DecisionCard, MatchEvent, Roster, TeamCode, WinProbPoint } from "../lib/contracts";
import type { Timed } from "../lib/datasource";
import type { Translate } from "../lib/i18n";

const H = 132;
const PAD = { left: 34, right: 12, top: 18, bottom: 26 };

function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

interface Props {
  winprob: Timed<WinProbPoint>[];
  goals: Timed<MatchEvent>[];
  cards: Timed<DecisionCard>[];
  playhead: number;
  duration: number;
  firstHalfEnd: number;
  roster: Roster | null;
  focus: TeamCode;
  onSeek: ((pos: number) => void) | null;
  t: Translate;
}

export function Timeline({ winprob, goals, cards, playhead, duration, firstHalfEnd, roster, focus, onSeek, t }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const innerW = Math.max(0, width - PAD.left - PAD.right);
  const innerH = H - PAD.top - PAD.bottom;
  const span = Math.max(duration, 1);
  const x = (pos: number) => PAD.left + (pos / span) * innerW;
  const y = (p: number) => PAD.top + (1 - p) * innerH;
  // The series is the home side's; for the away side the payload's own loss field is its win.
  const home = roster?.home;
  const value = (w: WinProbPoint) => (focus === w.team ? w.win : w.loss);
  const teamName = roster?.teams[focus]?.name ?? focus;
  const shown = winprob.filter((w) => w.pos <= playhead);
  const path = shown.map((w, i) => `${i ? "L" : "M"}${x(w.pos).toFixed(1)} ${y(value(w.item)).toFixed(1)}`).join(" ");
  const area = shown.length ? `${path} L${x(shown[shown.length - 1].pos).toFixed(1)} ${y(0)} L${x(shown[0].pos).toFixed(1)} ${y(0)} Z` : "";
  const halfX = x(toPos(2, 2_700_000, firstHalfEnd));

  const seekFromClick = (e: MouseEvent<SVGRectElement>) => {
    if (!onSeek) return;
    const box = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - box.left) / box.width) * span);
  };
  const keySeek = (pos: number) => (e: KeyboardEvent) => {
    if (onSeek && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      onSeek(pos);
    }
  };

  return (
    <section className="timeline" aria-label={t("timeline")}>
      <div className="section-head">
        <h2 className="eyebrow">{t("timelineTeam", { team: teamName })}</h2>
        {onSeek && <span className="help">{t("seekHint")}</span>}
      </div>
      <div ref={ref} className="timeline-plot">
        {width > 0 && (
          <svg width={width} height={H} role="img" aria-label={t("timelineTeam", { team: teamName })}>
            {[0, 0.25, 0.5, 0.75, 1].map((g) => (
              <g key={g} className={`grid${g === 0.5 ? " mid" : ""}`}>
                <line x1={PAD.left} x2={PAD.left + innerW} y1={y(g)} y2={y(g)} />
                {g % 0.5 === 0 && (
                  <text x={PAD.left - 6} y={y(g) + 3.5} textAnchor="end">
                    {g * 100}%
                  </text>
                )}
              </g>
            ))}
            <line className="half-line" x1={halfX} x2={halfX} y1={PAD.top - 6} y2={y(0)} />
            {onSeek && (
              <rect className="seek-area" x={PAD.left} y={0} width={innerW} height={H - PAD.bottom + 4} onClick={seekFromClick} />
            )}
            <path className={`wp-area ${focus === home ? "home" : "away"}`} d={area} />
            <path className={`wp-line ${focus === home ? "home" : "away"}`} d={path} />
            {goals
              .filter((g) => g.pos <= playhead)
              .map((g) => (
                <g key={g.item.seq} className={`goal-mark ${g.item.team === home ? "home" : "away"}`} transform={`translate(${x(g.pos)} ${PAD.top - 9})`}>
                  <title>{`${formatMinute(g.item.period, g.item.t_ms)} ${t("goal")} ${g.item.team}`}</title>
                  <circle r={4.5} />
                  <line y1={4.5} y2={y(0) - PAD.top + 9} />
                </g>
              ))}
            {cards.map((c) => {
              const minute = formatMinute(c.item.period, c.item.payload.t_ms);
              const past = c.pos <= playhead;
              return (
                <g
                  key={c.item.payload.decision_id}
                  className={`diamond${past ? " past" : ""}${c.item.payload.team === home ? " home" : " away"}`}
                  transform={`translate(${x(c.pos)} ${y(0) + 12})`}
                  role={onSeek ? "button" : undefined}
                  tabIndex={onSeek ? 0 : undefined}
                  aria-label={t("jumpTo", { minute })}
                  onClick={onSeek ? () => onSeek(c.pos) : undefined}
                  onKeyDown={keySeek(c.pos)}
                >
                  <title>{t("jumpTo", { minute })}</title>
                  <rect x={-12} y={-12} width={24} height={24} className="hit" />
                  <path d="M0 -6 L6 0 L0 6 L-6 0 Z" />
                </g>
              );
            })}
            <line className="playhead" x1={x(playhead)} x2={x(playhead)} y1={PAD.top - 6} y2={y(0)} />
          </svg>
        )}
      </div>
    </section>
  );
}
