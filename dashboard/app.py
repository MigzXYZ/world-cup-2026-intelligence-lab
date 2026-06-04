from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.data_loader import load_all_data
from src.fan_votes import aggregate_votes, has_supabase, load_votes, submit_vote
from src.modeling import MatchModelConfig, match_prediction, prepare_team_strength
from src.simulation import group_difficulty, projected_group_tables, simulate_group, simulate_tournament
from src.travel import schedule_difficulty, travel_table
from src.visualizations import probability_bar

st.set_page_config(
    page_title="World Cup 2026 Intelligence Lab",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def get_data():
    bundle = load_all_data()
    teams = prepare_team_strength(bundle.teams)
    return teams, bundle.matches, bundle.cities, bundle.stadiums


@st.cache_data(show_spinner=False)
def cached_group_sim(group_df: pd.DataFrame, matches: pd.DataFrame, n: int, seed: int):
    return simulate_group(group_df, n_sims=n, seed=seed, matches=matches)


@st.cache_data(show_spinner=True)
def cached_tournament_sim(teams: pd.DataFrame, matches: pd.DataFrame, n: int, seed: int):
    return simulate_tournament(teams, matches, n_sims=n, seed=seed)


def pct(x: float) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return "-"


def small_note(text: str):
    st.markdown(f"<div class='note-box'>{text}</div>", unsafe_allow_html=True)


st.markdown(
    """
<style>
.big-title {font-size: 2.55rem; font-weight: 850; line-height: 1.05; margin-bottom: .15rem;}
.subtitle {font-size: 1.05rem; color: #6b7280; margin-bottom: 1.0rem;}
.note-box {background: #fff8e6; padding: .85rem 1rem; border-radius: .85rem; border: 1px solid #ffe1a6; margin: .5rem 0 1rem 0;}
.ok-box {background: #ecfdf5; padding: .85rem 1rem; border-radius: .85rem; border: 1px solid #a7f3d0; margin: .5rem 0 1rem 0;}
.warn-box {background: #fef2f2; padding: .85rem 1rem; border-radius: .85rem; border: 1px solid #fecaca; margin: .5rem 0 1rem 0;}
.metric-caption {color: #6b7280; font-size: .85rem;}
</style>
""",
    unsafe_allow_html=True,
)

teams, matches, cities, stadiums = get_data()

st.sidebar.title("⚽ WC26 Lab")
page = st.sidebar.radio(
    "Navigate",
    [
        "Home",
        "Teams Explorer",
        "Groups Explorer",
        "Match Predictor",
        "Group Simulation",
        "Tournament Simulator",
        "Travel Intelligence",
        "Fan Zone",
        "Results & Tables",
        "Data Health",
        "Methodology",
    ],
)
st.sidebar.markdown("---")
st.sidebar.caption("v1.0 analytical engine. Uses seed ratings unless official Elo/FIFA/recent-form fields are added.")
if has_supabase():
    st.sidebar.success("Supabase voting: connected")
else:
    st.sidebar.info("Supabase voting: local/session fallback")

# Soft data warnings.
warnings = teams.attrs.get("group_size_warnings", {})
unknown_teams = matches.attrs.get("unknown_team_warnings", [])
if warnings:
    st.sidebar.warning(f"Group size warning: {warnings}")
if unknown_teams:
    st.sidebar.warning(f"Unknown match teams: {unknown_teams[:5]}")

if page == "Home":
    st.markdown('<div class="big-title">World Cup 2026 Intelligence Lab</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">A public data product for match prediction, group difficulty, tournament simulation, travel context, and fan intelligence.</div>',
        unsafe_allow_html=True,
    )
    small_note(
        "This site is an explainable probabilistic model. It estimates probabilities, not certainties. The engine is production-ready structurally and becomes stronger as official ratings, fixtures, results, and travel data are added."
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Teams", len(teams))
    c2.metric("Groups", teams["group"].nunique())
    c3.metric("Matches loaded", len(matches))
    c4.metric("Host cities", len(cities))
    c5.metric("Avg model rating", f"{teams['model_rating_final'].mean():.1f}")

    health_path = ROOT / "data" / "processed" / "data_health_report.csv"
    if health_path.exists():
        health = pd.read_csv(health_path)
        errors = int((health["severity"] == "error").sum()) if "severity" in health.columns else 0
        warnings_count = int((health["severity"] == "warning").sum()) if "severity" in health.columns else 0
        h1, h2, h3 = st.columns(3)
        h1.metric("Data errors", errors)
        h2.metric("Data warnings", warnings_count)
        h3.metric("Data layer", "Processed" if (ROOT / "data" / "processed" / "teams_current.csv").exists() else "Fallback")
        if errors:
            st.error("Data validation errors exist. Open Data Health before publishing strong claims.")
        elif warnings_count:
            st.warning("Data validation warnings exist. The app can run, but check Data Health before public launch.")
        else:
            st.success("Data health checks passed.")
    else:
        st.warning("No processed data health report found. Run: python -m src.pipelines.update_all")

    left, right = st.columns([1.08, 1])
    with left:
        st.subheader("Group of Death Index")
        gd = group_difficulty(teams)
        fig = px.bar(
            gd,
            x="group",
            y="group_of_death_score",
            hover_data=["avg_rating", "top_three_avg_rating", "rating_spread"],
            text_auto=".1f",
        )
        fig.update_layout(yaxis_title="Difficulty score", xaxis_title="Group", height=430)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Top model-rated teams")
        top = teams.sort_values("model_rating_final", ascending=False).head(12)
        fig2 = px.bar(top, x="model_rating_final", y="team", orientation="h", color="group", text="model_rating_final")
        fig2.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Model rating", yaxis_title="", height=430)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Quick fan pulse")
    votes = load_votes()
    agg = aggregate_votes(votes)
    v1, v2, v3 = st.columns(3)
    v1.metric("Public votes", agg["count"])
    v2.metric("Average confidence", f"{agg['avg_confidence']:.1f}/10" if agg["count"] else "-")
    if not agg["champions"].empty:
        v3.metric("Fan favorite", agg["champions"].iloc[0]["team"])
    else:
        v3.metric("Fan favorite", "No votes yet")

elif page == "Teams Explorer":
    st.title("Teams Explorer")
    col1, col2, col3 = st.columns(3)
    group_filter = col1.multiselect("Group", sorted(teams["group"].unique()), default=[])
    conf_filter = col2.multiselect("Confederation", sorted(teams["confederation"].dropna().unique()), default=[])
    host_only = col3.checkbox("Host teams only")

    df = teams.copy()
    if group_filter:
        df = df[df["group"].isin(group_filter)]
    if conf_filter:
        df = df[df["confederation"].isin(conf_filter)]
    if host_only:
        df = df[df["is_host"] == 1]

    show_cols = [
        "group", "team", "confederation", "is_host", "model_rating_final", "model_rating_seed",
        "fifa_rank", "elo_rating", "recent_form", "attack_strength", "defense_strength",
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(df[show_cols].sort_values("model_rating_final", ascending=False), hide_index=True, use_container_width=True)
    fig = px.scatter(
        df,
        x="attack_strength",
        y="defense_strength",
        size="model_rating_final",
        color="group",
        hover_name="team",
        title="Attack vs Defense Strength Profile",
    )
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

elif page == "Groups Explorer":
    st.title("Groups Explorer")
    group = st.selectbox("Choose group", sorted(teams["group"].unique()))
    gdf = teams[teams["group"] == group].sort_values("model_rating_final", ascending=False)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader(f"Group {group} teams")
        st.dataframe(gdf[["group", "team", "confederation", "is_host", "model_rating_final"]], hide_index=True, use_container_width=True)
    with c2:
        fig = px.bar(gdf, x="team", y="model_rating_final", color="confederation", text_auto=".1f")
        fig.update_layout(xaxis_title="", yaxis_title="Model rating", height=400)
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Group matches")
    gm = matches[matches.get("group") == group]
    st.dataframe(gm[[c for c in ["match_id", "date", "team_a", "team_b", "city", "venue", "status", "score_a", "score_b"] if c in gm.columns]], hide_index=True, use_container_width=True)

elif page == "Match Predictor":
    st.title("Match Predictor")
    st.caption("Combines an Elo-style rating model, Poisson scoreline model, recent-form layer, and context layer.")
    col1, col2 = st.columns(2)
    team_names = teams["team"].tolist()
    team_a = col1.selectbox("Team A", team_names, index=0)
    team_b = col2.selectbox("Team B", team_names, index=1)
    if team_a == team_b:
        st.warning("Choose two different teams.")
    else:
        row_a = teams.loc[teams["team"] == team_a].iloc[0]
        row_b = teams.loc[teams["team"] == team_b].iloc[0]
        pred = match_prediction(row_a, row_b, MatchModelConfig())
        probs = pred["final"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(f"{team_a} win", pct(probs["team_a_win"]))
        c2.metric("Draw", pct(probs["draw"]))
        c3.metric(f"{team_b} win", pct(probs["team_b_win"]))
        c4.metric(f"{team_a} xG", f"{pred['xg_a']:.2f}")
        c5.metric(f"{team_b} xG", f"{pred['xg_b']:.2f}")
        st.plotly_chart(
            probability_bar([f"{team_a} win", "Draw", f"{team_b} win"], [probs["team_a_win"], probs["draw"], probs["team_b_win"]], "Final blended probability"),
            use_container_width=True,
        )
        left, right = st.columns([1, 1])
        with left:
            st.subheader("Top scorelines")
            score_df = pd.DataFrame(pred["top_scorelines"])
            score_df["scoreline"] = score_df["score_a"].astype(str) + " - " + score_df["score_b"].astype(str)
            score_df["probability"] = score_df["probability"].map(pct)
            st.dataframe(score_df[["scoreline", "probability"]], hide_index=True, use_container_width=True)
        with right:
            st.subheader("Model layers")
            layer_df = pd.DataFrame([
                {"Layer": "Rating/Elo", **pred["rating_model"]},
                {"Layer": "Poisson Goals", **pred["poisson_model"]},
                {"Layer": "Final Ensemble", **pred["final"]},
            ])
            for col in ["team_a_win", "draw", "team_b_win"]:
                layer_df[col] = layer_df[col].map(pct)
            st.dataframe(layer_df, hide_index=True, use_container_width=True)
        with st.expander("Why this prediction?"):
            exp = pred["explanation"]
            st.write(f"Rating gap: **{exp['rating_gap']:.2f}** points toward {team_a if exp['rating_gap'] > 0 else team_b}.")
            st.write(f"{team_a} attack/defense: **{exp['team_a_attack_strength']:.2f} / {exp['team_a_defense_strength']:.2f}**")
            st.write(f"{team_b} attack/defense: **{exp['team_b_attack_strength']:.2f} / {exp['team_b_defense_strength']:.2f}**")

elif page == "Group Simulation":
    st.title("Group Simulation")
    group = st.selectbox("Choose group", sorted(teams["group"].unique()))
    n = st.slider("Number of simulations", 1000, 50000, 5000, step=1000)
    seed = st.number_input("Random seed", value=42, step=1)
    gdf = teams[teams["group"] == group]
    result = cached_group_sim(gdf, matches, int(n), int(seed))
    st.subheader(f"Group {group} probability table")
    display = result.copy()
    for col in ["finish_1st_prob", "top2_prob", "top3_prob"]:
        display[col] = display[col].map(pct)
    display["avg_points"] = display["avg_points"].map(lambda x: f"{x:.2f}")
    st.dataframe(display, hide_index=True, use_container_width=True)
    plot_df = result.melt(id_vars=["team"], value_vars=["finish_1st_prob", "top2_prob", "top3_prob"], var_name="Metric", value_name="Probability")
    fig = px.bar(plot_df, x="team", y="Probability", color="Metric", barmode="group")
    fig.update_layout(yaxis_tickformat=".0%", height=460)
    st.plotly_chart(fig, use_container_width=True)

elif page == "Tournament Simulator":
    st.title("Tournament Simulator")
    small_note("This page simulates all groups, selects top two plus best third-place teams, then runs a model-seeded knockout bracket. Add an official bracket mapping file later if you want exact FIFA route replication.")
    n = st.slider("Tournament simulations", 500, 20000, 2000, step=500)
    seed = st.number_input("Random seed", value=123, step=1)
    if st.button("Run tournament simulation", type="primary"):
        sim = cached_tournament_sim(teams, matches, int(n), int(seed))
        st.session_state["last_tournament_sim"] = sim
    sim = st.session_state.get("last_tournament_sim")
    if sim is None:
        st.info("Run the simulation to calculate tournament probabilities.")
    else:
        top = sim.head(20).copy()
        for col in [c for c in top.columns if c.endswith("_prob")]:
            top[col] = top[col].map(pct)
        st.dataframe(top, hide_index=True, use_container_width=True)
        fig = px.bar(sim.head(15), x="champion_prob", y="team", orientation="h", color="group", text=sim.head(15)["champion_prob"].map(pct), title="Champion probability")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_tickformat=".0%", height=520)
        st.plotly_chart(fig, use_container_width=True)

elif page == "Travel Intelligence":
    st.title("Travel Intelligence")
    small_note("Travel scores become meaningful when matches include city/date fields. With incomplete fixtures, this page shows the working engine and safely marks missing data.")
    if cities.empty:
        st.warning("No city data found.")
    else:
        st.map(cities.rename(columns={"lat": "latitude", "lon": "longitude"}), latitude="latitude", longitude="longitude", size=80)
    travel = travel_table(teams, matches, cities) if not cities.empty else pd.DataFrame()
    if not travel.empty:
        st.subheader("Travel Burden Score")
        st.dataframe(travel, hide_index=True, use_container_width=True)
        fig = px.bar(travel.head(20), x="travel_burden_score", y="team", orientation="h", text="travel_burden_score")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Schedule Difficulty Score")
        sched = schedule_difficulty(teams, matches, cities)
        st.dataframe(sched, hide_index=True, use_container_width=True)

elif page == "Fan Zone":
    st.title("Fan Zone")
    st.caption("Persistent public voting works when Supabase secrets are configured. Otherwise, votes are saved locally for this browser session.")
    with st.form("fan_vote"):
        display_name = st.text_input("Display name optional", max_chars=40)
        user_country = st.text_input("Country optional", max_chars=40)
        favorite = st.selectbox("Who will win the World Cup?", teams["team"].tolist())
        surprise = st.selectbox("Pick one surprise team", teams["team"].tolist(), index=min(10, len(teams)-1))
        group_death = st.selectbox("Which group looks hardest?", sorted(teams["group"].unique()))
        confidence = st.slider("Your confidence", 1, 10, 6)
        submitted = st.form_submit_button("Submit vote", type="primary")
    if submitted:
        ok, msg = submit_vote({
            "display_name": display_name,
            "user_country": user_country,
            "favorite_team": favorite,
            "surprise_team": surprise,
            "group_of_death": group_death,
            "confidence": confidence,
        })
        st.success(msg) if ok else st.warning(msg)
    votes = load_votes()
    agg = aggregate_votes(votes)
    c1, c2 = st.columns(2)
    c1.metric("Total votes", agg["count"])
    c2.metric("Average confidence", f"{agg['avg_confidence']:.1f}/10" if agg["count"] else "-")
    if agg["count"]:
        left, right = st.columns(2)
        with left:
            st.subheader("Fan champion picks")
            st.plotly_chart(px.bar(agg["champions"].head(15), x="votes", y="team", orientation="h"), use_container_width=True)
        with right:
            st.subheader("Fan surprise picks")
            st.plotly_chart(px.bar(agg["surprises"].head(15), x="votes", y="team", orientation="h"), use_container_width=True)
        with st.expander("Recent raw votes"):
            st.dataframe(votes.tail(50), hide_index=True, use_container_width=True)

elif page == "Results & Tables":
    st.title("Results & Tables")
    st.caption("Uses actual finished scores when score/status fields are available, and model projections for scheduled matches.")
    st.subheader("Matches")
    match_cols = [c for c in ["match_id", "stage", "group", "date", "team_a", "team_b", "city", "status", "score_a", "score_b"] if c in matches.columns]
    st.dataframe(matches[match_cols], hide_index=True, use_container_width=True)
    st.subheader("Projected group tables")
    tables = projected_group_tables(teams, matches)
    st.dataframe(tables[["group", "rank", "team", "played", "wins", "draws", "losses", "gf", "ga", "gd", "points"]], hide_index=True, use_container_width=True)

elif page == "Data Health":
    st.title("Data Health & Source Reliability")
    small_note("This page protects the project from fake or unverified data. Hard facts come from processed files and source logs. Missing values are shown as missing, not invented.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Teams", len(teams))
    c2.metric("Groups", teams["group"].nunique())
    c3.metric("Matches", len(matches))
    c4.metric("Finished matches", int((matches["status"].astype(str).str.lower() == "finished").sum()) if "status" in matches.columns else 0)

    health_path = ROOT / "data" / "processed" / "data_health_report.csv"
    source_log_path = ROOT / "data" / "source_logs" / "latest_source_log.csv"

    st.subheader("Validation report")
    if health_path.exists():
        health = pd.read_csv(health_path)
        st.dataframe(health, hide_index=True, use_container_width=True)
    else:
        st.warning("No data health report found. Run `python -m src.pipelines.update_all` locally or through GitHub Actions.")

    st.subheader("Source log")
    if source_log_path.exists():
        st.dataframe(pd.read_csv(source_log_path), hide_index=True, use_container_width=True)
    else:
        st.info("No source log found yet. The current app is likely using fallback local files.")

    st.subheader("Publication mode")
    has_processed = (ROOT / "data" / "processed" / "teams_current.csv").exists() and (ROOT / "data" / "processed" / "matches_current.csv").exists()
    if has_processed:
        st.success("Processed data layer is active.")
    else:
        st.warning("Fallback mode is active. Do not publish formal prediction claims until processed official/rating files are added.")

    with st.expander("Columns currently available"):
        st.write("Teams columns:", list(teams.columns))
        st.write("Matches columns:", list(matches.columns))

elif page == "Methodology":
    st.title("Methodology")
    st.markdown(
        """
## What the model does
This project estimates football outcomes using transparent probabilities. It combines:

1. **Team strength preparation** from seed ratings, Elo, FIFA ranking, recent form, host status, attack, and defense fields when available.
2. **Rating/Elo probability model** for win/draw/loss.
3. **Poisson goal model** to estimate expected goals and likely scorelines.
4. **Ensemble blend** to produce final match probabilities.
5. **Monte Carlo simulation** for group and tournament outcomes.
6. **Travel intelligence** from host-city coordinates and match locations.
7. **Fan intelligence** from public voting through Supabase or local fallback.

## Important limitation
No football prediction model is guaranteed. The current repository ships with seed ratings so the product works immediately. For formal publication, add official rankings/Elo and historical results, then backtest the model before making strong accuracy claims.

## How to make it stronger
- Add `data/teams_official.csv` with FIFA rank, Elo, recent form, attack, and defense columns.
- Add `data/matches_official.csv` with dates, cities, venues, scores, and status.
- Configure Supabase secrets to make fan votes persistent.
- Add historical international results and run backtesting.
- Add official knockout bracket mapping when available in structured form.
"""
    )
    st.subheader("Available columns")
    st.write("Teams:", list(teams.columns))
    st.write("Matches:", list(matches.columns))
