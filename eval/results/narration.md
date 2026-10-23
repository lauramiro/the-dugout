# Narration eval

Run 2026-10-23 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 212 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 84.2% (154 of 183 replies; narrator 76/100, localizer 78/83) |
| Retries | 29 (12 passed on the retry) |
| Template fallbacks | 17 of 100 cards (ungrounded 17) |
| Cards shown from the model | 83 of 100 (83.0%) |
| Calls with no reply | 0 timeouts, 0 errors |
| Median latency, one model call | 1.31 s (95th percentile 1.75 s) |
| Median latency, one card (both stages and any retry) | 2.78 s (95th percentile 4.05 s) |

Why replies failed the check:

- over the word limit: 24
- number not in payload: 18
- casual: interval, decimals or a probability: 12
- strength label missing: 8
- casual: zero points: 2
- internal name: 1

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
