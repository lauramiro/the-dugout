import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { formatMinute, lastAtOrBefore } from "../../lib/clock";
import type { DecisionCard, Locale, Narration, Roster } from "../../lib/contracts";
import { withNames } from "../../lib/derive";
import { SPEEDS, type FeedState, type PlaybackControls, type Timed } from "../../lib/datasource";
import { decimal, type StringKey, type Translate } from "../../lib/i18n";
import { TraceSteps } from "../TraceSteps";
import { CLAUDE_COMMAND, HOOD_CHAIN, HOOD_FLOW, HOOD_SERVICES, MCP_URL, REPO_URL, VSCODE_CONFIG } from "../../lib/hood";

// What a first-time viewer needs around the picture: the name and premise, links that are
// always on screen, chapters to jump between decisions, a slate while there is no picture,
// and the About, How it's graded and Under the hood panels.

export type PanelId = "about" | "graded" | "hood" | "trace";

const REPO = `${REPO_URL}/blob/main`;
const TITLE_MS = 8000;

/** Keeps ?source=live and ?t= when moving to the desk. */
function DeskLink({ t, className }: { t: Translate; className?: string }) {
  return (
    <a className={className} href="/desk" onClick={(e) => { e.currentTarget.href = `/desk${window.location.search}`; }}>
      {t("analystDesk")}
    </a>
  );
}

interface ChromeProps {
  cards: readonly Timed<DecisionCard>[];
  duration: number;
  feed: FeedState;
  controls: PlaybackControls | null;
  onPanel: (panel: PanelId) => void;
  onSeek: () => void;
  /** Starts the guided story; absent when there is none (live, or a ?t= link). */
  onStory?: () => void;
  t: Translate;
}

/** Name and links, always on; on a replay, play, speed and one chapter per decision plus
 *  kick-off and full time. */
export function Chrome({ cards, duration, feed, controls, onPanel, onSeek, onStory, t }: ChromeProps) {
  const ready = feed.status === "ready";
  const chapters = [
    { pos: 0, label: t("kickOffShort"), title: t("jumpKickOff") },
    ...cards.map((c) => {
      const minute = formatMinute(c.item.period, c.item.payload.t_ms);
      return { pos: c.pos, label: minute, title: t("jumpTo", { minute }) };
    }),
    { pos: duration, label: t("fullTimeShort"), title: t("jumpFullTime") },
  ];
  const current = lastAtOrBefore(chapters, feed.playhead);
  const jump = (pos: number) => {
    if (!controls) return;
    controls.seek(pos);
    if (!feed.playing && pos < duration) controls.play();
    onSeek();
  };
  return (
    <div className="bc-chrome">
      <nav className="bc-nav" aria-label="The Dugout">
        <span className="bc-brand">The Dugout</span>
        {onStory && <button type="button" onClick={onStory}>{t("watchStory")}</button>}
        <button type="button" onClick={() => onPanel("about")}>{t("about")}</button>
        <DeskLink t={t} />
        <button type="button" onClick={() => onPanel("graded")}>{t("howGraded")}</button>
        <button type="button" onClick={() => onPanel("hood")}>{t("hoodNav")}</button>
      </nav>
      {controls && ready && (
        <div className="bc-transport">
          <button type="button" className="bc-play" onClick={() => (feed.playing ? controls.pause() : controls.play())}>
            {feed.playing ? t("pause") : t("play")}
          </button>
          <span className="bc-speeds" role="group" aria-label={t("speed")}>
            {SPEEDS.map((s) => (
              <button key={s} type="button" aria-pressed={feed.speed === s} onClick={() => controls.setSpeed(s)}>
                {s}x
              </button>
            ))}
          </span>
          <span className="bc-chapters" role="group" aria-label={t("chapters")}>
            {chapters.map((c, i) => (
              <button key={`${c.pos}-${i}`} type="button" title={c.title} aria-label={c.title}
                aria-current={i === current ? "true" : undefined} onClick={() => jump(c.pos)}>
                {c.label}
              </button>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}

/** The name and premise over the running picture for TITLE_MS, until the first decision
 *  opens, or until clicked. */
export function TitleCard({ replay, onDone, t }: { replay: boolean; onDone: () => void; t: Translate }) {
  useEffect(() => {
    const timer = setTimeout(onDone, TITLE_MS);
    return () => clearTimeout(timer);
  }, [onDone]);
  return (
    <section className="bc-title" aria-labelledby="bc-title-name" onClick={onDone}>
      <h1 id="bc-title-name">The Dugout</h1>
      <p className="bc-title-premise">{t("premise")}</p>
      <p className="bc-title-hint">{t("titleHint")}</p>
      {replay && <p className="bc-title-note">{t("demoNote")}</p>}
      <button type="button" className="bc-title-close" onClick={onDone}>{t("dismiss")}</button>
    </section>
  );
}

/** Centred over the picture while there is nothing to show: loading, waiting for live, or an error. */
export function Slate({ kind, error, t }: { kind: "loading" | "waiting" | "error"; error: string | null; t: Translate }) {
  return (
    <div className={`bc-slate ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <p className="bc-slate-name">The Dugout</p>
      <p className="bc-slate-text">
        {kind === "error" ? t("loadError", { error: error ?? "" }) : kind === "waiting" ? t("waitingLive") : t("loading")}
      </p>
      {kind === "waiting" && <a className="bc-slate-link" href="/">{t("watchReplay")}</a>}
    </div>
  );
}

/** A modal panel over the whole window (the top layer, so the picture's size does not limit it). */
function Panel({ title, onClose, children, t, className }: { title: string; onClose: () => void; children: ReactNode; t: Translate; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className={className ? `bc-dialog ${className}` : "bc-dialog"}
      aria-labelledby="bc-dialog-title"
      onClose={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bc-dialog-body">
        <header className="bc-dialog-head">
          <h2 id="bc-dialog-title">{title}</h2>
          <button type="button" onClick={onClose}>{t("close")}</button>
        </header>
        {children}
      </div>
    </dialog>
  );
}

export function AboutPanel({ onClose, onPanel, t }: { onClose: () => void; onPanel: (panel: PanelId) => void; t: Translate }) {
  return (
    <Panel title="The Dugout" onClose={onClose} t={t}>
      <p className="bc-dialog-lead">{t("premise")}</p>
      <p>{t("aboutLead")}</p>
      <ol className="bc-dialog-steps">
        <li>{t("aboutHow1")}</li>
        <li>{t("aboutHow2")}</li>
        <li>{t("aboutHow3")}</li>
      </ol>
      <p>{t("aboutScreen")}</p>
      <p className="bc-dialog-note">{t("aboutData")}</p>
      <p className="bc-dialog-links">
        <DeskLink t={t} />
        <button type="button" onClick={() => onPanel("graded")}>{t("howGraded")}</button>
        <button type="button" onClick={() => onPanel("hood")}>{t("hoodNav")}</button>
      </p>
    </Panel>
  );
}

// From docs/evaluation.md (rerun 2026-10-22, test set, calibrated constants) and
// eval/results/narration.md (run 2026-10-23). Rerun those and update these together.
const GRADED = {
  r: 0.74,
  rCi: [0.62, 0.83],
  sign: 78.4,
  points: 74,
  fadeSign: 100,
  fadePoints: 16,
  narrated: 83,
  narratedOf: 100,
  firstPass: 84.2,
};

/** How one line was written: each agent step and what the code check made of it. */
export function TracePanel({ narration, roster, onClose, t }: {
  narration: Narration | undefined; roster: Roster | null; onClose: () => void; t: Translate;
}) {
  return (
    <Panel title={t("traceTitle")} onClose={onClose} t={t}>
      <p className="bc-dialog-lead">{narration ? withNames(`${narration.headline} ${narration.reason}`, roster) : ""}</p>
      <p className="bc-dialog-note">{t("traceLead")}</p>
      <TraceSteps narration={narration} roster={roster} t={t} />
    </Panel>
  );
}

export function GradedPanel({ onClose, locale, t }: { onClose: () => void; locale: Locale; t: Translate }) {
  const n = (v: number, digits: number) => decimal(v, locale, digits);
  const stats: { value: string; detail: string; label: string }[] = [
    { value: `r ${n(GRADED.r, 2)}`, detail: `${t("ci90")} ${n(GRADED.rCi[0], 2)} / ${n(GRADED.rCi[1], 2)}`, label: t("gradedR") },
    { value: `${n(GRADED.sign, 1)}%`, detail: t("gradedPoints", { n: GRADED.points }), label: t("gradedSign") },
    { value: `${GRADED.fadeSign}%`, detail: t("gradedPoints", { n: GRADED.fadePoints }), label: t("gradedFade") },
    {
      value: `${GRADED.narrated}/${GRADED.narratedOf}`,
      detail: t("gradedFirstPass", { v: n(GRADED.firstPass, 1) }),
      label: t("gradedNarration"),
    },
  ];
  return (
    <Panel title={t("howGraded")} onClose={onClose} t={t}>
      <p className="bc-dialog-lead">{t("gradedLead")}</p>
      <dl className="bc-graded-stats">
        {stats.map((s) => (
          <div key={s.label}>
            <dt>{s.label}</dt>
            <dd><strong>{s.value}</strong> <span>{s.detail}</span></dd>
          </div>
        ))}
      </dl>
      <p className="bc-dialog-note">{t("gradedScope")}</p>
      <figure className="bc-graded-figure">
        {/* A copy of eval/results/counterfactual.svg, written by eval/counterfactual.py. */}
        <img src="/eval/counterfactual.svg" alt={t("gradedScatter")} width={940} height={508} />
        <figcaption>{t("gradedScatter")}</figcaption>
      </figure>
      <p className="bc-dialog-note">{t("gradedCaveat")}</p>
      <p className="bc-dialog-links">
        <a href={`${REPO}/docs/evaluation.md`} target="_blank" rel="noreferrer">{t("gradedMore")}</a>
        <a href={`${REPO}/eval/results/narration.md`} target="_blank" rel="noreferrer">{t("narrationMore")}</a>
      </p>
    </Panel>
  );
}

/** What runs where: the architecture, one row per service, the agent chain and the MCP endpoint.
 *  No live status: the decision service scales to zero, so a cold start would read as broken. */
export function HoodPanel({ onClose, onPanel, t }: { onClose: () => void; onPanel: (panel: PanelId) => void; t: Translate }) {
  return (
    <Panel title={t("hoodTitle")} onClose={onClose} t={t} className="bc-hood-dialog">
      <p className="bc-dialog-lead">{t("hoodLead")}</p>
      <figure className="bc-hood-figure">
        {/* Drawn here so it reads at any width; the full diagram (docs/architecture.svg) opens below. */}
        <div className="bc-flow" role="img" aria-label={t("hoodDiagramAlt")}>
          {HOOD_FLOW.map((lane) => (
            <div key={lane.id} className="bc-flow-lane">
              <p className="bc-flow-title">{t(`hoodLane_${lane.id}` as StringKey)}</p>
              <ol className="bc-flow-row" aria-hidden="true">
                {lane.nodes.map((node, i) => (
                  <Fragment key={`${lane.id}-${node.id}`}>
                    {i > 0 && <li className="bc-flow-edge">{t(`hoodEdge_${lane.edges[i - 1]}` as StringKey)}</li>}
                    <li className={`bc-flow-node${node.brand ? " brand" : ""}`}>
                      <b>{node.brand ?? t(`hoodNode_${node.id}` as StringKey)}</b>
                      <span>{t(`hoodSub_${node.id}` as StringKey)}</span>
                    </li>
                  </Fragment>
                ))}
              </ol>
            </div>
          ))}
          <p className="bc-flow-note">{t("hoodFlowRegistry")}</p>
        </div>
        <figcaption>
          <a className="bc-hood-open" href="/architecture.svg" target="_blank" rel="noreferrer">
            {t("hoodDiagramOpen")} <span className="bc-sr">{t("newTab")}</span>
          </a>
        </figcaption>
      </figure>
      <h3 className="bc-hood-h">{t("hoodServices")}</h3>
      <dl className="bc-hood-services">
        {HOOD_SERVICES.map((s) => (
          <div key={s.id}>
            <dt>{s.name}</dt>
            <dd>{t(`hood_${s.id}`)}</dd>
          </div>
        ))}
      </dl>
      <h3 className="bc-hood-h">{t("hoodChain")}</h3>
      <ol className="bc-hood-chain" role="list">
        {HOOD_CHAIN.map((s) => (
          <li key={s.id} className={s.check ? "check" : undefined}>{t(`hood_${s.id}`)}</li>
        ))}
      </ol>
      <p className="bc-dialog-note">{t("hoodChainNote")}</p>
      <h3 className="bc-hood-h">{t("hoodMcp")}</h3>
      <p className="bc-hood-url"><code>{MCP_URL}</code></p>
      <p className="bc-hood-label">{t("hoodMcpClaude")}</p>
      <p className="bc-hood-url"><code>{CLAUDE_COMMAND}</code></p>
      <p className="bc-hood-label">{t("hoodMcpVscode")}</p>
      <p className="bc-hood-url"><code>{VSCODE_CONFIG}</code></p>
      <p className="bc-dialog-links">
        <a href={REPO_URL} target="_blank" rel="noreferrer">{t("hoodRepo")} <span className="bc-sr">{t("newTab")}</span></a>
        <button type="button" onClick={() => onPanel("graded")}>{t("howGraded")}</button>
      </p>
    </Panel>
  );
}

/** Whether the title card is still up: once per page load, closed by its timer, a click,
 *  a jump, or the first decision. */
export function useTitleCard(firstDecision: boolean): [boolean, () => void] {
  const [shown, setShown] = useState(true);
  useEffect(() => {
    if (firstDecision) setShown(false);
  }, [firstDecision]);
  const hide = useCallback(() => setShown(false), []);
  return [shown, hide];
}
