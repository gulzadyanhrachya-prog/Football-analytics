import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Scraping Master 2026", layout="wide")

# --- KONFIGURACE URL ADRES ---
# Mapování názvů lig na URL slugy webu WorldFootball.net
LIGY_URL = {
    "🇬🇧 Premier League": "eng-premier-league",
    "🇬🇧 Championship": "eng-championship",
    "🇨🇿 Fortuna Liga": "cze-1-liga",
    "🇩🇪 Bundesliga": "ger-bundesliga",
    "🇩🇪 2. Bundesliga": "ger-2-bundesliga",
    "🇪🇸 La Liga": "esp-primera-division",
    "🇪🇸 La Liga 2": "esp-segunda-division",
    "🇮🇹 Serie A": "ita-serie-a",
    "🇮🇹 Serie B": "ita-serie-b",
    "🇫🇷 Ligue 1": "fra-ligue-1",
    "🇳🇱 Eredivisie": "ned-eredivisie",
    "🇪🇺 Liga Mistrů": "champions-league"
}

# --- SIDEBAR ---
st.sidebar.title("Nastavení")
vybrana_liga = st.sidebar.selectbox("Soutěž:", list(LIGY_URL.keys()))
url_slug = LIGY_URL[vybrana_liga]

# PŘIDÁNO: Možnost vybrat rok 2025 (pro sezónu 25/26)
rok = st.sidebar.selectbox("Sezóna (Rok startu):", [2025, 2024, 2023], index=0)
sezona_str = f"{rok}-{rok+1}"

st.sidebar.info(f"Hledám data na adrese: worldfootball.net/competition/{url_slug}-{sezona_str}/")

# --- FUNKCE PRO SCRAPING ---
@st.cache_data(ttl=3600) 
def scrape_data(league_slug, season_str):
    # Sestavení URL
    base_url = f"https://www.worldfootball.net/competition/{league_slug}-{season_str}"
    
    # Hlavička prohlížeče (aby nás web nezablokoval)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(base_url, headers=headers)
        
        # Kontrola, zda stránka existuje
        if response.status_code == 404:
            return None, None, f"Stránka pro sezónu {season_str} nebyla nalezena (Chyba 404). Pravděpodobně ještě není vytvořena."
        if response.status_code != 200:
            return None, None, f"Chyba připojení: {response.status_code}"

        # Pandas najde tabulky v HTML
        dfs = pd.read_html(response.text)
        
        # 1. Hledání tabulky ligy
        tabulka_df = None
        for df in dfs:
            # Hledáme tabulku, která má sloupce jako Team, Pt, Pts, nebo #
            cols = [c.lower() for c in df.columns]
            if any("team" in c for c in cols) and (any("pt" in c for c in cols) or "goals" in cols):
                tabulka_df = df
                break
        
        # 2. Hledání zápasů (Aktuální kolo)
        zapasy_df = None
        for df in dfs:
            # Tabulka zápasů má obvykle 3 sloupce (Domácí, Skóre, Hosté) a čas
            if len(df.columns) >= 5 and df.shape[0] > 0:
                # Heuristika: Hledáme pomlčku v datech (skóre nebo čas)
                if df.iloc[0].astype(str).str.contains("-").any():
                     zapasy_df = df
                     break
        
        return tabulka_df, zapasy_df, None

    except ValueError:
        return None, None, "Na stránce nebyla nalezena žádná tabulka (ValueError)."
    except Exception as e:
        return None, None, f"Chyba scrapingu: {e}"

# --- UI APLIKACE ---
st.title(f"⚽ {vybrana_liga}")
st.caption(f"Sezóna {sezona_str}")

with st.spinner(f"Stahuji data pro sezónu {sezona_str}..."):
    df_tabulka, df_zapasy, error = scrape_data(url_slug, sezona_str)

if error:
    st.error(error)
    st.write("Možné řešení:")
    st.write("1. Zkus přepnout na starší sezónu (2024), abys ověřil, že scraper funguje.")
    st.write("2. Pokud 2024 funguje a 2025 ne, znamená to, že web WorldFootball.net ještě nevytvořil stránku pro novou sezónu.")
else:
    tab1, tab2 = st.tabs(["📊 Tabulka Ligy", "📅 Zápasy / Kolo"])
    
    with tab1:
        if df_tabulka is not None:
            # Přejmenování sloupců pro hezčí vzhled (pokud existují)
            rename_map = {
                "Team": "Tým", "M.": "Z", "W": "V", "D": "R", "L": "P", 
                "Goals": "Skóre", "Dif": "+/-", "Pt": "Body", "Pts": "Body"
            }
            df_tabulka = df_tabulka.rename(columns=rename_map)
            st.dataframe(df_tabulka, hide_index=True, use_container_width=True)
        else:
            st.warning("Tabulka ligy nebyla na stránce nalezena.")

    with tab2:
        if df_zapasy is not None:
            st.write("Nalezený rozpis (zápasy):")
            st.dataframe(df_zapasy, hide_index=True, use_container_width=True)
        else:
            st.info("Na stránce nebyly nalezeny žádné aktuální zápasy.")
