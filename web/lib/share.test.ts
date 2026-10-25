import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(new URL(path, import.meta.url));

test("the share image is 1200x630 and the link preview points at the site the README gives", () => {
  const png = read("../app/opengraph-image.png");
  assert.equal(png.readUInt32BE(16), 1200);
  assert.equal(png.readUInt32BE(20), 630);
  const site = /new URL\("([^"]+)"\)/.exec(read("../app/layout.tsx").toString())?.[1];
  assert.ok(site && read("../../README.md").toString().includes(`**Try it:** ${site}`), String(site));
});
