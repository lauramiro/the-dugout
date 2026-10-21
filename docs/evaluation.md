# Evaluation: the counterfactual check

Does the decision engine's estimated gap match the gap the match really holds? The simulator knows the answer: fork its hidden state at a decision point, play the change and no change to the end many times, and count. This page compares the two at every decision point the system raises, then calibrates the engine's fatigue constants on one set of seeds and reports on another.

Everything here is synthetic: fictional clubs, simulated matches, illustrative rates.

Rerun with one command (about 35 minutes on 4 workers; the pairs step saves after every seed and resumes, so pass `--fresh` after any change to the state engine or the triggers):

    uv run python -m eval.counterfactual all --workers 4 --fresh

Outputs in `eval/results/`: `counterfactual_pairs.csv` (every point, with the engine's inputs), `calibration.json` (every number below), `counterfactual.svg` (the scatter).

This page was rerun on 2026-10-21 after lanes K and O changed the engine's input: the condition estimate is now mostly accumulated load, starts lower for a player with recent minutes, and the condition card is `condition_drop`. The first version of this page (lane J before K and O) is in git history; its headline numbers are at the end.

## Method

**Seeds.** 31 matches of the Riverside v Castleton scenario. Fit set: seeds 2 to 30, even (15 seeds). Test set: seeds 1 to 29, odd, and the demo seed 73 (16 seeds). Seed 73 is never fitted.

**Decision points.** Each match's events go through `dugout.stream.state_engine` and `dugout.stream.triggers`, exactly as live: `condition_drop` (a player 0.10 below his team's outfield median and under 0.69), a goal from 55', or a substitution, one open card at a time. 167 points over the 31 seeds.

**Engine gap.** `decide(snapshot, team, trigger)` on the decision point's snapshot. The like-for-like option replaces the outfielder with the lowest condition estimate; its gap is its win probability minus no change's, with a 90% interval (20,000 runs on common random numbers).

**True gap.** The simulator is stepped to the same `(period, t_ms)`, second by second, so it has played exactly the events the snapshot covers. It is then forked (`dugout.sim.counterfactual`): 500 branches with no change and 500 with the same player off for a bench player in the same role, branch k of each option sharing a random stream. The deciding team's simulated manager is frozen in every branch. The true gap is the difference in win rate, with a paired standard error from the branch outcomes.

**Pairs.** 149 of the 167 points pair up. 14 have no bench player in the same role left and 4 have no substitution window left, so the change cannot be made in the simulator. Of the 149, 74 are fit-set trigger points, 74 test-set trigger points, and one is the story point below.

**Story point.** The demo is built around seed 73 at 64:00, when RFC-03's hidden condition first drops below the simulated manager's fade line. That moment is added by hand, with RFC-03 off for RFC-15, and reported on its own, not in the test metrics. Since lane O the triggers also raise a real card for him on seed 73, at 60:00; it is an ordinary test point.

**Calibration.** Least squares between engine gap and true gap over the 74 fit points, on a grid over `FATIGUE_SLOPE` (0 to 6), `FATIGUE_FLOOR` (0.60 to 1.00) and `BENCH_QUALITY` (0.97 to 1.06), then a finer grid around the best cell (5,000 engine runs per option while searching).

## Why this is not circular

The simulator grading itself would be circular if the engine could read the simulator's state. It cannot. `dugout.engine` never imports `dugout.sim`; it sees only the snapshot, built by the state engine from the public event stream and the lineup: clock, score, substitutions left, rolling xG rates, a condition estimate per player from his minutes on the pitch, his minutes in the last 7 days, the runs he made and his running against his own first 20 minutes, and threat by channel. The only thing read from the scenario file is the lineup (each player's id, team, role, side, whether he starts, and his recent minutes, all of which a club knows before kick-off). Hidden condition, player ratings, the simulator's possession model and its managers' plans stay on the simulator's side. The engine's win model (minute-level Poisson with a fatigue penalty on one flank) is also a different and much simpler model than the second-by-second possession simulator that produces the truth. So the check asks a fair question: from what a real system could observe, how well does the engine estimate what a change is worth?

Two caveats belong here. The condition estimate's per-minute and per-run costs are the simulator's own fatigue assumptions for an average player, and the cost of a recent minute is a stated assumption that happens to sit close to the hidden played-midweek lever (see `eval/results/condition_estimate.md`). On real data both would have to be fitted, so the input here is better than a real system's would be.

Calibration uses the truth, but only on the fit seeds, and only to set three constants. The test seeds are untouched until the numbers below.

## Results

Test set: seeds 1 to 29 odd and 73, 74 trigger points. Gaps and errors are in points of win probability. Brackets are 90% bootstrap intervals over test seeds.

| Test set (16 seeds, 74 points) | Illustrative constants | Calibrated |
| --- | --- | --- |
| Constants (slope, floor, bench) | 0.6, 0.8, 1.03 | 1.35, 0.925, 1.06 |
| Mean engine gap | +0.38 | +1.86 |
| Mean true gap | +1.98 | +1.98 |
| Mean error (engine minus true) | -1.60 [-2.17, -1.09] | -0.12 [-0.62, +0.30] |
| Mean absolute error | 1.77 | 1.47 |
| RMSE | 2.83 | 2.17 |
| Correlation | 0.71 [0.56, 0.82] | 0.72 [0.58, 0.82] |
| Sign agreement | 67.6% | 75.7% |
| True gap inside the engine's 90% interval | 8.1% | 10.8% |

The mean standard error of a true gap at 500 forks is 1.44 points, so much of the remaining RMSE of 2.17 is noise in the truth itself. Fit-set RMSE after calibration was 2.45 (74 points; reported only as a fit diagnostic).

By trigger, test set, before and after calibration:

| Trigger | Points | Mean true gap | Mean error | Correlation | Sign agreement |
| --- | --- | --- | --- | --- | --- |
| Condition drop | 16 | +4.65 | -3.51 / -0.11 | 0.70 / 0.75 | 93.8% / 100% |
| Goal after 55' | 23 | +1.22 | -0.95 / +0.30 | 0.75 / 0.74 | 73.9% / 65.2% |
| Manager substitution | 35 | +1.25 | -1.15 / -0.40 | 0.25 / 0.26 | 51.4% / 71.4% |

Seed 73, calibrated constants:

- Condition card at 60:00, RFC-03 (estimate 0.689, hidden 0.617): engine +6.3 [+6.0, +6.6], true +4.4 (standard error 3.0).
- Story point at 64:00, RFC-03 off for RFC-15 (estimate 0.683, hidden 0.599): engine +4.8 [+4.6, +5.1], true +10.0 (standard error 3.0, 500 forks; lane G measured +9.3 with 1,000). With the illustrative constants the engine gave +1.0.

What the numbers say:

- **The engine now ranks the points.** Correlation on the test set went from 0.13 (the first version of this page) to 0.72. Calibration did not do that: with the illustrative constants it is already 0.71. The input did. The condition estimate of the player the engine would take off now correlates 0.91 with his hidden condition at the test points (it was -0.01), and only 9.5% of true gaps are negative (23.5% before): the engine mostly replaces players who are actually tired.
- **Calibration fixes the level.** The illustrative constants understate the gap by 1.6 points on the new estimate, which reads lower than the old one did; the fitted ones are unbiased within noise. Sign agreement rises from 68% to 76%.
- **The ranking is carried by the condition cards.** Condition-drop points have the largest true gaps (mean +4.65) and the engine gets their sign right every time. Substitution points made by the simulated manager are close to zero on both sides, and there the engine ranks poorly (correlation 0.26).
- **Big gaps are still understated at the demo moment.** At seed 73's 64' fade the engine says +4.8 against a true +10.0. At the 60' card it says +6.3 against +4.4. The engine's one fatigue penalty per player, a straight line below a floor, does not capture how fast a tired full-back's flank degrades in the simulator; a single seed cannot say more than that.
- **The engine's 90% interval is not a statement about the truth.** It covers only the engine's own Monte Carlo noise (about half a point wide at 20,000 runs), not model error or input error, so the true gap lands inside it about 10% of the time. The card's interval should not be read as "the true gap is in here".

First version of this page, for comparison (old estimate, `condition_below_60`, 153 test points): correlation 0.14 illustrative and 0.13 calibrated, mean error +0.93 and -0.23, RMSE 3.19 and 2.44, constants 0.3, 0.725, 1.0, and the 64' story point at 0.0 calibrated.

## Limits

- **Like-for-like substitutions only.** Attacking and defensive changes have no simulator counterpart yet (the engine models them as rate multipliers), so they are not checked here. Neither is the timing of a sub (now against later).
- **Win probability only.** The engine's draw, loss and expected points per option are not compared; the CSV keeps the true expected-points gap for later.
- **Noise in the truth.** 500 forks give a standard error of about 1.4 points per point; individual pairs are noisy, which also caps the correlation any engine could reach.
- **One scenario, 31 seeds.** The fit and test seeds share squads, ratings and levers, including RFC-03's midweek start in every match. Most condition cards are his. Calibrated constants are for this scenario's simulator and should not be read as football effects.
- **An optimistic input.** The condition estimate uses the simulator's own cost assumptions and a recent-minutes cost close to the hidden lever (see "Why this is not circular"). The correlation of 0.72 is an upper bound on what the same engine would show on real tracking data.
- **Story point by hand.** The 64' point is added to show the demo moment; it is not part of the test metrics.
