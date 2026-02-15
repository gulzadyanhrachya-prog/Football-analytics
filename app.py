import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---
if "FOOTBALL_API_KEY" in st.secrets:
    API_KEY = st.secrets["FOOTBALL_API_KEY"]
else:
    st.error("Chybí API klíč v Secrets! Nastav ho v .streamlit/secrets.toml nebo na Streamlit Cloud.")
    st.stop()

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {'X-Auth-Token': API_KEY}

st.set_page_config(page_title="Betting Pro", layout="wide")

# --- DEFINICE LIG (Kódování API) ---
# Toto jsou ligy dostupné ve Free Tieru
LIGY = {
    "🇬🇧 Premier League (Anglie 1)": "PL",
    "🇬🇧 Championship (Anglie 2)": "ELC",
    "🇩🇪 Bundesliga (Německo 1)": "BL1",
    "🇪🇸 La Liga (Španělsko 1)": "PD",
    "🇮🇹 Serie A (Itálie 1)": "SA",
    "🇫🇷 Ligue 1 (Francie 1)": "FL1",
    "🇳🇱 Eredivisie (Holandsko 1)": "DED",
    "🇵🇹 Primeira Liga (Portugalsko 1)": "PPL",
    "🇪🇺 Liga Mistrů (Champions League)": "CL"
}

# --- SIDEBAR (VÝBĚR LIGY) ---
st.sidebar.title("Nastavení")
vybrana_liga_nazev = st.sidebar.selectbox("Vyber soutěž:", list(LIGY.keys()))
KOD_LIGY = LIGY[vybrana_liga_nazev]

st.sidebar.info(f"Právě analyzuji: {vybrana_liga_nazev}")
st.sidebar.markdown("---")
st.sidebar.write("Poznámka: Free verze API má omezený počet volání za minutu. Pokud data nenaskočí, chvíli počkej.")

# --- FUNKCE ---

@st.cache_data(ttl=600)
def nacti_data_ligy(kod_ligy):
    # Stáhneme tabulku pro VYBRANOU ligu
    url = f"{BASE_URL}/competitions/{kod_ligy}/standings"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        return None

    data = response.json()
    # Některé ligy (třeba Liga mistrů) mají jinou strukturu, zkusíme najít tabulku 'TOTAL'
    try:
        tabulka = data['standings'][0]['table']
    except (KeyError, IndexError):
        return None
    
    tymy_info = {}
    for radek in tabulka:
        tym = radek['team']['name']
        logo = radek['team']['crest']
        body = radek['points']
        
        raw_form = radek.get('form')
        if raw_form is None:
            forma = ""
        else:
            forma = raw_form
        
        bonus = forma.count("W") * 3 
        sila = body + bonus
        
        tymy_info[tym] = {
            "sila": sila,
            "logo": logo,
            "forma": forma
        }
        
    return tymy_info

def nacti_zapasy(kod_ligy):
    # Stáhneme zápasy pro VYBRANOU ligu
    url = f"{BASE_URL}/competitions/{kod_ligy}/matches?status=SCHEDULED"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return []
    return response.json()['matches']

# --- UI APLIKACE ---

st.title(f"⚽ {vybrana_liga_nazev}")
st.markdown("---")

# 1. Načtení dat
with st.spinner(f'Stahuji data pro {vybrana_liga_nazev}...'):
    tymy_db = nacti_data_ligy(KOD_LIGY)

if not tymy_db:
    st.warning(f"Pro soutěž {vybrana_liga_nazev} se nepodařilo načíst tabulku. (Možná právě neprobíhá nebo má jiný formát).")
    st.stop()

# 2. Načtení zápasů
zapasy = nacti_zapasy(KOD_LIGY)

if not zapasy:
    st.info("Žádné naplánované zápasy v dohledu pro tuto ligu.")
else:
    st.subheader(f"📅 Nadcházející zápasy ({len(zapasy)})")
    
    # Limit na 15 zápasů, ať se to nenačítá věčnost
    for zapas in zapasy[:15]: 
        domaci = zapas['homeTeam']['name']
        hoste = zapas['awayTeam']['name']
        datum = zapas['utcDate'][:10]
        
        info_domaci = tymy_db.get(domaci)
        info_hoste = tymy_db.get(hoste)
        
        if info_domaci and info_hoste:
            # --- MATEMATIKA SÁZENÍ ---
            sila_d = info_domaci['sila'] + 10 
            sila_h = info_hoste['sila']
            
            celkova_sila = sila_d + sila_h
            
            if celkova_sila == 0:
                sance_domaci = 50
                sance_hoste = 50
            else:
                sance_domaci = (sila_d / celkova_sila) * 100
                sance_hoste = (sila_h / celkova_sila) * 100
            
            try:
                kurz_domaci = 100 / sance_domaci
                kurz_hoste = 100 / sance_hoste
            except ZeroDivisionError:
                kurz_domaci = 0
                kurz_hoste = 0
            
            # --- VIZUALIZACE ---
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([1, 3, 2, 3, 1])
                
                with col2:
                    st.image(info_domaci['logo'], width=50)
                    st.write(f"**{domaci}**")
                    st.caption(f"Forma: {info_domaci['forma']}")
                
                with col3:
                    st.write(f"*{datum}*")
                    st.markdown(f"### {int(sance_domaci)}% vs {int(sance_hoste)}%")
                    
                    if sance_domaci > 60:
                        st.success(f"Tip: {domaci}")
                    elif sance_hoste > 60:
                        st.error(f"Tip: {hoste}")
                    else:
                        st.warning("Tip: Remíza/Risk")

                with col4:
                    st.image(info_hoste['logo'], width=50)
                    st.write(f"**{hoste}**")
                    st.caption(f"Forma: {info_hoste['forma']}")
                
                with st.expander(f"📊 Analýza a Kurzy: {domaci} vs {hoste}"):
                    c1, c2 = st.columns(2)
                    c1.metric("Férový Kurz (Domácí)", f"{kurz_domaci:.2f}")
                    c2.metric("Férový Kurz (Hosté)", f"{kurz_hoste:.2f}")
                    st.info("Porovnej s kurzy sázkové kanceláře.")
                
                st.markdown("---")
