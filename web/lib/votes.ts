// "Your call" votes. A replay keeps them in the page; live mode also posts them to the
// decision service (POST /votes, GET /votes/{decision_id}) for the crowd tally.

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

// public/config.json is written at deploy time by infra/deploy.sh: {"stubUrl": "https://..."}
export class ServiceVotes implements VoteStore {
  private base: Promise<string> | null = null;
  private viewer: string | null = null;

  private url(): Promise<string> {
    this.base ??= fetch("/config.json")
      .then((res) => res.json() as Promise<{ stubUrl: string }>)
      .then((c) => c.stubUrl)
      .catch((err: unknown) => {
        this.base = null; // a failed fetch is tried again on the next vote, not kept
        throw err;
      });
    return this.base;
  }

  async cast(decisionId: string, optionId: string): Promise<Tally | null> {
    this.viewer ??= viewerId();
    const res = await fetch(`${await this.url()}/votes`, {
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
    const res = await fetch(`${await this.url()}/votes/${encodeURIComponent(decisionId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as Tally;
  }
}
