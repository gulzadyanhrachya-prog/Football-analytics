import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

st.set_page_config(page_title="Pro Football Analyst v48", layout="wide")

# ==============================================================================\n# 1. KONFIGURACE LIG (Football-Data.org)\n# ==============================================================================\n# Free Tier zahrnuje tyto ligy:\nLEAGUES = {
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

# ==============================================================================\n# 2. API FUNKCE\n# ==============================================================================\n
def get_headers(api_key):
    return {'X-Auth-Token': api_key}

@st.cache_data(ttl=3600)
def get_standings(api_key, code):
    url = f"https://api.football-data.org/v4/competitions/{code}/standings"
    try:
        r = requests.get(url, headers=get_headers(api_key))
        if r.status_code != 200: return None
        data = r.json()
        return data['standings'][0]['table']
    except: return None

@st.cache_data(ttl=3600)
def get_matches(api_key, code):
    # Stáhneme zápasy na příštích 7 dní
    dnes = datetime.now().strftime("%Y-%m-%d")
    za_tyden = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/competitions/{code}/matches?dateFrom={dnes}&dateTo={za_tyden}"
    try:
        r = requests.get(url, headers=get_headers(api_key))
        if r.status_code != 200: return None
        data = r.json()
        return data['matches']
    except: return None

# ==============================================================================\n# 3. MATEMATICKÝ MODEL (POISSON & xG)\n# ==============================================================================\n
def calculate_team_stats(standings):
    if not standings: return None, 0
    
    stats = {}
    total_goals = 0
    total_games = 0
    
    for row in standings:
        team_id = row['team']['id']
        played = row['playedGames']
        if played < 2: continue # Potřebujeme alespoň pár zápasů
        
        gf = row['goalsFor']
        ga = row['goalsAgainst']
        pts = row['points']
        
        total_goals += gf
        total_games += played
        
        # Výpočet průměrů na zápas
        stats[team_id] = {
            "name": row['team']['name'],
            "gf_avg": gf / played, # Útočná síla (hrubá)
            "ga_avg": ga / played, # Obranná slabost (hrubá)
            "points": pts,
            "form": row.get('form', '')
        }
        
    if total_games == 0: return None, 0
    league_avg = total_goals / total_games
    
    # Normalizace síly (Attack/Defense Strength)
    for t_id, data in stats.items():
        data["att_strength"] = data["gf_avg"] / league_avg if league_avg > 0 else 1
        data["def_strength"] = data["ga_avg"] / league_avg if league_avg > 0 else 1
        
    return stats, league_avg

def predict_match(home_id, away_id, stats, league_avg):
    if home_id not in stats or away_id not in stats: return None
    
    h = stats[home_id]
    a = stats[away_id]
    
    # 1. Výpočet xG (Očekávané góly)
    # Home xG = Home Attack * Away Defense * League Avg * Home Advantage
    xg_h = h["att_strength"] * a["def_strength"] * league_avg * 1.15
    
    # Away xG = Away Attack * Home Defense * League Avg
    xg_a = a["att_strength"] * h["def_strength"] * league_avg
    
    # 2. Poissonova simulace
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
            
    # 3. Pravděpodobnosti
    prob_1 = np.sum(np.tril(matrix, -1))
    prob_0 = np.sum(np.diag(matrix))
    prob_2 = np.sum(np.triu(matrix, 1))
    
    prob_over_25 = 0
    prob_btts = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "1": prob_1, "0": prob_0, "2": prob_2,
        "Over 2.5": prob_over_25, "BTTS": prob_btts,
        "xG_H": xg_h, "xG_A": xg_a,
        "Home": h["name"], "Away": a["name"],
        "Form_H": h["form"], "Form_A": a["form"]
    }

# ==============================================================================\n# 4. UI APLIKACE\n# ==============================================================================\n
st.title("🧠 Pro Football Analyst (Stable)")
st.caption("Oficiální data + Poissonův model. Žádné výpadky.")

# Sidebar
st.sidebar.header("Nastavení")
api_key = st.sidebar.text_input("Vlož API Klíč (football-data.org):", type="password")
selected_league = st.sidebar.selectbox("Vyber ligu:", list(LEAGUES.keys()))

if not api_key:
    st.warning("⬅️ Pro spuštění vlož prosím svůj API klíč do levého menu.")
    st.markdown("[Získat klíč zdarma zde](https://www.football-data.org/client/register)")
else:
    code = LEAGUES[selected_league]
    
    with st.spinner("Stahuji data a počítám predikce..."):
        standings = get_standings(api_key, code)
        matches = get_matches(api_key, code)
        
    if standings is None:
        st.error("Chyba API. Zkontroluj klíč nebo zkus jinou ligu.")
    elif matches is None:
        st.warning("Nepodařilo se načíst zápasy.")
    else:
        # Výpočet modelu
        stats_db, league_avg = calculate_team_stats(standings)
        
        if not matches:
            st.info("V příštích 7 dnech nejsou v této lize žádné zápasy.")
        else:
            st.success(f"Analyzováno {len(matches)} zápasů.")
            
            # Filtry
            min_conf = st.slider("Minimální důvěra (%):", 40, 90, 50)
            
            for m in matches:
                hid = m['homeTeam']['id']
                aid = m['awayTeam']['id']
                date_str = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ").strftime("%d.%m. %H:%M")
                
                pred = predict_match(hid, aid, stats_db, league_avg)
                
                if not pred: continue
                
                # Určení nejlepšího tipu
                tips = []
                if pred["1"] > 0.5: tips.append(("Výhra Domácí", pred["1"], "green"))
                elif pred["2"] > 0.5: tips.append(("Výhra Hosté", pred["2"], "red"))
                
                if pred["Over 2.5"] > 0.55: tips.append(("Over 2.5 Gólů", pred["Over 2.5"], "blue"))
                if pred["BTTS"] > 0.60: tips.append(("BTTS (Oba dají)", pred["BTTS"], "orange"))
                
                # Pokud není silný tip, zkusíme dvojitou šanci
                if not tips:
                    if pred["1"] + pred["0"] > 0.7: tips.append(("Neprohra Domácí", pred["1"]+pred["0"], "gray"))
                    elif pred["2"] + pred["0"] > 0.7: tips.append(("Neprohra Hosté", pred["2"]+pred["0"], "gray"))
                
                if not tips: continue
                
                best_tip = max(tips, key=lambda x: x[1])
                
                # Filtr důvěry
                if best_tip[1] * 100 < min_conf: continue
                
                # Vykreslení
                with st.container():
                    c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                    
                    with c1:
                        st.write(f"**{date_str}**")
                        st.caption(f"Kolo {m['matchday']}")
                        
                    with c2:
                        st.write(f"**{pred['Home']}**")
                        st.write(f"**{pred['Away']}**")
                        
                    with c3:
                        st.markdown(f"#### :{best_tip[2]}[{best_tip[0]}]")
                        st.caption(f"Důvěra: {int(best_tip[1]*100)}%")
                        
                    with c4:
                        st.metric("Férový kurz", f"{1/best_tip[1]:.2f}")
                        
                    with st.expander("Detailní statistiky"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**xG:** {pred['xG_H']:.2f} - {pred['xG_A']:.2f}")
                            st.write(f"**Forma D:** {pred['Form_H'].replace(',', ' ')}")
                            st.write(f"**Forma H:** {pred['Form_A'].replace(',', ' ')}")
                        with col_b:
                            st.write(f"1: {int(pred['1']*100)}% | X: {int(pred['0']*100)}% | 2: {int(pred['2']*100)}%")
                            st.write(f"Over 2.5: {int(pred['Over 2.5']*100)}%")
                            st.write(f"BTTS: {int(pred['BTTS']*100)}%")
                            
                    st.markdown("---")
