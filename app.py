import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Betting Auto-Pilot v33 (Offline)", layout="wide")

# ==============================================================================\n# 1. VESTAVĚNÁ DATABÁZE TÝMŮ (Elo Ratingy - Odhad 2025)\n# ==============================================================================\n
TEAMS_DB = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Manchester City": 2050, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Liverpool": 2000, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Arsenal": 1980,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Chelsea": 1850, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Man Utd": 1820, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Tottenham": 1830,
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Aston Villa": 1800, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Newcastle": 1780, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 West Ham": 1750,
    
    "🇪🇸 Real Madrid": 1990, "🇪🇸 Barcelona": 1950, "🇪🇸 Atletico Madrid": 1880,
    "🇪🇸 Girona": 1790, "🇪🇸 Real Sociedad": 1780, "🇪🇸 Bilbao": 1770,
    
    "🇩🇪 Bayern Munich": 1960, "🇩🇪 Leverkusen": 1920, "🇩🇪 Dortmund": 1850,
    "🇩🇪 RB Leipzig": 1840, "🇩🇪 Stuttgart": 1780,
    
    "🇮🇹 Inter Milan": 1940, "🇮🇹 Juventus": 1860, "🇮🇹 AC Milan": 1850,
    "🇮🇹 Atalanta": 1840, "🇮🇹 Napoli": 1820, "🇮🇹 Roma": 1790,
    
    "🇫🇷 PSG": 1880, "🇫🇷 Monaco": 1780, "🇫🇷 Lille": 1760,
    
    "🇵🇹 Benfica": 1810, "🇵🇹 Porto": 1800, "🇵🇹 Sporting": 1790,
    "🇳🇱 PSV": 1800, "🇳🇱 Feyenoord": 1780, "🇳🇱 Ajax": 1750,
    
    "🇨🇿 Sparta Praha": 1680, "🇨🇿 Slavia Praha": 1690, "🇨🇿 Plzeň": 1620,
    "🇨🇿 Baník Ostrava": 1500,
    
    "🇹🇷 Galatasaray": 1700, "🇹🇷 Fenerbahce": 1710,
    "🇬🇷 Olympiacos": 1650, "🇬🇷 PAOK": 1640
}

# ==============================================================================\n# 2. MATEMATICKÉ MODELY\n# ==============================================================================\n
def calculate_probs(elo_h, elo_a):
    # Výhra (Elo)
    elo_diff = elo_h - elo_a + 100 # Domácí výhoda
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

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("🤖 Betting Auto-Pilot (Offline Mode)")
st.info("ℹ️ Server ClubElo má výpadek. Aplikace běží v nezávislém režimu s interní databází.")

tabs = st.tabs(["⚔️ Duel (Vyber týmy)", "🎲 Generátor Tipů"])

# --- TAB 1: DUEL ---
with tabs[0]:
    st.header("Analyzátor Zápasu")
    
    c1, c2 = st.columns(2)
    with c1:
        home_team = st.selectbox("Domácí tým:", list(TEAMS_DB.keys()), index=0)
    with c2:
        # Abychom nevybrali stejný tým, vyfiltrujeme ho
        away_options = [t for t in TEAMS_DB.keys() if t != home_team]
        away_team = st.selectbox("Hostující tým:", away_options, index=0)
        
    if st.button("Analyzovat Zápas"):
        elo_h = TEAMS_DB[home_team]
        elo_a = TEAMS_DB[away_team]
        
        stats = calculate_probs(elo_h, elo_a)
        best_bet, conf = pick_best_bet(stats)
        fair_odd = 1/conf
        
        # Výsledky
        st.markdown("---")
        res_c1, res_c2, res_c3 = st.columns(3)
        
        with res_c1:
            st.metric("Doporučená sázka", best_bet)
        with res_c2:
            st.metric("Důvěra modelu", f"{conf*100:.1f} %")
        with res_c3:
            st.metric("Férový kurz", f"{fair_odd:.2f}")
            
        # Detaily
        with st.expander("📊 Zobrazit detailní pravděpodobnosti", expanded=True):
            d1, d2 = st.columns(2)
            with d1:
                st.write("**Hlavní trhy:**")
                st.write(f"Výhra Domácí: {stats['1']*100:.1f}% (Kurz {1/stats['1']:.2f})")
                st.write(f"Remíza: {stats['0']*100:.1f}% (Kurz {1/stats['0']:.2f})")
                st.write(f"Výhra Hosté: {stats['2']*100:.1f}% (Kurz {1/stats['2']:.2f})")
            with d2:
                st.write("**Góly:**")
                st.write(f"Over 2.5: {stats['Over 2.5']*100:.1f}%")
                st.write(f"BTTS (Oba dají gól): {stats['BTTS Yes']*100:.1f}%")
                st.write(f"xG: {stats['xG_Home']:.2f} vs {stats['xG_Away']:.2f}")
                
        # Graf
        fig, ax = plt.subplots(figsize=(6, 3))
        sns.heatmap(stats['Matrix'], annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
        ax.set_title("Pravděpodobnost přesného skóre")
        ax.set_xlabel(away_team)
        ax.set_ylabel(home_team)
        st.pyplot(fig)

# --- TAB 2: GENERÁTOR ---
with tabs[1]:
    st.header("Generátor Sázkového Tiketu")
    st.write("Tato funkce náhodně vylosuje 10 zápasů z databáze a najde nejlepší sázky.")
    
    if st.button("🎲 Vygenerovat Tiket"):
        import random
        teams_list = list(TEAMS_DB.keys())
        results = []
        
        for _ in range(10):
            h = random.choice(teams_list)
            a = random.choice(teams_list)
            if h == a: continue
            
            elo_h = TEAMS_DB[h]
            elo_a = TEAMS_DB[a]
            
            stats = calculate_probs(elo_h, elo_a)
            best_bet, conf = pick_best_bet(stats)
            
            results.append({
                "Zápas": f"{h} vs {a}",
                "Tip": best_bet,
                "Důvěra": conf * 100,
                "Férový kurz": 1/conf
            })
            
        df_res = pd.DataFrame(results).sort_values(by="Důvěra", ascending=False)
        
        st.subheader("🔥 TOP TIPY (Simulace)")
        st.dataframe(df_res.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
