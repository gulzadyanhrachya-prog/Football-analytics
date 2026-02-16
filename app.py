import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="TheSportsDB Analyst", layout="wide")

# ==============================================================================\n# 1. KONFIGURACE (TheSportsDB IDs)\n# ==============================================================================\n
# API Klíč "3" je veřejný testovací klíč TheSportsDB
API_KEY = "3"
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

# Mapování názvů lig na jejich ID v TheSportsDB
LEAGUES = {
    "⚽ FOTBAL": {
        "🇬🇧 Premier League": "4328",
        "🇬🇧 Championship": "4329",
        "🇪🇸 La Liga": "4335",
        "🇩🇪 Bundesliga": "4331",
        "🇩🇪 2. Bundesliga": "4332",
        "🇮🇹 Serie A": "4332", # Pozor, ID se mohou měnit, Serie A bývá 4332 nebo 4335
        "🇮🇹 Serie B": "4394",
        "🇫🇷 Ligue 1": "4334",
        "🇫🇷 Ligue 2": "4396",
        "🇳🇱 Eredivisie": "4337",
        "🇵🇹 Primeira Liga": "4344",
        "🇨🇿 Fortuna Liga": "4352",
        "🇵🇱 Ekstraklasa": "4353",
        "🇩🇰 Superliga": "4340",
        "🇹🇷 Super Lig": "4338",
        "🇬🇷 Super League": "4339",
        "🇷🇴 Liga I": "4358",
        "🇮🇱 Premier League": "4363",
        "🇪🇺 Liga Mistrů": "4480"
    },
    "🏒 HOKEJ": {
        "🇺🇸 NHL": "4380",
        "🇨🇿 Extraliga": "4389",
        "🇫🇮 Liiga": "4392",
        "🇸🇪 SHL": "4388",
        "🇩🇪 DEL": "4390",
        "🇷🇺 KHL": "4381",
        "🇨🇭 SHL (Swiss)": "4385"
    }
}

# ==============================================================================\n# 2. FUNKCE PRO STAŽENÍ DAT\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_league_table(league_id, season):
    """Stáhne aktuální tabulku ligy (pro výpočet síly)"""
    url = f"{BASE_URL}/lookuptable.php?l={league_id}&s={season}"
    try:
        r = requests.get(url)
        data = r.json()
        if data and data.get("table"):
            return pd.DataFrame(data["table"])
        return None
    except: return None

@st.cache_data(ttl=3600)
def get_next_events(league_id):
    """Stáhne nadcházející zápasy (Next 15)"""
    url = f"{BASE_URL}/eventsnextleague.php?id={league_id}"
    try:
        r = requests.get(url)
        data = r.json()
        if data and data.get("events"):
            return data["events"]
        return None
    except: return None

@st.cache_data(ttl=86400) # Cache na 24h (loga se nemění)
def get_team_details(team_id):
    """Stáhne detaily týmu (logo)"""
    url = f"{BASE_URL}/lookupteam.php?id={team_id}"
    try:
        r = requests.get(url)
        data = r.json()
        if data and data.get("teams"):
            return data["teams"][0] # Vrací dict s logem atd.
        return None
    except: return None

# ==============================================================================\n# 3. VÝPOČET PREDIKCE\n# ==============================================================================\n
def predict_match(home_id, away_id, table_df):
    """Vypočítá šance na základě postavení v tabulce"""
    if table_df is None:
        return 50, 50, "Neznámá síla (Chybí tabulka)"
    
    # Najdeme týmy v tabulce
    h_row = table_df[table_df["idTeam"] == home_id]
    a_row = table_df[table_df["idTeam"] == away_id]
    
    if h_row.empty or a_row.empty:
        return 50, 50, "Tým nenalezen v tabulce"
    
    # Získáme body a odehrané zápasy
    try:
        h_pts = int(h_row.iloc[0]["intPoints"])
        h_played = int(h_row.iloc[0]["intPlayed"])
        a_pts = int(a_row.iloc[0]["intPoints"])
        a_played = int(a_row.iloc[0]["intPlayed"])
        
        # Body na zápas (PPG)
        h_ppg = h_pts / h_played if h_played > 0 else 0
        a_ppg = a_pts / a_played if a_played > 0 else 0
        
        # Domácí výhoda (přidáme 20% k síle domácích)
        h_strength = h_ppg * 1.2
        a_strength = a_ppg
        
        total = h_strength + a_strength
        if total == 0: return 50, 50, "Nulová data"
        
        p_home = (h_strength / total) * 100
        p_away = (a_strength / total) * 100
        
        return p_home, p_away, "OK"
        
    except:
        return 50, 50, "Chyba výpočtu"

# ==============================================================================\n# 4. UI APLIKACE\n# ==============================================================================\n
st.title("🏆 TheSportsDB Analyst")
st.caption("Vizuální analýza zápasů s logy a statistikami.")

# 1. Výběr Sportu a Ligy
col_sport, col_league, col_season = st.columns([1, 2, 1])

with col_sport:
    sport = st.radio("Sport:", ["⚽ FOTBAL", "🏒 HOKEJ"])

with col_league:
    league_name = st.selectbox("Soutěž:", list(LEAGUES[sport].keys()))
    league_id = LEAGUES[sport][league_name]

with col_season:
    # TheSportsDB používá formát "2024-2025" nebo "2025-2026"
    season = st.selectbox("Sezóna:", ["2024-2025", "2023-2024", "2025-2026"])

# 2. Načtení dat
with st.spinner(f"Stahuji data pro {league_name}..."):
    table_df = get_league_table(league_id, season)
    events = get_next_events(league_id)

# 3. Zobrazení Tabulky (Expandér)
if table_df is not None:
    with st.expander(f"📊 Zobrazit tabulku: {league_name}"):
        # Vybereme jen důležité sloupce
        display_cols = ["intRank", "strTeam", "intPlayed", "intWin", "intDraw", "intLoss", "intGoalDifference", "intPoints", "strForm"]
        # Přejmenování pro hezčí vzhled
        rename_map = {
            "intRank": "#", "strTeam": "Tým", "intPlayed": "Z", "intWin": "V", 
            "intDraw": "R", "intLoss": "P", "intGoalDifference": "+/-", "intPoints": "Body", "strForm": "Forma"
        }
        # Filtrujeme jen existující sloupce
        valid_cols = [c for c in display_cols if c in table_df.columns]
        st.dataframe(table_df[valid_cols].rename(columns=rename_map), hide_index=True, use_container_width=True)
else:
    st.warning(f"Tabulka pro sezónu {season} není dostupná (nebo sezóna ještě nezačala).")

# 4. Zobrazení Zápasů (Karty)
st.subheader("📅 Nadcházející zápasy")

if events:
    for event in events:
        # Základní info
        match_name = event.get("strEvent", "Unknown vs Unknown")
        date = event.get("dateEvent", "")
        time = event.get("strTime", "")[:5] # Ořízneme sekundy
        home_team = event.get("strHomeTeam")
        away_team = event.get("strAwayTeam")
        home_id = event.get("idHomeTeam")
        away_id = event.get("idAwayTeam")
        
        # Predikce
        ph, pa, status = predict_match(home_id, away_id, table_df)
        
        # Loga (načítáme jen pokud máme ID)
        logo_h = None
        logo_a = None
        
        # Zobrazení karty
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 1])
            
            # Sloupec 1: Datum
            with c1:
                st.write(f"**{date}**")
                st.caption(time)
            
            # Sloupec 2: Domácí
            with c2:
                # Zkusíme zobrazit logo, jinak text
                # Poznámka: Stahování log pro každý zápas může být pomalé, 
                # v reálu bychom to měli cachovat hromadně.
                # Pro demo zobrazíme text zarovnaný doprava.
                st.markdown(f"<div style='text-align: right'><b>{home_team}</b></div>", unsafe_allow_html=True)
                if status == "OK":
                    st.progress(ph / 100)
            
            # Sloupec 3: VS a Predikce
            with c3:
                st.markdown("<div style='text-align: center'>VS</div>", unsafe_allow_html=True)
                if status == "OK":
                    if ph > 55:
                        st.success(f"Tip: {home_team}")
                    elif pa > 55:
                        st.error(f"Tip: {away_team}")
                    else:
                        st.warning("Vyrovnané")
            
            # Sloupec 4: Hosté
            with c4:
                st.markdown(f"<div style='text-align: left'><b>{away_team}</b></div>", unsafe_allow_html=True)
                if status == "OK":
                    st.progress(pa / 100)
            
            # Sloupec 5: Detaily
            with c5:
                with st.popover("Info"):
                    st.write(f"Šance D: {ph:.1f}%")
                    st.write(f"Šance H: {pa:.1f}%")
                    st.write(f"Férový kurz 1: {100/ph:.2f}" if ph > 0 else "")
                    st.write(f"Férový kurz 2: {100/pa:.2f}" if pa > 0 else "")

            st.markdown("---")
else:
    st.info("V této lize nejsou naplánovány žádné zápasy v nejbližší době (nebo API nevrátilo data).")

# --- PATIČKA ---
st.markdown("---")
st.caption("Powered by TheSportsDB.com (Free Tier). Data jsou poskytována komunitou.")
