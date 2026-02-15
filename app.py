import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

st.set_page_config(page_title="Pro Football Analytics Model", layout="wide")

# --- 1. ZÍSKÁNÍ DAT (ClubElo API) ---
@st.cache_data(ttl=3600)
def get_elo_data():
    # ClubElo poskytuje CSV s aktuálním Elo ratingem pro všechny týmy v Evropě
    # Funguje to vždy, žádné blokování
    url = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    
    try:
        df = pd.read_csv(url)
        return df
    except:
        return None

# --- 2. MATEMATICKÉ MODELY ---

def calculate_win_prob_elo(elo_home, elo_away):
    # Základní vzorec pro Elo pravděpodobnost
    dr = elo_home - elo_away + 100 # +100 bodů výhoda domácího prostředí
    we = 1 / (10**(-dr/400) + 1)
    return we

def simulate_match_poisson(home_exp_goals, away_exp_goals):
    # Poissonovo rozdělení pro výpočet přesného skóre
    # Vytvoříme matici 5x5 gólů
    max_goals = 6
    probs = np.zeros((max_goals, max_goals))
    
    for i in range(max_goals):
        for j in range(max_goals):
            prob_h = poisson.pmf(i, home_exp_goals)
            prob_a = poisson.pmf(j, away_exp_goals)
            probs[i, j] = prob_h * prob_a
            
    # Součet pravděpodobností
    prob_home_win = np.sum(np.tril(probs, -1))
    prob_draw = np.sum(np.diag(probs))
    prob_away_win = np.sum(np.triu(probs, 1))
    
    return prob_home_win, prob_draw, prob_away_win, probs

# --- UI APLIKACE ---

st.title("⚽ Advanced Football Analytics Model (2025/2026)")
st.markdown("""
Tento nástroj používá **Elo Rating** a **Poissonovo rozdělení** k modelování zápasů.
Simuluje **xG (Očekávané góly)** na základě síly týmů a hledá **Value Bet**.
""")

with st.spinner("Stahuji aktuální Elo ratingy z celé Evropy..."):
    df = get_elo_data()

if df is not None:
    # Filtry pro výběr týmů
    countries = sorted(df['Country'].unique())
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("1. Výběr Domácích")
        country_h = st.selectbox("Země (Domácí):", countries, index=countries.index("ENG") if "ENG" in countries else 0)
        teams_h = sorted(df[df['Country'] == country_h]['Club'].unique())
        home_team = st.selectbox("Tým (Domácí):", teams_h)
        
    with col2:
        st.subheader("2. Výběr Hostů")
        country_a = st.selectbox("Země (Hosté):", countries, index=countries.index("ENG") if "ENG" in countries else 0)
        teams_a = sorted(df[df['Country'] == country_a]['Club'].unique())
        away_team = st.selectbox("Tým (Hosté):", teams_a)
        
    with col3:
        st.subheader("3. Parametry Modelu")
        # Uživatel může upravit odhadované xG, pokud má lepší info (zranění atd.)
        elo_h = df[df['Club'] == home_team]['Elo'].values[0]
        elo_a = df[df['Club'] == away_team]['Elo'].values[0]
        
        # Automatický odhad xG na základě rozdílu Elo
        elo_diff = elo_h - elo_a + 100 # Domácí výhoda
        expected_xg_h = 1.4 + (elo_diff / 500)
        expected_xg_a = 1.1 - (elo_diff / 500)
        
        # Ochrana proti záporným gólům
        expected_xg_h = max(0.1, expected_xg_h)
        expected_xg_a = max(0.1, expected_xg_a)
        
        xg_h_input = st.number_input("Odhadované xG (Domácí):", value=float(round(expected_xg_h, 2)), step=0.1)
        xg_a_input = st.number_input("Odhadované xG (Hosté):", value=float(round(expected_xg_a, 2)), step=0.1)

    st.markdown("---")

    # --- VÝPOČTY ---
    
    # 1. Elo Probabilities
    elo_prob_h = calculate_win_prob_elo(elo_h, elo_a)
    
    # 2. Poisson Probabilities
    p_h, p_d, p_a, score_matrix = simulate_match_poisson(xg_h_input, xg_a_input)
    
    # 3. Fair Odds (Férové kurzy)
    odd_h = 1 / p_h if p_h > 0 else 0
    odd_d = 1 / p_d if p_d > 0 else 0
    odd_a = 1 / p_a if p_a > 0 else 0

    # --- VIZUALIZACE VÝSLEDKŮ ---
    
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("📊 Analýza Síly (Elo)")
        st.write(f"**{home_team}**: {int(elo_h)}")
        st.write(f"**{away_team}**: {int(elo_a)}")
        
        delta = int(elo_h - elo_a)
        if delta > 0:
            st.success(f"Domácí jsou silnější o {delta} bodů")
        else:
            st.error(f"Hosté jsou silnější o {abs(delta)} bodů")
            
        st.markdown("### 🎯 Predikce (Poisson)")
        st.metric("Pravděpodobnost Výhry Domácích", f"{p_h*100:.1f} %")
        st.metric("Pravděpodobnost Remízy", f"{p_d*100:.1f} %")
        st.metric("Pravděpodobnost Výhry Hostů", f"{p_a*100:.1f} %")

    with c2:
        st.subheader("💰 Value Betting (Férové Kurzy)")
        st.info("Zadej kurz sázkové kanceláře a zjisti, zda se vyplatí vsadit.")
        
        kc1, kc2, kc3 = st.columns(3)
        kc1.metric("Férový kurz 1", f"{odd_h:.2f}")
        kc2.metric("Férový kurz X", f"{odd_d:.2f}")
        kc3.metric("Férový kurz 2", f"{odd_a:.2f}")
        
        # Input pro sázkovku
        market_odd = st.number_input("Kurz sázkovky na tvůj tip:", value=2.0, step=0.01)
        my_fair_odd = st.radio("Na co chceš sázet?", ["Výhra Domácí", "Remíza", "Výhra Hosté"])
        
        target_odd = odd_h if my_fair_odd == "Výhra Domácí" else (odd_d if my_fair_odd == "Remíza" else odd_a)
        
        if market_odd > target_odd:
            value = (market_odd / target_odd) - 1
            st.success(f"✅ **VALUE BET!** Sázkovka nabízí {market_odd}, ale férový kurz je {target_odd:.2f}. Hodnota: {value*100:.1f}%")
        else:
            st.error(f"❌ **NEVSÁZET.** Kurz je příliš nízký. Potřebuješ alespoň {target_odd:.2f}.")

    # --- HEATMAPA SKÓRE ---
    st.markdown("---")
    st.subheader("🔥 Pravděpodobnost Přesného Výsledku (Heatmapa)")
    
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(score_matrix, annot=True, fmt=".1%", cmap="YlGnBu", ax=ax,
                xticklabels=[0,1,2,3,4,5], yticklabels=[0,1,2,3,4,5])
    ax.set_xlabel(f"Góly {away_team}")
    ax.set_ylabel(f"Góly {home_team}")
    st.pyplot(fig)

else:
    st.error("Nepodařilo se načíst data z ClubElo. Zkus to za chvíli.")
