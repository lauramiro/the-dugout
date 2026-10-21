// Web PubSub feed (open the page with ?source=live). Messages have no envelope, so each is
// recognised by its shape: a closed card by its kind, a card by decision_id (the service's
// card carries the payload under `payload`; the old stub sent a bare payload), an event by
// seq, a tracking frame by ball, a snapshot by subs_left. Until the live pipeline sends the
// roster and period ends, only what arrives is shown.

import { HALF_MS, lastAtOrBefore, toPos } from "./clock";
import type { CardClosed, CardMessage, DecisionCard, DecisionPayload, MatchEvent, Snapshot, TrackingFrame } from "./contracts";
import { emptyLog, interpolate, type DataSource, type FeedState, type PitchFrame, type Timed } from "./datasource";

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

  private receive(msg: Record<string, unknown>): void {
    const log = this.state.log;
    const end1 = log.firstHalfEnd;
    const add = <T>(list: Timed<T>[], item: T, pos: number) => [...list, { pos, item }].sort((a, b) => a.pos - b.pos);
    let pos: number;
    let next = log;
    if (msg.kind === "card_closed") {
      const c = msg as unknown as CardClosed;
      pos = toPos(c.period, c.t_ms, end1);
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
          [full.mode]: { headline: full.headline, reason: full.reason, source: full.source },
        };
      }
      // The payload's t_ms alone is ambiguous in first-half added time; cards carry no period yet.
      const period = earlier?.period ?? (payload.t_ms >= HALF_MS ? 2 : 1);
      const card: DecisionCard = { ...earlier, period, payload, narration };
      pos = toPos(card.period, payload.t_ms, end1);
      // A card sent again (another mode, or once the manager has acted) replaces the earlier
      // copy and keeps its narrations and closing.
      const others = log.cards.filter((c) => c.item.payload.decision_id !== payload.decision_id);
      next = { ...log, cards: add(others, card, pos) };
    } else if ("seq" in msg) {
      const e = msg as unknown as MatchEvent;
      pos = toPos(e.period, e.t_ms, end1);
      next = { ...log, events: add(log.events, e, pos) };
    } else if ("ball" in msg) {
      const f = msg as unknown as TrackingFrame;
      pos = toPos(f.period, f.t_ms, end1);
      this.frames = add(this.frames, f, pos);
    } else if ("subs_left" in msg) {
      const s = msg as unknown as Snapshot;
      pos = toPos(s.t_ms >= HALF_MS ? 2 : 1, s.t_ms, end1);
      next = { ...log, snapshots: add(log.snapshots, s, pos) };
    } else {
      return;
    }
    const duration = Math.max(log.duration, pos);
    this.set({ log: { ...next, duration }, playhead: duration });
  }
}
