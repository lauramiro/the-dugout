# Narration eval

Run 2026-10-21 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 205 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 93.8% (180 of 192 replies; narrator 87/99, localizer 93/93) |
| Retries | 12 (6 passed on the retry) |
| Template fallbacks | 7 of 100 cards (timeout 1, ungrounded 6) |
| Cards shown from the model | 93 of 100 (93.0%) |
| Calls with no reply | 1 timeouts, 0 errors |
| Median latency, one model call | 1.65 s (95th percentile 2.37 s) |
| Median latency, one card (both stages and any retry) | 3.25 s (95th percentile 4.70 s) |

Why replies failed the check:

- over the word limit: 9
- number not in payload: 5
- strength label missing: 5
- internal name: 1

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
