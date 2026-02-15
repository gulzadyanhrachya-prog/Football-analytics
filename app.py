import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="Scraping Master", layout="wide")

# --- KONFIGURACE URL ADRES ---
# Tady mapujeme názvy lig na jejich adresy na webu WorldFootball.net
# Pokud chceš přidat ligu, najdi ji na worldfootball.net a zkopíruj část URL za /competition/
LIGY_URL = {
    "🇬🇧 Premier League": "eng-premier-league",
    "🇬🇧 Championship": "eng-championship",
    "🇨🇿 Fortuna Liga": "cze-1-liga",
    "🇩🇪 Bundesliga": "ger-bundesliga",
    "🇩🇪 2. Bundesliga": "ger-2-bundesliga",
    "🇪🇸 La Liga": "esp-primera-division",
    "🇮🇹 Serie A": "ita-serie-a",
    "🇫🇷 Ligue 1": "fra-ligue-1",
    "🇳🇱 Eredivisie": "ned-eredivisie",
    "🇪🇺 Liga Mistrů": "champions-league"
}

# --- SIDEBAR ---
st.sidebar.title("Nastavení")
vybrana_liga = st.sidebar.selectbox("Soutěž:", list(LIGY_URL.keys()))
url_slug = LIGY_URL[vybrana_liga]

# Výběr sezóny (WorldFootball používá formát "2023-2024")
rok = st.sidebar.selectbox("Sezóna:", [2024, 2023], index=0)
sezona_str = f"{rok}-{rok+1}"

st.sidebar.info("Data jsou získávána metodou Scraping z webu worldfootball.net. Není potřeba žádný API klíč.")

# --- FUNKCE PRO SCRAPING ---
@st.cache_data(ttl=3600) # Ukládáme do paměti na 1 hodinu
def scrape_data(league_slug, season_str):
    # 1. Sestavíme URL
    base_url = f"https://www.worldfootball.net/competition/{league_slug}-{season_str}"
    
    # 2. Musíme se tvářit jako prohlížeč, jinak nás zablokují
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        # Stáhneme stránku
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return None, None, f"Chyba připojení: {response.status_code}"

        # Pandas umí automaticky najít všechny tabulky v HTML
        # Toto je ta magická část
        dfs = pd.read_html(response.text)
        
        # WorldFootball má obvykle tabulku ligy jako první nebo druhou tabulku na stránce
        # Musíme najít tu správnou. Hledáme tu, která má sloupec "Team" nebo "Tým" nebo "#"
        tabulka_df = None
        for df in dfs:
            if "Team" in df.columns and "Pt" in df.columns: # Pt = Points
                tabulka_df = df
                break
            # Alternativa pro některé ligy
            if "Team" in df.columns and "Pts" in df.columns:
                tabulka_df = df
                break
        
        if tabulka_df is None:
            return None, None, "Nepodařilo se najít tabulku na stránce."

        # Vyčistíme tabulku
        # Přejmenujeme sloupce pro lepší čitelnost
        # Struktura WorldFootball: #, Team, M., W, D, L, Goals, Dif, Pt
        rename_map = {
            "Team": "Tým",
            "M.": "Zápasy",
            "W": "Výhry",
            "D": "Remízy",
            "L": "Prohry",
            "Goals": "Skóre",
            "Dif": "Rozdíl",
            "Pt": "Body",
            "Pts": "Body"
        }
        tabulka_df = tabulka_df.rename(columns=rename_map)
        
        # Získáme i zápasy? 
        # Na hlavní stránce soutěže bývají "Current round" (aktuální kolo)
        # Zkusíme najít tabulku, která má datum a čas
        zapasy_df = None
        for df in dfs:
            # Hledáme tabulku, která má sloupec s datem (často nepojmenovaný) a dva týmy
            if len(df.columns) >= 5 and df.shape[0] > 0:
                # Jednoduchá heuristika: pokud tabulka obsahuje pomlčku "-" ve sloupci skóre nebo času
                if df.iloc[0].astype(str).str.contains("-").any():
                     # Často je to tabulka s aktuálním kolem
                     zapasy_df = df
                     break
        
        return tabulka_df, zapasy_df, None

    except Exception as e:
        return None, None, f"Chyba scrapingu: {e}"

# --- UI APLIKACE ---
st.title(f"⚽ {vybrana_liga}")
st.caption(f"Zdroj dat: WorldFootball.net | Sezóna {sezona_str}")

with st.spinner("Stahuji data z webu..."):
    df_tabulka, df_zapasy, error = scrape_data(url_slug, sezona_str)

if error:
    st.error(error)
    st.write("Možné příčiny:")
    st.write("1. Tato liga v sezóně {sezona_str} na webu neexistuje.")
    st.write("2. Web změnil strukturu a scraper potřebuje úpravu.")
else:
    tab1, tab2 = st.tabs(["📊 Tabulka", "📅 Aktuální kolo"])
    
    with tab1:
        if df_tabulka is not None:
            # Vybereme jen důležité sloupce
            cols = ["#", "Tým", "Zápasy", "Výhry", "Remízy", "Prohry", "Skóre", "Body"]
            # Filtrujeme jen sloupce, které v tabulce skutečně jsou
            dostupne_cols = [c for c in cols if c in df_tabulka.columns]
            
            st.dataframe(df_tabulka[dostupne_cols], hide_index=True, use_container_width=True)
            
            # Vizualizace síly (Body)
            if "Tým" in df_tabulka.columns and "Body" in df_tabulka.columns:
                st.bar_chart(df_tabulka.set_index("Tým")["Body"])
        else:
            st.warning("Tabulka nenalezena.")

    with tab2:
        if df_zapasy is not None:
            st.write("Nalezené zápasy (Aktuální kolo):")
            # Zobrazíme surovou tabulku zápasů, protože parsing HTML zápasů je složitý
            st.dataframe(df_zapasy, hide_index=True, use_container_width=True)
            st.info("Poznámka: Toto jsou data přímo z webu. Pro predikce bychom museli složitě čistit názvy týmů.")
        else:
            st.info("Na stránce nebyly nalezeny žádné aktuální zápasy.")
