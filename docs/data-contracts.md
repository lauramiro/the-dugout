# Data contracts

Four shapes, fixed on day one. Every service and the UI code against them.

- Coordinates are metres on a 105 x 68 pitch, origin at a corner. `y` grows towards the left touchline as seen by a team attacking towards `x = 105`.
- Times are match-clock milliseconds. The second half starts at 45:00 (`t_ms = 2700000`), so first-half added time overlaps second-half times: order by `(period, t_ms)` or by `seq`, never by `t_ms` alone.
- `channel` is always given **from the perspective of the team in the event's `team` field**. A team's left channel is the opponent's right.

## 1. Event (simulator -> Event Hubs)

Types: `pass`, `carry`, `duel`, `press`, `shot`, `goal`, `foul`, `card`, `out`, `restart`, `sub`, `sprint`, `hsr`.

`sprint` and `hsr` (high-speed running) are the only fatigue signals the engine receives. Real tracking providers deliver the same counts.

Running events carry one extra field, `dist_m`: the metres covered in that run (a sprint is above 7 m/s, a high-speed run is the band below it; a sprint's metres are not counted again as `hsr`). Their `t_ms` is the second the run starts; `channel`, `x`, `y`, `end_x`, `end_y`, `outcome` and `xg` are null. Every other type leaves `dist_m` out of the JSON entirely, so their shape is unchanged; readers should treat a missing `dist_m` as null. `hsr_m_10m` in the snapshot is the sum of `dist_m` over a player's `hsr` events in the last 10 minutes.

```json
{"match_id": "rfc-cas-0001", "seq": 4813, "t_ms": 3725000, "period": 2,
 "type": "sprint", "team": "RFC", "player_id": "RFC-03", "channel": null,
 "x": null, "y": null, "end_x": null, "end_y": null, "outcome": null, "xg": null, "dist_m": 21.4}
```

```json
{"match_id": "rfc-cas-0001", "seq": 4812, "t_ms": 3725000, "period": 2,
 "type": "pass", "team": "RFC", "player_id": "RFC-03", "channel": "left",
 "x": 34.2, "y": 8.1, "end_x": 51.0, "end_y": 12.4, "outcome": "complete", "xg": null}
```

`outcome` by type in the simulator core:

| Type | Outcomes |
| --- | --- |
| `pass` | `complete` |
| `duel` | `won` (the event's team won the ball) |
| `shot` | `goal`, `saved`, `blocked`, `off_target` |
| `foul` | `committed` (by the event's team) |
| `out` | `throw_in` |
| `restart` | `kickoff`, `throw_in`, `goal_kick`, `corner`, `keeper`, `free_kick` |

Defined in code as `dugout.contracts.Event`.

## 2. Tracking frame (2 Hz; `v` in m/s)

Used only to draw the pitch, never as a decision-engine input.

```json
{"match_id": "rfc-cas-0001", "period": 2, "t_ms": 3725500, "ball": {"x": 51.0, "y": 12.4},
 "players": [{"id": "RFC-03", "x": 33.8, "y": 9.0, "v": 7.4}]}
```

One frame every 500 ms of match clock in each period, from the period's kick-off to its final whistle, listing every player on the pitch. `period` is there because first-half added time overlaps second-half `t_ms`; order frames by `(period, t_ms)`. `v` is the distance from the previous frame divided by 0.5 s (0 on a player's first frame of a period). Positions are a formation template shifted with the ball plus noise, so they are drawn, not measured. `python -m dugout.sim run --out X.jsonl` writes the frames to `X.tracking.jsonl`.

## 3. Snapshot (state engine, every 10 s; the decision engine's only input)

```json
{"t_ms": 3720000, "score": {"RFC": 1, "CAS": 0},
 "subs_left": {"RFC": 5, "CAS": 4}, "windows_left": {"RFC": 3, "CAS": 2},
 "rates": {"RFC": {"for90": 1.5, "against90": 1.2}},
 "players": [{"id": "RFC-03", "condition_est": 0.60, "condition_band": [0.52, 0.68],
              "trend_per_min": -0.008, "hsr_m_10m": 210, "baseline_hsr_m_10m": 380,
              "sprints_10m": 3, "baseline_sprints_10m": 7}],
 "threat_by_channel": {"RFC_left": 0.41, "RFC_centre": 0.33, "RFC_right": 0.26}}
```

Goalkeepers carry `"condition_est": null`.

## 4. Decision payload (decision engine output; the agents' only input)

```json
{"decision_id": "rfc-62-01", "t_ms": 3720000, "team": "RFC",
 "trigger": "condition_below_60",
 "options": [
   {"id": "no_change", "label": "No change", "win": 0.687, "draw": 0.240, "loss": 0.073, "xpts": 2.30, "delta_win": 0.0},
   {"id": "sub_lb", "label": "Replace left-back (RFC-03 for RFC-15)", "win": 0.726, "draw": 0.217, "loss": 0.057, "xpts": 2.39,
    "delta_win": 0.039, "ci90": [0.021, 0.057]}],
 "recommendation": {"option_id": "sub_lb", "strength": "strong"},
 "evidence": [{"type": "condition", "player_id": "RFC-03", "value": 0.60, "trend_per_min": -0.008},
              {"type": "flank_threat", "channel": "RFC_left", "share": 0.41}],
 "manager_action": null}
```

Triggers: `condition_below_60`, `goal_after_55`, `manager_sub`. Strength: `strong` (gap of 3 points or more), `lean` (1 to 3), `toss_up` (under 1). The `ci90` values above are placeholders.
