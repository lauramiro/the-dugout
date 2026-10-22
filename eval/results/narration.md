# Narration eval

Run 2026-10-22 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 218 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 88.1% (171 of 194 replies; narrator 91/99, localizer 80/95) |
| Retries | 23 (18 passed on the retry) |
| Template fallbacks | 6 of 100 cards (timeout 1, ungrounded 5) |
| Cards shown from the model | 94 of 100 (94.0%) |
| Calls with no reply | 1 timeouts, 0 errors |
| Median latency, one model call | 1.57 s (95th percentile 2.30 s) |
| Median latency, one card (both stages and any retry) | 3.33 s (95th percentile 5.11 s) |

Why replies failed the check:

- interval or decimals in casual: 20
- over the word limit: 10
- internal name: 4
- close on a strong or lean card: 3
- wrong article: 2
- wrong strength label: 2

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
