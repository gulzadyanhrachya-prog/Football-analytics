import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# ==============================================================================
# 1. NASTAVENÍ STRÁNKY
# ==============================================================================
st.set_page_config(page_title="Pro Football Analyst v2.0", layout="wide", page_icon="⚽")

# Stylování pro hezčí vzhled
st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. KONFIGURACE LIG (Football-Data.org)
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

# ==============================================================================
# 3. API FUNKCE
# ==============================================================================

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

# ==============================================================================
# 4. MATEMATICKÝ MODEL (POISSON & xG)
# ==============================================================================

def calculate_team_stats(standings):
    if not standings: return None, 0
    
    stats = {}
    total_goals = 0
    total_games = 0
    
    for row in standings:
        team_id = row['team']['id']
        played = row['playedGames']
        if played < 2: continue 
        
        gf = row['goalsFor']
        ga = row['goalsAgainst']
        pts = row['points']
        
        total_goals += gf
        total_games += played
        
        # Ukládáme i logo (crest)
        stats[team_id] = {
            "name": row['team']['name'],
            "crest": row['team'].get('crest', ''), # Získání loga
            "gf_avg": gf / played,
            "ga_avg": ga / played,
            "points": pts,
            "form": row.get('form', '')
        }
        
    if total_games == 0: return None, 0
    league_avg = total_goals / total_games
    
    # Normalizace síly
    for t_id, data in stats.items():
        data["att_strength"] = data["gf_avg"] / league_avg if league_avg > 0 else 1
        data["def_strength"] = data["ga_avg"] / league_avg if league_avg > 0 else 1
        
    return stats, league_avg

def predict_match(home_id, away_id, stats, league_avg):
    if home_id not in stats or away_id not in stats: return None
    
    h = stats[home_id]
    a = stats[away_id]
    
    # 1. Výpočet xG
    xg_h = h["att_strength"] * a["def_strength"] * league_avg * 1.15
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
        "Home_Crest": h["crest"], "Away_Crest": a["crest"],
        "Form_H": h["form"], "Form_A": a["form"]
    }

# ==============================================================================
# 5. UI APLIKACE
# ==============================================================================

st.title("🧠 Pro Football Analyst & Database")
st.caption("Predikce založené na Poissonově modelu a historických datech.")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Nastavení")

# Pokus o načtení klíče ze secrets (pro Cloud), jinak input (pro lokál)
try:
    api_key = st.secrets["FOOTBALL_DATA_KEY"]
    st.sidebar.success("🔑 API Klíč načten ze systému")
except:
    api_key = st.sidebar.text_input("Vlož API Klíč (football-data.org):", type="password")

selected_league = st.sidebar.selectbox("Vyber ligu:", list(LEAGUES.keys()))
min_conf = st.sidebar.slider("Minimální důvěra (%):", 40, 90, 50)

# --- HLAVNÍ LOGIKA ---
if not api_key:
    st.warning("⬅️ Pro spuštění vlož prosím svůj API klíč do levého menu.")
    st.markdown("[Získat klíč zdarma zde](https://www.football-data.org/client/register)")
else:
    code = LEAGUES[selected_league]
    
    with st.spinner("Stahuji data, loga a počítám predikce..."):
        standings = get_standings(api_key, code)
        matches = get_matches(api_key, code)
        
    if standings is None:
        st.error("Chyba API. Zkontroluj klíč nebo zkus jinou ligu (některé jsou v placené verzi).")
    elif matches is None:
        st.warning("Nepodařilo se načíst zápasy.")
    else:
        stats_db, league_avg = calculate_team_stats(standings)
        
        if not matches:
            st.info("V příštích 7 dnech nejsou v této lize žádné zápasy.")
        else:
            st.success(f"Analyzováno {len(matches)} zápasů.")
            
            # Seznam pro export dat
            export_data = []
            
            for m in matches:
                hid = m['homeTeam']['id']
                aid = m['awayTeam']['id']
                date_obj = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
                date_str = date_obj.strftime("%d.%m. %H:%M")
                
                pred = predict_match(hid, aid, stats_db, league_avg)
                
                if not pred: continue
                
                # Určení nejlepšího tipu
                tips = []
                if pred["1"] > 0.5: tips.append(("Výhra Domácí", pred["1"], "green"))
                elif pred["2"] > 0.5: tips.append(("Výhra Hosté", pred["2"], "red"))
                
                if pred["Over 2.5"] > 0.55: tips.append(("Over 2.5 Gólů", pred["Over 2.5"], "blue"))
                if pred["BTTS"] > 0.60: tips.append(("BTTS (Oba dají)", pred["BTTS"], "orange"))
                
                if not tips:
                    if pred["1"] + pred["0"] > 0.7: tips.append(("Neprohra Domácí", pred["1"]+pred["0"], "gray"))
                    elif pred["2"] + pred["0"] > 0.7: tips.append(("Neprohra Hosté", pred["2"]+pred["0"], "gray"))
                
                if not tips: continue
                
                best_tip = max(tips, key=lambda x: x[1])
                confidence_pct = int(best_tip[1] * 100)
                
                # Uložení do export listu (všechny zápasy, i ty s malou důvěrou)
                export_data.append({
                    "Datum": date_str,
                    "Domácí": pred["Home"],
                    "Hosté": pred["Away"],
                    "Tip": best_tip[0],
                    "Důvěra %": confidence_pct,
                    "Kurz (Fair)": round(1/best_tip[1], 2),
                    "xG Home": round(pred["xG_H"], 2),
                    "xG Away": round(pred["xG_A"], 2),
                    "Pravd. 1": round(pred["1"], 2),
                    "Pravd. 0": round(pred["0"], 2),
                    "Pravd. 2": round(pred["2"], 2)
                })

                # Filtr pro zobrazení na webu
                if confidence_pct < min_conf: continue
                
                # --- VYKRESLENÍ KARTY ZÁPASU ---
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 1, 2, 1])
                    
                    with c1:
                        if pred['Home_Crest']:
                            st.image(pred['Home_Crest'], width=50)
                    
                    with c2:
                        st.markdown(f"**{pred['Home']}** vs **{pred['Away']}**")
                        st.caption(f"📅 {date_str} | Kolo {m['matchday']}")
                        
                    with c3:
                        if pred['Away_Crest']:
                            st.image(pred['Away_Crest'], width=50)
                            
                    with c4:
                        st.markdown(f"**Tip:** :{best_tip[2]}[{best_tip[0]}]")
                        st.progress(confidence_pct)
                        st.caption(f"Důvěra modelu: {confidence_pct}%")
                        
                    with c5:
                        with st.popover("📊 Detaily"):
                            st.write(f"**Férový kurz:** {1/best_tip[1]:.2f}")
                            st.divider()
                            st.write(f"xG: {pred['xG_H']:.2f} - {pred['xG_A']:.2f}")
                            st.write(f"1: {int(pred['1']*100)}% | X: {int(pred['0']*100)}% | 2: {int(pred['2']*100)}%")
                            st.write(f"Over 2.5: {int(pred['Over 2.5']*100)}%")
            
            # --- EXPORT DAT ---
            st.divider()
            st.subheader("📥 Databáze predikcí")
            if export_data:
                df = pd.DataFrame(export_data)
                st.dataframe(df.style.format({"Kurz (Fair)": "{:.2f}", "xG Home": "{:.2f}"}), use_container_width=True, height=200)
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Stáhnout data do CSV (Excel)",
                    data=csv,
                    file_name=f'predikce_{datetime.now().strftime("%Y-%m-%d")}.csv',
                    mime='text/csv',
                )
