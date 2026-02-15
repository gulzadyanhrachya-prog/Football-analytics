import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---
# Získání klíče z trezoru
try:
    API_KEY = st.secrets["FOOTBALL_API_KEY"]
except FileNotFoundError:
    st.error("Chybí API klíč v Secrets!")
    st.stop()

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {'X-Auth-Token': API_KEY}

st.set_page_config(page_title="Betting Advisor", layout="wide")
st.title("⚽ Premier League: Predikce Zápasů")

# --- FUNKCE 1: Tabulka a síla týmů ---
@st.cache_data(ttl=600)
def nacti_silu_tymu():
    url = f"{BASE_URL}/competitions/PL/standings"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        st.error(f"Chyba při stahování tabulky: {response.status_code}")
        return None

    data = response.json()
    tabulka = data['standings'][0]['table']
    
    sila_tymu = {}
    for radek in tabulka:
        tym = radek['team']['name']
        body = radek['points']
        # Ošetření chyby: Pokud API nepošle formu, použijeme prázdný řetězec
        forma = radek.get('form', "") 
        
        # Výpočet síly: Body + (Výhry v posledních 5 zápasech * 2)
        if forma:
            bonus_formy = forma.count("W") * 2
        else:
            bonus_formy = 0
            
        sila_tymu[tym] = body + bonus_formy
        
    return sila_tymu

# --- FUNKCE 2: Nadcházející zápasy ---
def nacti_nadchazejici_zapasy():
    # Stáhneme zápasy na příštích 10 dní
    # API filtr: dateFrom (dnes) a dateTo (za 10 dní)
    dnes = datetime.now().strftime('%Y-%m-%d')
    # Jednoduchý trik: stáhneme prostě "SCHEDULED" (naplánované)
    url = f"{BASE_URL}/competitions/PL/matches?status=SCHEDULED"
    
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        st.warning(f"Nepodařilo se stáhnout rozpis zápasů (Kód {response.status_code}).")
        return []
        
    data = response.json()
    return data['matches']

# --- HLAVNÍ LOGIKA APLIKACE ---

# 1. Načtení síly týmů
with st.spinner('Analyzuji sílu týmů z tabulky...'):
    sila_tymu = nacti_silu_tymu()

if not sila_tymu:
    st.error("Aplikace nemůže pokračovat bez dat z tabulky.")
    st.stop()

st.success(f"✅ Úspěšně analyzováno {len(sila_tymu)} týmů.")

# 2. Načtení zápasů
with st.spinner('Hledám nadcházející zápasy...'):
    zapasy = nacti_nadchazejici_zapasy()

# 3. Výpočet predikcí
if len(zapasy) == 0:
    st.info("Momentálně nejsou naplánované žádné zápasy v blízké době (nebo API limituje výhled).")
else:
    st.subheader(f"🔮 Predikce na nejbližší zápasy")
    
    predikce_list = []
    
    # Zpracujeme jen prvních 10 nalezených zápasů
    for zapas in zapasy[:10]:
        domaci = zapas['homeTeam']['name']
        hoste = zapas['awayTeam']['name']
        datum_raw = zapas['utcDate']
        datum = datum_raw[:10] # Jen datum bez času
        
        # Získáme sílu (pokud tým neznáme, dáme 0)
        sila_domaci = sila_tymu.get(domaci, 0)
        sila_hoste = sila_tymu.get(hoste, 0)
        
        # Pokud nemáme data o síle (třeba tým postoupil a není v naší tabulce), přeskočíme
        if sila_domaci == 0 or sila_hoste == 0:
            continue

        # ALGORITMUS
        skore_domaci = sila_domaci + 5 # Výhoda domácích
        skore_hoste = sila_hoste
        
        rozdil = skore_domaci - skore_hoste
        sance_procenta = 50 + (rozdil / 2) # Hrubý odhad procent
        
        # Omezení procent na 5-95%
        sance_procenta = max(5, min(95, sance_procenta))

        if rozdil > 8:
            tip = f"Výhra {domaci}"
            duvera = "Vysoká"
        elif rozdil < -8:
            tip = f"Výhra {hoste}"
            duvera = "Vysoká"
        else:
            tip = "Remíza / Vyrovnané"
            duvera = "Nízká"
            
        predikce_list.append({
            "Datum": datum,
            "Domácí": domaci,
            "Hosté": hoste,
            "Náš Tip": tip,
            "Důvěra": duvera,
            "Síla D": sila_domaci,
            "Síla H": sila_hoste
        })
    
    if predikce_list:
        df_predikce = pd.DataFrame(predikce_list)
        # Zobrazíme tabulku bez indexu (číslování řádků)
        st.dataframe(df_predikce, hide_index=True)
        
        # Detailní rozbor prvního zápasu
        top_zapas = predikce_list[0]
        st.markdown("---")
        st.subheader(f"Detail: {top_zapas['Domácí']} vs {top_zapas['Hosté']}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Síla Domácí", top_zapas['Síla D'])
        col2.metric("Síla Hosté", top_zapas['Síla H'])
        col3.metric("Náš Tip", top_zapas['Náš Tip'])
        
    else:
        st.warning("Našla se data o zápasech, ale nepodařilo se je spárovat s tabulkou.")
