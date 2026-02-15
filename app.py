import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---
API_KEY = st.secrets["1718d4bf83e644c5983bd4d790e928a8"]
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {'X-Auth-Token': API_KEY}

st.set_page_config(page_title="Betting Advisor", layout="wide")
st.title("⚽ Premier League: Predikce Zápasů")

# --- FUNKCE 1: Tabulka a síla týmů ---
@st.cache_data(ttl=600)
def nacti_data_tymy():
    url = f"{BASE_URL}/competitions/PL/standings"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    tabulka = data['standings'][0]['table']
    
    # Vytvoříme slovník, kde klíčem je název týmu a hodnotou je jeho síla (body)
    sila_tymu = {}
    for radek in tabulka:
        tym = radek['team']['name']
        body = radek['points']
        forma = radek['form'] # Např. "W,L,W"
        # Jednoduchý výpočet síly: Body + bonus za formu
        bonus_formy = forma.count("W") * 2 # 2 body navíc za každou výhru v posledních 5 zápasech
        sila_tymu[tym] = body + bonus_formy
        
    return sila_tymu

# --- FUNKCE 2: Nadcházející zápasy ---
def nacti_nadchazejici_zapasy():
    # Stáhneme zápasy, které jsou naplánované (SCHEDULED)
    url = f"{BASE_URL}/competitions/PL/matches?status=SCHEDULED"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    return data['matches']

# --- HLAVNÍ LOGIKA ---

# 1. Nejdřív načteme sílu týmů z tabulky
try:
    sila_tymu = nacti_data_tymy()
    st.success("✅ Data o síle týmů načtena.")
except:
    st.error("Chyba API. Zkontroluj klíč.")
    st.stop()

# 2. Načteme budoucí zápasy
zapasy = nacti_nadchazejici_zapasy()

# 3. Zobrazíme predikce pro nejbližších 10 zápasů
st.subheader("🔮 Predikce na nejbližší zápasy")
st.write("Algoritmus porovnává body v tabulce + aktuální formu + výhodu domácího prostředí.")

# Vytvoříme seznam pro hezkou tabulku
predikce_list = []

for zapas in zapasy[:10]: # Bereme jen prvních 10
    domaci = zapas['homeTeam']['name']
    hoste = zapas['awayTeam']['name']
    datum = zapas['utcDate'][:10] # Ořízneme čas, necháme jen datum
    
    # Získáme sílu týmů (pokud tým nenajdeme, dáme 0)
    sila_domaci = sila_tymu.get(domaci, 0)
    sila_hoste = sila_tymu.get(hoste, 0)
    
    # --- NÁŠ PRVNÍ ALGORITMUS ---
    # Přidáme 5 bodů k síle domácích (výhoda domácího hřiště)
    skore_domaci = sila_domaci + 5
    skore_hoste = sila_hoste
    
    # Rozhodnutí
    rozdil = skore_domaci - skore_hoste
    
    if rozdil > 10:
        tip = f"Výhra {domaci} (Favorit)"
        barva = "green" # Jasná výhra
    elif rozdil < -10:
        tip = f"Výhra {hoste} (Favorit)"
        barva = "red" # Prohra domácích
    else:
        tip = "Vyrovnaný zápas / Remíza"
        barva = "orange" # Riziko
        
    predikce_list.append({
        "Datum": datum,
        "Domácí": domaci,
        "Hosté": hoste,
        "Síla D": sila_domaci,
        "Síla H": sila_hoste,
        "Náš Tip": tip
    })

# Převedeme na tabulku a zobrazíme
df_predikce = pd.DataFrame(predikce_list)
st.dataframe(df_predikce)

# Vizualizace síly pro první zápas
if len(predikce_list) > 0:
    prvni_zapas = predikce_list[0]
    st.subheader(f"Detail zápasu: {prvni_zapas['Domácí']} vs {prvni_zapas['Hosté']}")
    
    col1, col2 = st.columns(2)
    col1.metric("Síla Domácí", prvni_zapas['Síla D'])
    col2.metric("Síla Hosté", prvni_zapas['Síla H'], delta_color="inverse")
    
    if prvni_zapas['Síla D'] > prvni_zapas['Síla H']:
        st.info(f"Domácí {prvni_zapas['Domácí']} jsou papírově silnější.")
    else:
        st.info(f"Hosté {prvni_zapas['Hosté']} jsou papírově silnější.")
