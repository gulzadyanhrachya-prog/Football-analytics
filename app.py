import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Pro Football Analyst", layout="wide")

# ==============================================================================\n# 1. KONFIGURACE A API\n# ==============================================================================\n
API_KEY = "3" # Public key
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

LEAGUES = {
    "🇬🇧 Premier League": "4328",
    "🇬🇧 Championship": "4329",
    "🇪🇸 La Liga": "4335",
    "🇩🇪 Bundesliga": "4331",
    "🇮🇹 Serie A": "4332",
    "🇫🇷 Ligue 1": "4334",
    "🇳🇱 Eredivisie": "4337",
    "🇵🇹 Primeira Liga": "4344",
    "🇨🇿 Fortuna Liga": "4352",
    "🇵🇱 Ekstraklasa": "4353",
    "🇩🇰 Superliga": "4340",
    "🇹🇷 Super Lig": "4338",
    "🇬🇷 Super League": "4339",
    "🇷🇴 Liga I": "4358",
    "🇮🇱 Premier League": "4363",
    "🇧🇬 Parva Liga": "4342", # Bulharsko
    "🇺🇸 MLS": "4346"
}

# ==============================================================================\n# 2. STAHOVÁNÍ DAT\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_data(league_id, season):
    # 1. Tabulka (pro statistiky)
    url_table = f"{BASE_URL}/lookuptable.php?l={league_id}&s={season}"
    # 2. Zápasy (Next 15)
    url_events = f"{BASE_URL}/eventsnextleague.php?id={league_id}"
    
    table_data = None
    events_data = None
    
    try:
        r = requests.get(url_table)
        if r.status_code == 200: table_data = r.json().get("table")
    except: pass
    
    try:
        r = requests.get(url_events)
        if r.status_code == 200: events_data = r.json().get("events")
    except: pass
    
    return table_data, events_data

# ==============================================================================\n# 3. ANALYTICKÉ MODELY (POISSON)\n# ==============================================================================\n
def calculate_team_stats(table_data):
    if not table_data: return None, 0
    
    stats = {}
    total_goals = 0
    total_games = 0
    
    for row in table_data:
        played = int(row["intPlayed"])
        if played == 0: continue
        
        gf = int(row["intGoalsFor"])
        ga = int(row["intGoalsAgainst"])
        
        total_goals += gf
        total_games += played
        
        stats[row["idTeam"]] = {
            "name": row["strTeam"],
            "gf_avg": gf / played, # Vstřelené na zápas
            "ga_avg": ga / played, # Obdržené na zápas
            "points": int(row["intPoints"]),
            "played": played
        }
        
    if total_games == 0: return None, 0
    
    # Průměr ligy (góly na zápas na jeden tým)
    league_avg_goals = total_goals / total_games
    
    # Výpočet síly útoku a obrany (Attack/Defense Strength)
    for team_id, data in stats.items():
        data["att_strength"] = data["gf_avg"] / league_avg_goals
        data["def_strength"] = data["ga_avg"] / league_avg_goals
        
    return stats, league_avg_goals

def predict_match_poisson(home_id, away_id, stats, league_avg):
    if home_id not in stats or away_id not in stats:
        return None
    
    h = stats[home_id]
    a = stats[away_id]
    
    # Očekávané góly (xG)
    # Home xG = Home Attack * Away Defense * League Avg * Home Advantage (1.15)
    xg_home = h["att_strength"] * a["def_strength"] * league_avg * 1.15
    
    # Away xG = Away Attack * Home Defense * League Avg
    xg_away = a["att_strength"] * h["def_strength"] * league_avg
    
    # Poissonova simulace
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_home) * poisson.pmf(j, xg_away)
            
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    
    prob_over_25 = 0
    prob_btts = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "1": prob_h, "0": prob_d, "2": prob_a,
        "Over 2.5": prob_over_25, "BTTS": prob_btts,
        "xG_Home": xg_home, "xG_Away": xg_away,
        "Home_Name": h["name"], "Away_Name": a["name"],
        "Home_Att": h["att_strength"], "Home_Def": h["def_strength"],
        "Away_Att": a["att_strength"], "Away_Def": a["def_strength"]
    }

# ==============================================================================\n# 4. UI APLIKACE\n# ==============================================================================\n
st.title("🧠 Pro Football Analyst")
st.caption("Pokročilá analýza na základě síly útoku a obrany (Poisson Model)")

# --- SIDEBAR ---
c1, c2 = st.columns([2, 1])
with c1:
    league_name = st.selectbox("Vyber ligu:", list(LEAGUES.keys()))
with c2:
    season = st.selectbox("Sezóna:", ["2024-2025", "2025-2026", "2023-2024"])

league_id = LEAGUES[league_name]

# Načtení dat
with st.spinner("Analyzuji statistiky týmů..."):
    table_raw, events_raw = get_data(league_id, season)
    
stats_db, league_avg = calculate_team_stats(table_raw)

if not stats_db:
    st.error(f"Pro ligu {league_name} v sezóně {season} nejsou dostupná data tabulky.")
    st.info("Tip: Zkus změnit sezónu (např. na 2024-2025), pokud nová ještě nezačala.")
else:
    # --- HLAVNÍ PŘEHLED ---
    st.success(f"✅ Data načtena. Průměr gólů v lize: {league_avg:.2f} na tým.")
    
    tab1, tab2, tab3 = st.tabs(["📅 Nadcházející Zápasy", "⚔️ Simulátor", "📊 Síla Týmů"])
    
    # --- TAB 1: ZÁPASY ---
    with tab1:
        if not events_raw:
            st.warning("API nevrátilo žádné naplánované zápasy. Použij 'Simulátor' pro analýzu libovolného duelu.")
        else:
            st.subheader("Analýza nejbližších zápasů")
            for event in events_raw:
                hid = event["idHomeTeam"]
                aid = event["idAwayTeam"]
                date = event.get("dateEvent", "")
                
                pred = predict_match_poisson(hid, aid, stats_db, league_avg)
                
                if pred:
                    with st.container():
                        # Layout karty
                        c_time, c_match, c_probs, c_stats = st.columns([1, 3, 2, 2])
                        
                        with c_time:
                            st.write(f"**{date}**")
                            st.caption(event.get("strTime", "")[:5])
                            
                        with c_match:
                            st.write(f"**{pred['Home_Name']}**")
                            st.write(f"**{pred['Away_Name']}**")
                            
                        with c_probs:
                            # Zvýraznění favorita
                            if pred['1'] > 0.55: color = "green"
                            elif pred['2'] > 0.55: color = "red"
                            else: color = "orange"
                            
                            if color == "green": st.success(f"Tip: {pred['Home_Name']} ({int(pred['1']*100)}%)")
                            elif color == "red": st.error(f"Tip: {pred['Away_Name']} ({int(pred['2']*100)}%)")
                            else: st.warning(f"Remíza / Risk ({int(pred['0']*100)}%)")
                            
                        with c_stats:
                            st.write(f"xG: **{pred['xG_Home']:.2f}** - **{pred['xG_Away']:.2f}**")
                            st.write(f"Over 2.5: **{int(pred['Over 2.5']*100)}%**")
                        
                        # Detailní rozbalovátko
                        with st.expander("🔍 Detailní analýza síly"):
                            sc1, sc2 = st.columns(2)
                            with sc1:
                                st.write(f"**{pred['Home_Name']} (Domácí)**")
                                st.progress(min(1.0, pred['Home_Att'] / 2))
                                st.caption(f"Útok: {pred['Home_Att']:.2f}x průměr")
                                st.progress(min(1.0, (2 - pred['Home_Def']) / 2)) # Invertujeme obranu (méně je lépe)
                                st.caption(f"Obrana: {pred['Home_Def']:.2f}x průměr (Méně je lépe)")
                                
                            with sc2:
                                st.write(f"**{pred['Away_Name']} (Hosté)**")
                                st.progress(min(1.0, pred['Away_Att'] / 2))
                                st.caption(f"Útok: {pred['Away_Att']:.2f}x průměr")
                                st.progress(min(1.0, (2 - pred['Away_Def']) / 2))
                                st.caption(f"Obrana: {pred['Away_Def']:.2f}x průměr")
                        
                        st.markdown("---")

    # --- TAB 2: SIMULÁTOR ---
    with tab2:
        st.header("⚔️ Vlastní Simulace")
        st.write("Vyber si libovolné dva týmy z ligy a podívej se, jak by zápas dopadl podle matematiky.")
        
        teams_list = sorted([d["name"] for d in stats_db.values()])
        # Mapování jméno -> ID
        name_to_id = {v["name"]: k for k, v in stats_db.items()}
        
        sc1, sc2 = st.columns(2)
        with sc1:
            sim_home = st.selectbox("Domácí tým:", teams_list, index=0)
        with sc2:
            sim_away = st.selectbox("Hostující tým:", teams_list, index=1)
            
        if st.button("Simulovat Zápas"):
            hid = name_to_id[sim_home]
            aid = name_to_id[sim_away]
            
            res = predict_match_poisson(hid, aid, stats_db, league_avg)
            
            if res:
                st.markdown("### 🎯 Výsledek Predikce")
                m1, m2, m3 = st.columns(3)
                m1.metric(f"Výhra {sim_home}", f"{res['1']*100:.1f} %", f"Kurz: {1/res['1']:.2f}")
                m2.metric("Remíza", f"{res['0']*100:.1f} %", f"Kurz: {1/res['0']:.2f}")
                m3.metric(f"Výhra {sim_away}", f"{res['2']*100:.1f} %", f"Kurz: {1/res['2']:.2f}")
                
                st.markdown("#### ⚽ Očekávané góly (xG)")
                st.info(f"{sim_home}: **{res['xG_Home']:.2f}**  vs  {sim_away}: **{res['xG_Away']:.2f}**")
                
                st.markdown("#### 📈 Pravděpodobnost počtu gólů")
                g1, g2, g3 = st.columns(3)
                g1.write(f"Over 1.5: **{int((1 - poisson.cdf(1, res['xG_Home']+res['xG_Away']))*100)}%**")
                g2.write(f"Over 2.5: **{int(res['Over 2.5']*100)}%**")
                g3.write(f"BTTS (Oba dají): **{int(res['BTTS']*100)}%**")

    # --- TAB 3: SÍLA TÝMŮ ---
    with tab3:
        st.header("📊 Power Rankings")
        st.write("Kdo má nejlepší útok a kdo nejlepší obranu v lize?")
        
        # Převedeme dict na DataFrame
        df_stats = pd.DataFrame.from_dict(stats_db, orient='index')
        
        col_sort = st.radio("Seřadit podle:", ["Útok (Att Strength)", "Obrana (Def Strength)", "Body"])
        
        if col_sort == "Útok (Att Strength)":
            df_show = df_stats.sort_values(by="att_strength", ascending=False)
            st.bar_chart(df_show.set_index("name")["att_strength"])
        elif col_sort == "Obrana (Def Strength)":
            # U obrany je menší číslo lepší, ale pro graf chceme vidět "kvalitu", tak to můžeme otočit nebo nechat
            df_show = df_stats.sort_values(by="def_strength", ascending=True)
            st.bar_chart(df_show.set_index("name")["def_strength"])
        else:
            df_show = df_stats.sort_values(by="points", ascending=False)
            st.bar_chart(df_show.set_index("name")["points"])
            
        st.dataframe(df_show[["name", "played", "points", "att_strength", "def_strength"]], use_container_width=True)
