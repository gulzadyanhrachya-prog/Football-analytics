import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Sport Betting Hub v8", layout="wide")

# --- MAGICKÁ FUNKCE PRO OBCHÁZENÍ 403 ---
# Tato funkce pošle požadavek přes prostředníka (Proxy)
def get_html_via_proxy(url):
    # Použijeme corsproxy.io jako tunel
    proxy_url = f"https://corsproxy.io/?{url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(proxy_url, headers=headers)
        return response
    except Exception as e:
        return None

# ==========================================
# 1. MODUL: FOTBAL (WorldFootball přes Proxy)
# ==========================================

def app_fotbal():
    st.header("⚽ Fotbalový Svět")
    st.caption("Zdroj: WorldFootball.net (Tunelováno přes Proxy)")

    # --- DEFINICE LIG ---
    LIGY = {
        "🇬🇧 Premier League": "eng-premier-league",
        "🇬🇧 Championship": "eng-championship",
        "🇩🇪 Bundesliga": "ger-bundesliga",
        "🇩🇪 2. Bundesliga": "ger-2-bundesliga",
        "🇪🇸 La Liga": "esp-primera-division",
        "🇮🇹 Serie A": "ita-serie-a",
        "🇮🇹 Serie B": "ita-serie-b",
        "🇫🇷 Ligue 1": "fra-ligue-1",
        "🇫🇷 Ligue 2": "fra-ligue-2",
        "🇳🇱 Eredivisie": "ned-eredivisie",
        "🇳🇱 Eerste Divisie": "ned-eerste-divisie",
        "🇨🇿 Fortuna Liga": "cze-1-liga",
        "🇵🇱 Ekstraklasa": "pol-ekstraklasa",
        "🇩🇰 Superliga": "dnk-superliga",
        "🇵🇹 Primeira Liga": "por-primeira-liga",
        "🇷🇴 Liga 1": "rom-liga-1",
        "🇬🇷 Super League": "gre-super-league",
        "🇧🇬 Parva Liga": "bul-a-grupa",
        "🇮🇱 Premier League": "isr-ligat-haal",
        "🇸🇮 PrvaLiga": "svn-prvaliga",
        "🇷🇸 SuperLiga": "srb-super-liga",
        "🇹🇷 SüperLig": "tur-sueper-lig"
    }

    c1, c2 = st.columns([2, 1])
    with c1: vybrana_liga = st.selectbox("Vyber ligu:", list(LIGY.keys()))
    with c2: rok = st.selectbox("Sezóna (začátek):", [2025, 2024, 2023], index=1)
    
    slug = LIGY[vybrana_liga]
    sezona_str = f"{rok}-{rok+1}"

    @st.cache_data(ttl=3600)
    def scrape_worldfootball(league_slug, season):
        url = f"https://www.worldfootball.net/competition/{league_slug}-{season}/"
        
        # POUŽITÍ PROXY
        r = get_html_via_proxy(url)
        
        if r is None or r.status_code != 200:
            return None, None, f"Chyba připojení (Status: {r.status_code if r else 'Error'})"
        
        try:
            dfs = pd.read_html(r.text)
            
            # 1. Tabulka
            df_table = None
            for df in dfs:
                cols = [str(c).lower() for c in df.columns]
                if any("team" in c for c in cols) and any("pt" in c for c in cols):
                    df_table = df
                    break
            
            # 2. Zápasy
            df_matches = None
            for df in dfs:
                if len(df.columns) >= 3:
                    sample = str(df.iloc[0].values)
                    if ":" in sample or "-" in sample:
                        cols = [str(c).lower() for c in df.columns]
                        if not any("pt" in c for c in cols):
                            df_matches = df
                            break
            return df_table, df_matches, None
        except Exception as e:
            return None, None, str(e)

    with st.spinner(f"Stahuji data pro {vybrana_liga}..."):
        df_tab, df_match, err = scrape_worldfootball(slug, sezona_str)

    if err:
        st.error(err)
        st.write("Tip: Pokud vidíš chybu 404, tato liga v sezóně 2025 ještě neexistuje. Přepni na 2024.")
    else:
        # Výpočet síly
        sila_tymu = {}
        if df_tab is not None:
            try:
                col_team = [c for c in df_tab.columns if "Team" in str(c) or "Tým" in str(c)][0]
                col_pts = [c for c in df_tab.columns if "Pt" in str(c)][0]
                col_goals = [c for c in df_tab.columns if "Goals" in str(c) or "Skóre" in str(c)][0]
                
                for idx, row in df_tab.iterrows():
                    tym = str(row[col_team])
                    try: body = float(row[col_pts])
                    except: body = 0
                    
                    goals = str(row[col_goals])
                    diff = 0
                    if ":" in goals:
                        parts = goals.split(":")
                        diff = int(parts[0]) - int(parts[1])
                    
                    sila_tymu[tym] = body + (diff / 2)
            except: pass

        tab1, tab2 = st.tabs(["📅 Zápasy a Predikce", "📊 Tabulka"])
        
        with tab1:
            if df_match is not None:
                st.subheader("Aktuální kolo")
                for idx, row in df_match.iterrows():
                    try:
                        cas = str(row[0])
                        domaci = str(row[1])
                        hoste = str(row[3])
                        
                        if "Team" in domaci or pd.isna(domaci): continue
                        
                        s_d = 0; s_h = 0
                        for t_name, s_val in sila_tymu.items():
                            if domaci in t_name or t_name in domaci: s_d = s_val
                            if hoste in t_name or t_name in hoste: s_h = s_val
                        
                        tip = ""; barva = "gray"
                        if s_d > 0 and s_h > 0:
                            s_d += 5
                            total = s_d + s_h
                            p_d = (s_d / total) * 100
                            p_h = (s_h / total) * 100
                            
                            if p_d > 55: tip = f"Tip: {domaci} ({int(p_d)}%)"; barva = "green"
                            elif p_h > 55: tip = f"Tip: {hoste} ({int(p_h)}%)"; barva = "red"
                            else: tip = "Vyrovnané"; barva = "orange"
                        else:
                            tip = "Nedostatek dat"

                        with st.container():
                            c1, c2, c3 = st.columns([3, 2, 3])
                            with c1: st.markdown(f"<div style='text-align:right'><b>{domaci}</b></div>", unsafe_allow_html=True)
                            with c2: 
                                st.markdown(f"<div style='text-align:center'>{cas}<br>VS</div>", unsafe_allow_html=True)
                                if barva == "green": st.success(tip)
                                elif barva == "red": st.error(tip)
                                elif barva == "orange": st.warning(tip)
                                else: st.caption(tip)
                            with c3: st.markdown(f"<div style='text-align:left'><b>{hoste}</b></div>", unsafe_allow_html=True)
                            st.markdown("---")
                    except: continue
            else:
                st.info("Rozpis nenalezen.")

        with tab2:
            if df_tab is not None:
                st.dataframe(df_tab, hide_index=True, use_container_width=True)

# ==========================================
# 2. MODUL: TENIS (BettingClosed přes Proxy)
# ==========================================

def app_tenis():
    st.header("🎾 Tenisové Predikce")
    st.caption("Zdroj: BettingClosed.com (Tunelováno přes Proxy)")

    @st.cache_data(ttl=1800)
    def scrape_bettingclosed_proxy():
        url = "https://www.bettingclosed.com/predictions/date-matches/today/tennis/"
        
        # POUŽITÍ PROXY
        r = get_html_via_proxy(url)
        
        if r is None or r.status_code != 200:
            return [], f"Chyba {r.status_code if r else 'Connection'}"
            
        try:
            dfs = pd.read_html(r.text)
            matches = []
            
            for df in dfs:
                df_str = df.astype(str)
                if len(df) > 5:
                    for idx, row in df_str.iterrows():
                        row_text = " ".join(row.values)
                        if "-" in row_text and ("1" in row_text or "2" in row_text):
                            try:
                                cas = row[0]
                                zapas = row[2]
                                predikce = row.iloc[-1]
                                if len(zapas) > 5 and "-" in zapas:
                                    matches.append({"Čas": cas, "Zápas": zapas, "Predikce": predikce})
                            except: continue
                    if len(matches) > 0: break
            return matches, None
        except Exception as e:
            return [], str(e)

    with st.spinner("Stahuji tenisové tipy..."):
        matches, error = scrape_bettingclosed_proxy()

    if error:
        st.error(f"Chyba: {error}")
        st.write("Zkus obnovit stránku za chvíli.")
    elif not matches:
        st.warning("Nebyly nalezeny žádné zápasy.")
    else:
        st.success(f"Nalezeno {len(matches)} zápasů.")
        for m in matches:
            with st.container():
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{m['Zápas']}**")
                    st.caption(f"Čas: {m['Čas']}")
                with c2:
                    pred = str(m['Predikce']).lower()
                    if "1" in pred: st.success("Tip: Domácí (1)")
                    elif "2" in pred: st.error("Tip: Hosté (2)")
                    else: st.info(f"Tip: {m['Predikce']}")
                st.markdown("---")

# ==========================================
# HLAVNÍ ROZCESTNÍK
# ==========================================

st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🎾 Tenis"])

if sport == "⚽ Fotbal":
    app_fotbal()
elif sport == "🎾 Tenis":
    app_tenis()
