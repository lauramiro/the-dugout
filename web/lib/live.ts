// Web PubSub feed (open the page with ?source=live). Messages have no envelope, so each is
// recognised by its shape: a win-probability point or a closed card by its kind, a card by
// decision_id (the service's card carries the payload under `payload`; the old stub sent a
// bare payload), an event by seq (the pipeline sends key events only), a tracking frame by
// ball, a snapshot by subs_left. The roster comes from the demo's team sheet; until the
// pipeline sends period ends, only what arrives is shown. The demo match replays on a schedule
// (schedule.json, see ./schedule); a first-half message after the second half has started is
// the next replay, and starts a fresh log.

import { HALF_MS, lastAtOrBefore, liveHalf, toPos, type LiveHalf } from "./clock";
import type {
  CardClosed, CardMessage, DecisionCard, DecisionPayload, MatchEvent, Roster, Snapshot, TrackingFrame, WinProbMessage,
  WinProbPoint,
} from "./contracts";
import { emptyLog, interpolate, type DataSource, type FeedState, type PitchFrame, type Timed } from "./datasource";
import { parseSchedule, type Schedule } from "./schedule";

// public/config.json is written at deploy time by infra/deploy.sh: {"stubUrl": "https://..."}
async function loadStubUrl(): Promise<string> {
  const res = await fetch("/config.json");
  const { stubUrl } = (await res.json()) as { stubUrl: string };
  return stubUrl;
}

export class LiveDataSource implements DataSource {
  readonly kind = "live" as const;
  readonly controls = null;

  private state: FeedState = { status: "loading", error: null, log: emptyLog(), playhead: 0, playing: true, speed: 1 };
  private listeners = new Set<() => void>();
  private frames: Timed<TrackingFrame>[] = [];
  private ws: WebSocket | undefined;
  private disposed = false;
  private connecting: Promise<void> | null = null;
  private generation = 0;
  private half: LiveHalf = { firstHalfEnd: HALF_MS, secondHalf: false };
  /** Kick-off times, from schedule.json; null when the deployment has no scheduled replay. */
  schedule: Schedule | null = null;

  getState = (): FeedState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  start(): void {
    this.disposed = false;
    this.connecting ??= this.connect();
  }

  dispose(): void {
    this.disposed = true;
    this.ws?.close();
    this.ws = undefined;
    this.connecting = null;
  }

  frameAt(pos: number): PitchFrame | null {
    const i = lastAtOrBefore(this.frames, pos);
    return i < 0 ? null : interpolate(this.frames[i], this.frames[i], pos);
  }

  private set(patch: Partial<FeedState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }

  private async connect(): Promise<void> {
    const generation = ++this.generation;
    try {
      void this.loadRoster(generation);
      void this.loadSchedule(generation);
      const base = await loadStubUrl();
      const res = await fetch(`${base}/negotiate`);
      const { url } = (await res.json()) as { url: string | null };
      if (!url) throw new Error("Web PubSub is not configured on the stub");
      if (this.disposed || generation !== this.generation) return;
      this.ws = new WebSocket(url);
      this.ws.onopen = () => this.set({ status: "ready" });
      this.ws.onclose = () => this.set({ playing: false });
      this.ws.onerror = () => this.set({ status: "error", error: "Web PubSub connection failed" });
      this.ws.onmessage = (m) => {
        try {
          this.receive(JSON.parse(m.data as string) as Record<string, unknown>);
        } catch {
          // ignore messages that are not JSON
        }
      };
    } catch (err) {
      if (!this.disposed) this.set({ status: "error", error: err instanceof Error ? err.message : String(err) });
    }
  }

  // The scenario's team sheet, as a broadcaster has it before kick-off; without it the page
  // shows player ids.
  private async loadRoster(generation: number): Promise<void> {
    try {
      const res = await fetch("/demo/roster.json");
      if (!res.ok) return;
      const roster = (await res.json()) as Roster;
      if (this.disposed || generation !== this.generation) return;
      this.set({ log: { ...this.state.log, roster } });
    } catch {
      // no roster: names fall back to ids
    }
  }

  private async loadSchedule(generation: number): Promise<void> {
    try {
      const res = await fetch("/schedule.json");
      if (!res.ok) return;
      const schedule = parseSchedule(await res.json());
      if (this.disposed || generation !== this.generation) return;
      this.schedule = schedule;
      for (const l of this.listeners) l();
    } catch {
      // no schedule: the page waits for the feed without a kick-off time
    }
  }

  private receive(msg: Record<string, unknown>): void {
    if (msg.period === 1 && this.half.secondHalf) {
      // the next replay kicked off: keep the team sheet, drop the finished match
      this.half = { firstHalfEnd: HALF_MS, secondHalf: false };
      this.frames = [];
      this.set({ log: { ...emptyLog(), roster: this.state.log.roster }, playhead: 0 });
    }
    const log = this.state.log;
    const add = <T>(list: Timed<T>[], item: T, pos: number) => [...list, { pos, item }].sort((a, b) => a.pos - b.pos);
    // Each message's period (its own, or inferred) moves the learned end of the first half,
    // so first-half added time and the second half never share positions.
    const place = (period: 1 | 2 | undefined, tMs: number) => {
      const r = liveHalf(this.half, period, tMs);
      this.half = r.half;
      return { period: r.period, pos: toPos(r.period, tMs, r.half.firstHalfEnd) };
    };
    let pos: number;
    let next = log;
    if (msg.kind === "winprob") {
      const w = msg as unknown as WinProbMessage;
      pos = place(w.period, w.t_ms).pos;
      const point: WinProbPoint = { period: w.period, t_ms: w.t_ms, team: w.team, win: w.win, draw: w.draw, loss: w.loss };
      next = { ...log, winprob: add(log.winprob, point, pos) };
    } else if (msg.kind === "card_closed") {
      const c = msg as unknown as CardClosed;
      pos = place(c.period, c.t_ms).pos;
      const closed = { period: c.period, t_ms: c.t_ms, reason: c.reason };
      next = {
        ...log,
        cards: log.cards.map((x) => (x.item.payload.decision_id === c.id ? { ...x, item: { ...x.item, closed } } : x)),
      };
    } else if ("decision_id" in msg) {
      const full = "payload" in msg ? (msg as unknown as CardMessage) : null;
      const payload = full ? full.payload : (msg as unknown as DecisionPayload);
      const earlier = log.cards.find((c) => c.item.payload.decision_id === payload.decision_id)?.item;
      const narration = { ...earlier?.narration };
      if (full) {
        narration[full.locale] = {
          ...narration[full.locale],
          [full.mode]: { headline: full.headline, reason: full.reason, source: full.source, trace: full.trace },
        };
      }
      // Cards carry no period: a card keeps the one it got first, inferred from the halves so far.
      const placed = place(earlier?.period, payload.t_ms);
      const card: DecisionCard = { ...earlier, period: placed.period, payload, narration };
      pos = placed.pos;
      // A card sent again (another mode, or once the manager has acted) replaces the earlier
      // copy and keeps its narrations and closing.
      const others = log.cards.filter((c) => c.item.payload.decision_id !== payload.decision_id);
      next = { ...log, cards: add(others, card, pos) };
    } else if ("seq" in msg) {
      const e = msg as unknown as MatchEvent;
      pos = place(e.period, e.t_ms).pos;
      next = { ...log, events: add(log.events, e, pos) };
    } else if ("ball" in msg) {
      const f = msg as unknown as TrackingFrame;
      pos = place(f.period, f.t_ms).pos;
      this.frames = add(this.frames, f, pos);
    } else if ("subs_left" in msg) {
      const s = msg as unknown as Snapshot;
      pos = place(s.period, s.t_ms).pos;
      next = { ...log, snapshots: add(log.snapshots, s, pos) };
    } else {
      return;
    }
    const duration = Math.max(log.duration, pos);
    this.set({ log: { ...next, firstHalfEnd: this.half.firstHalfEnd, duration }, playhead: duration });
  }
}
