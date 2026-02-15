import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---\ntry:
    API_KEY = st.secrets["FOOTBALL_API_KEY"]
except FileNotFoundError:
    st.error("Chybí API klíč v Secrets!")
    st.stop()

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {'X-Auth-Token': API_KEY}

st.set_page_config(page_title="Betting Pro", layout="wide")

# --- FUNKCE ---\n
@st.cache_data(ttl=600)
def nacti_data_ligy():
    # Stáhneme tabulku včetně log týmů
    url = f"{BASE_URL}/competitions/PL/standings"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        return None

    data = response.json()
    tabulka = data['standings'][0]['table']
    
    # Uložíme si data o týmech do slovníku pro rychlé vyhledávání
    tymy_info = {}
    for radek in tabulka:
        tym = radek['team']['name']
        logo = radek['team']['crest']
        body = radek['points']
        
        # --- OPRAVA CHYBY ZDE ---
        # Získáme formu, ale pokud je None (null), nahradíme ji prázdným řetězcem ""
        raw_form = radek.get('form')
        if raw_form is None:
            forma = ""
        else:
            forma = raw_form
        
        # Výpočet síly (Body + Bonus za formu)
        # Teď už 'forma' je vždy text, takže .count() nespadne
        bonus = forma.count("W") * 3 
        sila = body + bonus
        
        tymy_info[tym] = {
            "sila": sila,
            "logo": logo,
            "forma": forma
        }
        
    return tymy_info

def nacti_zapasy():
    url = f"{BASE_URL}/competitions/PL/matches?status=SCHEDULED"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return []
    return response.json()['matches']

# --- UI APLIKACE ---\n
st.title("⚽ Premier League: Smart Betting")
st.markdown("---")

# 1. Načtení dat
with st.spinner('Stahuji data a loga týmů...'):
    tymy_db = nacti_data_ligy()

if not tymy_db:
    st.error("Chyba při stahování dat. Zkontroluj API klíč nebo dostupnost služby.")
    st.stop()

# 2. Načtení zápasů
zapasy = nacti_zapasy()

if not zapasy:
    st.info("Žádné naplánované zápasy v dohledu.")
else:
    st.subheader(f"📅 Nadcházející příležitosti ({len(zapasy)})")
    
    # Projdeme zápasy a pro každý vytvoříme hezkou kartu
    for zapas in zapasy[:10]: # Limit na 10 zápasů
        domaci = zapas['homeTeam']['name']
        hoste = zapas['awayTeam']['name']
        datum = zapas['utcDate'][:10]
        
        # Získáme info z naší databáze
        info_domaci = tymy_db.get(domaci)
        info_hoste = tymy_db.get(hoste)
        
        # Zobrazíme jen pokud máme data o obou týmech
        if info_domaci and info_hoste:
            # --- MATEMATIKA SÁZENÍ ---
            sila_d = info_domaci['sila'] + 10 # Domácí výhoda
            sila_h = info_hoste['sila']
            
            celkova_sila = sila_d + sila_h
            
            # Ošetření dělení nulou (kdyby náhodou měli oba 0 bodů)
            if celkova_sila == 0:
                sance_domaci = 50
                sance_hoste = 50
            else:
                sance_domaci = (sila_d / celkova_sila) * 100
                sance_hoste = (sila_h / celkova_sila) * 100
            
            # Výpočet férového kurzu
            try:
                kurz_domaci = 100 / sance_domaci
                kurz_hoste = 100 / sance_hoste
            except ZeroDivisionError:
                kurz_domaci = 0
                kurz_hoste = 0
            
            # --- VIZUALIZACE KARTY ZÁPASU ---
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([1, 3, 2, 3, 1])
                
                with col2:
                    st.image(info_domaci['logo'], width=50)
                    st.write(f"**{domaci}**")
                    st.caption(f"Forma: {info_domaci['forma']}")
                
                with col3:
                    st.write(f"*{datum}*")
                    st.markdown(f"### {int(sance_domaci)}% vs {int(sance_hoste)}%")
                    
                    # Zvýraznění favorita
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
                
                # Detailní data pod kartou
                with st.expander(f"📊 Analýza a Kurzy pro: {domaci} vs {hoste}"):
                    c1, c2 = st.columns(2)
                    c1.metric("Náš Férový Kurz (Domácí)", f"{kurz_domaci:.2f}")
                    c2.metric("Náš Férový Kurz (Hosté)", f"{kurz_hoste:.2f}")
                    st.info("Pokud sázková kancelář nabízí vyšší kurz než je náš 'Férový', jde o výhodnou sázku (Value Bet).")
                
                st.markdown("---")
