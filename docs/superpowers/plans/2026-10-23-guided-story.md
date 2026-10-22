# Guided Story Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the landing page, a self-playing story shows the 60' decision of the demo match on three real screens (TV, the manager's tablet, the fan's phone), with a new fan view and a bench graphic.

**Architecture:** A pure timeline (`web/lib/story.ts`) turns the match log into story steps; a pure player reducer (`web/lib/storyPlayer.ts`) decides what the guide does on each tick, vote or viewer action; a thin React layer drives the existing replay `DataSource` from it. The analyst desk and the new fan view become components that take a shared data source, so during the story all three screens run on one playhead and one set of votes.

**Tech Stack:** Next.js 16 static export, React 19, TypeScript, Node's test runner (`npm test` runs `node --test lib/*.test.ts`).

**Spec:** `docs/superpowers/specs/2026-10-23-guided-story-design.md`

## Global Constraints

- Next.js 16 differs from older versions: read the relevant guide in `web/node_modules/next/dist/docs/` before writing Next-specific code (`web/AGENTS.md`).
- Static export only (`output: 'export'`), no server features; deploy is `infra/deploy.sh --apply`, run by Laura.
- English and Spanish for every string a viewer reads, through `web/lib/i18n.ts` (`en` and `es` dicts; `StringKey` is `keyof typeof en`).
- No emojis or em-dashes in code, copy or docs (CLAUDE.md).
- No invented numbers: no crowd split, percentage or quote that is not in the data. Captions that quote a number take it from the match log, card narration, payload or review.
- Must keep working: `/` without the story, `/desk`, `/broadcast`, `?t=`, `?source=live`, `?cues=json`, voting, and every existing test.
- The story is replay only; live keeps its kick-off countdown.
- Checks for every task: in `web/`, `npm test`, `npm run typecheck`, `npm run build` all pass. Python is untouched.

## Review Focus

1. **The viewer acts during the story** (clicks a chapter, presses Space, changes speed, votes on the TV lower third): the guide pauses or stops and never fights the viewer for the playhead. Pinned in Task 3's reducer tests.
2. **The data lacks a step** (no goal by the opponent after the card, the manager never acts, no condition card for the club): those steps are left out and the story still ends cleanly; with no condition card there is no story and the page behaves as today. Pinned in Task 1's tests.
3. **Leaving mid-story** on the tablet or phone: the viewer lands on `/desk` or `/fan` at the same minute, paused, and a reload of that URL gives the same view. Pinned in Task 3 (`leaveUrl`) and checked by hand in Task 7.
4. **Language switch during the story**: captions change language at once and keep their numbers. Pinned in Task 3 (captions resolve through `t` at render) and checked by hand.
5. **A narrow window** (390 x 844): no device frames, each step full-screen, nothing overflows sideways. Checked by hand in Task 5 with the probe script.
6. **Storage blocked or cleared** (private window): the intro still shows and the story still plays; nothing throws. Pinned in Task 3 (the first-visit read and write are wrapped in try/catch, as `SettingsChip.readPrefs` is).

---

## File Structure

- Create `web/lib/story.ts` (+ `story.test.ts`): `buildStory`, the step list from the match log.
- Create `web/lib/storyPlayer.ts` (+ `storyPlayer.test.ts`): `storyReducer`, `leaveUrl`.
- Create `web/lib/fan.ts` (+ `fan.test.ts`): `fanContext`, `fanCard`, what the fan view shows at a pos.
- Create `web/lib/bench.ts` (+ `bench.test.ts`): `benchAt`, who has not played yet.
- Create `web/components/desk/DeskView.tsx`: the desk body moved out of `web/app/desk/page.tsx`, taking a data source.
- Create `web/components/fan/FanView.tsx`, `web/app/fan/page.tsx`, `web/app/fan.css`.
- Create `web/components/story/Story.tsx` (overlay, intro, end card, device frames) and `web/components/story/useStory.ts` (drives the source from the reducer).
- Create `web/components/broadcast/Bench.tsx`.
- Create `web/lib/useVotes.ts`: the vote state now in `web/app/page.tsx`, shared by the TV and the phone.
- Modify `web/app/page.tsx`, `web/app/desk/page.tsx`, `web/components/Dugout.tsx`, `web/app/broadcast.css`, `web/lib/i18n.ts`, `README.md`.

---

### Task 1: Story timeline

**Files:**
- Create: `web/lib/story.ts`
- Test: `web/lib/story.test.ts`

**Interfaces:**
- Consumes: `MatchLog`, `Timed` (`lib/datasource.ts`); `DecisionCard`, `TeamCode`, `Roster` (`lib/contracts.ts`); `managerPos` (`lib/calls.ts`); `StringKey` (`lib/i18n.ts`).
- Produces:
  ```ts
  export type StoryScreen = "tv" | "tablet" | "phone" | "end";
  export type StoryWait =
    | { kind: "play"; untilPos: number; speed: 1 | 5 | 20 } // play from `startPos` until the playhead reaches untilPos
    | { kind: "hold"; ms: number }                          // paused, advance after ms of wall time
    | { kind: "vote"; ms: number; decisionId: string }      // paused, advance on a vote or after ms
    | { kind: "stay" };                                     // the end: never advances
  export interface StoryStep {
    id: "tv-open" | "tv-decision" | "tablet" | "vote" | "equaliser" | "manager" | "full-time" | "end";
    screen: StoryScreen;
    startPos: number;   // seek here when the step starts (the same pos as the previous step's end if unchanged)
    wait: StoryWait;
    caption: { key: StringKey; vars: Record<string, string> };
  }
  export interface StoryOptions { club: TeamCode; phone: boolean }
  export function buildStory(log: MatchLog, options: StoryOptions): StoryStep[] | null;
  export const STORY_LEAD_MS = 80_000;   // TV opens this long before the card
  export const DECISION_HOLD_MS = 7_000, TABLET_HOLD_MS = 12_000, VOTE_MS = 15_000, FULL_TIME_HOLD_MS = 12_000;
  ```

Rules `buildStory` follows (the tests pin each):
- The story's card is the club's first card with trigger `condition_drop`; none means `null`.
- The flagged player is the card's `evidence` entry of type `condition`; his name comes from the roster.
- Steps in order: `tv-open` (startPos = card pos minus `STORY_LEAD_MS`, floored at 0, play at 5x until card pos + 2_000), `tv-decision` (hold), `tablet` (hold), `vote` (screen `phone` when `options.phone`, else `tv`), `equaliser` (only if the opponent scores after the card: startPos = goal pos minus 15_000, play at 5x until goal pos + 6_000, screen `tv`), `manager` (only if `managerPos(card, log.firstHalfEnd)` is not null: startPos = that pos minus 3_000, play at 5x until that pos + 6_000, screen `phone` when `options.phone`, else `tv`), `full-time` (startPos = `log.duration`, hold, screen `tv`), `end` (stay).
- The equaliser caption names the flank only when the goal came down the flagged player's side: the goal event's `channel` mirrored (`left` and `right` swap, the opponent attacks the other way) equals the player's roster `side`. Otherwise the caption is the plain one.
- Caption keys and vars (strings added in Task 3): `story_open {team}`, `story_decision {player}`, `story_tablet {player}`, `story_vote`, `story_equaliser_flank {team, player}` or `story_equaliser {team}`, `story_manager {minutes}` (minutes between the card and the manager's change: the difference of the two positions in ms divided by 60_000, `Math.round`ed), `story_full_time {minute}` (the card's minute from `formatMinute`), `story_end`.

- [ ] **Step 1: Write the failing tests**

In `web/lib/story.test.ts`, build synthetic logs the way `lib/cues.test.ts` does (its `card()` and `pos()` helpers), plus one test on the real demo files read with `node:fs` from `public/demo/` (parse `cards.json`, `match.jsonl`, `roster.json`, and set positions with `toPos` and `tracking/index.json`'s `period_end_t_ms`).

```ts
test("buildStory: no condition card for the club means no story", () => {
  assert.equal(buildStory(logWith({ cards: [goalCard] }), { club: "RFC", phone: true }), null);
});
test("buildStory: the demo match tells the 60' Varga story in eight steps", () => {
  const steps = buildStory(demoLog(), { club: "RFC", phone: true })!;
  assert.deepEqual(steps.map((s) => s.id), ["tv-open", "tv-decision", "tablet", "vote", "equaliser", "manager", "full-time", "end"]);
  assert.deepEqual(steps.map((s) => s.screen), ["tv", "tv", "tablet", "phone", "tv", "phone", "tv", "end"]);
  assert.equal(steps[1].caption.vars.player, "Leon Varga");
  assert.equal(steps[4].caption.key, "story_equaliser_flank"); // CAS-07 scored down the right, Varga plays left
  assert.equal(steps[5].caption.vars.minutes, "19");           // card 60:20, change 79:00
  assert.equal(steps[0].startPos, demoCardPos - STORY_LEAD_MS);
});
test("buildStory: without a phone the vote and the manager's call stay on TV", () => {
  const steps = buildStory(demoLog(), { club: "RFC", phone: false })!;
  assert.equal(steps.find((s) => s.id === "vote")!.screen, "tv");
  assert.equal(steps.find((s) => s.id === "manager")!.screen, "tv");
});
test("buildStory: no goal by the opponent after the card leaves out the equaliser step", () => { /* log without the goal */ });
test("buildStory: a manager who never acts leaves out the manager step", () => { /* manager_action null */ });
test("buildStory: a goal on the other flank gets the plain equaliser caption", () => { /* channel "left" */ });
test("buildStory: a card in the first two minutes opens the story at kick-off, not before it", () => { /* startPos 0 */ });
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd web && npm test`
Expected: FAIL, `buildStory` not exported.

- [ ] **Step 3: Implement `buildStory` in `web/lib/story.ts`** with the constants and rules above. Goal events are `log.events` items with `type === "goal"` and `team !== club`, the first with pos greater than the card's pos.

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass, 0 type errors.

- [ ] **Step 5: Commit**

```bash
git add web/lib/story.ts web/lib/story.test.ts
git commit -m "web: story timeline from the match log (buildStory)"
```

---

### Task 2: The desk as a component

**Files:**
- Create: `web/components/desk/DeskView.tsx`
- Modify: `web/app/desk/page.tsx` (becomes a thin wrapper)

**Interfaces:**
- Consumes: `DataSource`, `FeedState` (`lib/datasource.ts`).
- Produces:
  ```ts
  export function DeskView(props: {
    source: DataSource;
    feed: FeedState;
    /** Picked out in the condition list and the decision card (the story's flagged player). */
    highlight?: string | null;
    /** Inside the story: no page header links, no own replay controls (the story drives the playhead). */
    embedded?: boolean;
  }): JSX.Element;
  ```

- [ ] **Step 1: Move the body of `web/app/desk/page.tsx` into `DeskView`** unchanged except that `source` and `feed` come from props; `page.tsx` keeps `useDataSource()` and `useFeed()` and renders `<DeskView source={source} feed={feed} />`. Settings (mode, focus, locale, storage) stay inside `DeskView`.

- [ ] **Step 2: Add `highlight`**: the matching row in `web/components/Dugout.tsx`'s condition list gets the class `highlight` (accent outline, CSS in `globals.css`), and is scrolled into view once when `highlight` changes. With `embedded`, the header's links and the replay controls row are not rendered.

- [ ] **Step 3: Check nothing changed for `/desk`**

Run: `cd web && npm test && npm run typecheck && npm run build`, then `npx serve out` (or `python -m http.server` in `out/`) and open `/desk` and `/desk?t=60` at 1440 x 900: same page as before, Play works, the 60' card shows at `?t=60` after pressing Play.
Expected: all pass, page unchanged.

- [ ] **Step 4: Commit**

```bash
git add web/components/desk/DeskView.tsx web/app/desk/page.tsx web/components/Dugout.tsx web/app/globals.css
git commit -m "web: the analyst desk as a component that takes a data source"
```

---

### Task 3: The guide on the landing page (first deployable cut)

**Files:**
- Create: `web/lib/storyPlayer.ts`, `web/lib/storyPlayer.test.ts`
- Create: `web/lib/useVotes.ts`
- Create: `web/components/story/useStory.ts`, `web/components/story/Story.tsx`
- Modify: `web/app/page.tsx`, `web/components/broadcast/Landing.tsx` (the title card is replaced), `web/lib/i18n.ts`, `web/app/broadcast.css`

**Interfaces:**
- Consumes: `buildStory`, `StoryStep` (Task 1); `DeskView` (Task 2); `PlaybackControls`, `FeedState`.
- Produces:
  ```ts
  // lib/storyPlayer.ts
  export interface StoryState { status: "intro" | "playing" | "paused" | "left" | "done"; index: number; stepStartedAt: number }
  export type StoryEvent =
    | { type: "start"; now: number }
    | { type: "skip-intro" }
    | { type: "tick"; now: number; playhead: number }
    | { type: "vote"; decisionId: string; now: number }
    | { type: "pause" } | { type: "resume"; now: number }
    | { type: "next"; now: number }
    | { type: "viewer-seek" } | { type: "viewer-speed" }   // the viewer used the replay controls
    | { type: "leave" };
  export type StoryCommand = { seek?: number; speed?: 1 | 5 | 20; play?: boolean };
  export function storyReducer(steps: readonly StoryStep[], state: StoryState, event: StoryEvent): { state: StoryState; command: StoryCommand | null };
  export function leaveUrl(step: StoryStep, playhead: number, firstHalfEnd: number): string; // "/?t=60", "/desk?t=60", "/fan?t=60"
  // lib/useVotes.ts (moved from app/page.tsx, behaviour unchanged)
  export function useVotes(live: boolean): { votes: Record<string, Vote>; castVote: (id: string, option: string | null) => void };
  // components/story/useStory.ts
  export function useStory(steps: StoryStep[] | null, source: DataSource, feed: FeedState): {
    state: StoryState; step: StoryStep | null; send: (e: StoryEvent) => void;
  };
  // components/story/Story.tsx
  export function StoryIntro(props: { onStart: () => void; onSkip: () => void; t: Translate }): JSX.Element;
  export function StoryOverlay(props: { step: StoryStep; state: StoryState; total: number; send: (e: StoryEvent) => void; t: Translate }): JSX.Element;
  export function StoryEnd(props: { onReplay: () => void; onPanel: (p: PanelId) => void; t: Translate }): JSX.Element;
  ```

Reducer rules (each pinned by a test): `start` moves to the first step and commands its seek, speed and play; a `play` step advances on `tick` once `playhead >= untilPos`; `hold` advances on `tick` once `now - stepStartedAt >= ms`; `vote` advances on a `vote` for its `decisionId` or on timeout; entering a step that is not `play` commands `play: false`; `pause` and `resume` stop and restart the step clock (a held step keeps its remaining time); `viewer-seek` and `viewer-speed` set status `left` and command nothing (the viewer owns the replay from then on); `leave` sets `left`; reaching `end` sets `done`.

`leaveUrl` uses the whole minute of the playhead (`Math.floor(tMs / 60000)` from `fromPos`, with 45 added in the second half as `?t=` expects): TV step `/?t=M`, tablet `/desk?t=M`, phone `/fan?t=M`. The fan route lands in Task 4; until then the phone screen is not in use (`phone: false`).

- [ ] **Step 1: Write the failing reducer and `leaveUrl` tests** in `web/lib/storyPlayer.test.ts`, on a three-step fixture (`play`, `hold`, `vote`) and the rules above, including: "a chapter click during the story leaves it and commands nothing", "pause on a held step keeps its remaining time", "a vote for another card does not advance the vote step", "leaveUrl on the tablet step at 60:20 is /desk?t=60".

- [ ] **Step 2: Run them to see them fail.** Run: `cd web && npm test`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement `storyReducer` and `leaveUrl`.**

- [ ] **Step 4: Run the tests.** Run: `cd web && npm test`. Expected: PASS.

- [ ] **Step 5: Move the vote state from `web/app/page.tsx` into `useVotes`** with no change in behaviour; `page.tsx` calls it.

- [ ] **Step 6: Implement `useStory`**: a `useReducer`-like wrapper around `storyReducer` that runs `tick` on `requestAnimationFrame` while status is `playing`, applies each command to `source.controls`, and sends `viewer-seek` / `viewer-speed` when the replay controls in `Chrome` (chapters, speed buttons) are used while the story plays. Space keeps toggling pause through `pause` / `resume`.

- [ ] **Step 7: Wire the story into `web/app/page.tsx`**: replay only and no `t` in the query string; `buildStory(log, { club: roster.home, phone: false })`. The title card is replaced by `StoryIntro` ("Watch the story" starts, "Skip" dismisses it and the page is as today). The intro shows on a first visit only: Start or Skip writes `localStorage` key `dugout.storySeen`; read and write are wrapped in try/catch, and with storage unavailable the intro simply shows every time. During the story render the screen of the current step: `tv` is today's picture; `tablet` renders `<DeskView source feed highlight={player} embedded />` full-screen over the stage; `end` renders `StoryEnd`. `StoryOverlay` shows the caption, step progress, Pause, Next and Leave; Leave on the TV step stays on `/` and replaces the URL with `leaveUrl` (`history.replaceState`), on other steps navigates to it. A small "Watch the story" button in the top bar (`Chrome`) restarts it.

- [ ] **Step 8: Add the strings** to both dicts in `web/lib/i18n.ts`: `storyStart`, `storySkip`, `storyPause`, `storyResume`, `storyNext`, `storyLeave`, `storyReplay`, and the caption keys from Task 1. English copy: "On TV: the match as it plays.", "The model flags {player}: a change is worth discussing.", "In the dugout, the manager sees why: every player's condition, the options priced, the bench.", "Your call: what would you do?", "{team} equalise down {player}'s flank.", "{team} equalise.", "The manager's change comes {minutes} minutes after the card.", "Full time: what the {minute} call was worth.", "Keep exploring: the TV picture, the analyst desk, the fan view, or how it's graded." Spanish in the same register as the existing `es` dict.

- [ ] **Step 9: Run every check and look at it.** Run: `cd web && npm test && npm run typecheck && npm run build`; serve `out/` and open `/` at 1440 x 900: the intro shows, "Watch the story" plays TV from about 59' at 5x, holds on the 60' card, cuts to the desk with Varga picked out, then the vote on the TV lower third, the 72' equaliser, the 79' manager's call, full time, the end card. Then reload and check: Skip gives today's page; a chapter click mid-story leaves the story; `/?t=60` shows no intro.
Expected: all checks pass and the walk-through matches.

- [ ] **Step 10: Commit**

```bash
git add web/lib/storyPlayer.ts web/lib/storyPlayer.test.ts web/lib/useVotes.ts web/components/story web/app/page.tsx web/components/broadcast/Landing.tsx web/lib/i18n.ts web/app/broadcast.css
git commit -m "web: the guided story on the landing page (TV and the manager's desk)"
```

---

### Task 4: Fan view

**Files:**
- Create: `web/lib/fan.ts`, `web/lib/fan.test.ts`
- Create: `web/components/fan/FanView.tsx`, `web/app/fan/page.tsx`, `web/app/fan.css`
- Modify: `web/lib/i18n.ts`, `web/app/page.tsx` (story uses `phone: true`), `web/components/story/Story.tsx` (phone step renders `FanView`)

**Interfaces:**
- Consumes: `MatchLog`, `Snapshot`, `DecisionCard`, `Roster`; `revealPos`, `managerOption` (`lib/calls.ts`); `trend`, `playerName`, `teamPlayers`, `forecasts` (`lib/derive.ts`); `benchAt` is not available yet (Task 7), so "who is ready" uses the roster players of the flagged player's role who are not in the snapshot.
- Produces:
  ```ts
  // lib/fan.ts
  export interface FanContext {
    decisionId: string; minute: string; trigger: Trigger; strength: Strength;
    player: { id: string; name: string; condition: number | null; trend: Trend; rank: number; of: number } | null; // rank 1 = lowest condition on his team
    flankShare: number | null;               // from the card's flank_threat evidence, null without it
    options: { id: string; label: string; win: number; deltaWin: number; pick: boolean }[];
    ready: { id: string; name: string; role: string }[];
    subsLeft: number; windowsLeft: number;
    narration: Narration | null;             // the viewer's locale and mode, falling back as LowerThird does
  }
  export type FanMoment =
    | { kind: "waiting" }
    | { kind: "decision"; context: FanContext }
    | { kind: "call"; context: FanContext; manager: string | null; model: string }   // after revealPos
    | { kind: "full-time" };
  export function fanMoment(log: MatchLog, pos: number, club: TeamCode, locale: Locale, mode: Mode): FanMoment;
  // components/fan/FanView.tsx
  export function FanView(props: { log: MatchLog; playhead: number; club: TeamCode; locale: Locale; mode: Mode;
    vote: Vote | undefined; onVote: (decisionId: string, option: string | null) => void; t: Translate }): JSX.Element;
  ```

- [ ] **Step 1: Write the failing tests** in `web/lib/fan.test.ts`, on the demo files (as in Task 1) and small fixtures:

```ts
test("fanMoment: at 60:30 the Riverside fan sees Varga's card with his rank and the options", () => {
  const m = fanMoment(demoLog(), posAt(2, 3_630_000), "RFC", "en", "casual");
  assert.equal(m.kind, "decision");
  const c = (m as { context: FanContext }).context;
  assert.equal(c.player!.name, "Leon Varga");
  assert.equal(c.player!.rank, 1);                       // lowest condition on Riverside
  assert.equal(c.options.find((o) => o.pick)!.id, "sub_like_for_like");
  assert.equal(c.strength, "strong");
});
test("fanMoment: a Castleton card is not shown to a Riverside fan", () => { /* 69:20 -> waiting */ });
test("fanMoment: after the manager's change the call shows beside the model's", () => { /* 79:30 on the 60' card -> kind call */ });
test("fanMoment: a toss-up card still lists every option, none marked as the pick of a change", () => { /* strength toss_up */ });
test("fanMoment: no flank evidence means flankShare is null, not 0", () => {});
test("fanMoment: at full time the moment is full-time", () => {});
```

- [ ] **Step 2: Run them to see them fail.** `cd web && npm test`, expected FAIL.

- [ ] **Step 3: Implement `fanMoment`.** The open card is the club's card with pos at or before `pos` and not closed before it (`closed` converted with `toPos`); after a card closes, its `call` moment shows from `revealPos` for `MANAGER_CALL_MS` (from `lib/cues.ts`); full time from `log.duration`.

- [ ] **Step 4: Run the tests.** Expected: PASS.

- [ ] **Step 5: Build `FanView`** to the spec's goal 4: score and clock always; the decision moment shows who, why now, the options (win probability and gap in plain words, the pick and strength marked; a toss-up says the options are close), who is ready with subs and windows left, and the vote (`VOTE_SECONDS` timer, same `Vote` shape as the TV); the call moment shows the viewer's call, the model's and the manager's; full time shows the What if lead row and recap from the card's `review`. Casual shows a few large numbers; analyst adds the interval and the trend. Phone-first CSS in `web/app/fan.css` (max width 420px, centred on wider screens).

- [ ] **Step 6: Add the route** `web/app/fan/page.tsx`: `useDataSource()`, `useFeed()`, `useVotes(live)`, a club picker (the roster's two clubs, home by default, kept in `localStorage` key `dugout.fan` with try/catch), mode and language toggles, Play and speed controls in replay. Add the strings to both dicts.

- [ ] **Step 7: Use the phone in the story**: `buildStory(..., { phone: true })`; the phone step renders `FanView` full-screen with the story's shared `useVotes` state, so the 60' vote is the one revealed at 79'. A vote on the phone sends the story `vote` event.

- [ ] **Step 8: Run every check and look at it.** `cd web && npm test && npm run typecheck && npm run build`; serve `out/`: `/fan` at 390 x 844 and 1440 x 900 in replay (Play, the 60' card with Varga 69% and the options, vote, the 79' call, full time); the story's vote and manager steps now on the phone; `/fan?source=live` shows the waiting moment without errors.
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add web/lib/fan.ts web/lib/fan.test.ts web/components/fan web/app/fan web/app/fan.css web/lib/i18n.ts web/app/page.tsx web/components/story/Story.tsx
git commit -m "web: fan view with the decision's context and the vote, on the phone in the story"
```

---

### Task 5: Device frames and transitions

**Files:**
- Modify: `web/components/story/Story.tsx`, `web/app/broadcast.css`

**Interfaces:**
- Consumes: `StoryStep.screen` (Task 1), `DeskView` (Task 2), `FanView` (Task 4).
- Produces: `export function DeviceFrame(props: { device: "tablet" | "phone"; children: ReactNode }): JSX.Element;` in `Story.tsx`.

- [ ] **Step 1: Wrap the tablet and phone steps in `DeviceFrame`**: a tablet bezel (4:3, rounded, dark border) over a dimmed, blurred TV picture as if in the dugout; a phone bezel (9:19.5) over the same. The desk and the fan view stay fully usable inside (scroll, click).

- [ ] **Step 2: Transitions** between screens: a short push-in from the TV to the frame (about 500 ms scale and fade) and a cut back to TV; respect `prefers-reduced-motion` (no scaling, fade only).

- [ ] **Step 3: Narrow windows**: under `max-width: 700px` no frames and no dimmed TV behind; each step is full-screen.

- [ ] **Step 4: Look at it.** `npm run build`, serve `out/`, run the story at 1440 x 900 and 390 x 844 (the probe at `~/.claude/skills/page-audit/scripts/probe.cjs` reports overflow). Expected: frames on desktop, none on the phone size, no horizontal overflow, controls inside the frames usable.

- [ ] **Step 5: Commit**

```bash
git add web/components/story/Story.tsx web/app/broadcast.css
git commit -m "web: tablet and phone frames for the story, full-screen on narrow windows"
```

---

### Task 6: Bench graphic

**Files:**
- Create: `web/lib/bench.ts`, `web/lib/bench.test.ts`, `web/components/broadcast/Bench.tsx`
- Modify: `web/app/page.tsx`, `web/components/Dugout.tsx`, `web/lib/fan.ts` (use `benchAt` for "who is ready"), `web/lib/i18n.ts`, `web/app/broadcast.css`

**Interfaces:**
- Consumes: `MatchLog`, `Roster`, `Snapshot`.
- Produces:
  ```ts
  export interface BenchPlayer { id: string; name: string; role: string }
  /** The club's roster players who have not played by `pos`: not on the pitch in the latest snapshot and never subbed off. */
  export function benchAt(log: MatchLog, pos: number, club: TeamCode): BenchPlayer[];
  export function Bench(props: { log: MatchLog; pos: number; snapshot: Snapshot | null; t: Translate }): JSX.Element; // both clubs
  ```

- [ ] **Step 1: Write the failing tests**: on the demo files, at 60:00 Riverside's bench lists the seven players who have not played and includes Femi Osei; at 80:00 it no longer lists Femi Osei (on since 79') and does not list Leon Varga (subbed off); a club with no snapshot yet returns every non-starter.

- [ ] **Step 2: Run them to see them fail**, then **Step 3: implement `benchAt`**, then **Step 4: run them to see them pass** (`cd web && npm test`).

- [ ] **Step 5: The TV strip**: `Bench` renders one compact strip per club (name, position, "not played yet"; subs and windows left from the snapshot) under the scorebug for the home club and under the settings chip for the away club; it hides while the What if segment is on and never overlaps the decision lower third or the worm (check at 1440 x 900 and 1114 x 533). The label says "on the bench", not "ready".

- [ ] **Step 6: The desk** lists the same players in the dugout panel (`Dugout.tsx`) under each club's subs and windows chips; the fan view's "who is ready" uses `benchAt` filtered to the flagged player's role.

- [ ] **Step 7: Run every check and look at it.** `cd web && npm test && npm run typecheck && npm run build`; serve `out/`, check `/` at 59', 60:30 (lower third open), 80' and full time, and `/desk`.

- [ ] **Step 8: Commit**

```bash
git add web/lib/bench.ts web/lib/bench.test.ts web/components/broadcast/Bench.tsx web/app/page.tsx web/components/Dugout.tsx web/lib/fan.ts web/lib/i18n.ts web/app/broadcast.css
git commit -m "web: bench graphic on the broadcast picture, the desk and the fan view"
```

---

### Task 7: README and a full walk-through

**Files:**
- Modify: `README.md` (the "Try it" line and the Broadcast mode section: the guided story, `/fan`)

- [ ] **Step 1: Update the README**: the landing page now starts with the guided story; `/fan` is the fan view; the "Personalize" row of the challenge table mentions the fan view's decision context.

- [ ] **Step 2: Walk through everything on a production build** at 1440 x 900 and 390 x 844: the story start to end; Skip; Leave on each step (TV stays on `/?t=M`, tablet goes to `/desk?t=M`, phone to `/fan?t=M`, each paused at that minute, and a reload gives the same); a chapter click mid-story; switching to ES mid-story; `/?t=60`; `/desk`; `/fan`; `/broadcast`; `?cues=json`; `?source=live` (no story, countdown or live match). Note any defect and fix it in the task that owns the code before committing.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: the guided story and the fan view in the README"
```
