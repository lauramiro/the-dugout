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

`sub` events carry one extra field, `player_in_id`: the player coming on. `player_id` is the player going off, `team` is their team, `outcome` says what kind of change it is, and `channel`, `x`, `y`, `end_x`, `end_y` and `xg` are null. Every other type leaves `player_in_id` out of the JSON. Changes are made at a dead ball or at half-time; the changes a team makes at one `(period, t_ms)` form one window. Half-time changes have `period` 2 and `t_ms` 2700000 and come before the second-half kick-off; they do not use up an in-play window. Each team gets five changes in at most three in-play windows, and a player who goes off never comes back.

```json
{"match_id": "rfc-cas-0001", "seq": 6120, "t_ms": 4680000, "period": 2,
 "type": "sub", "team": "RFC", "player_id": "RFC-03", "channel": null,
 "x": null, "y": null, "end_x": null, "end_y": null, "outcome": "like_for_like", "xg": null,
 "player_in_id": "RFC-15"}
```

`outcome` by type in the simulator:

| Type | Outcomes |
| --- | --- |
| `pass` | `complete` |
| `duel` | `won` (the event's team won the ball) |
| `shot` | `goal`, `saved`, `blocked`, `off_target` |
| `foul` | `committed` (by the event's team) |
| `out` | `throw_in` |
| `restart` | `kickoff`, `throw_in`, `goal_kick`, `corner`, `keeper`, `free_kick` |
| `sub` | `like_for_like` (same role or cover for it), `attacking` (a forward for a midfielder or full-back), `tactical` (any other change) |
| `sprint`, `hsr` | null |

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

Written by `dugout.stream.state_engine` from events in `seq` order plus a lineup (each player's id, team, role, side and whether he starts; nothing hidden). Additions to the shape above:

- `match_id` and `period` at the top level; `period` because first-half added time overlaps second-half `t_ms`. A snapshot at `(period, t_ms)` covers every event of that period with a smaller `t_ms`. Snapshots run every 10 s from each period's kick-off; a period's last snapshot is the first boundary after its last event.
- `rates` has an entry for each team: a pre-match prior (1.35 xG/90 by default) blended with rolling xG over the last 20 played minutes, the rolling weight growing to 0.6 at 90'.
- `players` lists everyone on the pitch, both teams, with `team` and `role`. The condition estimate compares exponentially weighted running per in-play minute (hsr metres weighted above sprints) with the player's own first 20 minutes on the pitch, clipped to 0.3 to 1.0; it stays 1.0 until that baseline is complete, and `condition_band`, `baseline_hsr_m_10m` and `baseline_sprints_10m` are null until then. `condition_band` is a 90% interval from the run counts behind the estimate, so it is wide (typically 0.5 across, wider for centre-backs, who run least); goalkeepers also carry `"condition_band": null`.
- `threat_by_channel` has keys for both teams (`RFC_left` = attacks on Riverside's left, from Riverside's view): the share of the opponent's xG over the last 15 played minutes, shrunk towards the first-half split. `threat_by_channel_first_half` gives that first-half split (the first half so far while it is being played; even until the first shot).

Decision points (`dugout.stream.triggers`), one record each, carrying the snapshot the card opens on with the deciding team first in `rates`:

```json
{"kind": "decision_point", "id": "rfc-62-01", "t_ms": 3720000, "period": 2, "team": "RFC",
 "trigger": "condition_below_60", "raised_t_ms": 3720000,
 "detail": {"player_id": "RFC-03", "condition_est": 0.594, "condition_band": [0.35, 0.86]}, "snapshot": {"t_ms": 3720000, "...": "..."}}
```

`detail` is `{"player_id", "condition_est", "condition_band"}` for `condition_below_60` (the estimate crossing 0.60; the band is usually wide, so the card should read as a possible rather than a certain drop), `{"scorer_team"}` for `goal_after_55` (one point for each team, the conceding team first) and `{"subs": [{"off", "on"}]}` for `manager_sub` (one per team per window). One card is open at a time and the rest wait, oldest first. A card closes when its team makes a change, after 3 minutes of match clock or at the end of the stream, written as `{"kind": "card_closed", "id", "t_ms", "period", "team", "reason"}` with `reason` `change`, `timeout` or `full_time`. `python -m dugout.stream.snapshots` writes snapshots as `{"kind": "snapshot", "snapshot": {...}}` with these records in between.

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
