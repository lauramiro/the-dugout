import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CLAUDE_COMMAND, HOOD_CHAIN, HOOD_FLOW, HOOD_SERVICES, MCP_URL, VSCODE_CONFIG, flowKeys } from "./hood.ts";
import { translator, type StringKey } from "./i18n.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const en = translator("en");
const es = translator("es");
const hoodKeys = [
  ...HOOD_SERVICES.map((s) => `hood_${s.id}`),
  ...HOOD_CHAIN.map((s) => `hood_${s.id}`),
  ...flowKeys(),
  "hoodFlowRegistry",
  "hoodNav", "hoodTitle", "hoodLead", "hoodDiagramAlt", "hoodDiagramOpen", "hoodServices", "hoodChain",
  "hoodChainNote", "hoodMcp", "hoodMcpClaude", "hoodMcpVscode", "hoodRepo", "newTab",
] as StringKey[];

test("every hood string exists in both languages and Spanish is translated", () => {
  for (const key of hoodKeys) {
    assert.notEqual(en(key), key, key);
    assert.notEqual(es(key), key, key);
    assert.notEqual(es(key), en(key), `${key} is not translated`);
  }
});

test("hood strings are picked up from the dictionary, not only from the list above", () => {
  const source = read("./i18n.ts");
  const listed = new Set<string>(hoodKeys);
  for (const [, key] of source.matchAll(/^ {2}(hood\w*):/gm)) assert.ok(listed.has(key), `${key} is not covered`);
});

test("no long dashes in any hood string", () => {
  for (const key of hoodKeys) {
    for (const text of [en(key), es(key)]) assert.doesNotMatch(text, /[–—]/, key);
  }
});

test("Web PubSub is described without the Free tier", () => {
  for (const text of [en("hood_webpubsub"), es("hood_webpubsub")]) assert.doesNotMatch(text, /free|gratis|gratuit/i);
});

test("Spanish uses the other panels' terms", () => {
  assert.doesNotMatch(es("hood_check1") + es("hood_check2") + es("hoodChainNote") + es("hood_agentframework"), /fundamento/i);
  assert.equal(es("hood_localizer"), "Localizador");
});

test("the MCP endpoint and the connect commands match the README", () => {
  const readme = read("../../README.md");
  assert.ok(readme.includes(MCP_URL));
  assert.ok(readme.includes(CLAUDE_COMMAND), "claude command");
  assert.ok(readme.includes(VSCODE_CONFIG), "vs code config");
  assert.ok(MCP_URL.startsWith("https://") && MCP_URL.endsWith("/mcp"));
});

test("service ids are unique", () => {
  const ids = HOOD_SERVICES.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
});

test("the published diagram says Standard, not the Free tier", () => {
  const svg = read("../public/architecture.svg");
  assert.match(svg, /Standard/);
  assert.doesNotMatch(svg, /Free/);
});

test("the drawn flow: every lane has one label between each pair of nodes, and only brand names are left untranslated", () => {
  for (const lane of HOOD_FLOW) {
    assert.equal(lane.edges.length, lane.nodes.length - 1, lane.id);
    for (const node of lane.nodes) assert.ok("brand" in node || en(`hoodNode_${node.id}` as StringKey) !== `hoodNode_${node.id}`, node.id);
  }
  const keys = flowKeys();
  assert.ok(keys.includes("hoodLane_live") && keys.includes("hoodEdge_socket") && keys.includes("hoodSub_runner"));
});

test("the drawn flow names every Azure service the services list names, so the two cannot drift", () => {
  const brands = new Set(HOOD_FLOW.flatMap((l) => l.nodes.flatMap((n) => ("brand" in n ? [n.brand] : []))));
  for (const name of ["Azure Event Hubs", "Azure Web PubSub", "Azure Static Web Apps", "Microsoft Foundry"]) assert.ok(brands.has(name), name);
});
