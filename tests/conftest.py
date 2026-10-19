from pathlib import Path

import pytest

from dugout.sim.scenario import load_scenario

SCENARIO = Path(__file__).resolve().parents[1] / "scenarios" / "riverside-castleton.yaml"


@pytest.fixture(scope="session")
def scenario():
    return load_scenario(SCENARIO)
