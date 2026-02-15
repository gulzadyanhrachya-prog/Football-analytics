import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

st.set_page_config(page_title="Fortuna Betting Model", layout="wide")

# --- 1. ZÍSKÁNÍ DAT (ClubElo API) ---\n@st.cache_data(ttl=3600)
def get_elo_data():
    # Stáhne aktuální Elo ratingy
    url = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    try:
        df = pd.read_csv(url)
        return df
    except:
        return None

# --- 2. MATEMATICKÉ MODELY ---\n
def calculate_win_prob_elo(elo_home, elo_away):
    dr = elo_home - elo_away + 100 # Domácí výhoda
    we = 1 / (10**(-dr/400) + 1)
    return we

def simulate_match_poisson(home_exp_goals, away_exp_goals):
    # Vytvoříme matici pravděpodobností 6x6 gólů
    max_goals = 6
    probs = np.zeros((max_goals, max_goals))
    
    for i in range(max_goals):
        for j in range(max_goals):
            prob_h = poisson.pmf(i, home_exp_goals)
            prob_a = poisson.pmf(j, away_exp_goals)
            probs[i, j] = prob_h * prob_a
            
    return probs

# --- 3. VÝPOČET SÁZKOVÝCH TRHŮ (FORTUNA) ---\n
def get_fair_odd(prob):
    if prob <= 0: return 0
    return 1 / prob

def calculate_markets(probs):
    # Základní pravděpodobnosti
    prob_home = np.sum(np.tril(probs, -1))
    prob_draw = np.sum(np.diag(probs))
    prob_away = np.sum(np.triu(probs, 1))
    
    # 1. Dvojitá šance
    prob_10 = prob_home + prob_draw
    prob_02 = prob_away + prob_draw
    prob_12 = prob_home + prob_away
    
    # 2. Over/Under (Počet gólů)
    prob_over_15 = 0; prob_under_15 = 0
    prob_over_25 = 0; prob_under_25 = 0
    prob_over_35 = 0; prob_under_35 = 0
    
    for i in range(probs.shape[0]):
        for j in range(probs.shape[1]):
            total_goals = i + j
            p = probs[i, j]
            
            if total_goals > 1.5: prob_over_15 += p
            else: prob_under_15 += p
            
            if total_goals > 2.5: prob_over_25 += p
            else: prob_under_25 += p
            
            if total_goals > 3.5: prob_over_35 += p
            else: prob_under_35 += p
            
    # 3. BTTS (Oba dají gól)
    # Suma pravděpodobností kde i > 0 a j > 0
    prob_btts_yes = 0
    for i in range(1, probs.shape[0]):
        for j in range(1, probs.shape[1]):
            prob_btts_yes += probs[i, j]
    prob_btts_no = 1 - prob_btts_yes
    
    return {
        "1": get_fair_odd(prob_home), "0": get_fair_odd(prob_draw), "2": get_fair_odd(prob_away),
        "10": get_fair_odd(prob_10), "02": get_fair_odd(prob_02), "12": get_fair_odd(prob_12),
        "Over 1.5": get_fair_odd(prob_over_15), "Under 1.5": get_fair_odd(prob_under_15),
        "Over 2.5": get_fair_odd(prob_over_25), "Under 2.5": get_fair_odd(prob_under_25),
        "Over 3.5": get_fair_odd(prob_over_35), "Under 3.5": get_fair_odd(prob_under_35),
        "BTTS Yes": get_fair_odd(prob_btts_yes), "BTTS No": get_fair_odd(prob_btts_no)
    }

# --- UI APLIKACE ---\n
st.title("⚽ Fortuna Betting Model (Elo + Poisson)")
st.markdown("Model vypočítá **férové kurzy** pro trhy, které najdeš na Fortuně.")

with st.spinner("Načítám data týmů..."):
    df = get_elo_data()

if df is not None:
    # Filtry
    countries = sorted(df['Country'].unique())
    
    c1, c2, c3 = st.columns(3)
    with c1:
        country_h = st.selectbox("Země (Domácí):", countries, index=countries.index("CZE") if "CZE" in countries else 0)
        teams_h = sorted(df[df['Country'] == country_h]['Club'].unique())
        home_team = st.selectbox("Tým (Domácí):", teams_h)
    with c2:
        country_a = st.selectbox("Země (Hosté):", countries, index=countries.index("CZE") if "CZE" in countries else 0)
        teams_a = sorted(df[df['Country'] == country_a]['Club'].unique())
        away_team = st.selectbox("Tým (Hosté):", teams_a)
    with c3:
        # Automatický odhad xG
        elo_h = df[df['Club'] == home_team]['Elo'].values[0]
        elo_a = df[df['Club'] == away_team]['Elo'].values[0]
        elo_diff = elo_h - elo_a + 100 
        
        # Model xG (zjednodušený)
        exp_xg_h = max(0.1, 1.45 + (elo_diff / 600))
        exp_xg_a = max(0.1, 1.15 - (elo_diff / 600))
        
        st.write("📊 **Nastavení xG (Očekávané góly)**")
        xg_h = st.number_input(f"xG {home_team}:", value=float(round(exp_xg_h, 2)), step=0.1)
        xg_a = st.number_input(f"xG {away_team}:", value=float(round(exp_xg_a, 2)), step=0.1)

    st.markdown("---")

    # Výpočty
    probs_matrix = simulate_match_poisson(xg_h, xg_a)
    odds = calculate_markets(probs_matrix)

    # --- ZOBRAZENÍ KURZŮ (FORTUNA STYLE) ---
    st.subheader("💰 Fortuna Sázkové Parametry (Férové kurzy)")
    st.caption("Porovnej tyto kurzy s nabídkou sázkové kanceláře. Pokud je kurz na Fortuně VYŠŠÍ než zde, je to Value Bet.")

    # 1. Hlavní sázka + Dvojitá šance
    col_main, col_dc = st.columns(2)
    
    with col_main:
        st.info("Zápas (1 - 0 - 2)")
        m1, m0, m2 = st.columns(3)
        m1.metric(f"Výhra {home_team}", f"{odds['1']:.2f}")
        m0.metric("Remíza", f"{odds['0']:.2f}")
        m2.metric(f"Výhra {away_team}", f"{odds['2']:.2f}")
        
    with col_dc:
        st.warning("Dvojitá šance (10 - 02 - 12)")
        d1, d2, d3 = st.columns(3)
        d1.metric("Neprohra Dom. (10)", f"{odds['10']:.2f}")
        d2.metric("Neprohra Host. (02)", f"{odds['02']:.2f}")
        d3.metric("Nikdo neremizuje (12)", f"{odds['12']:.2f}")

    # 2. Góly a BTTS
    col_goals, col_btts = st.columns(2)
    
    with col_goals:
        st.success("Počet gólů (Over / Under)")
        g1, g2 = st.columns(2)
        g1.write("**Více než (Over)**")
        g1.write(f"Over 1.5: **{odds['Over 1.5']:.2f}**")
        g1.write(f"Over 2.5: **{odds['Over 2.5']:.2f}**")
        g1.write(f"Over 3.5: **{odds['Over 3.5']:.2f}**")
        
        g2.write("**Méně než (Under)**")
        g2.write(f"Under 1.5: **{odds['Under 1.5']:.2f}**")
        g2.write(f"Under 2.5: **{odds['Under 2.5']:.2f}**")
        g2.write(f"Under 3.5: **{odds['Under 3.5']:.2f}**")
        
    with col_btts:
        st.error("Oba týmy dají gól (BTTS)")
        b1, b2 = st.columns(2)
        b1.metric("ANO (GG)", f"{odds['BTTS Yes']:.2f}")
        b2.metric("NE (NG)", f"{odds['BTTS No']:.2f}")
        
        st.markdown("#### 🔥 Nejpravděpodobnější přesné výsledky")
        # Najdeme top 3 výsledky v matici
        flat_indices = np.argsort(probs_matrix.ravel())[::-1] # Seřadit sestupně
        top_indices = flat_indices[:3]
        
        for idx in top_indices:
            score_h, score_a = np.unravel_index(idx, probs_matrix.shape)
            prob = probs_matrix[score_h, score_a] * 100
            odd = 100 / prob
            st.write(f"**{score_h}:{score_a}** (Šance: {prob:.1f}%) -> Kurz: **{odd:.2f}**")

    # --- HEATMAPA ---
    with st.expander("Zobrazit detailní Heatmapu pravděpodobností"):
        fig, ax = plt.subplots(figsize=(6, 4))
        sns.heatmap(probs_matrix, annot=True, fmt=".1%", cmap="YlGnBu", ax=ax,
                    xticklabels=[0,1,2,3,4,5], yticklabels=[0,1,2,3,4,5])
        ax.set_xlabel(f"Góly {away_team}")
        ax.set_ylabel(f"Góly {home_team}")
        st.pyplot(fig)

else:
    st.error("Chyba při načítání dat. Zkus obnovit stránku.")
