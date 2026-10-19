"""Sanity check for The Dugout decision engine: minute-level Poisson Monte Carlo
with score-state effects and a fatigue multiplier on one flank.
All rates and multipliers are illustrative assumptions, not fitted values."""
import numpy as np

N = 200_000
ADDED = 6  # assumed second-half added time, minutes


def simulate(t0, home_goals, away_goals, lam_home90, lam_away90,
             lb_c0=None, lb_drain=0.0, sub_at=None, sub_c=1.0, sub_quality=1.03,
             seed=7):
    rng = np.random.default_rng(seed)  # same seed for every option = common random numbers
    h = np.full(N, home_goals)
    a = np.full(N, away_goals)
    end = 90 + ADDED
    c = lb_c0
    for minute in range(t0, end):
        lh = lam_home90 / 90.0
        la = lam_away90 / 90.0
        # score state: leader sits deeper, trailer pushes
        lead = h - a
        lh_m = np.where(lead > 0, lh * 0.9, np.where(lead < 0, lh * 1.15, lh))
        la_m = np.where(lead < 0, la * 0.9, np.where(lead > 0, la * 1.15, la))
        # fatigue of home left-back raises away threat on that flank
        if c is not None:
            if sub_at is not None and minute >= sub_at:
                mult = sub_quality  # fresh but slightly weaker bench player
            else:
                mult = 1 + 0.6 * max(0.0, 0.8 - c)
            la_m = la_m * mult
            c = max(0.3, c - lb_drain)
        h = h + rng.poisson(lh_m)
        a = a + rng.poisson(la_m)
    win = np.mean(h > a)
    draw = np.mean(h == a)
    loss = np.mean(h < a)
    xpts = 3 * win + draw
    return win, draw, loss, xpts


def show(label, r):
    w, d, l, x = r
    print(f"{label:<38} W {w:6.1%}  D {d:6.1%}  L {l:6.1%}  xPts {x:4.2f}")


print("Baseline sanity")
show("0' 0-0, equal 1.35 v 1.35", simulate(0, 0, 0, 1.35, 1.35))
show("0' 0-0, home 1.5 v away 1.2", simulate(0, 0, 0, 1.5, 1.2))
show("80' 1-0, home 1.5 v away 1.2", simulate(80, 1, 0, 1.5, 1.2))
show("85' 2-0, home 1.5 v away 1.2", simulate(85, 2, 0, 1.5, 1.2))

print("\nDemo decision at 62', Riverside (home) lead 1-0, left-back condition 0.60")
base = dict(t0=62, home_goals=1, away_goals=0, lam_home90=1.5, lam_away90=1.2,
            lb_c0=0.60, lb_drain=0.008)
no_change = simulate(**base)
sub_now = simulate(**base, sub_at=62)
sub_78 = simulate(**base, sub_at=78)
show("No change", no_change)
show("Sub left-back now (62')", sub_now)
show("Sub left-back at 78' (manager)", sub_78)
print(f"\nDelta WP sub now vs no change:  {sub_now[0]-no_change[0]:+.1%}")
print(f"Delta WP sub now vs sub at 78':  {sub_now[0]-sub_78[0]:+.1%}")
print(f"Delta xPts sub now vs at 78':    {sub_now[3]-sub_78[3]:+.2f}")

# path to victory: P(away scores >= 1) from 75' at 1-0 down, closed form
la = 1.2 / 90 * 1.15
mins = 90 + ADDED - 75
print(f"\nPath to victory: away need 1 in {mins} min at {la*90:.2f} xG/90 -> P = {1-np.exp(-la*mins):.0%}")
