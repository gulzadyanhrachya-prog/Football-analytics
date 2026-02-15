import streamlit as st
import pandas as pd
import requests

# --- KONFIGURACE ---
# Tady si aplikace sáhne do "trezoru" pro tvůj klíč
API_KEY = st.secrets["FOOTBALL_API_KEY"]
BASE_URL = "https://api.football-data.org/v4"

# Nastavení stránky
st.set_page_config(page_title="Live Sport Data", layout="wide")
st.title("⚽ Fotbalový Analytik - Premier League")

# --- FUNKCE PRO STAŽENÍ DAT ---
@st.cache_data(ttl=600) # Data se uloží do paměti na 10 minut (šetříme limity API)
def nacti_tabulku_pl():
    headers = {'X-Auth-Token': API_KEY}
    # Kód 'PL' znamená Premier League
    url = f"{BASE_URL}/competitions/PL/standings"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        st.error(f"Chyba při stahování dat: {response.status_code}")
        return None
        
    data = response.json()
    # Vytáhneme jen celkovou tabulku (TOTAL)
    tabulka = data['standings'][0]['table']
    return tabulka

# --- HLAVNÍ ČÁST APLIKACE ---

st.write("Stahuji aktuální data z Anglie...")

raw_data = nacti_tabulku_pl()

if raw_data:
    # Zpracování dat do hezké tabulky pro Python
    tymy = []
    for radek in raw_data:
        tymy.append({
            'Pozice': radek['position'],
            'Tým': radek['team']['name'],
            'Zápasy': radek['playedGames'],
            'Výhry': radek['won'],
            'Remízy': radek['draw'],
            'Prohry': radek['lost'],
            'Body': radek['points'],
            'Góly': f"{radek['goalsFor']}:{radek['goalsAgainst']}",
            'Forma': radek['form'] # Např. "W,L,W,D,W"
        })
    
    df = pd.DataFrame(tymy)
    
    # Zobrazení tabulky
    st.subheader("Aktuální tabulka Premier League")
    st.dataframe(df, use_container_width=True)
    
    # Jednoduchá vizualizace bodů
    st.subheader("Porovnání bodů")
    st.bar_chart(df.set_index('Tým')['Body'])
    
    # Analýza formy (Bonus)
    st.subheader("Tip pro sázení: Týmy s nejlepší formou")
    st.write("Týmy, které vyhrály posledních 5 zápasů:")
    # Filtrujeme týmy, které mají ve formě samé výhry (nebo alespoň neprohrály)
    # Toto je jednoduchý příklad, později to vylepšíme
    for index, row in df.iterrows():
        if row['Forma'] and row['Forma'].count('W') >= 4: # 4 a více výher z 5
            st.success(f"🔥 {row['Tým']} je v ráži! (Forma: {row['Forma']})")

else:
    st.warning("Nepodařilo se načíst data. Zkontroluj API klíč v Secrets.")
