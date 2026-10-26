import { test } from "node:test";
import assert from "node:assert/strict";
import { serviceUrl } from "./config.ts";

test("serviceUrl: a failed /config.json is fetched again next time; a good one is kept", async () => {
  const realFetch = globalThis.fetch;
  const answers = [new Response("", { status: 500 }), new Response(JSON.stringify({ stubUrl: "https://svc.example" }))];
  let calls = 0;
  globalThis.fetch = (async () => {
    calls += 1;
    return answers.shift() ?? assert.fail("fetched more than twice");
  }) as typeof fetch;
  try {
    await assert.rejects(serviceUrl(), /HTTP 500/);
    assert.equal(await serviceUrl(), "https://svc.example");
    assert.equal(await serviceUrl(), "https://svc.example");
    assert.equal(calls, 2);
  } finally {
    globalThis.fetch = realFetch;
  }
});
