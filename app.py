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
SEZONA = 2023 

st.set_page_config(page_title="Betting Master v2", layout="wide")

# --- DEFINICE LIG ---
LIGY = {
    "🇨🇿 Fortuna Liga (Česko 1)": 345,
    "🇬🇧 Premier League (Anglie 1)": 39,
    "🇬🇧 Championship (Anglie 2)": 40,
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
    """Převede 'WWLD' na barevné kuličky"""
    if not forma_str: return ""
    mapping = {"W": "🟢", "D": "⚪", "L": "🔴"}
    return "".join([mapping.get(char, "❓") for char in forma_str])

# --- SIDEBAR ---
st.sidebar.title("Výběr Soutěže")
vybrana_liga_nazev = st.sidebar.selectbox("Liga:", list(LIGY.keys()))
LIGA_ID = LIGY[vybrana_liga_nazev]
st.sidebar.info(f"Limit API: 100 požadavků/den.")

# --- NAČÍTÁNÍ DAT ---
@st.cache_data(ttl=3600)
def nacti_tabulku(liga_id):
    url = f"{URL_BASE}/standings"
    querystring = {"season": str(SEZONA), "league": str(liga_id)}
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        data = response.json()
        
        if not data['response']: return None

        standings = data['response'][0]['league']['standings'][0]
        
        tymy_info = {}
        seznam_tymu = [] # Pro zobrazení tabulky
        
        for radek in standings:
            tym_nazev = radek['team']['name']
            logo = radek['team']['logo']
            body = radek['points']
            skore_plus = radek['all']['goals']['for']
            skore_minus = radek['all']['goals']['against']
            rozdil_skore = radek['goalsDiff']
            forma = radek['form'] 
            
            # --- NOVÝ ALGORITMUS SÍLY ---
            # 1. Základ jsou body
            # 2. Bonus za formu (W=3, D=1)
            # 3. Bonus za skóre (Rozdíl skóre / 2) -> Tým co vyhrává 5:0 je silnější
            
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
def nacti_zapasy(liga_id):
    url = f"{URL_BASE}/fixtures"
    querystring = {"season": str(SEZONA), "league": str(liga_id), "next": "10"}
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        return response.json()['response']
    except:
        return []

# --- UI APLIKACE ---
st.title(f"⚽ {vybrana_liga_nazev}")

# 1. Načtení dat
with st.spinner("Analyzuji statistiky..."):
    tymy_db, df_tabulka = nacti_tabulku(LIGA_ID)

if not tymy_db:
    st.warning("Nepodařilo se načíst data. Zkontroluj sezónu nebo limity.")
    st.stop()

# TABS - Rozdělení na Predikce a Tabulku
tab1, tab2 = st.tabs(["🔮 Predikce & Kurzy", "📊 Tabulka Ligy"])

with tab1:
    zapasy = nacti_zapasy(LIGA_ID)
    
    if not zapasy:
        st.info("Žádné naplánované zápasy.")
    else:
        st.write(f"Nalezeno {len(zapasy)} nadcházejících zápasů:")
        
        for zapas in zapasy:
            domaci = zapas['teams']['home']['name']
            hoste = zapas['teams']['away']['name']
            datum = datetime.fromisoformat(zapas['fixture']['date'].replace("Z", "+00:00")).strftime("%d.%m. %H:%M")
            
            info_d = tymy_db.get(domaci)
            info_h = tymy_db.get(hoste)
            
            if info_d and info_h:
                # Výpočet šancí
                sila_d = info_d['sila'] + 15 # Domácí výhoda
                sila_h = info_h['sila']
                celkova = sila_d + sila_h
                if celkova == 0: celkova = 1
                
                proc_d = (sila_d / celkova) * 100
                proc_h = (sila_h / celkova) * 100
                
                # Kurzy
                try:
                    kurz_d = 100 / proc_d
                    kurz_h = 100 / proc_h
                except:
                    kurz_d = 0; kurz_h = 0

                # KARTA ZÁPASU
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
                    
                    with c2:
                        st.image(info_d['logo'], width=40)
                        st.write(f"**{domaci}**")
                        st.caption(f"#{info_d['pozice']} | {info_d['forma_visual']}")
                    
                    with c3:
                        st.write(f"*{datum}*")
                        st.markdown(f"#### {int(proc_d)}% : {int(proc_h)}%")
                        
                        # Logika tipu
                        if proc_d > 60: 
                            st.success(f"Tip: {domaci}")
                        elif proc_h > 60: 
                            st.error(f"Tip: {hoste}")
                        else: 
                            st.warning("Tip: Remíza / Risk")
                            
                    with c4:
                        st.image(info_h['logo'], width=40)
                        st.write(f"**{hoste}**")
                        st.caption(f"#{info_h['pozice']} | {info_h['forma_visual']}")
                    
                    with st.expander("💰 Detailní analýza a kurzy"):
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Férový kurz (1)", f"{kurz_d:.2f}")
                        k2.metric("Férový kurz (2)", f"{kurz_h:.2f}")
                        k3.metric("Rozdíl síly", f"{int(sila_d - sila_h)}")
                        
                        st.write("**Srovnání skóre:**")
                        st.write(f"{domaci}: {info_d['skore']}")
                        st.write(f"{hoste}: {info_h['skore']}")
                    
                    st.markdown("---")

with tab2:
    st.dataframe(df_tabulka, hide_index=True, use_container_width=True)
