
from itertools import combinations
import numpy as np
import pandas as pd
from .modeling import match_probabilities


def simulate_group(group_df: pd.DataFrame, n_sims: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = group_df['team'].tolist()
    ratings = dict(zip(group_df['team'], group_df['model_rating_seed']))
    counters = {team: {'top1':0, 'top2':0, 'top3':0, 'avg_points':0.0} for team in teams}

    for _ in range(n_sims):
        table = {team: {'points':0, 'rating_noise': rng.normal(0, 0.01)} for team in teams}
        for a, b in combinations(teams, 2):
            probs = match_probabilities(ratings[a], ratings[b])
            outcome = rng.choice(['a','d','b'], p=[probs['team_a_win'], probs['draw'], probs['team_b_win']])
            if outcome == 'a':
                table[a]['points'] += 3
            elif outcome == 'b':
                table[b]['points'] += 3
            else:
                table[a]['points'] += 1
                table[b]['points'] += 1
        ranked = sorted(
            teams,
            key=lambda t: (table[t]['points'], ratings[t], table[t]['rating_noise']),
            reverse=True,
        )
        for team in teams:
            counters[team]['avg_points'] += table[team]['points'] / n_sims
        counters[ranked[0]]['top1'] += 1
        for t in ranked[:2]: counters[t]['top2'] += 1
        for t in ranked[:3]: counters[t]['top3'] += 1

    out = []
    for team in teams:
        out.append({
            'team': team,
            'group': group_df[group_df['team'] == team]['group'].iloc[0],
            'avg_points': counters[team]['avg_points'],
            'finish_1st_prob': counters[team]['top1'] / n_sims,
            'top2_prob': counters[team]['top2'] / n_sims,
            'top3_prob': counters[team]['top3'] / n_sims,
        })
    return pd.DataFrame(out).sort_values(['top2_prob','avg_points'], ascending=False)


def group_difficulty(teams_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group, gdf in teams_df.groupby('group'):
        ratings = gdf['model_rating_seed'].astype(float)
        rows.append({
            'group': group,
            'avg_rating': ratings.mean(),
            'top_two_avg_rating': ratings.sort_values(ascending=False).head(2).mean(),
            'rating_spread': ratings.max() - ratings.min(),
            'group_of_death_score': ratings.mean() * 0.55 + ratings.sort_values(ascending=False).head(3).mean() * 0.35 - ratings.std() * 0.10,
        })
    return pd.DataFrame(rows).sort_values('group_of_death_score', ascending=False)
