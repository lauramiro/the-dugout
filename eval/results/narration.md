# Narration eval

Run 2026-10-26 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 223 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 80.6% (150 of 186 replies; narrator 77/100, localizer 73/86) |
| Retries | 36 (20 passed on the retry) |
| Template fallbacks | 17 of 100 cards (timeout 1, ungrounded 16) |
| Cards shown from the model | 83 of 100 (83.0%) |
| Calls with no reply | 1 timeouts, 0 errors |
| Median latency, one model call | 1.30 s (95th percentile 2.44 s) |
| Median latency, one card (both stages and any retry) | 3.14 s (95th percentile 5.16 s) |

Why replies failed the check:

- casual: decimals: 26
- toss-up headline calls for an action: 18
- strength word twice: 18
- number not in payload: 8
- casual: interval: 7
- over the word limit: 3
- internal name: 3
- long dash: 3
- casual: a win, draw or loss probability: 2
- unknown player id: 1

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.

## Repeat run

The same command run once more on 2026-10-26, minutes earlier and before the failure classes above were split, gave 73 of 100 cards from the model (79.7% grounded on the first attempt, 13 of 37 retries passed, 5 timeouts, 27 fallbacks), mostly from casual replies that kept a decimal. Model replies vary from run to run, so read the share shown from the model as about 73% to 83% on this payload set.
