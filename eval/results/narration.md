# Narration eval

Run 2026-10-21 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 210 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 85.8% (157 of 183 replies; narrator 78/99, localizer 79/84) |
| Retries | 26 (11 passed on the retry) |
| Template fallbacks | 16 of 100 cards (timeout 1, ungrounded 15) |
| Cards shown from the model | 84 of 100 (84.0%) |
| Calls with no reply | 1 timeouts, 0 errors |
| Median latency, one model call | 1.54 s (95th percentile 2.04 s) |
| Median latency, one card (both stages and any retry) | 3.15 s (95th percentile 4.64 s) |

Why replies failed the check:

- number not in payload: 42
- over the word limit: 2

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
