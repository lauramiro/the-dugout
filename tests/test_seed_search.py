import subprocess
import sys

from dugout.contracts import Event
from dugout.sim.counterfactual import NO_CHANGE, Option, play_to, true_gap
from dugout.sim.match import new_match, run_match
from dugout.sim.seed_search import (NARROW, WIDE, Match, check_story, fallback_step, honest_gap, play_seed,
                                    rank_by_gap, search)

_seq = iter(range(1, 10_000))


def goal(team: str, minute: int, channel: str = "centre", second: int = 0) -> Event:
    return Event(match_id="rfc-cas-0001", seq=next(_seq), t_ms=(minute * 60 + second) * 1000,
                 period=1 if minute < 45 else 2, type="goal", team=team, player_id=f"{team}-09",
                 channel=channel)


def sub_off(minute: int, player: str = "RFC-03", team: str = "RFC") -> Event:
    return Event(match_id="rfc-cas-0001", seq=next(_seq), t_ms=minute * 60_000, period=2, type="sub",
                 team=team, player_id=player, player_in_id="RFC-15", outcome="like_for_like")


def story(*, rfc_goal: int = 20, fade: int = 62, eq_min: int = 75, eq_channel: str = "right",
          sub_min: int = 78) -> list[Event]:
    return [goal("RFC", rfc_goal), goal("CAS", eq_min, eq_channel), sub_off(sub_min)]


def test_the_full_story_matches():
    m = check_story(story(), fade_minute=62, windows=NARROW)
    assert m is not None
    assert (m.fade, m.equaliser, m.sub) == (62, 75, 78)


def test_castleton_equaliser_down_riversides_left_is_castletons_right_channel():
    assert check_story(story(eq_channel="right"), 62, NARROW) is not None
    assert check_story(story(eq_channel="left"), 62, NARROW) is None
    assert check_story(story(eq_channel="centre"), 62, NARROW) is None


def test_riverside_must_lead_at_60():
    level = [goal("CAS", 30, "right"), goal("RFC", 40), goal("CAS", 75, "right"), sub_off(78)]
    assert check_story(level, 62, NARROW) is None
    late_lead = [goal("RFC", 61), goal("CAS", 75, "right"), sub_off(78)]
    assert check_story(late_lead, 62, NARROW) is None


def test_the_goal_must_level_the_score():
    two_up = [goal("RFC", 10), goal("RFC", 50), goal("CAS", 75, "right"), sub_off(78)]
    assert check_story(two_up, 62, NARROW) is None


def test_fade_window():
    assert check_story(story(), 60, NARROW) is not None
    assert check_story(story(), 64, NARROW) is not None
    assert check_story(story(), 59, NARROW) is None
    assert check_story(story(), 65, NARROW) is None
    assert check_story(story(), None, NARROW) is None


def test_equaliser_window_narrow_then_wide():
    early, late = story(eq_min=67, sub_min=78), story(eq_min=83, sub_min=84)
    assert check_story(early, 62, NARROW) is None and check_story(early, 62, WIDE) is not None
    assert check_story(late, 62, NARROW) is None and check_story(late, 62, WIDE) is not None
    assert check_story(story(eq_min=64), 62, WIDE) is None
    assert check_story(story(eq_min=86, sub_min=88), 62, WIDE) is None


def test_the_window_is_whole_minutes_inclusive():
    assert check_story([goal("RFC", 20), goal("CAS", 80, "right", second=59), sub_off(80)], 62, NARROW)
    assert not check_story([goal("RFC", 20), goal("CAS", 81, "right"), sub_off(80)], 62, NARROW)


def test_sub_window_narrow_is_about_78_wide_is_any_time_after_the_fade():
    assert check_story(story(sub_min=76), 62, NARROW) is not None
    assert check_story(story(sub_min=80), 62, NARROW) is not None
    assert check_story(story(sub_min=75), 62, NARROW) is None
    assert check_story(story(sub_min=85), 62, NARROW) is None
    assert check_story(story(sub_min=70), 62, WIDE) is not None
    assert check_story(story(sub_min=90), 62, WIDE) is not None
    assert check_story(story(sub_min=61), 62, WIDE) is None


def test_the_sub_must_be_riversides_left_back_going_off():
    assert check_story([goal("RFC", 20), goal("CAS", 75, "right"), sub_off(78, "RFC-11")], 62, NARROW) is None
    assert check_story([goal("RFC", 20), goal("CAS", 75, "right"), sub_off(78, "CAS-03", "CAS")], 62, NARROW) is None
    assert check_story([goal("RFC", 20), goal("CAS", 75, "right")], 62, NARROW) is None


def test_the_equaliser_is_the_goal_that_levels_not_an_earlier_one():
    events = [goal("RFC", 10), goal("RFC", 50), goal("CAS", 66, "centre"), goal("CAS", 76, "right"),
              sub_off(78)]
    m = check_story(events, 62, NARROW)  # 2-1 at 66 down the middle, level at 76 down the flank
    assert m is not None and m.equaliser == 76
    events = [goal("RFC", 10), goal("RFC", 50), goal("CAS", 66, "right"), goal("CAS", 76, "centre"),
              sub_off(78)]
    assert check_story(events, 62, NARROW) is None  # the levelling goal came down the middle


# --- running the search ------------------------------------------------------


def test_play_seed_matches_run_match_and_reads_the_hidden_fade(scenario):
    events, fade = play_seed(scenario, 2)  # RFC-03 is at about 0.6 around 62' in this seed
    _, expected = run_match(scenario, 2)
    assert [e.to_dict() for e in events] == [e.to_dict() for e in expected]
    assert fade is not None and 55 <= fade <= 70


def test_search_returns_only_seeds_whose_events_pass_the_checks(scenario):
    found = search(scenario, range(1, 41), WIDE, workers=1)
    for seed, m in found:
        events, fade = play_seed(scenario, seed)
        assert check_story(events, fade, WIDE) == m


def test_search_gives_the_same_result_in_parallel(scenario):
    assert search(scenario, range(1, 41), WIDE, workers=2) == search(scenario, range(1, 41), WIDE, workers=1)


def test_fallback_step_is_the_first_step_that_finds_the_seed():
    m = Match(fade=62, equaliser=75, sub=78)
    assert fallback_step(100, m) == 1
    assert fallback_step(2000, m) == 1
    assert fallback_step(2001, m) == 3
    wide_only = Match(fade=62, equaliser=67, sub=70)
    assert fallback_step(100, wide_only) == 2
    assert fallback_step(5000, wide_only) == 3


def test_cli_search_lists_seeds_and_steps():
    out = subprocess.run([sys.executable, "-m", "dugout.sim", "search", "--seeds", "30", "--wide"],
                         check=True, capture_output=True, text=True).stdout
    assert "seeds 1-30" in out


# --- ranking by honest gap ---------------------------------------------------


def test_honest_gap_is_no_change_against_the_like_for_like_bench_player_at_the_fade(scenario):
    s, _ = new_match(scenario, 17)
    play_to(s, 63)
    off = Option("sub", "RFC-03 off, RFC-15 on", subs=(("RFC-03", "RFC-15"),))
    expected = true_gap(s, "RFC", [NO_CHANGE, off], n=20)[1]
    got = honest_gap(scenario, 17, 63, n=20)
    assert got.on == "RFC-15"
    assert got.delta_win == expected.delta_win and got.delta_xpts == expected.delta_xpts


def test_rank_by_gap_puts_the_largest_gap_first(scenario):
    found = [(17, Match(63, 77, 80)), (73, Match(64, 72, 79))]
    ranked = rank_by_gap(scenario, found, n=20, workers=1)
    assert sorted(r.seed for r in ranked) == [17, 73]
    assert ranked[0].delta_win >= ranked[1].delta_win
