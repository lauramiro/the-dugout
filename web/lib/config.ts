// public/config.json is written at deploy time by infra/deploy.sh: {"stubUrl": "https://..."},
// the decision service's base URL. Read once per page by the live feed and the votes.

let cached: Promise<string> | null = null;

/** The decision service's base URL. A failed fetch is tried again next time, not kept. */
export function serviceUrl(): Promise<string> {
  cached ??= fetch("/config.json")
    .then((res) => {
      if (!res.ok) throw new Error(`/config.json: HTTP ${res.status}`);
      return res.json() as Promise<{ stubUrl: string }>;
    })
    .then((c) => c.stubUrl)
    .catch((err: unknown) => {
      cached = null;
      throw err;
    });
  return cached;
}
