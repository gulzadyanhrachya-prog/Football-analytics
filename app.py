import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io
import urllib.parse

st.set_page_config(page_title="Betting Auto-Pilot v29 (X-RAY)", layout="wide")

# ==============================================================================
# 1. ROBUSTNÍ NAČÍTÁNÍ DAT
# ==============================================================================

@st.cache_data(ttl=3600)
def get_football_data_robust():
    url_direct = "http://api.clubelo.com/Fixtures"
    url_proxy_1 = f"https://api.allorigins.win/get?url={urllib.parse.quote(url_direct)}"
    url_proxy_2 = f"https://corsproxy.io/?{url_direct}"
    
    df = None
    status = "Nenačteno"

    # 1. POKUS: Přímo (Když ti to fungovalo, zkusíme to jako první)
    try:
        r = requests.get(url_direct, timeout=15)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
            status = "✅ Direct Connection"
    except: pass

    # 2. POKUS: Proxy AllOrigins
    if df is None:
        try:
            r = requests.get(url_proxy_1, timeout=15)
            data = r.json()
            content = data.get("contents")
            if content:
                df = pd.read_csv(io.StringIO(content))
                status = "✅ AllOrigins Proxy"
        except: pass

    # 3. POKUS: Proxy CorsProxy
    if df is None:
        try:
            r = requests.get(url_proxy_2, timeout=15)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                status = "✅ CorsProxy"
        except: pass

    return df, status

# ==============================================================================
# 2. MATEMATICKÉ MODELY
# ==============================================================================

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
    prob_btts = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "1": real_h, "0": prob_draw, "2": real_a,
        "Over 2.5": prob_over_25, "BTTS Yes": prob_btts
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

# ==============================================================================
# 3. UI APLIKACE (DIAGNOSTICKÁ)
# ==============================================================================

st.title("🤖 Betting Auto-Pilot (X-RAY Mode)")

# --- FOTBAL ---
st.header("⚽ Fotbal")

with st.spinner("Stahuji data..."):
    df_fix, status_msg = get_football_data_robust()

st.success(f"Stav připojení: {status_msg}")

if df_fix is not None:
    # --- DIAGNOSTIKA DAT ---
    with st.expander("🔍 KLIKNI ZDE PRO ZOBRAZENÍ SUROVÝCH DAT", expanded=True):
        st.write(f"Počet řádků v souboru: **{len(df_fix)}**")
        st.write("Názvy sloupců:", df_fix.columns.tolist())
        st.write("Prvních 5 řádků:")
        st.dataframe(df_fix.head())
        
        # Kontrola data
        if 'Date' in df_fix.columns:
            try:
                df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
                min_date = df_fix['DateObj'].min()
                max_date = df_fix['DateObj'].max()
                st.write(f"📅 Data v souboru jsou od **{min_date.date()}** do **{max_date.date()}**")
                st.write(f"📅 Dnešní datum je: **{datetime.now().date()}**")
            except Exception as e:
                st.error(f"Chyba při čtení data: {e}")

    # --- FILTRACE A VÝPOČET ---
    try:
        df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
        dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # ZMĚNA: Rozšíříme okno na 7 dní, abychom něco našli
        limit = dnes + timedelta(days=7) 
        
        mask = (df_fix['DateObj'] >= dnes) & (df_fix['DateObj'] <= limit)
        upcoming = df_fix[mask].copy()
        
        st.write(f"Počet zápasů v příštích 7 dnech: **{len(upcoming)}**")
        
        if upcoming.empty:
            st.warning("⚠️ V příštích 7 dnech nejsou v databázi žádné zápasy. Zkontroluj 'Surová data' výše, jestli tam vůbec jsou nějaké budoucí zápasy.")
        else:
            results = []
            progress_bar = st.progress(0)
            total_rows = len(upcoming)
            
            for i, (idx, row) in enumerate(upcoming.iterrows()):
                if i % 10 == 0: progress_bar.progress(min(i / total_rows, 1.0))
                
                try:
                    home, away = row['Home'], row['Away']
                    elo_h = row.get('EloHome')
                    elo_a = row.get('EloAway')
                    
                    if pd.isna(elo_h) or pd.isna(elo_a): continue

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
            
            progress_bar.empty()
            
            df_res = pd.DataFrame(results)
            if not df_res.empty:
                st.subheader("🔥 TOP FOTBALOVÉ TUTOVKY")
                tutovky = df_res[df_res["Důvěra"] >= 65].sort_values(by="Důvěra", ascending=False)
                st.dataframe(tutovky.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
                
                st.subheader("💡 VŠECHNY TIPY")
                st.dataframe(df_res.sort_values(by="Důvěra", ascending=False), hide_index=True, use_container_width=True)
            else: 
                st.warning("Nepodařilo se vypočítat predikce (možná chybí Elo data v řádcích).")
                
    except Exception as e:
        st.error(f"Kritická chyba při zpracování: {e}")

else:
    st.error("Nepodařilo se načíst data.")

# --- HOKEJ (NHL) ---
st.markdown("---")
st.header("🏒 NHL")

@st.cache_data(ttl=3600)
def get_nhl_data():
    try:
        r_stats = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=10).json()
        stats = {}
        for t in r_stats['standings']:
            stats[t['teamAbbrev']['default']] = {
                "GF": t['goalFor']/t['gamesPlayed'],
                "GA": t['goalAgainst']/t['gamesPlayed']
            }
        
        today = datetime.now().strftime("%Y-%m-%d")
        r_sch = requests.get(f"https://api-web.nhle.com/v1/schedule/{today}", timeout=10).json()
        
        matches = []
        avg_gf = 3.0
        
        for day in r_sch['gameWeek']:
            for game in day['games']:
                h = game['homeTeam']['abbrev']
                a = game['awayTeam']['abbrev']
                if h in stats and a in stats:
                    xg_h = (stats[h]['GF'] * stats[a]['GA']) / avg_gf * 1.05
                    xg_a = (stats[a]['GF'] * stats[h]['GA']) / avg_gf
                    
                    max_g = 10
                    matrix = np.zeros((max_g, max_g))
                    for i in range(max_g):
                        for j in range(max_g):
                            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
                    
                    prob_h = np.sum(np.tril(matrix, -1)) + (np.sum(np.diag(matrix)) * 0.5)
                    prob_a = np.sum(np.triu(matrix, 1)) + (np.sum(np.diag(matrix)) * 0.5)
                    
                    tip = f"Výhra {h}" if prob_h > prob_a else f"Výhra {a}"
                    conf = max(prob_h, prob_a)
                    
                    matches.append({
                        "Datum": day['date'],
                        "Zápas": f"{h} vs {a}",
                        "Tip": tip,
                        "Důvěra": conf * 100,
                        "Férový kurz": 1/conf
                    })
        return matches
    except: return []

matches = get_nhl_data()
if matches:
    df = pd.DataFrame(matches).sort_values(by="Důvěra", ascending=False)
    st.dataframe(df.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
else:
    st.warning("Žádné zápasy NHL.")
