import pandas as pd
from src.data_loader import normalize_teams, generate_group_matches
from src.simulation import simulate_group, simulate_tournament


def sample_teams():
    return normalize_teams(pd.DataFrame({
        "group": ["A", "A", "A", "A", "B", "B", "B", "B", "C", "C", "C", "C", "D", "D", "D", "D", "E", "E", "E", "E", "F", "F", "F", "F", "G", "G", "G", "G", "H", "H", "H", "H", "I", "I", "I", "I", "J", "J", "J", "J", "K", "K", "K", "K", "L", "L", "L", "L"],
        "team": [f"T{i}" for i in range(48)],
        "confederation": ["X"] * 48,
        "is_host": [0] * 48,
        "model_rating_seed": list(range(50, 98)),
    }))


def test_group_simulation_runs():
    teams = sample_teams()
    g = teams[teams["group"] == "A"]
    matches = generate_group_matches(teams)
    out = simulate_group(g, n_sims=20, matches=matches)
    assert len(out) == 4
    assert out["top2_prob"].between(0, 1).all()


def test_tournament_simulation_runs():
    teams = sample_teams()
    matches = generate_group_matches(teams)
    out = simulate_tournament(teams, matches, n_sims=10)
    assert len(out) == 48
    assert out["champion_prob"].between(0, 1).all()
