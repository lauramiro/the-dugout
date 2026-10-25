import { test } from "node:test";
import assert from "node:assert/strict";
import { HOOD_CHAIN, HOOD_SERVICES, MCP_URL } from "./hood.ts";
import { translator, type StringKey } from "./i18n.ts";

test("every service and chain stage has a line in both languages, and Spanish is translated", () => {
  const en = translator("en");
  const es = translator("es");
  const keys = [
    ...HOOD_SERVICES.map((s) => `hood_${s.id}`),
    ...HOOD_CHAIN.map((s) => `hood_${s.id}`),
  ] as StringKey[];
  for (const key of keys) {
    assert.notEqual(en(key), key, key);
    assert.notEqual(es(key), key, key);
    assert.notEqual(es(key), en(key), `${key} is not translated`);
  }
});

test("service ids are unique and the MCP endpoint ends at /mcp", () => {
  const ids = HOOD_SERVICES.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(MCP_URL.startsWith("https://") && MCP_URL.endsWith("/mcp"));
});

test("Web PubSub is described without the Free tier", () => {
  assert.doesNotMatch(translator("en")("hood_webpubsub"), /free/i);
  assert.doesNotMatch(translator("es")("hood_webpubsub"), /gratuit/i);
});
