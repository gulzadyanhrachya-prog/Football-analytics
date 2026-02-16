import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# ==============================================================================\n# 1. NASTAVENÍ STRÁNKY A STYLŮ
# ==============================================================================\n
st.set_page_config(page_title="Pro Football Analyst v3.0", layout="wide", page_icon="⚽")

st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    .big-font { font-size: 18px !important; font-weight: bold; }
    .match-card { border: 1px solid #e0e0e0; padding: 10px; border-radius: 5px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================\n# 2. KONFIGURACE LIG (Rozšířená Evropa)
# ==============================================================================\n# Poznámka: Některé ligy vyžadují placený API klíč (Tier 1/2)
LEAGUES = {
    "🇬🇧 Premier League": "PL",
    "🇬🇧 Championship (2. liga)": "ELC",
    "🇪🇺 Liga Mistrů": "CL",
    "🇩🇪 Bundesliga": "BL1",
    "🇩🇪 2. Bundesliga": "BL2",
    "🇪🇸 La Liga": "PD",
    "🇪🇸 Segunda Division (2. liga)": "SD",
    "🇫🇷 Ligue 1": "FL1",
    "🇫🇷 Ligue 2": "FL2",
    "🇮🇹 Serie A": "SA",
    "🇮🇹 Serie B": "SB",
    "🇳🇱 Eredivisie": "DED",
    "🇵🇹 Primeira Liga": "PPL",
    "🇧🇷 Série A (Brazílie)": "BSA"
}

# ==============================================================================\n# 3. API FUNKCE
# ==============================================================================\n
def get_headers(api_key):
    return {'X-Auth-Token': api_key}

@st.cache_data(ttl=3600)
def get_standings(api_key, code):
    url = f"https://api.football-data.org/v4/competitions/{code}/standings"
    try:
        r = requests.get(url, headers=get_headers(api_key))
        if r.status_code == 403: return "RESTRICTED" # Ošetření free tieru
        if r.status_code != 200: return None
        data = r.json()
        return data['standings'][0]['table']
    except: return None

@st.cache_data(ttl=3600)
def get_matches(api_key, code):
    dnes = datetime.now().strftime("%Y-%m-%d")
    za_tyden = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/competitions/{code}/matches?dateFrom={dnes}&dateTo={za_tyden}"
    try:
        r = requests.get(url, headers=get_headers(api_key))
        if r.status_code != 200: return None
        data = r.json()
        return data['matches']
    except: return None

# ==============================================================================\n# 4. MATEMATICKÝ MODEL (POISSON & xG)
# ==============================================================================\n
def calculate_team_stats(standings):
    if not standings or standings == "RESTRICTED": return None, 0
    
    stats = {}
    total_goals = 0
    total_games = 0
    
    for row in standings:
        team_id = row['team']['id']
        played = row['playedGames']
        if played < 2: continue 
        
        gf = row['goalsFor']
        ga = row['goalsAgainst']
        
        total_goals += gf
        total_games += played
        
        stats[team_id] = {
            "name": row['team']['name'],
            "crest": row['team'].get('crest', ''),
            "gf_avg": gf / played,
            "ga_avg": ga / played,
            "points": row['points'],
            "form": row.get('form', '')
        }
        
    if total_games == 0: return None, 0
    league_avg = total_goals / total_games
    
    for t_id, data in stats.items():
        data["att_strength"] = data["gf_avg"] / league_avg if league_avg > 0 else 1
        data["def_strength"] = data["ga_avg"] / league_avg if league_avg > 0 else 1
        
    return stats, league_avg

def predict_match(home_id, away_id, stats, league_avg):
    if home_id not in stats or away_id not in stats: return None
    
    h = stats[home_id]
    a = stats[away_id]
    
    # xG Výpočet
    xg_h = h["att_strength"] * a["def_strength"] * league_avg * 1.15
    xg_a = a["att_strength"] * h["def_strength"] * league_avg
    
    # Poisson Matrix
    max_g = 8 # Zvýšeno pro přesnější výpočet vysokých skóre
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
            
    # Základní pravděpodobnosti
    prob_1 = np.sum(np.tril(matrix, -1))
    prob_0 = np.sum(np.diag(matrix))
    prob_2 = np.sum(np.triu(matrix, 1))
    
    # Gólové trhy
    prob_over_15 = 0
    prob_over_25 = 0
    prob_over_35 = 0
    prob_btts = 0
    
    for i in range(max_g):
        for j in range(max_g):
            total = i + j
            if total > 1.5: prob_over_15 += matrix[i, j]
            if total > 2.5: prob_over_25 += matrix[i, j]
            if total > 3.5: prob_over_35 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "Home": h["name"], "Away": a["name"],
        "Home_Crest": h["crest"], "Away_Crest": a["crest"],
        "xG_H": xg_h, "xG_A": xg_a,
        "1": prob_1, "0": prob_0, "2": prob_2,
        "1X": prob_1 + prob_0, "X2": prob_2 + prob_0,
        "O1.5": prob_over_15, "O2.5": prob_over_25, "O3.5": prob_over_35,
        "BTTS": prob_btts
    }

def get_fair_odd(prob):
    if prob <= 0.01: return 99.0
    return round(1 / prob, 2)

def color_confidence(prob):
    if prob > 0.7: return "green"
    if prob > 0.5: return "blue"
    if prob > 0.4: return "orange"
    return "red"

# ==============================================================================\n# 5. UI APLIKACE
# ==============================================================================\n
st.title("🧠 Pro Football Analyst - Full Database")
st.caption("Kompletní analýza evropských lig. Vyber ligu, získej pravděpodobnosti a férové kurzy.")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Nastavení")
try:
    api_key = st.secrets["FOOTBALL_DATA_KEY"]
    st.sidebar.success("🔑 API Klíč načten")
except:
    api_key = st.sidebar.text_input("Vlož API Klíč:", type="password")

selected_league = st.sidebar.selectbox("Vyber ligu:", list(LEAGUES.keys()))

# --- HLAVNÍ LOGIKA ---
if not api_key:
    st.warning("⬅️ Vlož API klíč.")
else:
    code = LEAGUES[selected_league]
    
    with st.spinner("Analyzuji trh..."):
        standings = get_standings(api_key, code)
        matches = get_matches(api_key, code)
        
    if standings == "RESTRICTED":
        st.error(f"⛔ Tvůj API klíč nemá přístup k lize {selected_league}. Free verze podporuje jen PL, PD, SA, BL1, FL1, DED, PPL.")
    elif standings is None or matches is None:
        st.error("Chyba při stahování dat.")
    else:
        stats_db, league_avg = calculate_team_stats(standings)
        
        if not matches:
            st.info("Žádné zápasy v příštích 7 dnech.")
        else:
            st.success(f"Nalezeno {len(matches)} zápasů. Rozklikni pro detaily.")
            
            export_data = []
            
            for m in matches:
                hid = m['homeTeam']['id']
                aid = m['awayTeam']['id']
                date_str = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ").strftime("%d.%m. %H:%M")
                
                pred = predict_match(hid, aid, stats_db, league_avg)
                if not pred: continue
                
                # Příprava dat pro export
                export_data.append({
                    "Datum": date_str,
                    "Zápas": f"{pred['Home']} - {pred['Away']}",
                    "1 (%)": round(pred['1']*100, 1),
                    "0 (%)": round(pred['0']*100, 1),
                    "2 (%)": round(pred['2']*100, 1),
                    "Over 2.5 (%)": round(pred['O2.5']*100, 1),
                    "BTTS (%)": round(pred['BTTS']*100, 1),
                    "xG Home": round(pred['xG_H'], 2),
                    "xG Away": round(pred['xG_A'], 2)
                })

                # --- VYKRESLENÍ KARTY ZÁPASU (EXPANDER) ---
                with st.expander(f"⚽ {date_str} | {pred['Home']} vs {pred['Away']}"):
                    
                    # Hlavička s logy
                    c1, c2, c3 = st.columns([1, 4, 1])
                    with c1: st.image(pred['Home_Crest'], width=60)
                    with c2: 
                        st.markdown(f"<h3 style='text-align: center;'>{pred['Home']} vs {pred['Away']}</h3>", unsafe_allow_html=True)
                        st.markdown(f"<p style='text-align: center;'>xG: {pred['xG_H']:.2f} - {pred['xG_A']:.2f}</p>", unsafe_allow_html=True)
                    with c3: st.image(pred['Away_Crest'], width=60)
                    
                    st.divider()
                    
                    # Záložky pro různé typy sázek
                    tab1, tab2, tab3 = st.tabs(["🏆 Vítěz zápasu (1X2)", "🥅 Góly (Over/Under)", "🤝 Ostatní (BTTS, DC)"])
                    
                    # TAB 1: 1X2
                    with tab1:
                        col_h, col_d, col_a = st.columns(3)
                        with col_h:
                            st.metric("Výhra Domácí (1)", f"{int(pred['1']*100)}%", f"Kurz: {get_fair_odd(pred['1'])}")
                            st.progress(pred['1'])
                        with col_d:
                            st.metric("Remíza (0)", f"{int(pred['0']*100)}%", f"Kurz: {get_fair_odd(pred['0'])}")
                            st.progress(pred['0'])
                        with col_a:
                            st.metric("Výhra Hosté (2)", f"{int(pred['2']*100)}%", f"Kurz: {get_fair_odd(pred['2'])}")
                            st.progress(pred['2'])
                            
                    # TAB 2: GÓLY
                    with tab2:
                        g1, g2, g3 = st.columns(3)
                        with g1:
                            st.markdown("**Over 1.5**")
                            st.write(f"Pravděpodobnost: **{int(pred['O1.5']*100)}%**")
                            st.caption(f"Fair kurz: {get_fair_odd(pred['O1.5'])}")
                            st.progress(pred['O1.5'])
                        with g2:
                            st.markdown("**Over 2.5**")
                            st.write(f"Pravděpodobnost: **{int(pred['O2.5']*100)}%**")
                            st.caption(f"Fair kurz: {get_fair_odd(pred['O2.5'])}")
                            st.progress(pred['O2.5'])
                        with g3:
                            st.markdown("**Over 3.5**")
                            st.write(f"Pravděpodobnost: **{int(pred['O3.5']*100)}%**")
                            st.caption(f"Fair kurz: {get_fair_odd(pred['O3.5'])}")
                            st.progress(pred['O3.5'])
                            
                    # TAB 3: OSTATNÍ
                    with tab3:
                        o1, o2 = st.columns(2)
                        with o1:
                            st.subheader("Oba dají gól (BTTS)")
                            st.write(f"ANO: **{int(pred['BTTS']*100)}%** (Kurz: {get_fair_odd(pred['BTTS'])})")
                            st.progress(pred['BTTS'])
                            st.write(f"NE: **{int((1-pred['BTTS'])*100)}%** (Kurz: {get_fair_odd(1-pred['BTTS'])})")
                        with o2:
                            st.subheader("Dvojitá šance")
                            st.write(f"1X (Neprohra domácí): **{int(pred['1X']*100)}%**")
                            st.write(f"X2 (Neprohra hosté): **{int(pred['X2']*100)}%**")

            # Export tlačítko
            st.divider()
            if export_data:
                df = pd.DataFrame(export_data)
                st.download_button(
                    label="📥 Stáhnout kompletní databázi (CSV)",
                    data=df.to_csv(index=False).encode('utf-8'),
                    file_name=f'football_db_{datetime.now().strftime("%Y-%m-%d")}.csv',
                    mime='text/csv',
                )
