import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- KONFIGURACE ---\nif "APISPORTS_KEY" in st.secrets:
    API_KEY = st.secrets["APISPORTS_KEY"]
else:
    st.error("Chybí APISPORTS_KEY v Secrets!")
    st.stop()

URL_BASE = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

st.set_page_config(page_title="Betting Master Diagnostic", layout="wide")

# --- DEFINICE LIG ---\nLIGY = {
    "🇬🇧 Premier League (Anglie 1)": 39,
    "🇬🇧 Championship (Anglie 2)": 40,
    "🇨🇿 Fortuna Liga (Česko 1)": 345,
    "🇩🇪 Bundesliga (Německo 1)": 78,
    "🇪🇸 La Liga (Španělsko 1)": 140,
    "🇮🇹 Serie A (Itálie 1)": 135,
    "🇫🇷 Ligue 1 (Francie 1)": 61,
    "🇪🇺 Liga Mistrů": 2
}

# --- POMOCNÉ FUNKCE ---\ndef format_formy(forma_str):
    if not forma_str: return ""
    mapping = {"W": "🟢", "D": "⚪", "L": "🔴"}
    return "".join([mapping.get(char, "❓") for char in forma_str])

# --- SIDEBAR ---\nst.sidebar.title("Nastavení")
vybrana_liga_nazev = st.sidebar.selectbox("Soutěž:", list(LIGY.keys()))
LIGA_ID = LIGY[vybrana_liga_nazev]

# Změnil jsem výchozí index na 2023, protože tam data určitě jsou
vybrana_sezona = st.sidebar.selectbox("Sezóna (Rok startu):", [2025, 2024, 2023], index=2)

st.sidebar.markdown("---")
st.sidebar.subheader("🛠️ Diagnostika API")

# --- NAČÍTÁNÍ DAT S DIAGNOSTIKOU ---\n# Zrušil jsem cache, abychom viděli aktuální chybu hned
def nacti_tabulku(liga_id, sezona):
    url = f"{URL_BASE}/standings"
    querystring = {"season": str(sezona), "league": str(liga_id)}
    
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        data = response.json()
        
        # VYPÍŠEME CHYBY PŘÍMO DO SIDEBARU
        if "errors" in data and data["errors"]:
            st.sidebar.error("CHYBA API:")
            st.sidebar.json(data["errors"])
            return None, None
            
        if "response" not in data or not data['response']:
            st.sidebar.warning(f"API vrátilo prázdná data pro sezónu {sezona}.")
            st.sidebar.write("Tip: Zkus přepnout na rok 2023.")
            return None, None

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
                "forma_visual": format_formy(forma),
                "pozice": radek['rank'],
                "skore": f"{skore_plus}:{skore_minus}"
            }
            
            seznam_tymu.append({
                "Pozice": radek['rank'],
                "Tým": tym_nazev,
                "Body": body,
                "Skóre": f"{skore_plus}:{skore_minus}",
                "Forma": format_formy(forma)
            })
            
        return tymy_info, pd.DataFrame(seznam_tymu)
        
    except Exception as e:
        st.sidebar.error(f"Kritická chyba kódu: {e}")
        return None, None

def nacti_zapasy(liga_id, sezona):
    url = f"{URL_BASE}/fixtures"
    querystring = {"season": str(sezona), "league": str(liga_id), "next": "10"}
    try:
        response = requests.get(url, headers=HEADERS, params=querystring)
        data = response.json()
        if "errors" in data and data["errors"]:
            return []
        return data['response']
    except:
        return []

# --- UI APLIKACE ---\nst.title(f"⚽ {vybrana_liga_nazev}")
st.caption(f"Sezóna: {vybrana_sezona}/{vybrana_sezona+1}")

with st.spinner("Komunikuji se serverem..."):
    tymy_db, df_tabulka = nacti_tabulku(LIGA_ID, vybrana_sezona)

if not tymy_db:
    st.warning("Žádná data k zobrazení. Podívej se vlevo do sekce 'Diagnostika API'.")
else:
    tab1, tab2 = st.tabs(["🔮 Predikce", "📊 Tabulka"])
    
    with tab1:
        zapasy = nacti_zapasy(LIGA_ID, vybrana_sezona)
        if not zapasy:
            st.info("Žádné zápasy.")
        else:
            for zapas in zapasy:
                domaci = zapas['teams']['home']['name']
                hoste = zapas['teams']['away']['name']
                datum = datetime.fromisoformat(zapas['fixture']['date'].replace("Z", "+00:00")).strftime("%d.%m. %H:%M")
                
                info_d = tymy_db.get(domaci)
                info_h = tymy_db.get(hoste)
                
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
                    if info_d and info_h:
                        sila_d = info_d['sila'] + 15
                        sila_h = info_h['sila']
                        celkova = sila_d + sila_h
                        if celkova == 0: celkova = 1
                        proc_d = (sila_d / celkova) * 100
                        proc_h = (sila_h / celkova) * 100
                        
                        with c2: st.write(f"**{domaci}**"); st.caption(info_d['forma_visual'])
                        with c3: 
                            st.write(f"*{datum}*")
                            st.markdown(f"#### {int(proc_d)}% : {int(proc_h)}%")
                        with c4: st.write(f"**{hoste}**"); st.caption(info_h['forma_visual'])
                    else:
                        with c3: st.write(f"{domaci} vs {hoste}")
                    st.markdown("---")

    with tab2:
        st.dataframe(df_tabulka, hide_index=True, use_container_width=True)
