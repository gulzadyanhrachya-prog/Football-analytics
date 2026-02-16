import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="SGO Explorer", layout="wide")
st.title("🕵️ SportsGameOdds API Explorer")

# 1. Načtení klíče
try:
    API_KEY = st.secrets["SGO_KEY"]
    st.success("✅ API Klíč načten.")
except:
    st.error("Chybí SGO_KEY v Secrets!")
    st.stop()

# 2. Konfigurace
BASE_URL = "https://api.sportsgameodds.com/v1" # Základní adresa (podle dokumentace)

# 3. Výběr Endpointu (podle dokumentace)
st.subheader("Testování Endpointů")
endpoint_type = st.selectbox("Co chceš stáhnout?", [
    "Seznam Sportů (Sports)",
    "Seznam Lig (Leagues)",
    "Zápasy na dnešek (Games)",
    "Kurzy (Odds)",
    "Vlastní URL"
])

# Sestavení URL
url = ""
params = {}

if endpoint_type == "Seznam Sportů (Sports)":
    url = f"{BASE_URL}/sports"
    
elif endpoint_type == "Seznam Lig (Leagues)":
    sport_id = st.number_input("ID Sportu (např. 1 pro fotbal):", value=1)
    url = f"{BASE_URL}/leagues"
    params = {"sportId": sport_id}

elif endpoint_type == "Zápasy na dnešek (Games)":
    sport_id = st.number_input("ID Sportu:", value=1)
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Podle dokumentace SGO se často používá date nebo startDate
    url = f"{BASE_URL}/games"
    params = {"sportId": sport_id, "date": date_str}

elif endpoint_type == "Kurzy (Odds)":
    game_id = st.text_input("ID Zápasu (Game ID):")
    url = f"{BASE_URL}/odds"
    if game_id:
        params = {"gameId": game_id}

else: # Vlastní URL
    custom_suffix = st.text_input("Zadej část za v1/ (např. /sports):", "/sports")
    url = f"{BASE_URL}{custom_suffix}"

# 4. Tlačítko pro odeslání
if st.button("🚀 Odeslat požadavek"):
    st.write(f"Volám URL: `{url}`")
    st.write(f"Parametry: `{params}`")
    
    headers = {
        "X-Api-Key": API_KEY,  # SGO obvykle používá tento header
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        st.write(f"Status Code: **{response.status_code}**")
        
        if response.status_code == 200:
            data = response.json()
            st.success("Data úspěšně stažena!")
            
            # Zobrazení JSONu
            with st.expander("Zobrazit surový JSON"):
                st.json(data)
            
            # Pokus o převod na tabulku
            if isinstance(data, list):
                st.dataframe(pd.DataFrame(data))
            elif isinstance(data, dict) and "data" in data:
                st.dataframe(pd.DataFrame(data["data"]))
            else:
                st.write("Data mají složitou strukturu, podívej se do JSONu výše.")
                
        elif response.status_code == 401 or response.status_code == 403:
            st.error("⛔ Chyba ověření (401/403). Zkontroluj API klíč.")
        else:
            st.error(f"Chyba serveru: {response.text}")
            
    except Exception as e:
        st.error(f"Kritická chyba: {e}")
