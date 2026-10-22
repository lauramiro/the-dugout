# Guided story: one decision, three screens

Date: 2026-10-23. Status: approved direction (Laura, 2026-10-23), design for planning.

## Intent

The Dugout's point is that one engine, with numbers checked in code, serves three audiences: the
broadcaster, the manager and the fan. Today a judge sees only the broadcast picture unless they go
looking for the analyst desk, and nothing shows the fan's side as its own thing. The guided story
shows all three around a single moment, the 60' decision on the demo match, in about a minute,
and leaves the judge inside whichever real screen they want to keep using.

Laura's picture: a live game on TV showing the tiring player and both benches; the view moves into
the coach's tablet with the full detail; then the audience's own version. A 3D prototype was tried
and dropped (2026-10-22): realistic players are out of reach before the deadline, and nearly
realistic ones invite a comparison with video games that the entry would lose. The story, not the
rendering, is what should impress.

## Goals

1. **A guided story that plays by itself** on the landing page `/`, replay only. On a first visit it
   replaces today's title card: "Watch the story" starts it, "Skip" leaves the viewer on the
   broadcast picture as it is today. A visible control replays it later. The viewer can pause it,
   skip a step, or leave it at any point; leaving keeps them on the screen they were on, fully
   usable.
2. **Three real screens, not mock-ups.** Each step shows the working app driven by the demo
   match's data:
   - **TV:** the existing broadcast picture (`web/app/page.tsx`).
   - **Tablet:** the existing analyst desk (`/desk`) inside a tablet frame, as if in the dugout,
     opened at the decision's minute with the flagged player (Leon Varga, RFC-03) picked out. The
     judge can use the desk inside the frame.
   - **Phone:** a new fan view (see 4) inside a phone frame.
3. **The story, in this order** (seed 73, demo match; minutes from the data, not hard-coded where
   the data can supply them):
   1. TV from about 59': the match, scorebug, the bench graphic (5), Varga's ring and tag.
   2. The 60' card opens on TV: the decision lower third ("Take Leon Varga off for a fresh
      player ... about 6 points better (strong)", from the card's narration). The guide pauses on
      it with a caption.
   3. Cut to the tablet: the desk at that minute, Varga picked out in the condition list, the
      options with their intervals, subs and windows left, the substitution-window forecast.
   4. Cut to the phone: the fan's version of the same card with the vote. The guide waits for a
      vote or a short timeout.
   5. The equaliser down Varga's flank (about 72', from the goal event) on TV, with a caption.
   6. The manager's change (79', from the sub event): on the phone, the viewer's call beside the
      model's and the manager's.
   7. Full time: the What if segment on TV (+2.6 pts for the 60' call on the current build).
   8. End: the three ways in (TV, analyst desk, fan view) and "How it's graded".
   The whole story runs about 60 to 90 seconds at its own pace.
4. **Fan view:** a new phone-sized screen and route, reachable on its own as well as inside the
   story, so a fan sees what the manager is weighing, not only a question. Score and clock always.
   When a decision card opens it shows the card's context (Laura, 2026-10-23):
   - **Who:** the flagged player, his condition, its trend over the last minutes, and where he
     stands against his teammates (for example Varga at 69% and falling, lowest on Riverside).
   - **Why now:** what opened the card (fading against his team, a goal after 55', a
     substitution), and his flank's share of the danger when the card carries it.
   - **The bench's options:** no change, like-for-like, attacking, defensive, each with its win
     probability and its gap to no change in plain words; the model's pick and its strength
     marked. A toss-up says plainly that the options are close: a card is not always a sign that a
     change is coming, and the view must not imply that it is.
   - **Who is ready:** the bench players for that position, subs and windows left.
   - **Your call:** the vote under all of this, so the fan decides with the same information.
   Then the manager's call when it comes, with the viewer's call and the model's beside it, and the
   What if at full time. Casual by default (a few large numbers); analyst adds intervals and the
   trend. English and Spanish. Same data source as the other screens (replay, or live with
   `?source=live`). The fan view follows one club, chosen by the viewer (Riverside in the story),
   and shows only that club's cards; the standalone view also shows cards the story skips (the 72'
   card, for example), each with its own vote.
   The manager's tablet keeps the full depth (the desk); the fan view is the lighter cut of the
   same information. More depth for the manager's view is welcome later and is not part of this
   design.
5. **Bench graphic:** on the broadcast picture, a strip per team naming who is ready on the bench
   (name and position from the roster), with subs and windows left from the snapshot. The tablet
   view shows the same bench. It must not hide the decision lower third or the win-probability
   worm when they are on screen.
6. **Captions:** short lines that say what the viewer is looking at ("On TV, the moment the model
   flags Varga", "In the dugout, the manager sees why", "In your hand, your call"). Captions that
   quote a number take it from the data (card narration, payload, review), never typed in, so a
   rebuild of the demo files keeps them right. English and Spanish.

## Non-goals

- 3D players or stadium (tried and dropped, see Intent).
- Visibly slower movement for tired players. The tracking data does not slow them; Varga's ring,
  tag and the decision graphic carry the moment. No change to the simulator, the tracking files
  or the demo match.
- New engine, narration or backend work. No new Azure resources.
- The guide in live mode. Live keeps its kick-off countdown; the story plays the recorded match.

## Anti-goals (a failure even if it works)

- **Invented numbers.** No made-up crowd split, percentages or quotes. The replay has no crowd:
  the phone shows the viewer's call, the model's and the manager's; the real crowd tally appears
  only in live mode, where it exists.
- **A guide that traps the viewer.** Skip, pause and leave must always work, and the judge must be
  able to stay in any screen and use it.
- **Anything that reads as a fake video game or a slide show.** The screens are the product,
  running.
- **Breaking what works:** the landing page without the guide, `/desk`, `/broadcast`, `?t=`,
  `?source=live`, `?cues=json`, the vote, the existing tests.

## Constraints

- Deadline: submission by 28 October 2026, 07:59 Madrid; Laura's own target is 27 October, 23:00.
  The story is also the spine of the demo video, so it needs to be done and deployed with time to
  record (aim: 25 October).
- Next.js 16 static export on Azure Static Web Apps, no server features. Next 16 differs from
  older versions: read the relevant guide in `web/node_modules/next/dist/docs/` before writing
  code (see `web/AGENTS.md`).
- English and Spanish everywhere a viewer reads, through `web/lib/i18n.ts`.
- Pure, testable logic goes in `web/lib/` with Node's test runner (`npm test`), as `cues.ts` does;
  the story's timeline (its steps, minutes and captions from the match log) should be such a pure
  function.
- Project writing rules (CLAUDE.md): no emojis or em-dashes in code, copy or docs.
- Deploy is `infra/deploy.sh --apply`, run by Laura.

## Decided

- Guided and self-playing, with skip, pause and leave (Laura).
- The real app in every frame, not screenshots or recordings (Laura).
- Built into the app, not only shown in the video (Laura).
- No visible-fatigue change to the tracking (Laura).
- First visit plays the story instead of the title card; skip goes to the broadcast picture as
  today (Claude's call, accepted).
- No invented crowd numbers; crowd split only live (Claude's call, accepted).
- The bench graphic on TV and in the tablet (Laura's ask, Claude's placement).
- The fan view shows the decision's context, not only the vote; the manager's view keeps the most
  depth (Laura).
- **Small screens** (Claude's call): on a narrow window the device frames are dropped and each step
  plays full-screen; the desk already works on a phone.
- **Leaving the story** (Claude's call): during the story the three screens live in one page with
  one playhead and one set of votes, so the 60' vote can be revealed at 79'. Leaving hands off to
  the real route for the step the viewer is on (the broadcast page, `/desk`, or the fan view) at the
  same minute, paused, with the URL updated so it can be shared or reloaded.
- **Bench list** (Claude's call): the players in the roster who have not played; the data has no
  "ready" flag, and the label should not claim more than that.
- **`?t=` in the URL** (Claude's call): skips the story and opens the broadcast picture at that
  minute, as today.
- **If time runs short** (Claude's call; Laura has not ranked it): build and ship in this order,
  each a deployable cut: (1) the guide on the TV screen with captions and the tablet step showing
  the desk full-screen at the minute; (2) the fan view with the decision context and the vote;
  (3) the tablet and phone frames and transitions; (4) the bench graphic, TV first, tablet last.

## Left to the builder

- How the tablet hosts the desk (embedding the `/desk` route or rendering its components in the
  frame) and how the desk is told the minute and the player to pick out, as long as the judge can
  use the real desk inside it.
- The fan view's route name and layout within goal 4.
- Transition style between screens: quick and broadcast-like (cuts or short pushes), no long
  camera flights.
- Exact step timings, caption wording within goal 6, and the bench strip's placement within
  goal 5.
- Whether "first visit" is remembered per browser (storage is optional; the page must work
  without it).
