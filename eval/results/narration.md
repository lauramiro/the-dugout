# Narration eval

Run 2026-10-21 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 208 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 95.5% (190 of 199 replies; narrator 92/100, localizer 98/99) |
| Retries | 9 (7 passed on the retry) |
| Template fallbacks | 2 of 100 cards (ungrounded 2) |
| Cards shown from the model | 98 of 100 (98.0%) |
| Calls with no reply | 0 timeouts, 0 errors |
| Median latency, one model call | 1.50 s (95th percentile 1.97 s) |
| Median latency, one card (both stages and any retry) | 3.03 s (95th percentile 4.55 s) |

Why replies failed the check:

- internal name: 6
- number not in payload: 6
- over the word limit: 1
- strength label missing: 1

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
