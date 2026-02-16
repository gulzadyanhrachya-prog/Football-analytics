import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

st.set_page_config(page_title="Pro Football Analyst", layout="wide")

LEAGUES = {
    "🇬🇧 Premier League": "PL",
    "🇬🇧 Championship": "ELC",
    "🇪🇺 Liga Mistrů": "CL",
    "🇩🇪 Bundesliga": "BL1",
    "🇪🇸 La Liga": "PD",
    "🇫🇷 Ligue 1": "FL1",
    "🇮🇹 Serie A": "SA",
    "🇳🇱 Eredivisie": "DED",
    "🇵🇹 Primeira Liga": "PPL",
    "🇧🇷 Série A (Brazílie)": "BSA"
}

def get_headers(api_key):
    return {'X-Auth-Token': api_key}

@st.cache_data(ttl=3600)
def get_standings(api_key, code):
    url = f"https://api.football-data.org/v4/competitions/{code}/standings"
    try:
        r = requests.get(url, headers=get_headers(api_key))
        if r.status_code != 200:
            return None
        return r.json()['standings'][0]['table']
    except:
        return None

@st.cache_data(ttl=3600)
def get_matches(api_key, code):
    dnes = datetime.now().strftime("%Y-%m-%d")
    za_tyden = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/competitions/{code}/matches?dateFrom={dnes}&dateTo={za_tyden}"
    try:
        r = requests.get(url, headers=get_headers(api_key))
        if r.status_code != 200:
            return None
        return r.json()['matches']
    except:
        return None

def calculate_team_stats(standings):
    if not standings:
        return None, 0
    stats = {}
    total_goals = 0
    total_games = 0
    for row in standings:
        team_id = row['team']['id']
        played = row['playedGames']
        if played < 2:
            continue
        gf = row['goalsFor']
        ga = row['goalsAgainst']
        form = row.get('form', '') or ''
        total_goals += gf
        total_games += played
        stats[team_id] = {
            "name": row['team']['name'],
            "gf_avg": gf / played,
            "ga_avg": ga / played,
            "form": form
        }
    if total_games == 0:
        return None, 0
    league_avg = total_goals / total_games
    for t_id in stats:
        stats[t_id]["att_strength"] = stats[t_id]["gf_avg"] / league_avg if league_avg > 0 else 1
        stats[t_id]["def_strength"] = stats[t_id]["ga_avg"] / league_avg if league_avg > 0 else 1
    return stats, league_avg

def predict_match(home_id, away_id, stats, league_avg):
    if home_id not in stats or away_id not in stats:
        return None
    h = stats[home_id]
    a = stats[away_id]
    xg_h = h["att_strength"] * a["def_strength"] * league_avg * 1.
