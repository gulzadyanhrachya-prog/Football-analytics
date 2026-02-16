import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="Betting Auto-Pilot v26", layout="wide")

# ==============================================================================\n# 1. ROBUSTNÍ STAHOVÁNÍ DAT (Anti-Block)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_data_robust():
    # Použijeme proxy a hlavičky prohlížeče
    proxy_base = "https://corsproxy.io/?"
    url_fixtures = "http://api.clubelo.com/Fixtures"
    url_ratings = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/csv,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive"
    }
    
    df_fix = None
    df_elo = None
    
    # 1. Stažení Rozpisu
    try:
        # Zkusíme napřímo s timeoutem 30s
        r = requests.get(url_fixtures, headers=headers, timeout=30)
        if r.status_code == 200:
            df_fix = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
        else:
            # Pokud to selže, zkusíme přes proxy
            r = requests.get(proxy_base + url_fixtures, headers=headers, timeout=30)
            if r.status_code == 200:
                df_fix = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
    except Exception as e:
        st.warning(f"Chyba stahování rozpisu: {e}")

    # 2. Stažení Elo Ratingů
    try:
        r = requests.get(url_ratings, headers=headers, timeout=30)
        if r.status_code == 200:
            df_elo = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
        else:
            r = requests.get(proxy_base + url_ratings, headers=headers, timeout=30)
            if r.status_code == 200:
                df_elo = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
    except Exception as e:
        st.warning(f"Chyba stahování Elo: {e}")
        
    return df_fix, df_elo

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
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            
    prob_btts = 0
    for i in range(1, max_g):
        for j in range(1, max_g):
            prob_btts += matrix[i, j]
            
    return {
        "1": real_h, "0": prob_draw, "2": real_a,
        "Over 2.5": prob_over_25, "Under 2.5": 1 - prob_over_25,
        "BTTS Yes": prob_btts, "BTTS No": 1 - prob_btts
    }

def pick_best_bet(probs):
    candidates = [
        ("Výhra Domácích (1)", probs["1"]),
        ("Výhra Hostů (2)", probs["2"]),
        ("Over 2.5 Gólů", probs["Over 2.5"]),
        ("Under 2.5 Gólů", 1 - probs["Over 2.5"]),
        ("Oba dají gól (BTTS)", probs["BTTS Yes"])
    ]
    prob_10 = probs["1"] + probs["0"]
    prob_02 = probs["2"] + probs["0"]
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_bet = candidates[0]
    
    if best_bet[1] < 0.50:
        if prob_10 > prob_02: return "Neprohra Domácích (10)", prob_10
        else: return "Neprohra Hostů (02)", prob_02
            
    return best_bet[0], best_bet[1]

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("🤖 Betting Auto-Pilot (Anti-Block)")

# --- FOTBAL ---
st.header("⚽ Fotbal")

with st.spinner("Stahuji data (Timeout nastaven na 30s)..."):
    df_fix, df_elo = get_data_robust()

if df_fix is not None:
    # Zpracování data
    try:
        df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
    except:
        st.error("Chyba formátu data v souboru ClubElo.")
        st.stop()

    dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    limit = dnes + timedelta(days=4) 
    
    mask = (df_fix['DateObj'] >= dnes) & (df_fix['DateObj'] <= limit)
    upcoming = df_fix[mask].copy()
    
    if upcoming.empty:
        st.warning("V nejbližších dnech nejsou v databázi žádné zápasy.")
    else:
        elo_dict = {}
        if df_elo is not None: elo_dict = df_elo.set_index('Club')['Elo'].to_dict()

        results = []
        progress_bar = st.progress(0)
        total_rows = len(upcoming)
        
        for i, (idx, row) in enumerate(upcoming.iterrows()):
            if i % 10 == 0: progress_bar.progress(min(i / total_rows, 1.0))
            
            try:
                home, away = row['Home'], row['Away']
                elo_h = row.get('EloHome')
                elo_a = row.get('EloAway')
                
                # Fallback na databázi
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
        
        progress_bar.empty()
        
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
else:
    st.error("Nepodařilo se načíst data z ClubElo ani po zvýšení timeoutu.")

# --- HOKEJ ---
st.markdown("---")
st.header("🏒 NHL")

@st.cache_data(ttl=3600)
def get_nhl_data():
    try:
        # Statistiky
        r_stats = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=10).json()
        stats = {}
        for t in r_stats['standings']:
            stats[t['teamAbbrev']['default']] = {
                "GF": t['goalFor']/t['gamesPlayed'],
                "GA": t['goalAgainst']/t['gamesPlayed']
            }
        
        # Rozpis
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
                    
                    # Poisson Moneyline
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
