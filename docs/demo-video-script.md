# Demo video script

About 2 minutes 45 seconds. The guided story on the landing page is the spine: record it as it plays, then add three short segments it does not cover (how it is graded, the live pipeline on Azure, the MCP server). Every number below is what the deployed demo shows on the current build (seed 73, engine refit of 2026-10-22); if the demo files are rebuilt, check them again before recording.

## Before recording

- **A clean first visit:** open https://ashy-ocean-03bdf100f.2.azurestaticapps.net in a private window, so the story's intro shows (it is offered once per browser).
- **Window:** 1920 x 1080 (or 1440 x 900), browser in front and at 100% zoom. A hidden or background window pauses the animation.
- **Language:** English for the main take. Optionally record the 60' card again in Spanish (Settings, ES) for the closing seconds.
- **Live segment:** the demo match kicks off live at :00 and :30 past each hour (UTC) and runs about 20 minutes. Open `/?source=live` a couple of minutes after a kick-off to catch a card arriving.
- **MCP segment:** Claude Code or GitHub Copilot connected to `https://dugout-service.wittypond-73564413.northeurope.azurecontainerapps.io/mcp` (see the README). Try the question once before recording.

## Shots

| Time | On screen | Voiceover |
| --- | --- | --- |
| 0:00-0:12 | The intro card over the pitch | "F1 explains the pit wall. The NFL explains fourth down. In football, the dugout is still a black box. The Dugout opens it." |
| 0:12-0:30 | Story step 1: the match from 59' at 5x, bench strips, Leon Varga's ring | "A synthetic Premier League-style match, streamed through Azure. Every player's condition is estimated from running data alone: minutes, runs, and how hard he is still working against his own first twenty minutes." |
| 0:30-0:50 | Step 2: the 60' lower third, "Take Leon Varga off for a fresh player", like-for-like 82.1% against 76.3% for no change, +5.8 pts, strong | "At 60 minutes Varga, the left-back, has dropped to 69%, the lowest on his team. A Monte Carlo engine plays the rest of the match twenty thousand times for each option. A like-for-like change now is worth about six points of win probability: a strong call. The line is written by a model on Microsoft Foundry, but every number in it is checked in code before it reaches the screen." |
| 0:50-1:05 | Step 3: the camera moves to the tablet, the analyst desk with Varga picked out | "In the dugout, the manager sees why: every player's condition and trend, each option with its interval, the left flank's share of the danger, the bench." |
| 1:05-1:20 | Step 4: the phone, the same card with who, why now, the options and who is on the bench; cast a vote (key 2) | "The fan gets the same information on their phone, and makes their own call before the manager does." |
| 1:20-1:35 | Step 5: the 72' equaliser down Varga's flank | Let the moment play. "Castleton equalise. Down Varga's side." |
| 1:35-1:50 | Step 6: the phone at 79', Manager, Model and You side by side | "The manager makes the change nineteen minutes after the card. Same call as the model, and as you, just later." |
| 1:50-2:05 | Step 7: full time, What if led by the 60' row, +2.6 pts | "At full time every decision is replayed against the option not taken. Waiting cost Riverside about two and a half points of win probability. Model estimates, not hindsight." |
| 2:05-2:25 | How it's graded panel: the scatter, correlation 0.74, sign agreement 78.4%, fatigue cards 100% | "Isn't the simulator grading itself? The engine never sees the simulator's hidden state. At every decision we fork the simulator and play both options out to get the true gap. On matches it was never fitted to, the engine's gaps correlate 0.74 with the truth, and on fatigue cards it gets the direction right every time." |
| 2:25-2:40 | `/?source=live` with a card arriving, then the architecture diagram (README) | "And it runs live on Azure: Event Hubs in, a Container Apps runner, Foundry agents, Web PubSub out to every screen. The demo match kicks off live every half hour." |
| 2:40-2:45 | An MCP client asking "What was the left-back change worth at 64'?", the answer from `price_options` | "Any agent can ask the same engine through its MCP server. The Dugout: the bench's options, priced, explained, and checked." |

## Figures used above

- 60' card (rfc-60-20, condition drop, strong): like-for-like 82.1% against no change 76.3%, +5.8 points, 90% interval +5.5 to +6.1. Varga at 69%, lowest of 10 on Riverside. Left flank 14% of chances against.
- Equaliser: Castleton, 72:35, down the right, which is Riverside's left.
- Manager's change: 79:00, Varga off, Femi Osei on: 19 minutes after the card.
- What if: +2.6 points for the 60' call against the manager's later change.
- Evaluation (docs/evaluation.md): test correlation 0.74, sign agreement 78.4%, condition-drop cards 16 of 16.
