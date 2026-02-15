import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Universal Sport Predictor", layout="wide")

# ==========================================\n# 1. MODUL: FOTBAL (WorldFootball.net)\n# ==========================================\n
def app_fotbal():
    st.header("⚽ Fotbalový Svět")
    st.caption("Zdroj: WorldFootball.net (Tabulky + Rozlosování)")

    # --- DEFINICE LIG (Slugy pro URL) ---
    # Tady přidáváme vše, co jsi chtěl
    LIGY = {
        # Hlavní
        "🇬🇧 Premier League": "eng-premier-league",
        "🇬🇧 Championship (Anglie 2)": "eng-championship",
        "🇩🇪 Bundesliga": "ger-bundesliga",
        "🇩🇪 2. Bundesliga": "ger-2-bundesliga",
        "🇪🇸 La Liga": "esp-primera-division",
        "🇮🇹 Serie A": "ita-serie-a",
        "🇮🇹 Serie B": "ita-serie-b",
        "🇫🇷 Ligue 1": "fra-ligue-1",
        "🇫🇷 Ligue 2": "fra-ligue-2",
        "🇳🇱 Eredivisie": "ned-eredivisie",
        "🇳🇱 Eerste Divisie (Holandsko 2)": "ned-eerste-divisie",
        # Další Evropa
        "🇨🇿 Fortuna Liga": "cze-1-liga",
        "🇵🇱 Ekstraklasa (Polsko)": "pol-ekstraklasa",
        "🇩🇰 Superliga (Dánsko)": "dnk-superliga",
        "🇵🇹 Primeira Liga (Portugalsko)": "por-primeira-liga",
        "🇷🇴 Liga 1 (Rumunsko)": "rom-liga-1",
        "🇬🇷 Super League (Řecko)": "gre-super-league",
        "🇧🇬 Parva Liga (Bulharsko)": "bul-a-grupa",
        "🇮🇱 Premier League (Izrael)": "isr-ligat-haal",
        "🇸🇮 PrvaLiga (Slovinsko)": "svn-prvaliga",
        "🇷🇸 SuperLiga (Srbsko)": "srb-super-liga",
        "🇹🇷 SüperLig (Turecko)": "tur-sueper-lig"
    }

    # --- UI ---
    c1, c2 = st.columns([2, 1])
    with c1: vybrana_liga = st.selectbox("Vyber ligu:", list(LIGY.keys()))
    with c2: rok = st.selectbox("Sezóna (začátek):", [2025, 2024, 2023], index=1)
    
    slug = LIGY[vybrana_liga]
    sezona_str = f"{rok}-{rok+1}"

    # --- SCRAPING FUNKCE ---
    @st.cache_data(ttl=3600)
    def scrape_worldfootball(league_slug, season):
        url = f"https://www.worldfootball.net/competition/{league_slug}-{season}/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        
        try:
            r = requests.get(url, headers=headers)
            if r.status_code == 404:
                return None, None, f"Sezóna {season} pro tuto ligu ještě neexistuje."
            if r.status_code != 200:
                return None, None, f"Chyba připojení: {r.status_code}"
            
            dfs = pd.read_html(r.text)
            
            # 1. Najít tabulku (Standings)
            df_table = None
            for df in dfs:
                # Hledáme tabulku, která má sloupec "Team" a "Pt" (Body)
                cols = [str(c).lower() for c in df.columns]
                if any("team" in c for c in cols) and any("pt" in c for c in cols):
                    df_table = df
                    break
            
            # 2. Najít zápasy (Schedule)
            # WorldFootball má často aktuální kolo jako tabulku, která má "-" ve skóre nebo čase
            df_matches = None
            for df in dfs:
                if len(df.columns) >= 3:
                    # Hledáme tabulku, kde je datum nebo čas a dva týmy
                    sample = str(df.iloc[0].values)
                    if ":" in sample or "-" in sample:
                        # Pokud to není tabulka ligy (nemá body), je to asi rozpis
                        cols = [str(c).lower() for c in df.columns]
                        if not any("pt" in c for c in cols):
                            df_matches = df
                            break
            
            return df_table, df_matches, None

        except Exception as e:
            return None, None, str(e)

    # --- LOGIKA ---
    with st.spinner(f"Stahuji data z WorldFootball.net ({sezona_str})..."):
        df_tab, df_match, err = scrape_worldfootball(slug, sezona_str)

    if err:
        st.error(err)
    else:
        # Zpracování tabulky pro sílu týmů
        sila_tymu = {}
        if df_tab is not None:
            # Přejmenování sloupců
            # WorldFootball: #, Team, M., W, D, L, Goals, Dif, Pt
            try:
                # Najdeme správné indexy sloupců (občas se mění)
                col_team = [c for c in df_tab.columns if "Team" in str(c) or "Tým" in str(c)][0]
                col_pts = [c for c in df_tab.columns if "Pt" in str(c)][0]
                col_goals = [c for c in df_tab.columns if "Goals" in str(c) or "Skóre" in str(c)][0]
                
                for idx, row in df_tab.iterrows():
                    tym = str(row[col_team])
                    body = float(row[col_pts])
                    
                    # Rozdíl skóre (např. 50:20)
                    goals = str(row[col_goals])
                    diff = 0
                    if ":" in goals:
                        g_pro, g_proti = map(int, goals.split(":"))
                        diff = g_pro - g_proti
                    
                    # Síla = Body + (Rozdíl skóre / 2)
                    sila = body + (diff / 2)
                    sila_tymu[tym] = sila
            except:
                st.warning("Nepodařilo se zpracovat detaily tabulky, predikce budou méně přesné.")

        # Zobrazení
        tab1, tab2 = st.tabs(["📅 Zápasy a Predikce", "📊 Tabulka"])
        
        with tab1:
            if df_match is not None:
                st.subheader("Aktuální / Nadcházející kolo")
                
                # WorldFootball tabulka zápasů nemá hlavičky, jsou to indexy 0, 1, 2...
                # Obvykle: 0=Čas, 1=Domácí, 2=Skóre/Pomlčka, 3=Hosté
                
                for idx, row in df_match.iterrows():
                    try:
                        # Detekce sloupců
                        cas = str(row[0])
                        domaci = str(row[1])
                        hoste = str(row[3]) # Obvykle index 3, někdy 2
                        
                        # Pokud je to nadpis nebo prázdné
                        if "Team" in domaci or pd.isna(domaci): continue
                        
                        # Hledání síly (Fuzzy matching, protože názvy se mohou lišit)
                        s_d = 0
                        s_h = 0
                        
                        # Jednoduchý fuzzy match
                        for t_name, s_val in sila_tymu.items():
                            if domaci in t_name or t_name in domaci: s_d = s_val
                            if hoste in t_name or t_name in hoste: s_h = s_val
                        
                        # Predikce
                        tip = ""
                        barva = "gray"
                        
                        if s_d > 0 and s_h > 0:
                            s_d += 5 # Domácí výhoda
                            total = s_d + s_h
                            p_d = (s_d / total) * 100
                            p_h = (s_h / total) * 100
                            
                            if p_d > 55: 
                                tip = f"Tip: {domaci} ({int(p_d)}%)"
                                barva = "green"
                            elif p_h > 55: 
                                tip = f"Tip: {hoste} ({int(p_h)}%)"
                                barva = "red"
                            else: 
                                tip = "Vyrovnané / Remíza"
                                barva = "orange"
                        else:
                            tip = "Nedostatek dat pro predikci"

                        with st.container():
                            c1, c2, c3 = st.columns([3, 2, 3])
                            with c1: st.markdown(f"<div style=\'text-align:right\'><b>{domaci}</b></div>", unsafe_allow_html=True)
                            with c2: 
                                st.markdown(f"<div style=\'text-align:center\'>{cas}<br>VS</div>", unsafe_allow_html=True)
                                if barva == "green": st.success(tip)
                                elif barva == "red": st.error(tip)
                                elif barva == "orange": st.warning(tip)
                                else: st.caption(tip)
                            with c3: st.markdown(f"<div style=\'text-align:left\'><b>{hoste}</b></div>", unsafe_allow_html=True)
                            st.markdown("---")
                    except: continue
            else:
                st.info("Rozpis zápasů nebyl na stránce nalezen.")

        with tab2:
            if df_tab is not None:
                st.dataframe(df_tab, hide_index=True, use_container_width=True)
            else:
                st.warning("Tabulka ligy nebyla nalezena.")


# ==========================================\n# 2. MODUL: TENIS (BettingClosed)\n# ==========================================\n
def app_tenis():
    st.header("🎾 Tenisové Predikce")
    st.caption("Zdroj: BettingClosed.com (Dnešní zápasy)")

    @st.cache_data(ttl=1800)
    def scrape_bettingclosed():
        # Tato stránka obsahuje přímo predikce
        url = "https://www.bettingclosed.com/predictions/date-matches/today/tennis/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200: return [], f"Chyba {r.status_code}"
            
            dfs = pd.read_html(r.text)
            
            matches = []
            # BettingClosed má jednu hlavní tabulku se zápasy
            # Musíme najít tu správnou
            for df in dfs:
                # Převedeme na string
                df_str = df.astype(str)
                # Hledáme tabulku, která má hodně řádků a obsahuje predikce
                if len(df) > 5:
                    # Iterace
                    for idx, row in df_str.iterrows():
                        # Struktura je složitá, zkusíme najít jména hráčů a predikci
                        # Obvykle je to jeden dlouhý řetězec nebo rozdělené sloupce
                        row_text = " ".join(row.values)
                        
                        if "-" in row_text and ("1" in row_text or "2" in row_text):
                            # Pokus o extrakci
                            # Toto je velmi hrubý odhad, protože každá tabulka je jiná
                            # Ale BettingClosed často dává predikci do posledního sloupce
                            
                            # Zkusíme najít dva hráče
                            # Většinou sloupec 1 nebo 2
                            try:
                                cas = row[0]
                                zapas = row[2] # Často jména hráčů
                                predikce = row.iloc[-1] # Poslední sloupec bývá predikce
                                
                                if len(zapas) > 5 and "-" in zapas:
                                    matches.append({
                                        "Čas": cas,
                                        "Zápas": zapas,
                                        "Predikce": predikce
                                    })
                            except: continue
                    
                    if len(matches) > 0: break # Našli jsme tabulku
            
            return matches, None
            
        except Exception as e:
            return [], str(e)

    with st.spinner("Stahuji tenisové tipy z BettingClosed..."):
        matches, error = scrape_bettingclosed()

    if error:
        st.error(f"Chyba: {error}")
    elif not matches:
        st.warning("Nepodařilo se načíst zápasy. Web mohl změnit strukturu.")
        st.write("Zkusíme alternativní zdroj: **TennisExplorer (Schedule)**")
        st.markdown("[Otevřít TennisExplorer Schedule](https://www.tennisexplorer.com/matches/)")
    else:
        st.success(f"Nalezeno {len(matches)} zápasů s predikcí.")
        
        for m in matches:
            with st.container():
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{m[\'Zápas\']}**")
                    st.caption(f"Čas: {m[\'Čas\']}")
                with c2:
                    # Zvýraznění predikce
                    pred = str(m[\'Predikce\']).lower()
                    if "1" in pred: st.success("Tip: Domácí (1)")
                    elif "2" in pred: st.error("Tip: Hosté (2)")
                    else: st.info(f"Tip: {m[\'Predikce\']}")
                st.markdown("---")

# ==========================================\n# HLAVNÍ ROZCESTNÍK\n# ==========================================\n
st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🎾 Tenis"])

if sport == "⚽ Fotbal":
    app_fotbal()
elif sport == "🎾 Tenis":
    app_tenis()
