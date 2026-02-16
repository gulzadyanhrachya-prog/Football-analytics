import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="OddsBlaze Replica", layout="wide")

# ==============================================================================\n# POMOCNÉ FUNKCE (PROXY & MATH)\n# ==============================================================================\n
def get_html_via_proxy(url):
    proxy_url = f"https://corsproxy.io/?{url}"
    try:
        return requests.get(proxy_url, headers={"User-Agent": "Mozilla/5.0"})
    except: return None

def poisson_calc(home_xg, away_xg):
    max_g = 8
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg)
    
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    return prob_h, prob_d, prob_a

# ==============================================================================\n# 1. FOTBALOVÝ MODEL (ClubElo)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_football_opportunities():
    # Stáhneme data
    try:
        url = "http://api.clubelo.com/Fixtures"
        s = requests.get(url).content
        df = pd.read_csv(io.StringIO(s.decode('utf-8')))
        df['DateObj'] = pd.to_datetime(df['Date'])
    except: return []

    # Filtr na 3 dny
    dnes = datetime.now()
    limit = dnes + timedelta(days=3)
    mask = (df['DateObj'] >= dnes) & (df['DateObj'] <= limit)
    upcoming = df[mask].copy()
    
    opportunities = []
    
    for idx, row in upcoming.iterrows():
        try:
            elo_h = row['EloHome']
            elo_a = row['EloAway']
            
            # Výpočet xG z Elo
            elo_diff = elo_h - elo_a + 100
            xg_h = max(0.2, 1.35 + (elo_diff/500))
            xg_a = max(0.2, 1.35 - (elo_diff/500))
            
            ph, pd_raw, pa = poisson_calc(xg_h, xg_a)
            
            # Hledáme favorita
            if ph > 0.55:
                opportunities.append({
                    "Sport": "⚽ Fotbal",
                    "Liga": row['Country'],
                    "Čas": row['DateObj'].strftime("%d.%m. %H:%M"),
                    "Zápas": f"{row['Home']} vs {row['Away']}",
                    "Tip": "1 (Domácí)",
                    "Pravděpodobnost": ph,
                    "Férový Kurz": 1/ph
                })
            elif pa > 0.55:
                opportunities.append({
                    "Sport": "⚽ Fotbal",
                    "Liga": row['Country'],
                    "Čas": row['DateObj'].strftime("%d.%m. %H:%M"),
                    "Zápas": f"{row['Home']} vs {row['Away']}",
                    "Tip": "2 (Hosté)",
                    "Pravděpodobnost": pa,
                    "Férový Kurz": 1/pa
                })
        except: continue
        
    return opportunities

# ==============================================================================\n# 2. HOKEJOVÝ MODEL (NHL API)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_nhl_opportunities():
    try:
        # Statistiky
        r_stats = requests.get("https://api-web.nhle.com/v1/standings/now").json()
        team_stats = {}
        for t in r_stats['standings']:
            abbr = t['teamAbbrev']['default']
            gp = t['gamesPlayed']
            if gp > 0:
                team_stats[abbr] = {
                    "GF": t['goalFor']/gp,
                    "GA": t['goalAgainst']/gp
                }
        
        # Rozpis
        today = datetime.now().strftime("%Y-%m-%d")
        r_sch = requests.get(f"https://api-web.nhle.com/v1/schedule/{today}").json()
        
        opportunities = []
        avg_gf = 3.0 # Průměr ligy
        
        for day in r_sch['gameWeek']:
            for game in day['games']:
                h = game['homeTeam']['abbrev']
                a = game['awayTeam']['abbrev']
                
                if h in team_stats and a in team_stats:
                    # xG Model
                    xg_h = (team_stats[h]['GF'] * team_stats[a]['GA']) / avg_gf
                    xg_a = (team_stats[a]['GF'] * team_stats[h]['GA']) / avg_gf
                    
                    ph, pd_raw, pa = poisson_calc(xg_h, xg_a)
                    
                    # Moneyline (Vítěz do rozhodnutí)
                    ph_ml = ph + (pd_raw * 0.5)
                    pa_ml = pa + (pd_raw * 0.5)
                    
                    if ph_ml > 0.58:
                        opportunities.append({
                            "Sport": "🏒 NHL",
                            "Liga": "USA",
                            "Čas": day['date'],
                            "Zápas": f"{h} vs {a}",
                            "Tip": "Vítěz D (ML)",
                            "Pravděpodobnost": ph_ml,
                            "Férový Kurz": 1/ph_ml
                        })
                    elif pa_ml > 0.58:
                        opportunities.append({
                            "Sport": "🏒 NHL",
                            "Liga": "USA",
                            "Čas": day['date'],
                            "Zápas": f"{h} vs {a}",
                            "Tip": "Vítěz H (ML)",
                            "Pravděpodobnost": pa_ml,
                            "Férový Kurz": 1/pa_ml
                        })
        return opportunities
    except: return []

# ==============================================================================\n# 3. EVROPSKÝ HOKEJ (VitiSport Scraper)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_euro_hockey_opportunities():
    # Stáhneme hokejovou sekci VitiSportu
    url = "https://www.vitisport.cz/index.php?g=hokej&lang=en"
    r = get_html_via_proxy(url)
    
    if not r or r.status_code != 200: return []
    
    opportunities = []
    try:
        dfs = pd.read_html(r.text)
        main_df = max(dfs, key=len).astype(str)
        
        current_league = "Evropa"
        
        for idx, row in main_df.iterrows():
            col0 = str(row.iloc[0])
            col1 = str(row.iloc[1])
            
            # Detekce ligy
            if len(col0) > 2 and ("nan" in col1.lower() or col1 == col0):
                current_league = col0
                continue
                
            # Detekce zápasu
            if ":" in col0 and len(row) > 5:
                # VitiSport má sloupce s pravděpodobností (často index 5, 6, 7 nebo podobně)
                # Zkusíme najít tip
                tip = None
                prob = 0.0
                
                # Hledáme buňku, která obsahuje "1", "2" a není to skóre
                row_vals = row.values.tolist()
                
                # Jednoduchá heuristika: Pokud VitiSport dává tip, věříme mu
                # Hledáme sloupec s tipem
                found_tip = False
                for val in row_vals:
                    if val in ["1", "2"]:
                        tip = val
                        found_tip = True
                        break
                
                if found_tip:
                    # Odhadneme pravděpodobnost (VitiSport tipuje obvykle nad 50%)
                    # Pro účely OddsBlaze modelu dáme konzervativní odhad
                    prob = 0.55 
                    
                    opportunities.append({
                        "Sport": "🏒 Hokej",
                        "Liga": current_league,
                        "Čas": col0,
                        "Zápas": f"{row.iloc[1]} vs {row.iloc[2]}",
                        "Tip": f"Výhra {tip}",
                        "Pravděpodobnost": prob,
                        "Férový Kurz": 1.80 # Odhad pro VitiSport tipy
                    })
    except: pass
    
    return opportunities

# ==============================================================================\n# UI APLIKACE (OddsBlaze Style)\n# ==============================================================================\n
st.title("🔥 OddsBlaze Replica (EV Scanner)")
st.markdown("""
**Jak to funguje:** Tento nástroj skenuje fotbalové a hokejové ligy a hledá zápasy, kde má jeden tým statistickou převahu.
**Cíl:** Najít sázku, kde je kurz sázkovky vyšší než náš "Target Kurz".
""")

# 1. Sběr dat
with st.spinner("Skenuji trhy (Fotbal, NHL, Evropský Hokej)..."):
    opps_football = get_football_opportunities()
    opps_nhl = get_nhl_opportunities()
    opps_euro = get_euro_hockey_opportunities()
    
    all_opps = opps_football + opps_nhl + opps_euro

# 2. Zpracování do DataFrame
if all_opps:
    df = pd.DataFrame(all_opps)
    
    # Přidáme sloupec "Target Kurz" (Férový kurz + 5% marže pro jistotu)
    df["Target Kurz"] = df["Férový Kurz"] * 1.05
    
    # Seřadíme podle pravděpodobnosti (Důvěry)
    df = df.sort_values(by="Pravděpodobnost", ascending=False)
    
    # --- FILTRY ---
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        sport_filter = st.multiselect("Filtrovat Sport:", df["Sport"].unique(), default=df["Sport"].unique())
    with col_f2:
        min_prob = st.slider("Minimální pravděpodobnost (%):", 50, 90, 60)
        
    # Aplikace filtrů
    df_filtered = df[
        (df["Sport"].isin(sport_filter)) & 
        (df["Pravděpodobnost"] * 100 >= min_prob)
    ].copy()
    
    # Formátování pro zobrazení
    st.subheader(f"Nalezeno {len(df_filtered)} hodnotných příležitostí")
    
    # Vytvoříme hezkou tabulku
    for index, row in df_filtered.iterrows():
        prob_perc = int(row['Pravděpodobnost'] * 100)
        fair_odd = row['Férový Kurz']
        target_odd = row['Target Kurz']
        
        # Barva podle síly signálu
        border_color = "green" if prob_perc > 70 else "orange"
        
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])
            
            with c1:
                st.write(f"**{row['Sport']}**")
                st.caption(row['Liga'])
                
            with c2:
                st.write(f"**{row['Čas']}**")
                st.write(row['Zápas'])
                
            with c3:
                st.metric("Náš Tip", row['Tip'])
                
            with c4:
                st.metric("Pravděpodobnost", f"{prob_perc}%")
                
            with c5:
                st.metric("Target Kurz", f"{target_odd:.2f}", help="Vsaď, pokud je kurz sázkovky vyšší než toto číslo.")
                
            st.markdown("---")

else:
    st.warning("Nebyly nalezeny žádné příležitosti. Zkus to později.")

# --- VYSVĚTLIVKY ---
with st.expander("ℹ️ Jak číst tuto tabulku (OddsBlaze Metodika)"):
    st.write("""
    1.  **Pravděpodobnost:** Jak moc si je náš model jistý výsledkem.
    2.  **Target Kurz:** Toto je klíčová hodnota. Je to náš férový kurz navýšený o malou rezervu (5%).
    3.  **Strategie:** Otevři si svou sázkovku (Fortuna, Tipsport). Podívej se na kurz pro daný tip.
        *   Pokud je kurz sázkovky **VYŠŠÍ** než Target Kurz -> **VSADIT (Value Bet)**.
        *   Pokud je kurz sázkovky **NIŽŠÍ** -> **NEVSÁZET**.
    """)
