# Broadcast Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `/broadcast` route that shows the match as a full-bleed 16:9 TV picture with timed broadcast graphics (scorebug, decision lower third, fading tag, win-probability worm, manager's call, goal flash, full-time "What if"), personalised by mode, language, club and player focus, from replay or live data, plus an exportable cue sheet.

**Architecture:** A pure cue builder (`web/lib/cues.ts`) turns the existing `MatchLog` into timed cues; a `/broadcast` page plays them over the tracking animation through the existing `DataSource`. The live runner adds small messages (key match events, one win-probability point per minute) so live mode can fill the scorebug, goal flash and worm without tracking over Web PubSub; live mode borrows the recorded tracking when the live match is the demo match.

**Tech Stack:** Next.js 16 static export, React 19, TypeScript, CSS, SVG; Node 24's built-in test runner for the cue builder (no new dependency); Python 3.12 and pytest for the runner.

**Spec:** `docs/superpowers/specs/2026-10-22-broadcast-mode-design.md`

## Global Constraints

- No new runtime dependencies (web: React, Next, TypeScript only; Python: as in `pyproject.toml`).
- No tracking frames over Web PubSub (Free tier; it returned 429 on 21 Oct).
- Every number on a graphic comes from the engine payload, a snapshot, a review row or a win-probability point as given; the page derives no gaps.
- Copy: "options" and "trade-offs", never "wrong"; a manager's call that differs from the model is "a different call".
- English and Spanish for every new string (`web/lib/i18n.ts`), casual and analyst where the graphic has text.
- The page reads the match only through `DataSource` (`web/lib/datasource.ts`).
- Static export: no server code in `web/`; `npm run typecheck` and `npm run build` pass.
- Work in a worktree branch `lane/broadcast`; another session may be on `main`.

## Review Focus

- A card that is still open at full time (no `closed`): its decision cue must end, not run forever. Test in Task 1.
- Live: a card closes with reason "change" but no sub event of that team arrived (message dropped by a 429): the manager-call cue still appears, with an empty change list. Test in Task 1.
- Player focus on a substitute who never comes on, or a player id not in the roster: no focus cues, no crash. Test in Task 1.
- Second-half positions: a cue in first-half added time and one just after half-time order correctly (pos, not t_ms). Test in Task 1.
- Live page opened mid-match (no first snapshot, no roster yet): the stage renders the empty pitch and scorebug placeholders without throwing. Checked in Task 7's Chrome pass.

---

### Task 1: Cue builder and web test runner

**Files:**
- Create: `web/lib/cues.ts`
- Create: `web/lib/cues.test.ts`
- Modify: `web/tsconfig.json` (add `"allowImportingTsExtensions": true`)
- Modify: `web/package.json` (script `"test": "node --test lib/*.test.ts"`)

**Interfaces:**
- Consumes: `MatchLog`, `Timed` from `web/lib/datasource.ts`; `DecisionCard`, `MatchEvent` from `web/lib/contracts.ts` (type-only imports); `toPos` from `./clock.ts` (with the `.ts` extension: Node runs this file without a bundler, and `clock.ts` has no imports).
- Produces:
  - `type CueKind = "decision" | "fading" | "manager_call" | "goal" | "focus_event" | "whatif"`
  - `interface Cue { id: string; kind: CueKind; in_pos: number; out_pos: number; data: Record<string, unknown> }`
  - `buildCues(log: MatchLog, focus: string | null): Cue[]`, sorted by `in_pos`, then `id`
  - `activeCues(cues: readonly Cue[], pos: number): Cue[]`, the cues with `in_pos <= pos < out_pos`
  - `cueSheet(log: MatchLog, focus: string | null, source: "replay" | "live"): { match_id: string | null; source: string; cues: Cue[] }` (`match_id` from the first event, else null)
  - Durations in match ms: `DECISION_MAX_MS = 180_000`, `FADING_MS = 30_000`, `MANAGER_CALL_MS = 25_000`, `GOAL_MS = 20_000`, `FOCUS_EVENT_MS = 15_000`, `WHATIF_MS = 120_000`

Cue rules (all positions on the `pos` axis; `toPos(period, t_ms, log.firstHalfEnd)`):
- `decision:<decision_id>`: in = card pos; out = closed pos if `closed`, capped at in + `DECISION_MAX_MS`. Data `{ decision_id }`.
- `fading:<decision_id>`: only trigger `condition_drop`; in = card pos; out = in + `FADING_MS`. Data `{ decision_id, player_id, condition }` from the `condition` evidence.
- `manager_call:<decision_id>`: with `manager_action`: at = max(action pos, card pos); data `{ decision_id, team, subs, option_id, matched: option_id === recommendation.option_id, minutes_after: Math.round((at - card pos) / 60_000) }`. Without it but `closed.reason === "change"` (live): at = closed pos; `subs` from that team's `sub` events within 10 s of `at` as `{off: player_id, on: player_in_id}`; `option_id: null, matched: null`. out = at + `MANAGER_CALL_MS`.
- `goal:<seq>`: per `goal` event; data `{ team, player_id, score }` with the score after the goal (`Record<team, number>`, both teams from the roster, or from the goals seen).
- `focus_event:<seq>`: only when `focus` is set; events of type `goal`, `shot`, `sub`, `foul` where `player_id === focus` or `player_in_id === focus`; data `{ type, player_id, player_in_id }`.
- `whatif`: only when some card has `review`; in = `log.duration`; out = in + `WHATIF_MS`. Data `{ rows, lead }`: rows per reviewed card `{ decision_id, minute: card.payload.t_ms div 60000, model: review.model, manager: review.manager, gap_win: review.gap_win }` in card order; `lead` = the `decision_id` with the largest `gap_win` (ignoring null).

- [ ] **Step 1: Write the failing tests** in `web/lib/cues.test.ts` (node:test, `assert/strict`), with a small hand-built `MatchLog` helper (`firstHalfEnd: 2_870_000`, one roster with teams `RFC` and `CAS`):
  - `decision cue runs from the card to its closing`: card at pos 3_600_000 closed at 3_780_000 → `in_pos 3_600_000, out_pos 3_780_000`.
  - `an open card's decision cue ends after DECISION_MAX_MS`: no `closed` → `out_pos === in_pos + 180_000`.
  - `a condition_drop card adds a fading cue with the evidence player`: data `{ player_id: "RFC-03", condition: 0.689 }`, out = in + 30_000; a `goal_after_55` card adds none.
  - `manager call from manager_action says whether it matched`: action at period 2, t_ms 4_740_000, option `sub_like_for_like` equal to the recommendation → `matched: true`, `minutes_after: 19` for a card at 60'.
  - `live manager call comes from the closing and the sub events`: no `manager_action`, `closed.reason "change"`, one RFC `sub` event 4 s later → `subs [{off:"RFC-03", on:"RFC-15"}]`, `matched: null`; the same with no sub event → `subs []`.
  - `goal cues carry the score after the goal`: two goals RFC then CAS → second cue's `score` is `{ RFC: 1, CAS: 1 }`.
  - `focus cues only for the focused player`: focus `RFC-15` matches a `sub` with `player_in_id: "RFC-15"`; focus `RFC-99` (not in roster) gives no focus cues and no throw.
  - `what-if cue at full time leads with the largest gap`: two reviewed cards with `gap_win` 0.031 and 0.004 → `lead` is the first; no reviews → no `whatif` cue.
  - `cues sort by pos across half-time`: a card at period 1 t_ms 2_820_000 (added time) sorts before one at period 2 t_ms 2_760_000.
  - `activeCues is half-open`: a cue `[10, 20)` is active at 10 and 19, not at 20.
- [ ] **Step 2: Run** `cd web && npm test`. Expected: FAIL, `cues.ts` not found.
- [ ] **Step 3: Implement** `buildCues`, `activeCues`, `cueSheet` and the constants in `web/lib/cues.ts`; add `allowImportingTsExtensions` to `tsconfig.json` and the `test` script to `package.json`.
- [ ] **Step 4: Run** `cd web && npm test && npm run typecheck && npm run build`. Expected: all tests pass, typecheck clean, build OK (this also proves Next accepts the `.ts`-extension import; if the build rejects it, pass `firstHalfEnd` into a local `posOf` helper instead and drop the import).
- [ ] **Step 5: Commit** `git add web/lib/cues.ts web/lib/cues.test.ts web/tsconfig.json web/package.json && git commit -m "web: cue builder for broadcast graphics"`

### Task 2: Live runner sends key events and per-minute win probability

**Files:**
- Create: `dugout/stream/winprob.py`
- Modify: `dugout/stream/pipeline.py` (`PipelineRunner.send`, `_handle`)
- Modify: `web/scripts/build_demo_fixtures.py` (import `situation`/the point function from `dugout.stream.winprob` instead of its own `situation`)
- Modify: `web/lib/live.ts` (`receive`: a `winprob` branch; `connect`: load `/demo/roster.json` into `log.roster`)
- Modify: `web/lib/contracts.ts` (`WinProbMessage = WinProbPoint & { kind: "winprob" }`)
- Test: `tests/test_pipeline_live.py`, `tests/test_winprob.py`

**Interfaces:**
- Produces (Python): `winprob_point(snapshot: dict, home: str, n: int = 4000, seed: int | None = None) -> dict` returning `{"kind": "winprob", "period", "t_ms", "team": home, "win", "draw", "loss"}` (3 decimals), the same situation as `build_demo_fixtures.situation` and the same `simulate_diff`/`summarize` from `dugout.engine.wp` (first-half `t0` capped at 45, as the build script does).
- Produces (Python): `KEY_EVENT_TYPES = ("goal", "sub", "shot", "foul", "card")` in `pipeline.py`; `PipelineRunner(..., home: str | None = None)`, default the first lineup player's team.
- Produces (web): live `log.winprob` and `log.roster` filled; key events land in `log.events` through the existing `"seq"` branch.

- [ ] **Step 1: Write failing tests**
  - `tests/test_winprob.py::test_point_matches_the_build_scripts_series`: for three demo snapshots on whole minutes, `winprob_point(s, "RFC", n=20_000, seed=s["t_ms"])` equals the matching row of `web/public/demo/winprob.jsonl` within 0.02 on `win`.
  - `tests/test_winprob.py::test_point_is_fast`: `n=4000` takes under 0.25 s.
  - `tests/test_pipeline_live.py::test_key_events_are_published_and_others_are_not`: over the demo run, published messages with `seq` have types only in `KEY_EVENT_TYPES` and include all 5 goals and 3 subs; no `pass`, `hsr`, `sprint`.
  - `tests/test_pipeline_live.py::test_one_winprob_point_per_match_minute`: `winprob` messages have strictly increasing `(period, t_ms)`, `t_ms % 60_000 == 0`, and there are at least 90.
  - Update `test_cards_closings_and_snapshots_in_order` to ignore `seq` and `winprob` messages.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_winprob.py tests/test_pipeline_live.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `dugout/stream/winprob.py`; in `PipelineRunner.send` publish each event whose `type` is in `KEY_EVENT_TYPES` after feeding it; in `_handle` publish `winprob_point(snapshot, self._home)` for the first snapshot of each whole match minute. The point is computed on the stream's thread; keep `n` at 4000. Point `build_demo_fixtures.py` at the shared function (do not regenerate the demo files).
- [ ] **Step 4: Implement** the `live.ts` changes: a `msg.kind === "winprob"` branch before the others (`pos = toPos(period, t_ms, end1)`, add to `log.winprob`), and fetch `/demo/roster.json` in `connect()` (a failed fetch leaves `roster` null).
- [ ] **Step 5: Run** `.venv/Scripts/python -m pytest -q` and `cd web && npm run typecheck && npm run build`. Expected: all pass.
- [ ] **Step 6: Commit** `git commit -m "stream, web: live key events, per-minute win probability and roster"`

### Task 3: Broadcast page, stage, pitch, scorebug and settings

**Files:**
- Create: `web/app/broadcast/page.tsx`
- Create: `web/components/broadcast/Stage.tsx` (16:9 box scaled to the window, letterboxed)
- Create: `web/components/broadcast/FieldView.tsx` (full-bleed pitch from a `PitchFrame`, player dots in club colours, ball; reuses the pitch geometry of `web/components/Pitch.tsx`)
- Create: `web/components/broadcast/Scorebug.tsx`
- Create: `web/components/broadcast/SettingsChip.tsx`
- Create: `web/app/broadcast/broadcast.css` (imported by the page)
- Modify: `web/lib/i18n.ts` (new keys, en and es)

**Interfaces:**
- Consumes: `useDataSource`, `useFeed` (`web/lib/useFeed.ts`); `ReplayDataSource` (`web/lib/replay.ts`); `score`, `playerName` (`web/lib/derive.ts`); `formatClock`, `fromPos` (`web/lib/clock.ts`).
- Produces: `interface BroadcastPrefs { mode: Mode; locale: Locale; club: TeamCode | null; player: string | null }` exported from `web/components/broadcast/SettingsChip.tsx`; stored under localStorage key `dugout.broadcast` with the same try/catch pattern as `app/page.tsx`. `FieldView` props `{ frame: PitchFrame | null; roster: Roster | null; tags: PlayerTag[] }` with `interface PlayerTag { id: string; label: string; ring: number | null; tone: "focus" | "fading" }` (rendered in Task 4).
- Live tracking: when `source.kind === "live"`, the page creates one `ReplayDataSource`, starts it, seeks it to the live playhead on each change, and draws `recorded.frameAt(playhead)` only when the first live event's `match_id` equals the recorded log's first event `match_id`; the settings chip then shows the `recordedTracking` string.

- [ ] **Step 1: Implement** the page and components above. The settings chip offers mode (Casual/Analyst), language (EN/ES), favourite club (none, home, away) and player focus (any roster player, grouped by club). Replay mode keeps play/pause/speed controls in the chip.
- [ ] **Step 2: Add i18n keys** (en / es): `broadcastSettings` "Settings" / "Ajustes"; `favouriteClub` "Favourite club" / "Club favorito"; `playerFocus` "Player focus" / "Jugador a seguir"; `none` "None" / "Ninguno"; `recordedTracking` "Recorded tracking" / "Seguimiento grabado".
- [ ] **Step 3: Run** `cd web && npm run typecheck && npm run build`. Expected: pass.
- [ ] **Step 4: Check in Chrome** (`npm run dev`, `/broadcast` and `/broadcast?t=58`): the pitch fills the 16:9 stage with moving dots, the scorebug clock runs, the settings persist across a reload; at 375 px wide the stage scales down with no horizontal scroll.
- [ ] **Step 5: Commit** `git commit -m "web: broadcast page with stage, field view, scorebug and settings"`

### Task 4: Decision lower third and player tags

**Files:**
- Create: `web/components/broadcast/LowerThird.tsx`
- Create: `web/components/broadcast/useHeldCues.ts`
- Modify: `web/app/broadcast/page.tsx`, `web/components/broadcast/FieldView.tsx`, `web/app/broadcast/broadcast.css`, `web/lib/i18n.ts`

**Interfaces:**
- Consumes: `buildCues`, `activeCues`, `Cue` (Task 1); `BroadcastPrefs`, `PlayerTag` (Task 3); `withNames` (`web/lib/derive.ts`); `pct`, `points`, `strengthKey`, `triggerKey` (`web/lib/i18n.ts`).
- Produces: `useHeldCues(cues: Cue[], playhead: number, minWallMs = 4000): Cue[]`, active cues plus any cue that left less than `minWallMs` of wall-clock time ago (so 20x replay stays readable).

- [ ] **Step 1: Implement** `LowerThird` for the `decision` cue: trigger title and strength chip; the narration for the viewer's locale and mode (fall back to English casual while the other versions arrive; show nothing rather than a placeholder if none); options as horizontal win-probability bars (model's pick marked, gap in points; analyst adds the 90% interval); a "Your call" prompt line. Slides in from the bottom, out on cue end; leaves the top two thirds of the stage clear.
- [ ] **Step 2: Implement** tags in `FieldView`: the `fading` cue's player gets a ring whose fill is the latest snapshot's `condition_est` (colour by `band()`), with a callout "{name} · {condition}%" for the cue's duration; the focus player (prefs) always gets a tag with name and ring.
- [ ] **Step 3: Add i18n keys**: `yourCallPrompt` "Your call? Pick before the manager does" / "¿Tú qué harías? Elige antes que el entrenador"; `modelsPick` reuse the existing key if present.
- [ ] **Step 4: Run** `cd web && npm test && npm run typecheck && npm run build`. Expected: pass.
- [ ] **Step 5: Check in Chrome** at `/broadcast?t=58` replay at 5x and 20x: the 60' card's lower third appears with "Take RFC-03 off..." (casual) and the bars, stays readable at 20x, leaves when the card closes; RFC-03's ring is amber/red; switching to ES and Analyst changes the text.
- [ ] **Step 6: Commit** `git commit -m "web: broadcast lower third and player tags"`

### Task 5: Worm, goal flash, manager's call, focus cards and full-time "What if"

**Files:**
- Create: `web/components/broadcast/Worm.tsx`, `GoalFlash.tsx`, `ManagerCall.tsx`, `FocusCard.tsx`, `WhatIf.tsx`
- Modify: `web/app/broadcast/page.tsx`, `web/app/broadcast/broadcast.css`, `web/lib/i18n.ts`

**Interfaces:**
- Consumes: `Cue` data shapes from Task 1 (exactly as listed there); `log.winprob`; `BroadcastPrefs`.

- [ ] **Step 1: Implement** `Worm`: a thin strip along the bottom edge, win probability from `log.winprob` up to the playhead, for the home club by default (`win`) or for the favourite club when it is the away club (the point's `loss`, which is the away side's win as given), labelled with that club; card moments as small markers.
- [ ] **Step 2: Implement** `GoalFlash` (`goal` cue: club, scorer name, new score), `ManagerCall` (`manager_call` cue: "{off} off, {on} on"; replay adds "Same as the model's pick" or "A different call" and "{n} min after the card"), `FocusCard` (`focus_event` cue: player name and event type), `WhatIf` (`whatif` cue: lead row large, other rows small; model option, manager option, gap in points from `gap_win`, the review's recap line for locale and mode).
- [ ] **Step 3: Add i18n keys**: `managersCall` "Manager's call" / "Decisión del entrenador"; `sameAsModel` "Same as the model's pick" / "Igual que la opción del modelo"; `differentCall` "A different call" / "Otra decisión"; `minutesAfterCard` "{n} min after the card" / "{n} min después de la tarjeta"; `whatIf` "What if" / "¿Y si...?"; `offOn` "{off} off, {on} on" / "Sale {off}, entra {on}".
- [ ] **Step 4: Run** `cd web && npm test && npm run typecheck && npm run build`. Expected: pass.
- [ ] **Step 5: Check in Chrome** replay: goal flashes at each of the 5 goals; manager's call at 79' says "Same as the model's pick" (or the review's verdict) and the delay; with focus `RFC-15` a focus card appears when RFC-15 comes on; at full time the "What if" segment leads with the 60' decision and +3.1 points.
- [ ] **Step 6: Commit** `git commit -m "web: broadcast worm, goal flash, manager's call, focus cards and what-if"`

### Task 6: Cue sheet export

**Files:**
- Modify: `web/app/broadcast/page.tsx`, `web/components/broadcast/SettingsChip.tsx`, `web/lib/i18n.ts`

**Interfaces:**
- Consumes: `cueSheet` (Task 1).

- [ ] **Step 1: Implement** an "Export cues" button in the settings chip that downloads `cues-<match_id>.json` (pretty-printed `cueSheet(log, prefs.player, source.kind)`), and `?cues=json` which renders that JSON as plain text in a `<pre>` instead of the stage.
- [ ] **Step 2: Add i18n key** `exportCues` "Export cue sheet" / "Exportar guion de grafismos".
- [ ] **Step 3: Run** `cd web && npm run typecheck && npm run build`; open `/broadcast?cues=json` at full replay load and check the JSON has `decision`, `fading`, `manager_call`, `goal` and `whatif` cues with numeric `in_pos`/`out_pos`.
- [ ] **Step 4: Commit** `git commit -m "web: broadcast cue sheet export"`

### Task 7: Live check, deploy, README

**Files:**
- Modify: `README.md` (Broadcast mode section: what it shows, the cue sheet, live vs replay differences, recorded tracking in live)

- [ ] **Step 1: Deploy** with `BUDGET_EMAIL=lauramiro01@gmail.com BUDGET_USD=5 bash infra/deploy.sh --apply` (after the user's OK, from the merged branch).
- [ ] **Step 2: Live check in Chrome:** open `/broadcast?source=live`, run `uv run python -m dugout.stream.replay data/demo-rfc-cas-0073.jsonl --speed 20`; expect scorebug and goal flashes live, the worm growing, the 60' lower third in all four versions, the manager's call at 79' without a verdict, "Recorded tracking" in the chip, no new console errors, and no `publish failed` lines in `az containerapp logs show -n dugout-runner -g dugout-rg`.
- [ ] **Step 3: Check** `/broadcast` at 1920x1080 and 375 px wide in replay.
- [ ] **Step 4: Write** the README section and commit `git commit -m "docs: broadcast mode in the README"`.
- [ ] **Step 5: Vault note:** add a one-paragraph Progress line to `C:\Users\lmiro\second-brain\wiki\projects\The Dugout.md` (what shipped, commits, the live check result) and a matching line in `hot.md` and `log.md`.
