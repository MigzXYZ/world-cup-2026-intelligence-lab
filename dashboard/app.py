
from pathlib import Path
import sys
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.modeling import match_probabilities
from src.simulation import simulate_group, group_difficulty

st.set_page_config(
    page_title='World Cup 2026 Intelligence Lab',
    page_icon='⚽',
    layout='wide',
    initial_sidebar_state='expanded',
)

@st.cache_data
def load_data():
    teams = pd.read_csv(ROOT / 'data' / 'teams_seed.csv')
    matches = pd.read_csv(ROOT / 'data' / 'matches_template.csv')
    cities = pd.read_csv(ROOT / 'data' / 'host_cities.csv')
    return teams, matches, cities

teams, matches, cities = load_data()

st.markdown('''
<style>
.big-title {font-size: 2.6rem; font-weight: 800; line-height: 1.05; margin-bottom: 0.2rem;}
.subtitle {font-size: 1.05rem; color: #6b7280; margin-bottom: 1rem;}
.note-box {background: #fff8e6; padding: .75rem 1rem; border-radius: .8rem; border: 1px solid #ffe1a6;}
</style>
''', unsafe_allow_html=True)

st.sidebar.title('⚽ WC26 Intelligence Lab')
page = st.sidebar.radio('Navigate', ['Home', 'Groups Explorer', 'Match Predictor', 'Simulation Lab', 'Host Cities Map', 'Fan Zone', 'Methodology'])
st.sidebar.markdown('---')
st.sidebar.caption('MVP v0.1. Ratings are seed values for product/demo structure. Replace with official rankings/Elo before serious publication.')

def pct(x):
    return f'{x*100:.1f}%'

if page == 'Home':
    st.markdown('<div class="big-title">World Cup 2026 Intelligence Lab</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Predictive analytics, group difficulty, travel context, and public fan interaction for the biggest World Cup format ever.</div>', unsafe_allow_html=True)
    st.markdown('<div class="note-box">This first public MVP is designed to be transparent and easy to improve. It uses seed model ratings now, then you can plug in FIFA rankings, Elo ratings, live results, injuries, travel distance, and crowd signals.</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Teams', len(teams))
    c2.metric('Groups', teams['group'].nunique())
    c3.metric('Group matches template', len(matches))
    c4.metric('Host cities', len(cities))

    gd = group_difficulty(teams)
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader('Group of Death Index')
        fig = px.bar(gd, x='group', y='group_of_death_score', hover_data=['avg_rating','top_two_avg_rating','rating_spread'], text_auto='.1f')
        fig.update_layout(yaxis_title='Difficulty score', xaxis_title='Group', height=430)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader('Top seed ratings')
        top = teams.sort_values('model_rating_seed', ascending=False).head(12)
        fig2 = px.bar(top, x='model_rating_seed', y='team', orientation='h', color='group', text='model_rating_seed')
        fig2.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title='Seed rating', yaxis_title='', height=430)
        st.plotly_chart(fig2, use_container_width=True)

elif page == 'Groups Explorer':
    st.title('Groups Explorer')
    group = st.selectbox('Choose group', sorted(teams['group'].unique()))
    gdf = teams[teams['group'] == group].sort_values('model_rating_seed', ascending=False)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(gdf[['group','team','confederation','is_host','model_rating_seed']], hide_index=True, use_container_width=True)
    with c2:
        fig = px.bar(gdf, x='team', y='model_rating_seed', color='confederation', text='model_rating_seed')
        fig.update_layout(xaxis_title='', yaxis_title='Seed rating', height=400)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader('Group matches template')
    st.dataframe(matches[matches['group'] == group][['match_id','team_a','team_b','status']], hide_index=True, use_container_width=True)

elif page == 'Match Predictor':
    st.title('Match Predictor')
    st.caption('Transparent MVP predictor based on seed ratings. Later we calibrate it using historical international results and Elo.')
    col1, col2 = st.columns(2)
    team_a = col1.selectbox('Team A', teams['team'].tolist(), index=0)
    team_b = col2.selectbox('Team B', teams['team'].tolist(), index=1)
    if team_a == team_b:
        st.warning('Choose two different teams.')
    else:
        ra = float(teams.loc[teams['team'] == team_a, 'model_rating_seed'].iloc[0])
        rb = float(teams.loc[teams['team'] == team_b, 'model_rating_seed'].iloc[0])
        probs = match_probabilities(ra, rb)
        c1, c2, c3 = st.columns(3)
        c1.metric(f'{team_a} win', pct(probs['team_a_win']))
        c2.metric('Draw', pct(probs['draw']))
        c3.metric(f'{team_b} win', pct(probs['team_b_win']))
        chart_df = pd.DataFrame({
            'Outcome': [f'{team_a} win', 'Draw', f'{team_b} win'],
            'Probability': [probs['team_a_win'], probs['draw'], probs['team_b_win']],
        })
        fig = px.bar(chart_df, x='Outcome', y='Probability', text=chart_df['Probability'].map(lambda x: f'{x*100:.1f}%'))
        fig.update_layout(yaxis_tickformat='.0%', yaxis_title='Probability', height=430)
        st.plotly_chart(fig, use_container_width=True)

elif page == 'Simulation Lab':
    st.title('Simulation Lab')
    group = st.selectbox('Choose group to simulate', sorted(teams['group'].unique()))
    n = st.slider('Number of simulations', 1000, 20000, 5000, step=1000)
    seed = st.number_input('Random seed', value=42, step=1)
    result = simulate_group(teams[teams['group'] == group], n_sims=n, seed=int(seed))
    st.subheader(f'Group {group} qualification simulation')
    st.dataframe(result.assign(
        finish_1st_prob=lambda d: d['finish_1st_prob'].map(pct),
        top2_prob=lambda d: d['top2_prob'].map(pct),
        top3_prob=lambda d: d['top3_prob'].map(pct),
        avg_points=lambda d: d['avg_points'].map(lambda x: f'{x:.2f}')
    ), hide_index=True, use_container_width=True)
    plot_df = result.melt(id_vars=['team'], value_vars=['finish_1st_prob','top2_prob','top3_prob'], var_name='Metric', value_name='Probability')
    fig = px.bar(plot_df, x='team', y='Probability', color='Metric', barmode='group')
    fig.update_layout(yaxis_tickformat='.0%', xaxis_title='', height=460)
    st.plotly_chart(fig, use_container_width=True)

elif page == 'Host Cities Map':
    st.title('Host Cities Map')
    st.caption('Use this layer later to calculate travel burden, timezone shifts, and schedule difficulty per team.')
    st.map(cities.rename(columns={'lat':'latitude','lon':'longitude'}), latitude='latitude', longitude='longitude', size=80)
    st.dataframe(cities, hide_index=True, use_container_width=True)

elif page == 'Fan Zone':
    st.title('Fan Zone')
    st.caption('Public interaction layer. For real public deployment, connect this form to Supabase or Google Sheets.')
    with st.form('fan_vote'):
        favorite = st.selectbox('Who do you think will win the World Cup?', teams['team'].tolist())
        upset = st.selectbox('Pick one surprise team', teams['team'].tolist(), index=10)
        confidence = st.slider('Your confidence', 1, 10, 6)
        submitted = st.form_submit_button('Submit vote')
    if 'votes' not in st.session_state:
        st.session_state['votes'] = []
    if submitted:
        st.session_state['votes'].append({'favorite': favorite, 'upset': upset, 'confidence': confidence})
        st.success('Vote recorded for this session. Connect Supabase to make votes persistent across all visitors.')
    if st.session_state['votes']:
        votes = pd.DataFrame(st.session_state['votes'])
        st.subheader('Session votes')
        st.dataframe(votes, hide_index=True, use_container_width=True)
        st.plotly_chart(px.histogram(votes, x='favorite', title='Session champion picks'), use_container_width=True)
    else:
        st.info('No votes in this session yet.')

elif page == 'Methodology':
    st.title('Methodology')
    st.markdown('''
    ### Current MVP methodology
    - **Teams and groups:** stored in `data/teams_seed.csv`.
    - **Ratings:** transparent seed rating used only to make the website functional.
    - **Match probabilities:** Elo-style expected score + draw adjustment.
    - **Simulation:** group-stage Monte Carlo simulation using W/D/L probabilities.
    - **Fan interaction:** session-based voting now; recommended production layer is Supabase.

    ### Next model upgrades
    1. Replace seed ratings with FIFA rankings and/or World Football Elo.
    2. Add historical results and recent-form features.
    3. Add travel burden from host-city route calculations.
    4. Add live results and table updates.
    5. Add persistent public voting through Supabase.
    6. Add Arabic public interface after the MVP logic is stable.
    ''')
