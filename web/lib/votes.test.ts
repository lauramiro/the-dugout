import { test } from "node:test";
import assert from "node:assert/strict";
import { ServiceVotes } from "./votes.ts";

test("ServiceVotes: a failed /config.json is fetched again on the next vote, not cached", async () => {
  const realFetch = globalThis.fetch;
  let configCalls = 0;
  globalThis.fetch = (async (input: string | URL | Request) => {
    const url = String(input);
    if (url === "/config.json") {
      configCalls += 1;
      if (configCalls === 1) throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify({ stubUrl: "https://svc.example" }));
    }
    assert.equal(url, "https://svc.example/votes/rfc-60-20");
    return new Response(JSON.stringify({ decision_id: "rfc-60-20", counts: {}, total: 0 }));
  }) as typeof fetch;
  try {
    const votes = new ServiceVotes();
    await assert.rejects(votes.tally("rfc-60-20"));
    assert.deepEqual(await votes.tally("rfc-60-20"), { decision_id: "rfc-60-20", counts: {}, total: 0 });
    assert.equal(configCalls, 2);
  } finally {
    globalThis.fetch = realFetch;
  }
});
