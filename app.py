import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
import requests

st.set_page_config(page_title="Betting Fortress v39", layout="wide")

# ==============================================================================
# 1. INTERNÍ DATABÁZE ELO (ZÁCHRANA)
# ==============================================================================
# Toto zajišťuje, že aplikace funguje i bez API.
# Hodnoty jsou přibližné Elo ratingy k roku 2025.

INTERNAL_DB = {
    # ANGLIE
    "Man City": 2050, "Liverpool": 2000, "Arsenal": 1980, "Chelsea": 1850, 
    "Man Utd": 1820, "Tottenham": 1830, "Aston Villa": 1800, "Newcastle": 1780,
    "West Ham": 1750, "Brighton": 1740, "Everton": 1700, "Fulham": 1680,
    # ŠPANĚLSKO
    "Real Madrid": 1990, "Barcelona": 1950, "Atletico Madrid": 1880, "Girona": 1790,
    "Real Sociedad": 1780, "Bilbao": 1770, "Betis": 1750, "Sevilla": 1740,
    # NĚMECKO
    "Bayern Munich": 1960, "Leverkusen": 1920, "Dortmund": 1850, "RB Leipzig": 1840,
    "Stuttgart": 1780, "Frankfurt": 1750, "Wolfsburg": 1700,
    # ITÁLIE
    "Inter": 1940, "Juventus": 1860, "AC Milan": 1850, "Atalanta": 1840,
    "Napoli": 1820, "Roma": 1790, "Lazio": 1780, "Fiorentina": 1750,
    # FRANCIE
    "PSG": 1880, "Monaco": 1780, "Lille": 1760, "Lens": 1700, "Marseille": 1750,
    # OSTATNÍ EVROPA
    "Benfica": 1810, "Sporting CP": 1800, "Porto": 1790, "Braga": 1750,
    "PSV": 1800, "Feyenoord": 1780, "Ajax": 1750, "AZ Alkmaar": 1700,
    "Sparta Praha": 1680, "Slavia Praha": 1690, "Plzeň": 1620, "Baník Ostrava": 1500,
    "Galatasaray": 1720, "Fenerbahce": 1710, "Besiktas": 1680,
    "Celtic": 1650, "Rangers": 1640, "Salzburg": 1600,
    "Copenhagen": 1600, "Midtjylland": 1580,
    "Olympiacos": 1650, "PAOK": 1640, "AEK": 1630
}

# ==============================================================================
# 2. MATEMATICKÉ MODELY (POISSON)
# ==============================================================================

def calculate_prediction(elo_h, elo_a):
    # 1. Výpočet pravděpodobnosti výhry z Elo
    elo_diff = elo_h - elo_a + 100 # Domácí výhoda
    
    # 2. Odhad xG (Očekávané góly)
    # Průměrný tým má xG cca 1.35. Silnější tým více.
    exp_xg_h = max(0.2, 1.45 + (elo_diff / 500))
    exp_xg_a = max(0.2, 1.15 - (elo_diff / 500))
    
    # 3. Poissonova simulace (Matice skóre)
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    # 4. Sumarizace pravděpodobností
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    
    # 5. Odvozené sázky
    prob_over_25 = 0
    prob_btts = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "1": prob_h, "0": prob_d, "2": prob_a,
        "Over 2.5": prob_over_25, "BTTS": prob_btts,
        "xG_H": exp_xg_h, "xG_A": exp_xg_a,
        "Matrix": matrix
    }

# ==============================================================================
# 3. API FUNKCE (TheSportsDB - Best Effort)
# ==============================================================================

@st.cache_data(ttl=3600)
def get_live_schedule(league_id):
    # Použijeme TheSportsDB (Next 15 events)
    url = f"https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php?id={league_id}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json().get("events", [])
        return []
    except: return []

# ==============================================================================
# 4. UI APLIKACE
# ==============================================================================

st.title("🏰 Betting Fortress (Analytik)")

# TABS
tab_calc, tab_live = st.tabs(["🧮 Nezničitelná Kalkulačka", "📅 Live Rozpis (Beta)"])

# --- TAB 1: KALKULAČKA (VŽDY FUNKČNÍ) ---
with tab_calc:
    st.header("Manuální Analýza")
    st.caption("Vyber dva týmy z databáze a získej okamžitou predikci.")
    
    col_sel1, col_sel2 = st.columns(2)
    teams_sorted = sorted(list(INTERNAL_DB.keys()))
    
    with col_sel1:
        home = st.selectbox("Domácí tým:", teams_sorted, index=teams_sorted.index("Sparta Praha") if "Sparta Praha" in teams_sorted else 0)
    with col_sel2:
        away = st.selectbox("Hostující tým:", teams_sorted, index=teams_sorted.index("Slavia Praha") if "Slavia Praha" in teams_sorted else 1)
        
    if st.button("🔮 Vypočítat Predikci", type="primary"):
        elo_h = INTERNAL_DB[home]
        elo_a = INTERNAL_DB[away]
        
        res = calculate_prediction(elo_h, elo_a)
        
        # Hlavní karta
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        
        # Určení favorita
        best_prob = max(res['1'], res['0'], res['2'])
        if res['1'] == best_prob: 
            tip_text = f"Výhra {home}"; tip_color = "green"
        elif res['2'] == best_prob: 
            tip_text = f"Výhra {away}"; tip_color = "red"
        else: 
            tip_text = "Remíza"; tip_color = "orange"
            
        with c1:
            st.markdown(f"### Tip: :{tip_color}[{tip_text}]")
            st.caption(f"Důvěra: {best_prob*100:.1f}%")
            
        with c2:
            st.metric("Férový kurz", f"{1/best_prob:.2f}")
            
        with c3:
            st.metric("Očekávané góly (xG)", f"{res['xG_H']:.2f} : {res['xG_A']:.2f}")
            
        # Detailní trhy
        st.subheader("💰 Sázkové příležitosti")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("1 (Domácí)", f"{res['1']*100:.0f}%", f"Kurz: {1/res['1']:.2f}")
        d2.metric("0 (Remíza)", f"{res['0']*100:.0f}%", f"Kurz: {1/res['0']:.2f}")
        d3.metric("2 (Hosté)", f"{res['2']*100:.0f}%", f"Kurz: {1/res['2']:.2f}")
        d4.metric("Over 2.5", f"{res['Over 2.5']*100:.0f}%", f"Kurz: {1/res['Over 2.5']:.2f}")
        
        # Heatmapa
        with st.expander("Zobrazit pravděpodobnost přesného výsledku"):
            fig, ax = plt.subplots(figsize=(6, 3))
            sns.heatmap(res['Matrix'], annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
            ax.set_xlabel(away); ax.set_ylabel(home)
            st.pyplot(fig)

# --- TAB 2: LIVE ROZPIS (POKUS O API) ---
with tab_live:
    st.header("Live Rozpis (TheSportsDB)")
    st.caption("Pokusí se stáhnout nadcházející zápasy. Pokud data chybí, použij Kalkulačku.")
    
    LEAGUES_TSDB = {
        "🇬🇧 Premier League": "4328", "🇪🇸 La Liga": "4335", "🇩🇪 Bundesliga": "4331",
        "🇮🇹 Serie A": "4332", "🇫🇷 Ligue 1": "4334", "🇨🇿 Fortuna Liga": "4352",
        "🇵🇱 Ekstraklasa": "4353", "🇺🇸 MLS": "4346", "🇪🇺 Liga Mistrů": "4480"
    }
    
    sel_league = st.selectbox("Vyber ligu:", list(LEAGUES_TSDB.keys()))
    
    if st.button("Stáhnout rozpis"):
        events = get_live_schedule(LEAGUES_TSDB[sel_league])
        
        if not events:
            st.warning("API nevrátilo žádné zápasy pro tuto ligu (mimo sezónu nebo chyba API).")
        else:
            st.success(f"Nalezeno {len(events)} zápasů.")
            
            for e in events:
                home_team = e['strHomeTeam']
                away_team = e['strAwayTeam']
                date = e['dateEvent']
                
                # Zkusíme najít týmy v naší DB (Fuzzy match)
                elo_h = 1500 # Default
                elo_a = 1500
                found_h = False
                found_a = False
                
                for db_name, db_elo in INTERNAL_DB.items():
                    # Jednoduché porovnání částí názvu
                    if db_name.split(" ")[-1] in home_team: 
                        elo_h = db_elo; found_h = True
                    if db_name.split(" ")[-1] in away_team: 
                        elo_a = db_elo; found_a = True
                
                # Výpočet
                res = calculate_prediction(elo_h, elo_a)
                
                with st.container():
                    c1, c2, c3 = st.columns([1, 3, 2])
                    with c1: st.write(date)
                    with c2: st.write(f"**{home_team}** vs **{away_team}**")
                    with c3:
                        if found_h and found_a:
                            if res['1'] > 0.55: st.success(f"Tip: {home_team}")
                            elif res['2'] > 0.55: st.error(f"Tip: {away_team}")
                            else: st.warning("Vyrovnané")
                        else:
                            st.caption("Neznámá síla týmů")
                st.markdown("---")
