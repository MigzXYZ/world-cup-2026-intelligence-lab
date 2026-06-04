from src.modeling import match_probabilities, prepare_team_strength, match_prediction
import pandas as pd


def test_probabilities_sum_to_one():
    probs = match_probabilities(90, 80)
    assert abs(sum(probs.values()) - 1) < 1e-9
    assert all(0 <= v <= 1 for v in probs.values())


def test_prediction_package_runs():
    teams = pd.DataFrame({
        "group": ["A", "A"],
        "team": ["A", "B"],
        "confederation": ["X", "Y"],
        "is_host": [1, 0],
        "model_rating_seed": [80, 70],
    })
    strength = prepare_team_strength(teams)
    pred = match_prediction(strength.iloc[0], strength.iloc[1])
    assert "final" in pred
    assert abs(sum(pred["final"].values()) - 1) < 1e-9
    assert pred["xg_a"] > 0 and pred["xg_b"] > 0
