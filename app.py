import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime
import io
from scipy.stats import poisson

st.set_page_config(page_title="Bet365 Odds Scanner", layout="wide")

# ==============================================================================\n# 1. KONFIGURACE A API VOLÁNÍ\n# ==============================================================================\n
try:
    API_KEY = st.secrets["RAPID_API_KEY"]
    API_HOST = st.secrets["RAPID_API_HOST"]
except:
    st.error("Chybí API klíč v Secrets!")
    st.stop()

# ID sportů pro Bet365 API
SPORTS = {
    "⚽ Fotbal": "1",
    "🏒 Hokej": "17", 
    "🎾 Tenis": "13"
}

@st.cache_data(ttl=600) # Cache 10 minut (kurzy se mění)
def get_bet365_fixtures(sport_id):
    url = f"https://{API_HOST}/events/upcoming"
    
    querystring = {
        "sport_id": sport_id,
        "page": "1" 
    }
    
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        if response.status_code != 200:
            return None, f"Chyba API: {response.status_code}"
        return response.json(), None
    except Exception as e:
        return None, str(e)

# --- POMOCNÁ FUNKCE PRO FOTBALOVOU MATEMATIKU (ClubElo) ---
@st.cache_data(ttl=3600)
def get_elo_data():
    try:
        url = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
        s = requests.get(url).content
        return pd.read_csv(io.StringIO(s.decode('utf-8')))
    except: return None

def calculate_fair_odds(elo_h, elo_a):
    elo_diff = elo_h - elo_a + 100
    prob_h = 1 / (10**(-elo_diff/400) + 1)
    prob_a = 1 - prob_h
    prob_d = 0.25 # Zjednodušená remíza
    
    real_h = prob_h * (1 - prob_d)
    real_a = prob_a * (1 - prob_d)
    
    return 1/real_h, 1/prob_d, 1/real_a

# ==============================================================================\n# 2. ZPRACOVÁNÍ DAT\n# ==============================================================================\n
def process_matches(json_data, sport_name, elo_df=None):
    matches = []
    
    if "results" not in json_data:
        return []
        
    for item in json_data["results"]:
        try:
            # Základní info
            league = item.get("league", {}).get("name", "Unknown")
            home = item.get("home", {}).get("name", "Unknown")
            away = item.get("away", {}).get("name", "Unknown")
            time_stamp = int(item.get("time", 0))
            date_obj = datetime.fromtimestamp(time_stamp)
            
            # Kurzy (Main market: 1X2 nebo Moneyline)
            odds = item.get("main_odds", {})
            o1 = odds.get("home_od")
            oX = odds.get("draw_od")
            o2 = odds.get("away_od")
            
            # Převod na float
            try: o1 = float(o1) if o1 else 0
            except: o1 = 0
            try: oX = float(oX) if oX else 0
            except: oX = 0
            try: o2 = float(o2) if o2 else 0
            except: o2 = 0
            
            match_data = {
                "Liga": league,
                "Čas": date_obj.strftime("%d.%m. %H:%M"),
                "Zápas": f"{home} vs {away}",
                "1": o1,
                "X": oX,
                "2": o2,
                "Value": 0, # Default
                "Tip": ""
            }
            
            # --- POKUS O VALUE BETTING (JEN FOTBAL) ---
            if sport_name == "⚽ Fotbal" and elo_df is not None and o1 > 0 and o2 > 0:
                # Normalizace jmen pro ClubElo
                def clean(n): return n.replace(" FC", "").replace("FC ", "").strip()
                
                h_row = elo_df[elo_df['Club'].str.contains(clean(home), case=False, na=False)]
                a_row = elo_df[elo_df['Club'].str.contains(clean(away), case=False, na=False)]
                
                if not h_row.empty and not a_row.empty:
                    elo_h = h_row.iloc[0]['Elo']
                    elo_a = a_row.iloc[0]['Elo']
                    
                    fair_1, fair_X, fair_2 = calculate_fair_odds(elo_h, elo_a)
                    
                    # Výpočet hodnoty (ROI)
                    if o1 > fair_1:
                        match_data["Value"] = (o1 / fair_1 - 1) * 100
                        match_data["Tip"] = f"1 (Fair: {fair_1:.2f})"
                    elif o2 > fair_2:
                        match_data["Value"] = (o2 / fair_2 - 1) * 100
                        match_data["Tip"] = f"2 (Fair: {fair_2:.2f})"
            
            matches.append(match_data)
            
        except Exception as e:
            continue
            
    return matches

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("🏆 Bet365 Odds Scanner")
st.caption("Data přímo z Bet365 přes RapidAPI")

# Sidebar
selected_sport = st.sidebar.radio("Vyber sport:", list(SPORTS.keys()))
sport_id = SPORTS[selected_sport]

# Načtení dat
with st.spinner(f"Stahuji kurzy pro {selected_sport}..."):
    data, error = get_bet365_fixtures(sport_id)
    
    # Pro fotbal načteme i Elo
    elo_df = None
    if selected_sport == "⚽ Fotbal":
        elo_df = get_elo_data()

if error:
    st.error(error)
    st.write("Možné příčiny:")
    st.write("1. Vyčerpaný limit na RapidAPI (zkontroluj dashboard).")
    st.write("2. Špatný klíč v Secrets.")
elif data:
    matches = process_matches(data, selected_sport, elo_df)
    
    if not matches:
        st.warning("API vrátilo prázdný seznam zápasů.")
    else:
        df = pd.DataFrame(matches)
        
        # Filtry
        ligy = sorted(df["Liga"].unique())
        selected_league = st.sidebar.selectbox("Filtrovat ligu:", ["Vše"] + ligy)
        
        if selected_league != "Vše":
            df = df[df["Liga"] == selected_league]
            
        # Zobrazení
        st.subheader(f"Nalezeno {len(df)} zápasů")
        
        # Pokud je to fotbal, seřadíme podle Value
        if selected_sport == "⚽ Fotbal":
            df = df.sort_values(by="Value", ascending=False)
        
        for index, row in df.iterrows():
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([2, 3, 1, 1, 1])
                
                with c1:
                    st.caption(row["Liga"])
                    st.write(f"**{row['Čas']}**")
                    
                with c2:
                    st.write(f"**{row['Zápas']}**")
                    if row["Value"] > 5:
                        st.success(f"🔥 VALUE BET: {row['Tip']} (+{row['Value']:.1f}%)")
                
                with c3:
                    st.metric("1", f"{row['1']:.2f}")
                with c4:
                    st.metric("X", f"{row['X']:.2f}")
                with c5:
                    st.metric("2", f"{row['2']:.2f}")
                
                st.markdown("---")
