import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { formatMinute, lastAtOrBefore } from "../../lib/clock";
import type { DecisionCard, Locale } from "../../lib/contracts";
import { SPEEDS, type FeedState, type PlaybackControls, type Timed } from "../../lib/datasource";
import { decimal, type Translate } from "../../lib/i18n";

// What a first-time viewer needs around the picture: the name and premise, links that are
// always on screen, chapters to jump between decisions, a slate while there is no picture,
// and the About and How it's graded panels.

export type PanelId = "about" | "graded";

const REPO = "https://github.com/lauramiro/the-dugout/blob/main";
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
  t: Translate;
}

/** Name and links, always on; on a replay, play, speed and one chapter per decision plus
 *  kick-off and full time. */
export function Chrome({ cards, duration, feed, controls, onPanel, onSeek, t }: ChromeProps) {
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
        <button type="button" onClick={() => onPanel("about")}>{t("about")}</button>
        <DeskLink t={t} />
        <button type="button" onClick={() => onPanel("graded")}>{t("howGraded")}</button>
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
function Panel({ title, onClose, children, t }: { title: string; onClose: () => void; children: ReactNode; t: Translate }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="bc-dialog"
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
      </p>
    </Panel>
  );
}

// From docs/evaluation.md (rerun 2026-10-21, test set, calibrated constants) and
// eval/results/narration.md (run 2026-10-22). Rerun those and update these together.
const GRADED = {
  r: 0.72,
  rCi: [0.58, 0.82],
  sign: 75.7,
  points: 74,
  fadeSign: 100,
  fadePoints: 16,
  narrated: 94,
  narratedOf: 100,
  firstPass: 88.1,
};

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
