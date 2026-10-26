# Narration eval

Run 2026-10-26 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in Spanish in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 221 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 84.3% (161 of 191 replies; narrator 80/100, localizer 81/91) |
| Retries | 30 (18 passed on the retry) |
| Template fallbacks | 12 of 100 cards (timeout 1, ungrounded 11) |
| Cards shown from the model | 88 of 100 (88.0%) |
| Calls with no reply | 1 timeouts, 0 errors |
| Median latency, one model call | 1.28 s (95th percentile 2.39 s) |
| Median latency, one card (both stages and any retry) | 3.07 s (95th percentile 5.37 s) |

Why replies failed the check:

- toss-up headline calls for an action: 18
- strength word twice: 17
- unknown player id: 5
- over the word limit: 4
- number not in payload: 4
- wrong agreement: 3
- '~' for about: 1
- internal name: 1
- long dash: 1
- casual: zero points: 1

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
