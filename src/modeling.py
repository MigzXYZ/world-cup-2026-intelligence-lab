
def rating_to_elo(rating: float) -> float:
    """Convert a 0-100 public-facing model rating into an Elo-like scale."""
    return 1200 + float(rating) * 10


def match_probabilities(rating_a: float, rating_b: float) -> dict:
    """Return simple W/D/L probabilities using an Elo-style expected score.

    This is intentionally transparent for the MVP. Replace or calibrate this
    function later with real historical outcomes, team Elo, xG, squad value,
    rest days, travel distance, and injuries.
    """
    elo_a = rating_to_elo(rating_a)
    elo_b = rating_to_elo(rating_b)
    expected_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    rating_gap = abs(float(rating_a) - float(rating_b))
    draw = max(0.18, min(0.30, 0.29 - rating_gap * 0.006))
    p_a = expected_a * (1 - draw)
    p_b = (1 - expected_a) * (1 - draw)
    total = p_a + p_b + draw
    return {
        'team_a_win': p_a / total,
        'draw': draw / total,
        'team_b_win': p_b / total,
    }


def upset_probability(favorite_rating: float, underdog_rating: float) -> float:
    probs = match_probabilities(underdog_rating, favorite_rating)
    return probs['team_a_win']
