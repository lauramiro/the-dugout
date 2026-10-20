# Evaluation: the counterfactual check

Does the decision engine's estimated gap match the gap the match really holds? The simulator knows the answer: fork its hidden state at a decision point, play the change and no change to the end many times, and count. This page compares the two at every decision point the system raises, then calibrates the engine's fatigue constants on one set of seeds and reports on another.

Everything here is synthetic: fictional clubs, simulated matches, illustrative rates.

Rerun with one command (about 2 hours on 3 workers; the pairs step saves after every seed and resumes):

    uv run python -m eval.counterfactual all --workers 3

Outputs in `eval/results/`: `counterfactual_pairs.csv` (every point, with the engine's inputs), `calibration.json` (every number below), `counterfactual.svg` (the scatter).

## Method

**Seeds.** 31 matches of the Riverside v Castleton scenario. Fit set: seeds 2 to 30, even (15 seeds). Test set: seeds 1 to 29, odd, and the demo seed 73 (16 seeds). Seed 73 is never fitted.

**Decision points.** Each match's events go through `dugout.stream.state_engine` and `dugout.stream.triggers`, exactly as live: a condition estimate crossing 0.60, a goal from 55', or a substitution, one open card at a time. 346 points over the 31 seeds.

**Engine gap.** `decide(snapshot, team, trigger)` on the decision point's snapshot. The like-for-like option replaces the outfielder with the lowest condition estimate; its gap is its win probability minus no change's, with a 90% interval (20,000 runs on common random numbers).

**True gap.** The simulator is stepped to the same `(period, t_ms)`, second by second, so it has played exactly the events the snapshot covers. It is then forked (`dugout.sim.counterfactual`): 500 branches with no change and 500 with the same player off for a bench player in the same role, branch k of each option sharing a random stream. The deciding team's simulated manager is frozen in every branch. The true gap is the difference in win rate, with a paired standard error from the branch outcomes.

**Pairs.** 308 of the 346 points pair up. 27 have no bench player in the same role left and 11 have no substitution window left, so the change cannot be made in the simulator. Of the 308, 154 are fit-set trigger points, 153 test-set trigger points, and one is the story point below.

**Story point.** With the current state engine, seed 73 raises no decision point at 64', when the demo's left-back RFC-03 fades (his estimate reads 0.907; his hidden condition is 0.599). That moment is added by hand as a story point, with RFC-03 off for RFC-15, and reported on its own, not in the test metrics.

**Calibration.** Least squares between engine gap and true gap over the 154 fit points, on a grid over `FATIGUE_SLOPE` (0 to 6), `FATIGUE_FLOOR` (0.60 to 1.00) and `BENCH_QUALITY` (0.97 to 1.06), then a finer grid around the best cell (5,000 engine runs per option while searching).

## Why this is not circular

The simulator grading itself would be circular if the engine could read the simulator's state. It cannot. `dugout.engine` never imports `dugout.sim`; it sees only the snapshot, built by the state engine from the public event stream: clock, score, substitutions left, rolling xG rates, a condition estimate per player from his high-speed running against his own first 20 minutes, and threat by channel. The only thing read from the scenario file is the lineup (each player's id, team, role, side and whether he starts). Hidden condition, player ratings, the simulator's possession model and its managers' plans stay on the simulator's side. The engine's win model (minute-level Poisson with a fatigue penalty on one flank) is also a different and much simpler model than the second-by-second possession simulator that produces the truth. So the check asks a fair question: from what a real system could observe, how well does the engine estimate what a change is worth?

Calibration uses the truth, but only on the fit seeds, and only to set three constants. The test seeds are untouched until the numbers below.

## Results

Test set: seeds 1 to 29 odd and 73, 153 trigger points. Gaps and errors are in points of win probability. Brackets are 90% bootstrap intervals over test seeds.

| Test set (16 seeds, 153 points) | Illustrative constants | Calibrated |
| --- | --- | --- |
| Constants (slope, floor, bench) | 0.6, 0.8, 1.03 | 0.3, 0.725, 1.0 |
| Mean engine gap | +2.22 | +1.06 |
| Mean true gap | +1.29 | +1.29 |
| Mean error (engine minus true) | +0.93 [+0.48, +1.33] | -0.23 [-0.61, +0.11] |
| Mean absolute error | 2.22 | 1.79 |
| RMSE | 3.19 | 2.44 |
| Correlation | 0.14 [0.00, 0.29] | 0.13 [-0.01, 0.28] |
| Sign agreement | 68.6% | 64.7% |
| True gap inside the engine's 90% interval | 9.8% | 8.5% |

The mean standard error of a true gap at 500 forks is 1.87 points, so much of the remaining RMSE of 2.44 is noise in the truth itself. Fit-set RMSE after calibration was 2.24 (154 points; reported only as a fit diagnostic).

By trigger, test set, before and after:

| Trigger | Points | Mean true gap | Mean error | Correlation | Sign agreement |
| --- | --- | --- | --- | --- | --- |
| Condition below 0.60 | 99 | +1.56 | +1.52 / -0.08 | 0.05 / 0.04 | 71.7% / 67.7% |
| Goal after 55' | 22 | +0.54 | +0.23 / -0.19 | 0.37 / 0.35 | 63.6% / 77.3% |
| Manager substitution | 32 | +0.99 | -0.43 / -0.72 | 0.22 / 0.20 | 62.5% / 46.9% |

Story point, seed 73 at 64:00, RFC-03 off for RFC-15: true gap +10.0 points (standard error 3.0, 500 forks; lane G measured +9.3 with 1,000). Engine gap -0.5 with the illustrative constants and 0.0 calibrated, because the engine reads RFC-03 as fresh.

What the numbers say:

- **Calibration fixes the level, not the ranking.** The illustrative constants overstated the gap by about a point on average; the fitted ones are unbiased within noise. Correlation stays at about 0.13 and sign agreement does not improve.
- **The engine cannot tell which points matter, because its input carries no signal there.** At the test points the condition estimate of the player the engine would take off correlates -0.01 with his hidden condition. The truth does depend on hidden condition (correlation -0.20 between hidden condition and true gap: tireder players are worth more to replace), so the information exists in the match but not in the estimate. The engine's picks average an estimate of 0.58 and a hidden condition of 0.80, and 23.5% of the true gaps are negative: replacing a player who is not tired with a weaker bench player hurts.
- **The engine's 90% interval is not a statement about the truth.** It covers only the engine's own Monte Carlo noise (about half a point wide at 20,000 runs), not model error or input error, so the true gap lands inside it under 10% of the time. The card's interval should not be read as "the true gap is in here".
- **The demo moment is missed.** The clearest honest gap in the scenario, +10 points at seed 73's fade, is invisible to the engine because the estimate reads the fading left-back as fresh. The first data point from lane A (seed 2 at 62': true +9.5 against +3.9 in the sanity table) had suggested the fatigue effect was too weak; across 154 fit points the opposite holds on average, and the real gap is in the input.

## Limits

- **Like-for-like substitutions only.** Attacking and defensive changes have no simulator counterpart yet (the engine models them as rate multipliers), so they are not checked here. Neither is the timing of a sub (now against later).
- **Win probability only.** The engine's draw, loss and expected points per option are not compared; the CSV keeps the true expected-points gap for later.
- **Noise in the truth.** 500 forks give a standard error of about 1.9 points per point; individual pairs are noisy, which also caps the correlation any engine could reach.
- **One scenario, 31 seeds.** The fit and test seeds share squads, ratings and levers. Calibrated constants are for this scenario's simulator and should not be read as football effects.
- **The condition estimate is changing.** Lane K is replacing it. The constants fitted here are tied to the current estimate; after K lands, rerun the command above, refit, and update `wp.py` and this page.
- **Story point by hand.** The 64' point is added because the triggers do not raise it; it shows the miss but is not part of the test metrics.
