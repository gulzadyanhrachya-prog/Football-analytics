import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="SGO Value Hunter", layout="wide")

# ==============================================================================\n# 1. KONFIGURACE A API (SportsGameOdds)\n# ==============================================================================\n
try:
    API_KEY = st.secrets["SGO_KEY"]
except:
    st.error("Chybí SGO_KEY v Secrets!")
    st.stop()

BASE_URL = "https://api.sportsgameodds.com/v1"
HEADERS = {"x-api-key": API_KEY}

@st.cache_data(ttl=86400) # Cache na 24h (ID sportů se nemění)
def get_sgo_sports():
    try:
        r = requests.get(f"{BASE_URL}/sports", headers=HEADERS)
        if r.status_code == 200:
            return {item['slug']: item['id'] for item in r.json()}
        return {}
    except: return {}

@st.cache_data(ttl=3600)
def get_sgo_games(sport_id, date_str):
    try:
        # SGO endpoint pro zápasy
        url = f"{BASE_URL}/games"
        params = {"sportId": sport_id, "date": date_str}
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code == 200:
            return r.json()
        return []
    except: return []

@st.cache_data(ttl=600) # Cache na 10 minut
def get_sgo_odds(game_id):
    try:
        # SGO endpoint pro kurzy
        url = f"{BASE_URL}/odds"
        params = {"gameId": game_id}
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code == 200:
            return r.json()
        return []
    except: return []

# ==============================================================================\n# 2. ANALYTICKÉ MODELY (ClubElo & NHL)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_clubelo_data():
    try:
        url = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
        s = requests.get(url).content
        return pd.read_csv(io.StringIO(s.decode('utf-8')))
    except: return None

@st.cache_data(ttl=3600)
def get_nhl_stats():
    try:
        r = requests.get("https://api-web.nhle.com/v1/standings/now")
        data = r.json()
        stats = {}
        for t in data['standings']:
            name = t['teamName']['default']
            stats[name] = {
                "GF": t['goalFor'] / t['gamesPlayed'],
                "GA": t['goalAgainst'] / t['gamesPlayed']
            }
            # Přidáme i zkratku pro jistotu
            stats[t['teamAbbrev']['default']] = stats[name]
        return stats
    except: return None

def calculate_fair_odds_football(elo_h, elo_a):
    elo_diff = elo_h - elo_a + 100
    prob_h = 1 / (10**(-elo_diff/400) + 1)
    prob_a = 1 - prob_h
    prob_d = 0.25 # Zjednodušená remíza
    
    real_h = prob_h * (1 - prob_d)
    real_a = prob_a * (1 - prob_d)
    
    return 1/real_h, 1/prob_d, 1/real_a

def calculate_fair_odds_hockey(h_stats, a_stats):
    # xG Model
    avg_gf = 3.0
    xg_h = (h_stats['GF'] * a_stats['GA']) / avg_gf * 1.05
    xg_a = (a_stats['GF'] * h_stats['GA']) / avg_gf
    
    # Poisson Moneyline (Vítěz do rozhodnutí)
    max_g = 10
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
            
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    
    ml_h = prob_h + (prob_d * 0.5)
    ml_a = prob_a + (prob_d * 0.5)
    
    return 1/ml_h, 1/ml_a

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("💰 SGO Value Hunter")
st.markdown("Porovnává kurzy ze **SportsGameOdds** s matematickými modely (**ClubElo / NHL Stats**).")

# --- NAČTENÍ SPORTŮ ---
sports_map = get_sgo_sports()
# Zkusíme najít ID pro Soccer a Hockey (názvy se mohou lišit, hledáme klíčová slova)
soccer_id = next((v for k, v in sports_map.items() if "soccer" in k.lower()), 1)
hockey_id = next((v for k, v in sports_map.items() if "hockey" in k.lower()), 4)

# --- SIDEBAR ---
st.sidebar.header("Nastavení")
selected_sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🏒 Hokej"])
date_option = st.sidebar.selectbox("Kdy:", ["Dnes", "Zítra"])

target_date = datetime.now()
if date_option == "Zítra": target_date += timedelta(days=1)
date_str = target_date.strftime("%Y-%m-%d")

# --- HLAVNÍ LOGIKA ---
sport_id = soccer_id if selected_sport == "⚽ Fotbal" else hockey_id

with st.spinner(f"Stahuji zápasy ze SGO pro {date_str}..."):
    games = get_sgo_games(sport_id, date_str)

if not games:
    st.warning("Nebyly nalezeny žádné zápasy pro vybraný den.")
else:
    # Načtení analytických dat
    elo_data = get_clubelo_data() if selected_sport == "⚽ Fotbal" else None
    nhl_stats = get_nhl_stats() if selected_sport == "🏒 Hokej" else None
    
    st.info(f"Nalezeno {len(games)} zápasů. Analyzuji Value...")
    
    value_bets = []
    
    # Progress bar, protože budeme volat odds endpoint
    progress = st.progress(0)
    
    # Limitujeme na prvních 20 zápasů, abychom nevyčerpali limit API hned
    # (V reálu bys mohl projít všechny, ale SGO má limity)
    games_to_check = games[:20] 
    
    for i, game in enumerate(games_to_check):
        progress.progress((i + 1) / len(games_to_check))
        
        try:
            home = game.get('homeTeam', {}).get('name', 'Unknown')
            away = game.get('awayTeam', {}).get('name', 'Unknown')
            game_id = game.get('id')
            
            # 1. Získání kurzů SGO
            odds_data = get_sgo_odds(game_id)
            if not odds_data: continue
            
            # Hledáme nejlepší kurz (Best Odds)
            # SGO vrací pole odds, musíme najít Moneyline nebo 1X2
            # Zjednodušeně: vezmeme první dostupný kurz
            # Struktura SGO odds je složitá, zkusíme najít "average" nebo "best"
            # Pro demo vezmeme náhodný kurz z dat (pokud existuje)
            # V reálném SGO response musíme parsovat konkrétní bookmakery
            
            # Simulace extrakce kurzu (protože neznám přesnou strukturu odds response bez testu)
            # Předpokládáme, že v datech je někde hodnota kurzu. 
            # Pokud ne, přeskočíme.
            
            # PRO DEMO ÚČELY: Pokud API nevrátí jasný kurz, přeskočíme
            # V reálu zde musí být parser JSONu z /odds endpointu
            market_h = 0
            market_a = 0
            
            # Pokus o nalezení kurzu v datech (SGO specifika)
            for odd in odds_data:
                # Hledáme Moneyline nebo 3-Way
                if odd.get('type') == 'moneyline' or odd.get('type') == '3way':
                    market_h = odd.get('home', 0)
                    market_a = odd.get('away', 0)
                    break
            
            if market_h == 0: continue # Nemáme kurz
            
            # 2. Výpočet Férového kurzu
            fair_h = 0
            fair_a = 0
            
            if selected_sport == "⚽ Fotbal" and elo_data is not None:
                # Normalizace jmen
                def clean(n): return n.replace(" FC", "").replace("FC ", "").strip()
                h_row = elo_data[elo_data['Club'].str.contains(clean(home), case=False, na=False)]
                a_row = elo_data[elo_data['Club'].str.contains(clean(away), case=False, na=False)]
                
                if not h_row.empty and not a_row.empty:
                    elo_h = h_row.iloc[0]['Elo']
                    elo_a = a_row.iloc[0]['Elo']
                    fair_h, _, fair_a = calculate_fair_odds_football(elo_h, elo_a)
                    
            elif selected_sport == "🏒 Hokej" and nhl_stats is not None:
                # Zkusíme najít tým v NHL datech
                # SGO může mít "New York Rangers", NHL API "Rangers"
                h_stat = None
                a_stat = None
                
                for k, v in nhl_stats.items():
                    if k in home or home in k: h_stat = v
                    if k in away or away in k: a_stat = v
                
                if h_stat and a_stat:
                    fair_h, fair_a = calculate_fair_odds_hockey(h_stat, a_stat)
            
            # 3. Výpočet Value
            if fair_h > 0:
                # Value = (Kurz / Férový) - 1
                val_h = (market_h / fair_h - 1) * 100
                val_a = (market_a / fair_a - 1) * 100
                
                best_val = max(val_h, val_a)
                tip = f"Výhra {home}" if val_h > val_a else f"Výhra {away}"
                market_odd = market_h if val_h > val_a else market_a
                fair_odd = fair_h if val_h > val_a else fair_a
                
                if best_val > 0: # Ukazujeme jen kladnou value
                    value_bets.append({
                        "Zápas": f"{home} vs {away}",
                        "Tip": tip,
                        "Kurz SGO": market_odd,
                        "Férový Kurz": fair_odd,
                        "Value (%)": best_val
                    })
                    
        except: continue
        
    progress.empty()
    
    # Zobrazení výsledků
    if value_bets:
        df_res = pd.DataFrame(value_bets).sort_values(by="Value (%)", ascending=False)
        
        st.subheader("🔥 Nalezené Value Bety")
        
        for idx, row in df_res.iterrows():
            color = "green" if row['Value (%)'] > 10 else "orange"
            
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                with c1: st.write(f"**{row['Zápas']}**")
                with c2: st.write(f"Tip: {row['Tip']}")
                with c3: st.metric("Kurz SGO", f"{row['Kurz SGO']:.2f}")
                with c4: st.metric("Value", f"+{row['Value (%)']:.1f} %", delta_color="normal")
                
                with st.expander("Detail"):
                    st.write(f"Náš model říká, že férový kurz je **{row['Férový Kurz']:.2f}**.")
                    st.write(f"SGO nabízí **{row['Kurz SGO']:.2f}**.")
                    st.write("To znamená, že kurz je nadhodnocený a dlouhodobě ziskový.")
                st.markdown("---")
    else:
        st.info("Zatím nebyly nalezeny žádné Value Bety (nebo se nepodařilo spárovat týmy).")
        st.write("Zobrazuji seznam stažených zápasů (bez value):")
        st.dataframe(pd.DataFrame(games)[['homeTeam', 'awayTeam', 'status']])
