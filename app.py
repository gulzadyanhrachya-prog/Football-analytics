import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io
import urllib.parse

st.set_page_config(page_title="Betting Auto-Pilot v17", layout="wide")

# ==============================================================================
# MODUL 1: FOTBAL (ClubElo Math Model) - TOHLE FUNGUJE
# ==============================================================================

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

# ==============================================================================
# MODUL 2: TENIS (AllOrigins JSON Proxy) - NOVÁ METODA
# ==============================================================================

def app_tenis():
    st.header("🎾 Tenisový Auto-Pilot")
    st.caption("Zdroj: TennisExplorer (přes AllOrigins Proxy)")

    @st.cache_data(ttl=1800)
    def scrape_tennis_via_allorigins(date_obj):
        # 1. Sestavíme URL pro TennisExplorer
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day
        target_url = f"https://www.tennisexplorer.com/matches/?type=all&year={year}&month={month}&day={day}"
        
        # 2. Zabalíme to do AllOrigins (vrátí JSON s HTML uvnitř)
        # Tím obejdeme blokování, protože požadavek jde z jejich serveru
        proxy_url = f"https://api.allorigins.win/get?url={urllib.parse.quote(target_url)}"
        
        try:
            r = requests.get(proxy_url)
            data = r.json()
            html_content = data.get("contents")
            
            if not html_content: return [], "Prázdný obsah z proxy."
            
            # 3. Přečteme HTML pomocí Pandas
            dfs = pd.read_html(html_content)
            
            matches = []
            current_tournament = "Neznámý turnaj"
            
            # Hledáme správnou tabulku
            target_df = None
            for df in dfs:
                if len(df.columns) > 4:
                    sample = str(df.head(5))
                    if ":" in sample:
                        target_df = df
                        break
            
            if target_df is None: return [], "Tabulka nenalezena."

            # 4. Parsování
            for idx, row in target_df.iterrows():
                try:
                    col0 = str(row.iloc[0])
                    
                    # Turnaj
                    if ":" not in col0 and len(col0) > 3:
                        current_tournament = col0
                        continue
                    
                    # Zápas
                    if ":" in col0:
                        # TennisExplorer: Time | Player | Score | Sets | Odds1 | Odds2
                        odds1 = row.iloc[-2]
                        odds2 = row.iloc[-1]
                        
                        try:
                            o1 = float(odds1)
                            o2 = float(odds2)
                        except: continue 
                            
                        players = str(row.iloc[1])
                        if " - " in players:
                            p1, p2 = players.split(" - ", 1)
                            
                            matches.append({
                                "Datum": date_obj.strftime("%d.%m."),
                                "Čas": col0,
                                "Turnaj": current_tournament,
                                "Hráč 1": p1,
                                "Hráč 2": p2,
                                "Kurz 1": o1,
                                "Kurz 2": o2
                            })
                except: continue
            return matches, None
            
        except Exception as e:
            return [], str(e)

    # --- LOGIKA ---
    dnes = datetime.now()
    zitra = dnes + timedelta(days=1)
    
    with st.spinner("Stahuji tenisové zápasy (Dnešek + Zítřek)..."):
        zapasy_dnes, err1 = scrape_tennis_via_allorigins(dnes)
        zapasy_zitra, err2 = scrape_tennis_via_allorigins(zitra)
        vsechny_zapasy = zapasy_dnes + zapasy_zitra

    if not vsechny_zapasy:
        st.error("Nepodařilo se stáhnout data.")
        with st.expander("Detaily chyby"):
            st.write(f"Dnešek: {err1}")
            st.write(f"Zítřek: {err2}")
    else:
        # Filtr turnajů
        turnaje = sorted(list(set([z["Turnaj"] for z in vsechny_zapasy])))
        
        c1, c2 = st.columns(2)
        with c1: filtr_turnaj = st.selectbox("Filtrovat Turnaj:", ["Vše"] + turnaje)
        with c2: jen_atp = st.checkbox("Ukázat jen ATP/WTA", value=True)

        st.subheader(f"Nalezeno {len(vsechny_zapasy)} zápasů")
        
        count = 0
        for z in vsechny_zapasy:
            if jen_atp and ("ATP" not in z["Turnaj"] and "WTA" not in z["Turnaj"]): continue
            if filtr_turnaj != "Vše" and z["Turnaj"] != filtr_turnaj: continue
            
            count += 1
            
            # Výpočet predikce z kurzů
            prob1 = (1 / z["Kurz 1"])
            prob2 = (1 / z["Kurz 2"])
            margin = prob1 + prob2 
            
            real_prob1 = (prob1 / margin) * 100
            real_prob2 = (prob2 / margin) * 100
            
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([2, 3, 2, 3, 2])
                
                with c1: 
                    st.caption(f"{z['Datum']} {z['Čas']}")
                    st.caption(z["Turnaj"][:25])
                
                with c2: 
                    st.write(f"**{z['Hráč 1']}**")
                    st.write(f"Kurz: {z['Kurz 1']}")
                
                with c3:
                    st.markdown(f"<h4 style='text-align: center'>{int(real_prob1)}% : {int(real_prob2)}%</h4>", unsafe_allow_html=True)
                    if real_prob1 > 60: st.success(f"Tip: {z['Hráč 1']}")
                    elif real_prob2 > 60: st.error(f"Tip: {z['Hráč 2']}")
                    else: st.warning("Vyrovnané")
                    
                with c4:
                    st.write(f"**{z['Hráč 2']}**")
                    st.write(f"Kurz: {z['Kurz 2']}")
                
                st.markdown("---")
        
        if count == 0:
            st.info("Žádné zápasy neodpovídají filtru.")

# ==============================================================================
# HLAVNÍ ROZCESTNÍK
# ==============================================================================

st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal Auto-Pilot", "🎾 Tenis Auto-Pilot"])

if sport == "⚽ Fotbal Auto-Pilot":
    app_fotbal()
elif sport == "🎾 Tenis Auto-Pilot":
    app_tenis()
