import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io
import cloudscraper

st.set_page_config(page_title="Betting Auto-Pilot v14", layout="wide")

# ==============================================================================
# MODUL 1: FOTBAL (ClubElo Math Model)
# ==============================================================================

def app_fotbal():
    st.header("⚽ Fotbalový Auto-Pilot (Elo & Poisson)")
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

# ==============================================================================
# MODUL 2: TENIS (VitiSport Auto-Pilot)
# ==============================================================================

def app_tenis():
    st.header("🎾 Tenisový Auto-Pilot")
    st.caption("Zdroj: VitiSport.cz (Agresivní skenování)")

    @st.cache_data(ttl=1800)
    def scrape_tennis_tips():
        url = "https://www.vitisport.cz/index.php?g=tenis&lang=en"
        scraper = cloudscraper.create_scraper()
        try:
            r = scraper.get(url)
            if r.status_code != 200: return [], f"Chyba {r.status_code}"
            
            dfs = pd.read_html(r.text)
            matches = []
            
            # Projdeme všechny tabulky a hledáme ty se zápasy
            for df in dfs:
                df = df.astype(str)
                if len(df.columns) < 4: continue
                
                for idx, row in df.iterrows():
                    try:
                        # VitiSport struktura: Čas | Domácí | Hosté | ... | Tip | ...
                        # Musíme být flexibilní
                        row_list = row.values.tolist()
                        
                        # Hledáme čas (obsahuje :)
                        cas = next((x for x in row_list if ":" in str(x) and len(str(x)) < 6), None)
                        if not cas: continue
                        
                        # Hledáme tip (1 nebo 2)
                        # VitiSport dává tip do sloupce, který obsahuje jen "1" nebo "2"
                        tip = None
                        for item in row_list:
                            if item in ["1", "2"]:
                                tip = item
                                break
                        
                        if not tip: continue
                        
                        # Hledáme jména hráčů (jsou to ty nejdelší stringy v řádku)
                        strings = [str(x) for x in row_list if len(str(x)) > 3 and ":" not in str(x) and "Tip" not in str(x)]
                        if len(strings) >= 2:
                            p1 = strings[0]
                            p2 = strings[1]
                            
                            # Ignorujeme hlavičky
                            if "Home" in p1 or "Away" in p1: continue
                            
                            matches.append({
                                "Čas": cas,
                                "Hráč 1": p1,
                                "Hráč 2": p2,
                                "Tip": tip
                            })
                    except: continue
            return matches, None
        except Exception as e: return [], str(e)

    with st.spinner("Skenuji tenisové kurty..."):
        matches, error = scrape_tennis_tips()

    if error:
        st.error(f"Chyba: {error}")
    elif not matches:
        st.warning("Nebyly nalezeny žádné tenisové tipy.")
    else:
        # Zpracování do tabulky
        data = []
        for m in matches:
            doporuceni = f"Výhra {m['Hráč 1']}" if m['Tip'] == "1" else f"Výhra {m['Hráč 2']}"
            data.append({
                "Čas": m['Čas'],
                "Zápas": f"{m['Hráč 1']} vs {m['Hráč 2']}",
                "DOPORUČENÁ SÁZKA": doporuceni,
                "Tip Kód": m['Tip']
            })
            
        df_tenis = pd.DataFrame(data)
        
        # Zobrazení
        st.subheader(f"🔥 Nalezeno {len(df_tenis)} tenisových tipů")
        
        # Rozdělení na Tip 1 a Tip 2 pro přehlednost
        c1, c2 = st.columns(2)
        
        with c1:
            st.info("Tipy na Domácího (1)")
            df_1 = df_tenis[df_tenis["Tip Kód"] == "1"]
            if not df_1.empty:
                st.dataframe(df_1[["Čas", "Zápas", "DOPORUČENÁ SÁZKA"]], hide_index=True, use_container_width=True)
            else: st.write("Žádné tipy.")
            
        with c2:
            st.error("Tipy na Hosté (2)")
            df_2 = df_tenis[df_tenis["Tip Kód"] == "2"]
            if not df_2.empty:
                st.dataframe(df_2[["Čas", "Zápas", "DOPORUČENÁ SÁZKA"]], hide_index=True, use_container_width=True)
            else: st.write("Žádné tipy.")

# ==============================================================================
# HLAVNÍ ROZCESTNÍK
# ==============================================================================

st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal Auto-Pilot", "🎾 Tenis Auto-Pilot"])

if sport == "⚽ Fotbal Auto-Pilot":
    app_fotbal()
elif sport == "🎾 Tenis Auto-Pilot":
    app_tenis()
