"use client";

import type { ReactNode } from "react";
import type { StoryStep } from "../../lib/story";
import type { StoryEvent, StoryState } from "../../lib/storyPlayer";
import type { Translate } from "../../lib/i18n";
import type { PanelId } from "../broadcast/Landing";

// The guided story's own pieces: the intro that offers it, the caption bar that runs it, the
// end card, and the host that shows a step's screen over the TV picture.

const SEEN_KEY = "dugout.storySeen";

/** Whether this browser has started or skipped the story before. Storage is optional: without it
 *  the intro shows on every visit. */
export function storySeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function markStorySeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // storage blocked: the intro shows again next time
  }
}

/** Over the picture on a first visit: start the story, or skip to the broadcast as it is. */
export function StoryIntro({ onStart, onSkip, t }: { onStart: () => void; onSkip: () => void; t: Translate }) {
  return (
    <section className="st-intro" aria-labelledby="st-intro-name">
      <h1 id="st-intro-name">The Dugout</h1>
      <p className="st-intro-premise">{t("premise")}</p>
      <p className="st-intro-lead">{t("storyIntroLead")}</p>
      <p className="st-intro-actions">
        <button type="button" className="st-primary" onClick={onStart}>{t("storyStart")}</button>
        <button type="button" onClick={onSkip}>{t("storySkip")}</button>
      </p>
      <p className="st-intro-note">{t("demoNote")}</p>
    </section>
  );
}

/** The caption for the current step, its place in the story, and the controls. */
export function StoryOverlay({ step, state, total, send, onLeave, t }: {
  step: StoryStep;
  state: StoryState;
  total: number;
  send: (event: StoryEvent) => void;
  onLeave: () => void;
  t: Translate;
}) {
  const now = () => performance.now();
  const paused = state.status === "paused";
  return (
    <div className="st-bar" role="region" aria-label={t("storyLabel")}>
      <span className="st-count">{t("storyStep", { n: state.index + 1, total })}</span>
      <p className="st-caption" aria-live="polite">{t(step.caption.key, step.caption.vars)}</p>
      <span className="st-controls">
        <button type="button" onClick={() => send({ type: paused ? "resume" : "pause", now: now() })}>
          {paused ? t("storyResume") : t("storyPause")}
        </button>
        <button type="button" onClick={() => send({ type: "next", now: now() })}>{t("storyNext")}</button>
        <button type="button" onClick={onLeave}>{t("storyLeave")}</button>
      </span>
    </div>
  );
}

/** After full time: where to go next. */
export function StoryEnd({ onReplay, onClose, onPanel, extra, t }: {
  onReplay: () => void;
  onClose: () => void;
  onPanel: (panel: PanelId) => void;
  /** More ways in (the fan view, once it exists). */
  extra?: ReactNode;
  t: Translate;
}) {
  return (
    <section className="st-end" aria-labelledby="st-end-title">
      <h2 id="st-end-title">{t("story_end")}</h2>
      <p className="st-intro-actions">
        <button type="button" className="st-primary" onClick={onClose}>{t("storyTv")}</button>
        <a href="/desk">{t("analystDesk")}</a>
        {extra}
        <button type="button" onClick={() => onPanel("graded")}>{t("howGraded")}</button>
        <button type="button" onClick={onReplay}>{t("storyReplay")}</button>
      </p>
    </section>
  );
}

/** A step's screen over the TV picture (the tablet's desk, later the phone's fan view). */
export function StoryScreen({ device, children }: { device: "tablet" | "phone"; children: ReactNode }) {
  return <div className={`st-screen ${device}`}>{children}</div>;
}
