# Broadcast mode: design

Date: 2026-10-22. Status: approved direction (Laura, 2026-10-22), design for planning.

## Intent

The live page works but reads like a dashboard: panels of numbers beside a small pitch. The
hackathon brief asks for insight "rendered into something that can sit on screen alongside the
match", "timed and machine-readable enough to be rendered as synchronized graphical overlays on a
live match feed", and personalised for every fan, with player focus named explicitly. Broadcast
mode is the TV picture: the match fills a 16:9 frame and The Dugout appears as broadcast graphics
that come in at the moment they matter and go out again. It becomes the main experience and the
demo video. The current page stays as the analyst desk.

## Goals

1. A `/broadcast` route: one 16:9 stage, scaled to fit the window, the match drawn full-bleed from
   the 2 Hz tracking data (22 dots and the ball, interpolated), with broadcast graphics on top.
2. An overlay cue sheet: every graphic is a cue `{id, kind, in_pos, out_pos, data}` built by a pure
   function from the match log and the viewer's preferences. The stage only plays cues. The cue
   sheet can be exported as JSON (button and `?cues=json`), which is the brief's "timed,
   machine-readable" deliverable.
3. The graphics, in order of value:
   - **Scorebug:** clubs, score, match clock, top left, always on.
   - **Decision lower third:** when a card opens: trigger title, strength, the model's one-line
     headline and reason, the options as animated win-probability bars, "Your call" vote prompt.
   - **Fading tag:** a ring on the flagged player's dot that drains green → amber → red with
     condition, and a callout when the condition trigger fires.
   - **Win probability worm:** along the bottom edge, home win probability over the match, card
     moments marked.
   - **Manager's call:** when the manager acts on an open card: what they chose, whether it
     matched the model's pick, how long after the card.
   - **Goal flash:** short full-width strip on a goal.
   - **Full-time "What if":** a short closing segment from the review: the minute the model would
     have changed, the gap in win probability (the +3.1 pts story on seed 73), the manager's call.
4. Personalisation, in a small settings chip (top right, collapses): Casual/Analyst, EN/ES,
   favourite club (its graphics take the club colour and lead the worm), **player focus** (pick
   any player: a permanent tag that follows them with name, condition ring and running stats;
   their events get a mini player card).
5. Works on both sources: replay (static demo files, can seek and change speed) and live
   (`?source=live`, Web PubSub).

## Non-goals

- Real video, auto-eventing from video, 3D, a graphics engine. CSS transitions and SVG only.
- New engine or narration logic. Broadcast mode reads what exists.
- Mobile-first layout. The stage scales down to phone width without breaking, but is designed for
  16:9 screens.
- Replacing the current page.

## Anti-goals (a failure even if it works)

- Graphics that cover the action for long: a lower third must leave the play visible and go out on
  its own.
- Any number on a graphic that is not from the engine payload or the snapshot (same rule as the
  grounding check: code computes, words narrate).
- "Wrong" language about the manager: options and trade-offs only (existing rule).
- A demo that silently shows recorded data as live without saying so.

## Constraints

- Submit by Tue 27 Oct 23:00 Madrid; Mon 26 and Tue 27 are for the video and submission, so
  build Thu 22 to Sat 24 (about 3 days). 40-hour cap; hours not logged so far.
- Web PubSub is on the Free tier and throttled us (429) on 21 Oct. Live messages stay small:
  no tracking frames over Web PubSub.
- Next.js static export on Azure Static Web Apps (`web/`, `npm run build`); no server code in the
  page. Existing stack only: React, TypeScript, CSS; no new runtime dependencies.
- The page reads the match only through `DataSource` (`web/lib/datasource.ts`); keep that.

## Decided

- New route `web/app/broadcast/page.tsx`; components under `web/components/broadcast/`; the cue
  builder in `web/lib/cues.ts` as a pure, tested function.
- Cue timing is in match position (`pos`, as elsewhere). The stage holds each cue on screen for a
  minimum wall-clock time (about 4 s) so graphics stay readable at 5x and 20x replay.
- Live mode gaps, filled as follows (Laura's direction: live, but within the Free tier):
  - **Events:** the runner publishes match events of the kinds the graphics use (goal, sub, shot,
    foul), not passes, runs or duels. Small, and it makes the scorebug and goal flash live.
  - **Win probability:** the runner publishes one `winprob` point per match minute, the same
    calculation as `web/scripts/build_demo_fixtures.py` (no-change simulation for the home side)
    with fewer runs.
  - **Roster:** the page loads `demo/roster.json` for the scenario's clubs and players (fixed
    configuration, like a broadcaster's team sheet).
  - **Manager's call and "What if":** live cards carry no `manager_action` and no review (the
    build script adds both to the replay files). Live, the manager's-call graphic shows the change
    (who off, who on) when a card closes with reason "change", without the "matched the model's
    pick" verdict; the full-time "What if" segment is replay only.
  - **Tracking:** not sent live. When the live `match_id` is the recorded demo match, the stage
    draws the recorded tracking, aligned to the latest live `t_ms`, and the settings chip says
    "recorded tracking". Otherwise the pitch shows no dots.

## Left to the builder

- Exact visual design within the existing palette and type (dark, LED clock, club chips), motion
  timings, sizes, the stage's scaling method.
- How the worm marks cards; where the "Your call" prompt sits.
- The cue sheet's JSON field names beyond `{id, kind, in_pos, out_pos, data}`.
- Whether the full-time segment is one graphic or a short sequence.
- How the runner computes the per-minute win probability (reuse the engine's simulation; keep it
  well under a second per point).

## Done when

- `/broadcast` plays seed 73 end to end in replay and in live, in all four language and mode
  versions, with the graphics above and no console errors from the new code.
- The cue builder has unit tests; Python tests cover the new runner messages; `npm run typecheck`
  and `npm run build` pass.
- Checked in Chrome at 1920x1080 and at 375 px wide; a full live replay stays inside the Free tier
  (no 429).
- README section and a one-paragraph note for the vault.
