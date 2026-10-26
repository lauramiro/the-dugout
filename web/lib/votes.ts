// "Your call" votes. A replay keeps them in the page; live mode also posts them to the
// decision service (POST /votes, GET /votes/{decision_id}) for the crowd tally.

import { serviceUrl } from "./config.ts";

export interface Tally {
  decision_id: string;
  counts: Record<string, number>;
  total: number;
}

export interface VoteStore {
  /** Send a vote; resolves to the crowd tally, or null when there is no crowd (replay). */
  cast(decisionId: string, optionId: string): Promise<Tally | null>;
  tally(decisionId: string): Promise<Tally | null>;
}

const VIEWER_KEY = "dugout.viewer";

/** A random id per browser, so the service can refuse a second vote on the same card. */
function viewerId(): string {
  const fresh = () =>
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `v-${Math.random().toString(36).slice(2)}`;
  try {
    const known = localStorage.getItem(VIEWER_KEY);
    if (known) return known;
    const id = fresh();
    localStorage.setItem(VIEWER_KEY, id);
    return id;
  } catch {
    return fresh();
  }
}

export class LocalVotes implements VoteStore {
  async cast(): Promise<Tally | null> {
    return null;
  }

  async tally(): Promise<Tally | null> {
    return null;
  }
}

export class ServiceVotes implements VoteStore {
  private viewer: string | null = null;

  async cast(decisionId: string, optionId: string): Promise<Tally | null> {
    this.viewer ??= viewerId();
    const res = await fetch(`${await serviceUrl()}/votes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision_id: decisionId, viewer_id: this.viewer, option_id: optionId }),
    });
    // 409: this browser already voted on the card (a reload); the tally still stands.
    if (res.status === 409) return this.tally(decisionId);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as Tally;
  }

  async tally(decisionId: string): Promise<Tally | null> {
    const res = await fetch(`${await serviceUrl()}/votes/${encodeURIComponent(decisionId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as Tally;
  }
}
