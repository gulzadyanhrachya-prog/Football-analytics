import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io
import cloudscraper

st.set_page_config(page_title="Betting Auto-Pilot v15", layout="wide")

# ==============================================================================\n# MODUL 1: FOTBAL (ClubElo Math Model)\n# ==============================================================================\n
def app_fotbal():
    st.header("⚽ Fotbalový Auto-Pilot")
    st.caption("Zdroj: ClubElo API (Oficiální data + Matematický model)")

    @st.cache_data(ttl=3600)
    def get_data():
        url_fixtures = "http://api.clubelo.com/Fixtures"
        url_ratings = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
        df_fix, df_elo = None, None
        try:
            s_fix = requests.get(url_fixtures).content
            df_fix = pd.read_csv(io.StringIO(s_fix.decode('utf-8')))
        except: pass
        try:
            s_elo = requests.get(url_ratings).content
            df_elo = pd.read_csv(io.StringIO(s_elo.decode('utf-8')))
        except: pass
        return df_fix, df_elo

    def calculate_probs(elo_h, elo_a):
        elo_diff = elo_h - elo_a + 100
        prob_h_win = 1 / (10**(-elo_diff/400) + 1)
        prob_a_win = 1 - prob_h_win
        prob_draw = 0.25 
        if abs(prob_h_win - 0.5) < 0.1: prob_draw = 0.30 
        real_h = prob_h_win * (1 - prob_draw)
        real_a = prob_a_win * (1 - prob_draw)
        
        exp_xg_h = max(0.5, 1.45 + (elo_diff / 500))
        exp_xg_a = max(0.5, 1.15 - (elo_diff / 500))
        
        max_g = 6
        matrix = np.zeros((max_g, max_g))
        for i in range(max_g):
            for j in range(max_g):
                matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
                
        prob_over_25 = 0
        for i in range(max_g):
            for j in range(max_g):
                if i + j > 2.5: prob_over_25 += matrix[i, j]
        
        prob_btts = 0
        for i in range(1, max_g):
            for j in range(1, max_g):
                prob_btts += matrix[i, j]
                
        return {"1": real_h, "0": prob_draw, "2": real_a, "Over 2.5": prob_over_25, "BTTS": prob_btts}

    def pick_best_bet(probs):
        candidates = [
            ("Výhra Domácích (1)", probs["1"]),
            ("Výhra Hostů (2)", probs["2"]),
            ("Over 2.5 Gólů", probs["Over 2.5"]),
            ("Under 2.5 Gólů", 1 - probs["Over 2.5"]),
            ("Oba dají gól (BTTS)", probs["BTTS"])
        ]
        prob_10 = probs["1"] + probs["0"]
        prob_02 = probs["2"] + probs["0"]
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_bet = candidates[0]
        
        if best_bet[1] < 0.50:
            if prob_10 > prob_02: return "Neprohra Domácích (10)", prob_10
            else: return "Neprohra Hostů (02)", prob_02
        return best_bet[0], best_bet[1]

    with st.spinner("Počítám fotbalové predikce..."):
        df_fix, df_elo = get_data()

    if df_fix is not None:
        try: df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
        except: st.error("Chyba dat."); st.stop()

        dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        limit = dnes + timedelta(days=4) 
        mask = (df_fix['DateObj'] >= dnes) & (df_fix['DateObj'] <= limit)
        upcoming = df_fix[mask].copy()
        
        if upcoming.empty:
            st.warning("Žádné fotbalové zápasy v nejbližších dnech.")
        else:
            elo_dict = {}
            if df_elo is not None: elo_dict = df_elo.set_index('Club')['Elo'].to_dict()

            results = []
            for i, (idx, row) in enumerate(upcoming.iterrows()):
                try:
                    home, away = row['Home'], row['Away']
                    elo_h = row.get('EloHome')
                    elo_a = row.get('EloAway')
                    if (pd.isna(elo_h) or pd.isna(elo_a)) and df_elo is not None:
                        elo_h = elo_dict.get(home)
                        elo_a = elo_dict.get(away)
                    
                    if elo_h is None or elo_a is None: continue

                    probs = calculate_probs(elo_h, elo_a)
                    bet_name, confidence = pick_best_bet(probs)
                    fair_odd = 1 / confidence if confidence > 0 else 0
                    
                    results.append({
                        "Datum": row['DateObj'].strftime("%d.%m. %H:%M"),
                        "Soutěž": row.get('Country', 'EU'),
                        "Zápas": f"{home} vs {away}",
                        "DOPORUČENÁ SÁZKA": bet_name,
                        "Důvěra": confidence * 100,
                        "Férový kurz": fair_odd
                    })
                except: continue
            
            df_res = pd.DataFrame(results)
            if not df_res.empty:
                st.subheader("🔥 TOP FOTBALOVÉ TUTOVKY")
                tutovky = df_res[df_res["Důvěra"] >= 65].sort_values(by="Důvěra", ascending=False)
                if not tutovky.empty:
                    st.dataframe(tutovky.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
                else: st.info("Žádné tutovky nad 65%.")
                
                st.subheader("💡 VŠECHNY TIPY (Seřazeno)")
                st.dataframe(df_res.sort_values(by="Důvěra", ascending=False).style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
            else: st.warning("Nepodařilo se vypočítat predikce.")
    else: st.error("Chyba ClubElo API.")

# ==============================================================================\n# MODUL 2: TENIS (Foretennis Scraper)\n# ==============================================================================\n
def app_tenis():
    st.header("🎾 Tenisový Auto-Pilot")
    st.caption("Zdroj: Foretennis.com (Matematické predikce)")

    @st.cache_data(ttl=1800)
    def scrape_foretennis():
        url = "https://www.foretennis.com/prediction/"
        scraper = cloudscraper.create_scraper()
        
        try:
            r = scraper.get(url)
            if r.status_code != 200: return [], f"Chyba {r.status_code}"
            
            # Foretennis má jednoduché tabulky
            dfs = pd.read_html(r.text)
            matches = []
            
            # Projdeme tabulky a hledáme tu správnou
            for df in dfs:
                # Převedeme na string
                df = df.astype(str)
                
                # Hledáme tabulku, která má sloupec s procenty (%)
                # Foretennis má sloupce: Date, Player1, Player2, %, Prediction
                has_percent = False
                for col in df.columns:
                    if "%" in str(col) or "prob" in str(col).lower():
                        has_percent = True
                        break
                
                # Pokud tabulka nemá v hlavičce %, zkusíme se podívat do dat
                if not has_percent and not df.empty:
                    first_row = str(df.iloc[0].values)
                    if "%" in first_row: has_percent = True

                if has_percent or len(df.columns) >= 4:
                    for idx, row in df.iterrows():
                        try:
                            # Foretennis struktura se může měnit, ale obvykle:
                            # Player 1 | Player 2 | Prob 1 | Prob 2 | Prediction
                            
                            # Zkusíme najít jména a procenta
                            row_list = row.values.tolist()
                            row_str = " ".join([str(x) for x in row_list])
                            
                            # Pokud řádek neobsahuje procenta, přeskočíme
                            if "%" not in row_str: continue
                            
                            # Extrakce dat (pokus-omyl na základě obsahu)
                            p1 = row_list[1] # Obvykle index 1
                            p2 = row_list[2] # Obvykle index 2
                            
                            # Hledání procent
                            probs = []
                            for item in row_list:
                                s = str(item).replace("%", "").strip()
                                if s.isdigit():
                                    probs.append(float(s))
                            
                            if len(probs) >= 2:
                                prob1 = probs[0]
                                prob2 = probs[1]
                                
                                # Určení tipu
                                tip = p1 if prob1 > prob2 else p2
                                duvera = max(prob1, prob2)
                                
                                matches.append({
                                    "Zápas": f"{p1} vs {p2}",
                                    "Tip": tip,
                                    "Důvěra": duvera,
                                    "Férový kurz": 100 / duvera if duvera > 0 else 0
                                })
                        except: continue
            
            return matches, None
            
        except Exception as e:
            return [], str(e)

    with st.spinner("Stahuji tenisové predikce z Foretennis..."):
        matches, error = scrape_foretennis()

    if error:
        st.error(f"Chyba: {error}")
    elif not matches:
        st.warning("Nepodařilo se načíst data. Web mohl změnit strukturu.")
        st.write("Zkusíme záložní zdroj: **TennisExplorer** (bez predikcí, jen seznam).")
    else:
        st.success(f"Nalezeno {len(matches)} zápasů s predikcí.")
        
        # Seřadíme podle důvěry
        df_tenis = pd.DataFrame(matches).sort_values(by="Důvěra", ascending=False)
        
        # 1. TOP TUTOVKY
        st.subheader("🔥 TOP TENISOVÉ TUTOVKY (> 70%)")
        tutovky = df_tenis[df_tenis["Důvěra"] >= 70]
        
        if not tutovky.empty:
            st.dataframe(tutovky.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
        else:
            st.info("Dnes žádné extrémní tutovky.")
            
        # 2. OSTATNÍ
        st.subheader("💡 OSTATNÍ ZÁPASY")
        ostatni = df_tenis[df_tenis["Důvěra"] < 70]
        st.dataframe(ostatni.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)

# ==============================================================================\n# HLAVNÍ ROZCESTNÍK\n# ==============================================================================\n
st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal Auto-Pilot", "🎾 Tenis Auto-Pilot"])

if sport == "⚽ Fotbal Auto-Pilot":
    app_fotbal()
elif sport == "🎾 Tenis Auto-Pilot":
    app_tenis()
