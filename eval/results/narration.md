# Narration eval

Run 2026-10-21 with Foundry deployment gpt-5-mini.

50 decision payloads from data/demo-rfc-cas-0073.jsonl through the state engine and decision engine: 10 real decision points and 40 evenly spaced snapshots.

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
100 cards, 226 model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | 73.3% (129 of 176 replies; narrator 71/97, localizer 58/79) |
| Retries | 47 (21 passed on the retry) |
| Template fallbacks | 29 of 100 cards (timeout 3, ungrounded 26) |
| Cards shown from the model | 71 of 100 (71.0%) |
| Calls with no reply | 3 timeouts, 0 errors |
| Median latency, one model call | 1.58 s (95th percentile 2.12 s) |
| Median latency, one card (both stages and any retry) | 3.26 s (95th percentile 6.18 s) |

Why replies failed the check:

- strength label missing: 67
- number not in payload: 13

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the 3 s timeout per call.
