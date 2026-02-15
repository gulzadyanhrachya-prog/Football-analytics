import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="Betting Auto-Pilot", layout="wide")

# --- 1. ZÍSKÁNÍ DAT (ClubElo Fixtures) ---
@st.cache_data(ttl=3600)
def get_fixtures():
    # Stáhne oficiální rozpis zápasů s Elo ratingy
    url = "http://api.clubelo.com/Fixtures"
    try:
        s = requests.get(url).content
        df = pd.read_csv(io.StringIO(s.decode('utf-8')))
        return df
    except:
        return None

# --- 2. MATEMATICKÉ MODELY ---
def calculate_probs(elo_h, elo_a):
    # 1. Výhra (Elo)
    elo_diff = elo_h - elo_a + 100 # Domácí výhoda
    prob_h_win = 1 / (10**(-elo_diff/400) + 1)
    prob_a_win = 1 - prob_h_win
    
    # Korekce na remízu (zjednodušená)
    prob_draw = 0.25 
    if abs(prob_h_win - 0.5) < 0.1: prob_draw = 0.30 # Vyšší šance na remízu u vyrovnaných
    
    real_h = prob_h_win * (1 - prob_draw)
    real_a = prob_a_win * (1 - prob_draw)
    
    # 2. Góly (Poisson) - Odhad xG z Elo
    # Silnější tým dává více gólů
    exp_xg_h = max(0.5, 1.45 + (elo_diff / 500))
    exp_xg_a = max(0.5, 1.15 - (elo_diff / 500))
    
    # Matice pravděpodobností 0-5 gólů
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    # Over 2.5
    prob_over_25 = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            
    # BTTS (Both Teams To Score)
    prob_btts = 0
    for i in range(1, max_g):
        for j in range(1, max_g):
            prob_btts += matrix[i, j]
            
    return {
        "1": real_h,
        "0": prob_draw,
        "2": real_a,
        "Over 2.5": prob_over_25,
        "Under 2.5": 1 - prob_over_25,
        "BTTS Yes": prob_btts,
        "BTTS No": 1 - prob_btts
    }

# --- 3. LOGIKA VÝBĚRU NEJLEPŠÍ SÁZKY ---
def pick_best_bet(probs):
    # Definujeme prahy důvěry
    candidates = []
    
    # Hlavní trhy
    candidates.append(("Výhra Domácích (1)", probs["1"]))
    candidates.append(("Výhra Hostů (2)", probs["2"]))
    
    # Gólové trhy (jen pokud je vysoká pravděpodobnost)
    candidates.append(("Over 2.5 Gólů", probs["Over 2.5"]))
    candidates.append(("Under 2.5 Gólů", probs["Under 2.5"]))
    candidates.append(("Oba dají gól (BTTS)", probs["BTTS Yes"]))
    
    # Dvojitá šance (pro jistotu)
    prob_10 = probs["1"] + probs["0"]
    prob_02 = probs["2"] + probs["0"]
    
    # Vybereme tu s nejvyšším procentem, ale preferujeme hlavní trhy
    # Seřadíme podle pravděpodobnosti sestupně
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    best_bet = candidates[0]
    
    # Pokud je nejlepší sázka příliš riskantní (< 50%), zkusíme dvojitou šanci
    if best_bet[1] < 0.50:
        if prob_10 > prob_02:
            return "Neprohra Domácích (10)", prob_10
        else:
            return "Neprohra Hostů (02)", prob_02
            
    return best_bet[0], best_bet[1]

# --- UI APLIKACE ---
st.title("🤖 Betting Auto-Pilot")
st.markdown("""
Tato aplikace automaticky skenuje nadcházející zápasy v Evropě, 
počítá pravděpodobnosti pomocí **Elo & Poisson modelu** a vybírá **nejlepší sázku** pro každý zápas.
""")

with st.spinner("Skenuji evropské trávníky a počítám predikce..."):
    df = get_fixtures()

if df is not None:
    # Zpracování data
    df['DateObj'] = pd.to_datetime(df['Date'])
    dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    zitra = dnes + timedelta(days=1)
    pozitri = dnes + timedelta(days=2)
    limit = dnes + timedelta(days=4) # Koukáme na 4 dny dopředu
    
    # Filtr na nadcházející zápasy
    mask = (df['DateObj'] >= dnes) & (df['DateObj'] <= limit)
    upcoming = df[mask].copy()
    
    if upcoming.empty:
        st.warning("V nejbližších dnech nejsou v databázi žádné zápasy.")
    else:
        # --- HLAVNÍ VÝPOČETNÍ SMYČKA ---
        results = []
        
        progress_bar = st.progress(0)
        total_rows = len(upcoming)
        
        for i, (idx, row) in enumerate(upcoming.iterrows()):
            # Aktualizace progress baru (jen pro efekt, aby uživatel věděl, že se něco děje)
            if i % 10 == 0: progress_bar.progress(min(i / total_rows, 1.0))
            
            try:
                elo_h = row['EloHome']
                elo_a = row['EloAway']
                
                # Výpočet všech pravděpodobností
                probs = calculate_probs(elo_h, elo_a)
                
                # Výběr nejlepší sázky
                bet_name, confidence = pick_best_bet(probs)
                
                # Férový kurz
                fair_odd = 1 / confidence if confidence > 0 else 0
                
                results.append({
                    "Datum": row['DateObj'].strftime("%d.%m. %H:%M"),
                    "Soutěž": row['Country'],
                    "Zápas": f"{row['Home']} vs {row['Away']}",
                    "DOPORUČENÁ SÁZKA": bet_name,
                    "Důvěra": confidence * 100,
                    "Férový kurz": fair_odd,
                    "Elo Rozdíl": abs(elo_h - elo_a)
                })
            except:
                continue
        
        progress_bar.empty()
        
        # Převod na DataFrame
        df_res = pd.DataFrame(results)
        
        # --- FILTRY A ZOBRAZENÍ ---
        
        # 1. TOP TUTOVKY (Důvěra > 70%)
        st.header("🔥 TOP TUTOVKY (Důvěra > 70%)")
        st.caption("Zápasy s nejvyšší pravděpodobností úspěchu. Ideální do AKO tiketů.")
        
        tutovky = df_res[df_res["Důvěra"] >= 70].sort_values(by="Důvěra", ascending=False)
        
        if not tutovky.empty:
            st.dataframe(
                tutovky.style.format({
                    "Důvěra": "{:.1f} %",
                    "Férový kurz": "{:.2f}",
                    "Elo Rozdíl": "{:.0f}"
                }),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("Dnes žádné extrémní tutovky (nad 70%). Podívej se níže na standardní tipy.")
            
        # 2. VALUE TIPY (Důvěra 55% - 70%)
        st.header("💡 CHYTRÉ SÁZKY (Důvěra 55% - 70%)")
        st.caption("Zápasy, kde je favorit, ale kurz bude zajímavější (okolo 1.50 - 1.80).")
        
        smart_tips = df_res[(df_res["Důvěra"] < 70) & (df_res["Důvěra"] >= 55)].sort_values(by="Důvěra", ascending=False)
        
        # Filtr podle země (volitelný)
        zeme_list = ["Vše"] + sorted(smart_tips["Soutěž"].unique().tolist())
        vybrana_zeme = st.selectbox("Filtrovat podle země:", zeme_list)
        
        if vybrana_zeme != "Vše":
            smart_tips = smart_tips[smart_tips["Soutěž"] == vybrana_zeme]
            
        st.dataframe(
            smart_tips.style.format({
                "Důvěra": "{:.1f} %",
                "Férový kurz": "{:.2f}",
                "Elo Rozdíl": "{:.0f}"
            }),
            hide_index=True,
            use_container_width=True
        )
        
        # 3. GÓLOVÉ TIPY (Speciál)
        st.header("⚽ GÓLOVÉ SPECIÁLY")
        st.caption("Zápasy, kde model predikuje hodně gólů (Over 2.5) nebo BTTS.")
        
        goal_tips = df_res[df_res["DOPORUČENÁ SÁZKA"].str.contains("Over|BTTS")].sort_values(by="Důvěra", ascending=False)
        
        if not goal_tips.empty:
            st.dataframe(
                goal_tips.style.format({
                    "Důvěra": "{:.1f} %",
                    "Férový kurz": "{:.2f}"
                }),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("Model nenašel žádné silné gólové příležitosti.")

else:
    st.error("Nepodařilo se načíst data z ClubElo.")
