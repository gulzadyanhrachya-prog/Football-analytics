import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# ==============================================================================
# 1. NASTAVENÍ A STYLY
# ==============================================================================
st.set_page_config(page_title="Pro Football Analyst v4.1", layout="wide", page_icon="🧠")

st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    .form-badge { padding: 2px 8px; border-radius: 4px; color: white; font-weight: bold; margin-right: 4px; font-size: 0.8em; }
    .form-W { background-color: #28a745; }
    .form-D { background-color: #ffc107; color: black; }
    .form-L { background-color: #dc3545; }
    .stat-box { background-color: #f0f2f6; padding: 10px; border-radius: 5px; text-align: center; }
    .prediction-box { border-left: 5px solid #4CAF50; padding: 10px; background-color: #f9f9f9; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. KONFIGURACE LIG
# ==============================================================================
LEAGUES = {\n    "🇬🇧 Premier League": "PL",
    "🇬🇧 Championship": "ELC",
    "🇪🇺 Liga Mistrů": "CL",
    "🇩🇪 Bundesliga": "BL1",
    "🇪🇸 La Liga": "PD",
    "🇫🇷 Ligue 1": "FL1",
    "🇮🇹 Serie A": "SA",
    "🇳🇱 Eredivisie": "DED",
    "🇵🇹 Primeira Liga": "PPL",
    "🇧🇷 Série A": "BSA"
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
        if r.status_code == 403: return "RESTRICTED"
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

# ==============================================================================
# 4. MATEMATICKÝ MODEL & POMOCNÉ FUNKCE
# ==============================================================================

def render_form_html(form_str):
    """Převede string 'W,L,D' na barevné HTML odznaky."""
    if not form_str: return "<span style='color:grey'>N/A</span>"
    html = ""
    # API vrací formu jako "W,L,D" nebo "WLD". Upravíme pro jistotu.
    clean_form = form_str.replace(",", "").strip()
    # Bereme posledních 5 zápasů
    for char in clean_form[-5:]: 
        if char == 'W': html += "<span class='form-badge form-W'>V</span>"
        elif char == 'D': html += "<span class='form-badge form-D'>R</span>"
        elif char == 'L': html += "<span class='form-badge form-L'>P</span>"
    return html

def calculate_team_stats(standings):
    if not standings or standings == "RESTRICTED": return None, 0
    
    stats = {}\
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
        
        # OPRAVA CHYBY ZDE: Ošetření None hodnoty u formy a loga
        raw_form = row.get('form')
        safe_form = raw_form if raw_form is not None else ""
        
        raw_crest = row['team'].get('crest')
        safe_crest = raw_crest if raw_crest is not None else ""

        stats[team_id] = {
            "name": row['team']['name'],
            "crest": safe_crest,
            "gf_avg": gf / played,
            "ga_avg": ga / played,
            "points": row['points'],
            "form": safe_form.replace(",", "")
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
    
    # xG Výpočet (Home Advantage 15%)
    xg_h = h["att_strength"] * a["def_strength"] * league_avg * 1.15
    xg_a = a["att_strength"] * h["def_strength"] * league_avg
    
    # Poisson Matrix
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
            
    # Pravděpodobnosti
    prob_1 = np.sum(np.tril(matrix, -1))
    prob_0 = np.sum(np.diag(matrix))
    prob_2 = np.sum(np.triu(matrix, 1))
    
    prob_over_25 = np.sum([matrix[i, j] for i in range(max_g) for j in range(max_g) if i+j > 2.5])
    prob_btts = np.sum([matrix[i, j] for i in range(max_g) for j in range(max_g) if i>0 and j>0])
    
    # Nejpravděpodobnější přesné výsledky (Top 3)
    scores = []
    for i in range(max_g):
        for j in range(max_g):
            scores.append((f"{i}:{j}", matrix[i, j]))
    scores.sort(key=lambda x: x[1], reverse=True)
    
    # Smart Pick Logika
    smart_pick = "No Bet"
    smart_conf = 0
    smart_color = "gray"
    
    if prob_1 > 0.60:
        smart_pick = f"Výhra {h['name']}"
        smart_conf = prob_1
        smart_color = "green"
    elif prob_2 > 0.55: # Hosté potřebují menší práh pro hodnotu
        smart_pick = f"Výhra {a['name']}"
        smart_conf = prob_2
        smart_color = "red"
    elif prob_over_25 > 0.65:
        smart_pick = "Over 2.5 Gólů"
        smart_conf = prob_over_25
        smart_color = "blue"
    elif prob_btts > 0.65:
        smart_pick = "BTTS (Oba dají gól)"
        smart_conf = prob_btts
        smart_color = "orange"
    elif prob_1 + prob_0 > 0.80:
        smart_pick = f"Neprohra {h['name']}"
        smart_conf = prob_1 + prob_0
        smart_color = "green"
            
    return {
        "Home": h, "Away": a,
        "xG_H": xg_h, "xG_A": xg_a,
        "1": prob_1, "0": prob_0, "2": prob_2,
        "O2.5": prob_over_25, "BTTS": prob_btts,
        "Correct_Scores": scores[:3],
        "Smart_Pick": smart_pick,
        "Smart_Conf": smart_conf,
        "Smart_Color": smart_color
    }

def get_fair_odd(prob):
    return round(1/prob, 2) if prob > 0.01 else 99.0

# ==============================================================================
# 5. UI APLIKACE
# ==============================================================================

st.title("🧠 Pro Football Analyst v4.1")
st.caption("Pokročilá analýza: Forma, Power Index a Smart Picks")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Nastavení")
try:
    api_key = st.secrets["FOOTBALL_DATA_KEY"]
    st.sidebar.success("🔑 API Klíč aktivní")
except:
    api_key = st.sidebar.text_input("Vlož API Klíč:", type="password")

selected_league = st.sidebar.selectbox("Vyber ligu:", list(LEAGUES.keys()))

# --- HLAVNÍ LOGIKA ---
if not api_key:
    st.warning("⬅️ Vlož API klíč pro spuštění.")
else:
    code = LEAGUES[selected_league]
    
    with st.spinner("Analyzuji zápasy a počítám pravděpodobnosti..."):
        standings = get_standings(api_key, code)
        matches = get_matches(api_key, code)
        
    if standings == "RESTRICTED":
        st.error(f"⛔ Nemáš přístup k lize {selected_league} (Free Tier). Zkus PL, PD, SA, BL1, FL1.")
    elif standings is None or matches is None:
        st.error("Chyba při stahování dat. Zkontroluj API klíč nebo zkus jinou ligu.")
    else:
        stats_db, league_avg = calculate_team_stats(standings)
        
        if not matches:
            st.info("Žádné zápasy v příštích 7 dnech.")
        else:
            st.success(f"Nalezeno {len(matches)} zápasů.")
            
            for m in matches:
                hid = m['homeTeam']['id']
                aid = m['awayTeam']['id']
                date_str = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ").strftime("%d.%m. %H:%M")
                
                pred = predict_match(hid, aid, stats_db, league_avg)
                if not pred: continue
                
                # --- KARTA ZÁPASU ---
                with st.expander(f"⚽ {date_str} | {pred['Home']['name']} vs {pred['Away']['name']}"):
                    
                    # 1. HLAVIČKA S FORMOU
                    c1, c2, c3 = st.columns([1, 4, 1])
                    with c1: 
                        if pred['Home']['crest']:
                            st.image(pred['Home']['crest'], width=60)
                        st.markdown(render_form_html(pred['Home']['form']), unsafe_allow_html=True)
                    with c2: 
                        st.markdown(f"<h3 style='text-align: center;'>{pred['Home']['name']} vs {pred['Away']['name']}</h3>", unsafe_allow_html=True)
                        # Smart Pick Banner
                        st.markdown(f"""
                        <div class='prediction-box' style='border-color: {pred['Smart_Color']}'>
                            <strong>💡 Smart Pick:</strong> {pred['Smart_Pick']} <br>
                            <small>Důvěra: {int(pred['Smart_Conf']*100)}% | Fair Kurz: {get_fair_odd(pred['Smart_Conf'])}</small>
                        </div>
                        """, unsafe_allow_html=True)
                    with c3: 
                        if pred['Away']['crest']:
                            st.image(pred['Away']['crest'], width=60)
                        st.markdown(render_form_html(pred['Away']['form']), unsafe_allow_html=True)
                    
                    st.divider()
                    
                    # 2. POWER INDEX (ÚTOK vs OBRANA)
                    st.caption("📊 Power Index (Síla útoku vs. Síla obrany)")
                    col_att, col_def = st.columns(2)
                    
                    with col_att:
                        st.markdown("**Útočná síla (xG potenciál)**")
                        # Normalizace pro progress bar (max cca 3 góly)
                        att_h_norm = min(pred['xG_H'] / 3.0, 1.0)
                        att_a_norm = min(pred['xG_A'] / 3.0, 1.0)
                        st.progress(att_h_norm, text=f"Domácí: {pred['xG_H']:.2f} xG")
                        st.progress(att_a_norm, text=f"Hosté: {pred['xG_A']:.2f} xG")
                        
                    with col_def:
                        st.markdown("**Pravděpodobnost výhry**")
                        st.progress(pred['1'], text=f"Domácí: {int(pred['1']*100)}%")
                        st.progress(pred['2'], text=f"Hosté: {int(pred['2']*100)}%")

                    st.divider()

                    # 3. DETAILY SÁZEK (TABS)
                    t1, t2, t3 = st.tabs(["💰 Kurzy & 1X2", "🎯 Přesný výsledek", "📈 Statistiky"])
                    
                    with t1:
                        c_odds1, c_odds2, c_odds3 = st.columns(3)
                        c_odds1.metric("Domácí (1)", f"{int(pred['1']*100)}%", f"Kurz: {get_fair_odd(pred['1'])}")
                        c_odds2.metric("Remíza (0)", f"{int(pred['0']*100)}%", f"Kurz: {get_fair_odd(pred['0'])}")
                        c_odds3.metric("Hosté (2)", f"{int(pred['2']*100)}%", f"Kurz: {get_fair_odd(pred['2'])}")
                        
                        st.markdown("---")
                        st.write(f"**Over 2.5 Gólů:** {int(pred['O2.5']*100)}% (Kurz: {get_fair_odd(pred['O2.5'])})")
                        st.write(f"**BTTS (Oba dají):** {int(pred['BTTS']*100)}% (Kurz: {get_fair_odd(pred['BTTS'])})")

                    with t2:
                        st.write("Nejpravděpodobnější skóre podle modelu:")
                        cols_score = st.columns(3)
                        for idx, (score, prob) in enumerate(pred['Correct_Scores']):
                            with cols_score[idx]:
                                st.markdown(f"### {score}")
                                st.caption(f"{int(prob*100)}% (Kurz {get_fair_odd(prob)})")
                                
                    with t3:
                        st.write("Data z aktuální sezóny:")
                        st.dataframe(pd.DataFrame([
                            {"Tým": pred['Home']['name'], "Body": pred['Home']['points'], "Útok (síla)": round(pred['Home']['att_strength'],2), "Obrana (síla)": round(pred['Home']['def_strength'],2)},
                            {"Tým": pred['Away']['name'], "Body": pred['Away']['points'], "Útok (síla)": round(pred['Away']['att_strength'],2), "Obrana (síla)": round(pred['Away']['def_strength'],2)}
                        ]), hide_index=True)
