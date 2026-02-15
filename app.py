import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---
if "APISPORTS_KEY" in st.secrets:
    API_KEY = st.secrets["APISPORTS_KEY"]
else:
    st.error("Chybí APISPORTS_KEY v Secrets!")
    st.stop()

URL_BASE = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

st.set_page_config(page_title="Betting Master Future", layout="wide")

# --- DEFINICE LIG ---
LIGY = {
    "🇬🇧 Championship (Anglie 2)": 40,
    "🇬🇧 Premier League (Anglie 1)": 39,
    "🇨🇿 Fortuna Liga (Česko 1)": 345,
    "🇩🇪 Bundesliga (Německo 1)": 78,
    "🇩🇪 2. Bundesliga (Německo 2)": 79,
    "🇪🇸 La Liga (Španělsko 1)": 140,
    "🇪🇸 La Liga 2 (Španělsko 2)": 141,
    "🇮🇹 Serie A (Itálie 1)": 135,
    "🇮🇹 Serie B (Itálie 2)": 136,
    "🇫🇷 Ligue 1 (Francie 1)": 61,
    "🇫🇷 Ligue 2 (Francie 2)": 62,
    "🇳🇱 Eredivisie (Holandsko 1)": 88,
    "🇵🇱 Ekstraklasa (Polsko 1)": 106,
    "🇪🇺 Liga Mistrů": 2
}

# --- POMOCNÉ FUNKCE ---
def format_formy(forma_str):
    if not forma_str: return ""
    mapping = {"W": "🟢", "D": "⚪", "L": "🔴"}
    return "".join([mapping.get(char, "❓") for char in forma_str])

# --- SIDEBAR ---
st.sidebar.title("Nastavení")
vybrana_liga_nazev = st.sidebar.selectbox("Soutěž:", list(LIGY.keys()))
LIGA_ID = LIGY[vybrana_liga_nazev]

# PŘIDÁNO: Rozšířený výběr sezón včetně budoucnosti
# API bere rok startu sezóny (např. 2025 = sezóna 2025/2026)
vybrana_sezona = st.sidebar.selectbox("Začátek sezóny (Rok):", [2025, 2024, 2023, 2022], index=0)

st.sidebar.info(f"Limit API: 100 požadavků/den.")

# --- NAČÍTÁNÍ DAT ---
@st.cache_data(ttl=3600)
def nacti_tabulku(liga_id, sezona):
    url = f"{URL_BASE}/standings"
    querystring = {"season": str(sezona), "league": str(liga_id)}
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        data = response.json()
        
        if not data['response']: return None

        standings = data['response'][0]['league']['standings'][0]
        
        tymy_info = {}
        seznam_tymu = [] 
        
        for radek in standings:
            tym_nazev = radek['team']['name']
            logo = radek['team']['logo']
            body = radek['points']
            skore_plus = radek['all']['goals']['for']
            skore_minus = radek['all']['goals']['against']
            rozdil_skore = radek['goalsDiff']
            forma = radek['form'] 
            
            bonus_formy = 0
            if forma:
                bonus_formy = forma.count("W") * 3 + forma.count("D") * 1
            
            sila = body + bonus_formy + (rozdil_skore / 2)
            
            tymy_info[tym_nazev] = {
                "sila": sila,
                "logo": logo,
                "forma_raw": forma,
                "forma_visual": format_formy(forma),
                "pozice": radek['rank'],
                "skore": f"{skore_plus}:{skore_minus}"
            }
            
            seznam_tymu.append({
                "Pozice": radek['rank'],
                "Tým": tym_nazev,
                "Body": body,
                "Skóre": f"{skore_plus}:{skore_minus}",
                "Rozdíl": rozdil_skore,
                "Forma": format_formy(forma)
            })
            
        return tymy_info, pd.DataFrame(seznam_tymu)
        
    except Exception as e:
        return None, None

@st.cache_data(ttl=3600)
def nacti_zapasy(liga_id, sezona):
    url = f"{URL_BASE}/fixtures"
    # Hledáme "next 10" zápasů
    querystring = {"season": str(sezona), "league": str(liga_id), "next": "10"}
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        return response.json()['response']
    except:
        return []

# --- UI APLIKACE ---
st.title(f"⚽ {vybrana_liga_nazev}")
st.caption(f"Zobrazená sezóna: {vybrana_sezona}/{vybrana_sezona+1}")

# 1. Načtení dat
with st.spinner("Analyzuji statistiky..."):
    tymy_db, df_tabulka = nacti_tabulku(LIGA_ID, vybrana_sezona)

# Pokud tabulka neexistuje (např. začátek sezóny a API ještě nemá tabulku), zkusíme alespoň zápasy
if not tymy_db:
    st.warning(f"Tabulka pro sezónu {vybrana_sezona}/{vybrana_sezona+1} zatím není v API dostupná.")
    st.write("Důvod: Buď sezóna ještě nezačala, nebo API nemá data. Zkus přepnout rok v menu.")
    tymy_db = {} 

tab1, tab2 = st.tabs(["🔮 Predikce & Kurzy", "📊 Tabulka Ligy"])

with tab1:
    zapasy = nacti_zapasy(LIGA_ID, vybrana_sezona)
    
    if not zapasy:
        st.info(f"Žádné naplánované zápasy pro sezónu {vybrana_sezona} v nejbližší době.")
    else:
        st.write(f"Nalezeno {len(zapasy)} nadcházejících zápasů:")
        
        for zapas in zapasy:
            domaci = zapas['teams']['home']['name']
            hoste = zapas['teams']['away']['name']
            datum = datetime.fromisoformat(zapas['fixture']['date'].replace("Z", "+00:00")).strftime("%d.%m. %H:%M")
            
            # Loga (bereme přímo ze zápasu, kdyby nebyla v DB)
            logo_d = zapas['teams']['home']['logo']
            logo_h = zapas['teams']['away']['logo']

            info_d = tymy_db.get(domaci)
            info_h = tymy_db.get(hoste)
            
            # KARTA ZÁPASU
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
                
                # Pokud máme data pro predikci
                if info_d and info_h:
                    sila_d = info_d['sila'] + 15
                    sila_h = info_h['sila']
                    celkova = sila_d + sila_h
                    if celkova == 0: celkova = 1
                    proc_d = (sila_d / celkova) * 100
                    proc_h = (sila_h / celkova) * 100
                    
                    try:
                        kurz_d = 100 / proc_d
                        kurz_h = 100 / proc_h
                    except:
                        kurz_d = 0; kurz_h = 0
                        
                    tip_text = ""
                    if proc_d > 60: tip_text = f"Tip: {domaci}"
                    elif proc_h > 60: tip_text = f"Tip: {hoste}"
                    else: tip_text = "Tip: Remíza / Risk"
                    
                    stred_obsah = f"#### {int(proc_d)}% : {int(proc_h)}%"
                    detail_d = f"#{info_d['pozice']} | {info_d['forma_visual']}"
                    detail_h = f"#{info_h['pozice']} | {info_h['forma_visual']}"
                else:
                    # Pokud nemáme data (začátek sezóny), ukážeme jen zápas bez predikce
                    stred_obsah = "#### VS"
                    tip_text = "Čekám na data z tabulky..."
                    detail_d = ""
                    detail_h = ""

                with c2:
                    st.image(logo_d, width=40)
                    st.write(f"**{domaci}**")
                    if detail_d: st.caption(detail_d)
                
                with c3:
                    st.write(f"*{datum}*")
                    st.markdown(stred_obsah)
                    if "Tip" in tip_text and "Risk" not in tip_text:
                        st.success(tip_text)
                    else:
                        st.warning(tip_text)
                        
                with c4:
                    st.image(logo_h, width=40)
                    st.write(f"**{hoste}**")
                    if detail_h: st.caption(detail_h)
                
                if info_d and info_h:
                    with st.expander("💰 Detailní analýza"):
                        k1, k2 = st.columns(2)
                        k1.metric("Férový kurz (1)", f"{kurz_d:.2f}")
                        k2.metric("Férový kurz (2)", f"{kurz_h:.2f}")
                
                st.markdown("---")

with tab2:
    if df_tabulka is not None and not df_tabulka.empty:
        st.dataframe(df_tabulka, hide_index=True, use_container_width=True)
    else:
        st.info("Tabulka pro vybranou sezónu není k dispozici.")
