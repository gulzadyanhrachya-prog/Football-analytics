import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import json
import os

st.set_page_config(page_title="Pro Football Analyst + ML Database", layout="wide")

# ==============================================================================
# 1. KONFIGURACE
# ==============================================================================
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

# Cesty k datovým souborům (pro Streamlit Cloud použij st.session_state nebo externí DB)
DATA_DIR = "data"
PREDICTIONS_FILE = f"{DATA_DIR}/predictions_history.csv"
MATCHES_FILE = f"{DATA_DIR}/historical_matches.csv"

# ==============================================================================
# 2. DATABÁZOVÉ FUNKCE
# ==============================================================================

def ensure_data_dir():
    """Vytvoří složku pro data pokud neexistuje"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_predictions_history():
    """Načte historii predikcí"""
    ensure_data_dir()
    if os.path.exists(PREDICTIONS_FILE):
        return pd.read_csv(PREDICTIONS_FILE)
    return pd.DataFrame(columns=[
        'date', 'league', 'home_team', 'away_team', 
        'prediction_type', 'confidence', 'fair_odds',
        'actual_result', 'was_correct', 'match_id'
    ])

def save_prediction(pred_data):
    """Uloží novou predikci do historie"""
    df = load_predictions_history()
    new_row = pd.DataFrame([pred_data])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(PREDICTIONS_FILE, index=False)
    return df

def load_historical_matches():
    """Načte historická data zápasů"""
    ensure_data_dir()
    if os.path.exists(MATCHES_FILE):
        return pd.read_csv(MATCHES_FILE)
    return pd.DataFrame()

def save_historical_matches(matches_df):
    """Uloží historická data"""
    ensure_data_dir()
    matches_df.to_csv(MATCHES_FILE, index=False)

# ==============================================================================
# 3. API FUNKCE (rozšířené)
# ==============================================================================

def get_headers(api_key):
    return {'X-Auth-Token': api_key}

@st.cache_data(ttl=3600)
def get_standings(api_key, code):
    url = f"https://api.football-data.org/v4/competitions/{code}/standings"
