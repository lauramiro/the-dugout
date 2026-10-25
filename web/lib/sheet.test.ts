import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { PHONE_SHEET_QUERY } from "./sheet.ts";

test("the phone sheet query in code is the one broadcast.css lays the sheet out for", () => {
  const css = readFileSync(new URL("../app/broadcast.css", import.meta.url), "utf8");
  assert.ok(css.includes(`@media ${PHONE_SHEET_QUERY} {`), PHONE_SHEET_QUERY);
  assert.ok(css.includes(".bc-sheet"), "the sheet has styles");
});
