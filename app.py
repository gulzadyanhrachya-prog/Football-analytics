import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
import io
import urllib.parse

st.set_page_config(page_title="Betting Auto-Pilot v30 (Demo)", layout="wide")

# ==============================================================================
# 1. ROBUSTNÍ NAČÍTÁNÍ DAT (S DEMO REŽIMEM)
# ==============================================================================

@st.cache_data(ttl=3600)
def get_football_data_robust():
    url_direct = "http://api.clubelo.com/Fixtures"
    url_proxy = f"https://api.allorigins.win/get?url={urllib.parse.quote(url_direct)}"
    
    df = None
    status = "Nenačteno"

    # 1. Pokus o stažení
    try:
        r = requests.get(url_direct, timeout=5)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
            status = "✅ LIVE DATA (Direct)"
    except: pass

    # 2. Pokus přes proxy
    if df is None:
        try:
            r = requests.get(url_proxy, timeout=5)
            data = r.json()
            content = data.get("contents")
            if content:
                df = pd.read_csv(io.StringIO(content))
                status = "✅ LIVE DATA (Proxy)"
        except: pass

    # 3. DEMO DATA (Pokud vše selže)
    if df is None:
        status = "⚠️ DEMO DATA (Server nedostupný - Ukázka)"
        dnes = datetime.now()
        zitra = dnes + timedelta(days=1)
        
        # Vytvoříme fiktivní rozpis šlágrů pro ukázku funkčnosti
        data = {
            "Date": [
                dnes.strftime("%Y-%m-%d"), dnes.strftime("%Y-%m-%d"),
                dnes.strftime("%Y-%m-%d"), zitra.strftime("%Y-%m-%d"),
                zitra.strftime("%Y-%m-%d"), zitra.strftime("%Y-%m-%d")
            ],
            "Country": ["ENG", "ESP", "ITA", "GER", "FRA", "CZE"],
            "Home": ["Manchester City", "Real Madrid", "Inter Milan", "Bayern Munich", "PSG", "Sparta Praha"],
            "Away": ["Luton Town", "Barcelona", "Juventus", "Dortmund", "Marseille", "Slavia Praha"],
            "EloHome": [2050, 1980, 1950, 1920, 1850, 1650],
            "EloAway": [1600, 1970, 1940, 1880, 1800, 1640]
        }
        df = pd.DataFrame(data)

    # Zpracování data
    try:
        df['DateObj'] = pd.to_datetime(df['Date'])
    except: pass
        
    return df, status

# ==============================================================================
# 2. MATEMATICKÉ MODELY
# ==============================================================================

def calculate_probs(elo_h, elo_a):
    # Výhra (Elo)
    elo_diff = elo_h - elo_a + 100 
    prob_h_win = 1 / (10**(-elo_diff/400) + 1)
    prob_a_win = 1 - prob_h_win
    
    # Korekce na remízu
    prob_draw = 0.25 
    if abs(prob_h_win - 0.5) < 0.1: prob_draw = 0.30 
    
    real_h = prob_h_win * (1 - prob_draw)
    real_a = prob_a_win * (1 - prob_draw)
    
    # Góly (Poisson)
    exp_xg_h = max(0.5, 1.45 + (elo_diff / 500))
    exp_xg_a = max(0.5, 1.15 - (elo_diff / 500))
    
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    prob_over_25 = 0
    prob_btts = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "1": real_h, "0": prob_draw, "2": real_a,
        "Over 2.5": prob_over_25, "BTTS Yes": prob_btts,
        "xG_Home": exp_xg_h, "xG_Away": exp_xg_a, "Matrix": matrix
    }

def pick_best_bet(probs):
    candidates = [
        ("Výhra Domácích (1)", probs["1"]),
        ("Výhra Hostů (2)", probs["2"]),
        ("Over 2.5 Gólů", probs["Over 2.5"]),
        ("Oba dají gól (BTTS)", probs["BTTS Yes"])
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0], candidates[0][1]

# ==============================================================================
# 3. UI APLIKACE
# ==============================================================================

st.title("🤖 Betting Auto-Pilot (Ultimate)")

# --- FOTBAL ---\nst.header("⚽ Fotbal")

with st.spinner("Načítám data..."):
    df_fix, status_msg = get_football_data_robust()

# Indikátor stavu
if "DEMO" in status_msg:
    st.warning(f"Status: {status_msg}")
    st.info("ℹ️ Server s živými daty neodpovídá. Aplikace běží v ukázkovém režimu na simulovaných datech, abys viděl funkčnost.")
else:
    st.success(f"Status: {status_msg}")

if df_fix is not None:
    # Filtry
    dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    limit = dnes + timedelta(days=7) 
    
    # V Demo režimu ignorujeme datum, abychom vždy něco ukázali
    if "DEMO" in status_msg:
        upcoming = df_fix.copy()
    else:
        mask = (df_fix['DateObj'] >= dnes) & (df_fix['DateObj'] <= limit)
        upcoming = df_fix[mask].copy()
    
    if upcoming.empty:
        st.warning("Žádné zápasy.")
    else:
        results = []
        
        for i, (idx, row) in enumerate(upcoming.iterrows()):
            try:
                home, away = row['Home'], row['Away']
                elo_h = row.get('EloHome')
                elo_a = row.get('EloAway')
                
                if pd.isna(elo_h) or pd.isna(elo_a): continue

                probs = calculate_probs(elo_h, elo_a)
                bet_name, confidence = pick_best_bet(probs)
                fair_odd = 1 / confidence if confidence > 0 else 0
                
                results.append({
                    "Datum": row['DateObj'].strftime("%d.%m."),
                    "Soutěž": row.get('Country', 'EU'),
                    "Zápas": f"{home} vs {away}",
                    "DOPORUČENÁ SÁZKA": bet_name,
                    "Důvěra": confidence * 100,
                    "Férový kurz": fair_odd,
                    "Stats": probs, # Uložíme pro detail
                    "Domácí": home, "Hosté": away # Pro detail
                })
            except: continue
        
        df_res = pd.DataFrame(results)
        
        if not df_res.empty:
            # TABS
            tab1, tab2 = st.tabs(["📋 Seznam Tipů", "🔬 Detailní Analyzátor"])
            
            with tab1:
                st.subheader("🔥 TOP TIPY")
                df_show = df_res.sort_values(by="Důvěra", ascending=False)
                
                for idx, match in df_show.iterrows():
                    with st.container():
                        c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
                        with c1: st.write(f"**{match['Datum']}**"); st.caption(match['Soutěž'])
                        with c2: st.write(f"**{match['Zápas']}**")
                        with c3: 
                            st.write(f"**{match['DOPORUČENÁ SÁZKA']}**")
                            st.progress(match['Důvěra']/100)
                        with c4: st.metric("Kurz", f"{match['Férový kurz']:.2f}")
                        st.markdown("---")

            with tab2:
                st.subheader("🔬 Laboratoř")
                selected_match = st.selectbox("Vyber zápas:", df_res['Zápas'].unique())
                match_data = df_res[df_res['Zápas'] == selected_match].iloc[0]
                stats = match_data['Stats']
                
                c1, c2 = st.columns(2)
                with c1:
                    st.metric(f"xG {match_data['Domácí']}", f"{stats['xG_Home']:.2f}")
                    st.metric(f"xG {match_data['Hosté']}", f"{stats['xG_Away']:.2f}")
                with c2:
                    st.write("Pravděpodobnosti:")
                    st.write(f"1: {stats['1']*100:.1f}%")
                    st.write(f"0: {stats['0']*100:.1f}%")
                    st.write(f"2: {stats['2']*100:.1f}%")
                
                fig, ax = plt.subplots(figsize=(6, 4))
                sns.heatmap(stats['Matrix'], annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
                st.pyplot(fig)

        else: st.warning("Chyba výpočtu.")
else:
    st.error("Kritická chyba.")

# --- HOKEJ (NHL) ---\nst.markdown("---")
st.header("🏒 NHL (Live Data)")

@st.cache_data(ttl=3600)
def get_nhl_data():
    try:
        r_stats = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=5).json()
        stats = {}
        for t in r_stats['standings']:
            stats[t['teamAbbrev']['default']] = {
                "GF": t['goalFor']/t['gamesPlayed'],
                "GA": t['goalAgainst']/t['gamesPlayed']
            }
        
        today = datetime.now().strftime("%Y-%m-%d")
        r_sch = requests.get(f"https://api-web.nhle.com/v1/schedule/{today}", timeout=5).json()
        
        matches = []
        avg_gf = 3.0
        
        for day in r_sch['gameWeek']:
            for game in day['games']:
                h = game['homeTeam']['abbrev']
                a = game['awayTeam']['abbrev']
                if h in stats and a in stats:
                    xg_h = (stats[h]['GF'] * stats[a]['GA']) / avg_gf * 1.05
                    xg_a = (stats[a]['GF'] * stats[h]['GA']) / avg_gf
                    
                    max_g = 10
                    matrix = np.zeros((max_g, max_g))
                    for i in range(max_g):
                        for j in range(max_g):
                            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
                    
                    prob_h = np.sum(np.tril(matrix, -1)) + (np.sum(np.diag(matrix)) * 0.5)
                    prob_a = np.sum(np.triu(matrix, 1)) + (np.sum(np.diag(matrix)) * 0.5)
                    
                    tip = f"Výhra {h}" if prob_h > prob_a else f"Výhra {a}"
                    conf = max(prob_h, prob_a)
                    
                    matches.append({
                        "Datum": day['date'],
                        "Zápas": f"{h} vs {a}",
                        "Tip": tip,
                        "Důvěra": conf * 100,
                        "Férový kurz": 1/conf
                    })
        return matches
    except: return []

matches = get_nhl_data()
if matches:
    df = pd.DataFrame(matches).sort_values(by="Důvěra", ascending=False)
    st.dataframe(df.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
else:
    st.info("Žádné zápasy NHL v nejbližších dnech.")
