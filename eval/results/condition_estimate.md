# Condition estimate: what the events can and cannot tell

Measured with `uv run python eval/condition_estimate.py` (played-midweek lever on RFC-03).
Raw numbers: `condition_estimate_before.json`, `condition_estimate_after.json` (seeds 1-20),
`condition_estimate_after_21-100.json` (held out; no setting was chosen on these seeds except
the rate window and weight, which were scanned there and left where they were).

| | before | after, 1-20 | after, 21-100 | target |
| --- | --- | --- | --- | --- |
| correlation with hidden condition at 62' | 0.075 | 0.517 | 0.524 | 0.3 |
| the same, pooled over minutes | 0.106 | 0.613 | 0.624 | |
| at 62', against condition relative to his own baseline | 0.025 | 0.622 | 0.623 | |
| RFC-03 below the other Riverside starters' median at 62' | 14/20 | 16/20 | 68/80 | 17/20 |
| band coverage (relative condition) | 0.965 | 0.906 | 0.903 | 0.85 |
| median band width at 62' | 0.55 | 0.14 | 0.14 | |

A noise-free estimate of condition relative to the player's own baseline would correlate 0.95
with hidden condition at 62', so the target was learnable; the old estimate was noise.

## Why the running rate alone could not do it

Hidden condition at 62' spreads by sd 0.059 across outfield starters (0.038 relative to each
player's own first 20 minutes). The ratio of a player's recent run rate to his own baseline
rate rests on about one run per in-play minute, so its sd at 62' is about 0.25: the best a
pure rate estimator reached offline was r 0.19 (total runs rather than hsr metres and
sprints, which add run-length noise). A Poisson fit of each player's own drain multiplier over
his whole time on the pitch has an sd of about 1.5 on a multiplier that varies by about 0.2
between players, so the rate cannot be leaned on much, however it is windowed.

## What worked, and the caveat

Most of the spread in condition is load: minutes on the pitch, the role's drain, and the runs
made. Counting those from the events gives r 0.61 at 62' by itself. The estimate is now 0.9 of
that and 0.1 of the rate ratio, which costs some correlation (0.52) but is the only part that
sees a player tiring faster than his load says.

The caveat: the per-minute and per-run costs are the simulator's own fatigue assumptions for
an average player. In the simulator that is true by construction, so the 0.52 is an upper
bound on what the same idea would do on real data, where the costs would have to be fitted.

## What it cannot do: RFC-03

RFC-03 is lowest because he started at 0.85 (played midweek) and has low stamina. Neither
leaves a trace in load: his own load reads 0.82 at 62' against 0.83 for the other Riverside
starters, while his hidden condition relative to his own baseline is 0.75 against 0.85. Only
the rate ratio separates him, and it does so in about 85% of matches (68/80 held out, 16/20
on seeds 1-20). A larger rate weight trades correlation away without lifting this: 0.15 gives
67/80, 0.3 gives about 63/80 offline. Longer windows (25 and 40 minutes) give 67/80 and 66/80.
Counting duels and fouls in the load changes nothing held out (70/80 offline either way).

## What would close the gap (not done here)

1. A lineup field the club knows before kick-off, such as minutes played in the last 7 days
   or days since the last match. It is the played-midweek lever made observable, which real
   clubs have. Contract and scenario change.
2. Per-minute running distance by speed band per player, as real tracking providers deliver,
   instead of one event per run: many more independent observations per minute, so the rate
   ratio stops being Poisson-limited. Simulator and contract change; breaks the demo seed.

## Knock-on for the triggers

Starters now read about 0.8 at 60', so `condition_below_60` (triggers.py, 0.60) almost never
fires. Demo seed 73 had six condition cards, all noise (two centre-backs at 36' and 42'; RFC-03
never had one), and now has none. The line needs to change to something that fits a
calibrated estimate, for example a player more than a set margin below his team's median, or a
line near 0.75.

## Recent minutes in the lineup (done)

Change 1 above is now made. The lineup carries each player's `recent_minutes`, the minutes he
played in the last 7 days, which a real club knows before kick-off. In the scenario RFC-03 has 90
(a full midweek cup tie) and everyone else 0. **The estimator now knows who played midweek, as a
real club would.** It never reads the hidden `played_midweek` value.

How much a recent minute costs is a stated assumption, not a fit: half of a full match's load is
still there a few days later. A full match costs an outfield starter 0.283 in the estimator's own
load terms (mean over seeds 1-20, half-time recovery included), so 90 recent minutes start a
player at 1 - 0.14 = 0.86. The band widens by half of that residual, since the share could be
anywhere from about a quarter to three quarters. Treat the 0.14 with care: it lands close to the
hidden lever (RFC-03 starts at 0.85), so this is again an upper bound on what the field would do
on real data, where the residual share would have to be fitted.

Measured with `uv run python eval/condition_estimate.py [--no-recent]`. Before is the lineup
without the field (it reproduces the "after" numbers above); raw numbers in
`condition_estimate_recent.json` and `condition_estimate_recent_21-100.json`. No setting was
chosen on any seed.

| | before, 1-20 | after, 1-20 | before, 21-100 | after, 21-100 | target |
| --- | --- | --- | --- | --- | --- |
| correlation with hidden condition at 62' | 0.517 | 0.853 | 0.524 | 0.855 | 0.3 |
| the same, pooled over minutes | 0.613 | 0.889 | 0.624 | 0.897 | |
| at 62', against condition relative to his own baseline | 0.622 | 0.796 | 0.623 | 0.792 | |
| RFC-03 below the other Riverside starters' median at 62' | 16/20 | 20/20 | 68/80 | 80/80 | 17/20 |
| band coverage (relative condition) | 0.906 | 0.900 | 0.903 | 0.896 | 0.85 |
| band coverage (hidden condition itself) | 0.942 | 0.992 | 0.946 | 0.996 | |
| median band width at 62' | 0.14 | 0.14 | 0.14 | 0.14 | |

Read the correlation jump carefully. Every other player has 0 recent minutes, so his estimate is
unchanged; leaving RFC-03 out, the held-out correlation at 62' is 0.713 either way. The jump from
0.52 to 0.85 is one player per match, the one the old estimate got most wrong, moving to where he
belongs. Coverage against hidden condition itself is now the fairer band check, since the
estimate aims at where a player started and not only at his own first 20 minutes.

Not sensitive to the assumed share on held-out seeds 21-100: 0.25 gives r 0.748 and 80/80, 0.75
gives r 0.894 and 80/80; relative coverage stays 0.89 to 0.90.
