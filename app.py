import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---
# Hledáme klíč APISPORTS_KEY (pro API-Football)
if "APISPORTS_KEY" in st.secrets:
    API_KEY = st.secrets["APISPORTS_KEY"]
else:
    st.error("Chybí APISPORTS_KEY v Secrets! Zaregistruj se na dashboard.api-football.com a vlož klíč.")
    st.stop()

# --- ADRESA A HLAVIČKY ---
URL_BASE = "https://v3.football.api-sports.io"
HEADERS = {
    'x-apisports-key': API_KEY
}

# Aktuální sezóna (většina lig se hraje 2023/2024, takže pro API je to 2023)
SEZONA = 2023 

st.set_page_config(page_title="Betting Master", layout="wide")

# --- DEFINICE LIG (ID z API-Football) ---
LIGY = {
    "🇨🇿 Fortuna Liga (Česko 1)": 345,
    "🇬🇧 Premier League (Anglie 1)": 39,
    "🇬🇧 Championship (Anglie 2)": 40,
    "🇩🇪 Bundesliga (Německo 1)": 78,
    "🇩🇪 2. Bundesliga (Německo 2)": 79,
    "🇪🇸 La Liga (Španělsko 1)": 140,
    "🇪🇸 La Liga 2 (Španělsko 2)": 141,
    "🇮🇹 Serie A (Itálie 1)": 135,
    "🇮🇹 Serie B (Itálie 2)": 136,
    "🇫🇷 Ligue 1 (Francie 1)": 61,
    "🇫🇷 Ligue 2 (Francie 2)": 62,
    "🇳🇱 Eredivisie (Holandsko 1)": 88,
    "🇵🇱 Ekstraklasa (Polsko 1)": 106,
    "🇪🇺 Liga Mistrů": 2
}

# --- SIDEBAR ---
st.sidebar.title("Výběr Soutěže")
vybrana_liga_nazev = st.sidebar.selectbox("Liga:", list(LIGY.keys()))
LIGA_ID = LIGY[vybrana_liga_nazev]

st.sidebar.info(f"Limit API: 100 požadavků/den. Data se ukládají do paměti na 1 hodinu.")

# --- FUNKCE ---

@st.cache_data(ttl=3600)
def nacti_tabulku(liga_id):
    url = f"{URL_BASE}/standings"
    querystring = {"season": str(SEZONA), "league": str(liga_id)}
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        # Kontrola, zda API vrátilo data
        if not data['response']:
            return None

        standings = data['response'][0]['league']['standings'][0]
        
        tymy_info = {}
        for radek in standings:
            tym_nazev = radek['team']['name']
            tym_id = radek['team']['id']
            logo = radek['team']['logo']
            body = radek['points']
            forma = radek['form'] 
            
            if forma:
                bonus = forma.count("W") * 3 + forma.count("D") * 1
            else:
                bonus = 0
                forma = "?"
            
            sila = body + bonus
            
            tymy_info[tym_nazev] = {
                "id": tym_id,
                "sila": sila,
                "logo": logo,
                "forma": forma,
                "pozice": radek['rank']
            }
        return tymy_info
        
    except Exception as e:
        return None

@st.cache_data(ttl=3600)
def nacti_zapasy(liga_id):
    url = f"{URL_BASE}/fixtures"
    # Stáhneme "next 10" zápasů pro danou ligu
    querystring = {"season": str(SEZONA), "league": str(liga_id), "next": "10"}
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        data = response.json()
        return data['response']
    except:
        return []

# --- UI APLIKACE ---

st.title(f"⚽ {vybrana_liga_nazev}")
st.markdown("---")

# 1. Načtení dat o týmech
with st.spinner("Stahuji tabulku a statistiky..."):
    tymy_db = nacti_tabulku(LIGA_ID)

if not tymy_db:
    st.warning("Nepodařilo se načíst tabulku. Možné příčiny:")
    st.write("1. Pro tuto ligu ještě nezačala sezóna 2023/24.")
    st.write("2. Došel denní limit (100 volání).")
    st.write("3. Chyba v API klíči (zkontroluj Secrets).")
    st.stop()

# 2. Načtení zápasů
zapasy = nacti_zapasy(LIGA_ID)

if not zapasy:
    st.info("Žádné naplánované zápasy v nejbližší době.")
else:
    st.subheader("📅 Predikce na nadcházející zápasy")
    
    for zapas in zapasy:
        domaci_nazev = zapas['teams']['home']['name']
        hoste_nazev = zapas['teams']['away']['name']
        datum_raw = zapas['fixture']['date']
        datum = datetime.fromisoformat(datum_raw.replace("Z", "+00:00")).strftime("%d.%m. %H:%M")
        
        logo_domaci = zapas['teams']['home']['logo']
        logo_hoste = zapas['teams']['away']['logo']

        info_domaci = tymy_db.get(domaci_nazev)
        info_hoste = tymy_db.get(hoste_nazev)
        
        if info_domaci and info_hoste:
            sila_d = info_domaci['sila'] + 15 
            sila_h = info_hoste['sila']
            
            celkova = sila_d + sila_h
            if celkova == 0: celkova = 1
            
            proc_d = (sila_d / celkova) * 100
            proc_h = (sila_h / celkova) * 100
            
            try:
                kurz_d = 100 / proc_d
                kurz_h = 100 / proc_h
            except:
                kurz_d = 0
                kurz_h = 0

            with st.container():
                c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
                
                with c2:
                    st.image(logo_domaci, width=40)
                    st.write(f"**{domaci_nazev}**")
                    st.caption(f"#{info_domaci['pozice']} | {info_domaci['forma']}")
                
                with c3:
                    st.write(f"*{datum}*")
                    st.markdown(f"#### {int(proc_d)}% : {int(proc_h)}%")
                    if proc_d > 55: st.success(f"Tip: {domaci_nazev}")
                    elif proc_h > 55: st.error(f"Tip: {hoste_nazev}")
                    else: st.warning("Vyrovnané")
                
                with c4:
                    st.image(logo_hoste, width=40)
                    st.write(f"**{hoste_nazev}**")
                    st.caption(f"#{info_hoste['pozice']} | {info_hoste['forma']}")
                
                with st.expander("📊 Detailní kurzy"):
                    k1, k2 = st.columns(2)
                    k1.metric("Férový kurz Domácí", f"{kurz_d:.2f}")
                    k2.metric("Férový kurz Hosté", f"{kurz_h:.2f}")
                
                st.markdown("---")
