import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="Betting Auto-Pilot Stable", layout="wide")

# ==============================================================================\n# 1. MODUL: FOTBAL (ClubElo - Nejspolehlivější zdroj)\n# ==============================================================================\n
def app_fotbal():
    st.header("⚽ Fotbalový Auto-Pilot")
    st.caption("Zdroj: ClubElo (Oficiální data + Matematický model)")

    @st.cache_data(ttl=3600)
    def get_football_data():
        # Stáhne rozpis i s Elo ratingy v jednom souboru
        url = "http://api.clubelo.com/Fixtures"
        try:
            s = requests.get(url).content
            df = pd.read_csv(io.StringIO(s.decode('utf-8')))
            df['DateObj'] = pd.to_datetime(df['Date'])
            return df
        except: return None

    def calculate_probs(elo_h, elo_a):
        elo_diff = elo_h - elo_a + 100
        prob_h = 1 / (10**(-elo_diff/400) + 1)
        prob_a = 1 - prob_h
        prob_d = 0.25 
        if abs(prob_h - 0.5) < 0.1: prob_d = 0.30 
        
        real_h = prob_h * (1 - prob_d)
        real_a = prob_a * (1 - prob_d)
        
        # xG Model
        xg_h = max(0.5, 1.45 + (elo_diff / 500))
        xg_a = max(0.5, 1.15 - (elo_diff / 500))
        
        # Poisson pro góly
        max_g = 6
        matrix = np.zeros((max_g, max_g))
        for i in range(max_g):
            for j in range(max_g):
                matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
        
        prob_over_25 = 0
        prob_btts = 0
        for i in range(max_g):
            for j in range(max_g):
                if i + j > 2.5: prob_over_25 += matrix[i, j]
                if i > 0 and j > 0: prob_btts += matrix[i, j]
                
        return {"1": real_h, "0": prob_d, "2": real_a, "Over 2.5": prob_over_25, "BTTS": prob_btts}

    with st.spinner("Skenuji fotbalové zápasy..."):
        df = get_football_data()

    if df is not None:
        dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        limit = dnes + timedelta(days=4)
        mask = (df['DateObj'] >= dnes) & (df['DateObj'] <= limit)
        upcoming = df[mask].copy()
        
        if upcoming.empty:
            st.warning("Žádné zápasy v nejbližších dnech.")
        else:
            results = []
            for idx, row in upcoming.iterrows():
                try:
                    elo_h = row.get('EloHome')
                    elo_a = row.get('EloAway')
                    if pd.isna(elo_h) or pd.isna(elo_a): continue
                    
                    probs = calculate_probs(elo_h, elo_a)
                    
                    # Výběr nejlepší sázky
                    candidates = [
                        ("Výhra Domácích", probs["1"]),
                        ("Výhra Hostů", probs["2"]),
                        ("Over 2.5 Gólů", probs["Over 2.5"]),
                        ("BTTS (Oba dají gól)", probs["BTTS"])
                    ]
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    best_bet, conf = candidates[0]
                    
                    results.append({
                        "Datum": row['DateObj'].strftime("%d.%m. %H:%M"),
                        "Soutěž": row.get('Country', 'EU'),
                        "Zápas": f"{row['Home']} vs {row['Away']}",
                        "Tip": best_bet,
                        "Důvěra": conf * 100,
                        "Férový kurz": 1/conf if conf > 0 else 0
                    })
                except: continue
            
            df_res = pd.DataFrame(results).sort_values(by="Důvěra", ascending=False)
            
            st.subheader("🔥 TOP TIPY (Důvěra > 65%)")
            tutovky = df_res[df_res["Důvěra"] > 65]
            if not tutovky.empty:
                st.dataframe(tutovky.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
            else:
                st.info("Žádné tutovky.")
                
