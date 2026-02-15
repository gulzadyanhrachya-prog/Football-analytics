import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

st.set_page_config(page_title="Hybrid Analyzer Debug", layout="wide")

# --- KONFIGURACE ZDROJŮ DAT ---
# Pro novou sezónu 2024/2025 se odkazy mohou měnit. 
# Zkoušíme odkazy pro nadcházející sezónu (start podzim 2024).
LIGY_CONFIG = {
    "🇬🇧 Premier League": {
        "history": "https://www.football-data.co.uk/mmz4281/2324/E0.csv", # Zatím bereme data z minulé sezóny pro formu
        "future": "https://fixturedownload.com/download/epl-2024-GMTStandardTime.csv"
    },
    "🇬🇧 Championship": {
        "history": "https://www.football-data.co.uk/mmz4281/2324/E1.csv",
        "future": "https://fixturedownload.com/download/championship-2024-GMTStandardTime.csv"
    },
    "🇩🇪 Bundesliga": {
        "history": "https://www.football-data.co.uk/mmz4281/2324/D1.csv",
        "future": "https://fixturedownload.com/download/bundesliga-2024-UTC.csv"
    },
    "🇪🇸 La Liga": {
        "history": "https://www.football-data.co.uk/mmz4281/2324/SP1.csv",
        "future": "https://fixturedownload.com/download/la-liga-2024-UTC.csv"
    },
    "🇮🇹 Serie A": {
        "history": "https://www.football-data.co.uk/mmz4281/2324/I1.csv",
        "future": "https://fixturedownload.com/download/serie-a-2024-UTC.csv"
    },
    "🇫🇷 Ligue 1": {
        "history": "https://www.football-data.co.uk/mmz4281/2324/F1.csv",
        "future": "https://fixturedownload.com/download/ligue-1-2024-UTC.csv"
    }
}

# --- POMOCNÁ FUNKCE: PŘEKLADAČ TÝMŮ ---
def normalizuj_nazev(nazev):
    if not isinstance(nazev, str): return ""
    nazev = nazev.lower().strip()
    mapping = {
        "man city": "manchester city",
        "man utd": "manchester united",
        "man united": "manchester united",
        "leicester": "leicester city",
        "leeds": "leeds united",
        "notts forest": "nottingham forest",
        "nott'm forest": "nottingham forest",
        "wolves": "wolverhampton wanderers",
        "wolverhampton": "wolverhampton wanderers",
        "brighton": "brighton & hove albion",
        "spurs": "tottenham hotspur",
        "tottenham": "tottenham hotspur",
        "west ham": "west ham united",
        "newcastle": "newcastle united"
    }
    return mapping.get(nazev, nazev)

# --- FUNKCE PRO STAŽENÍ DAT ---
@st.cache_data(ttl=3600)
def nacti_data(liga_nazev):
    urls = LIGY_CONFIG[liga_nazev]
    
    # 1. Stažení HISTORIE
    try:
        r_hist = requests.get(urls["history"])
        if r_hist.status_code == 200:
            df_hist = pd.read_csv(io.StringIO(r_hist.text))
        else:
            df_hist = None
    except Exception:
        df_hist = None

    # 2. Stažení BUDOUCNOSTI
    try:
        r_fut = requests.get(urls["future"])
        if r_fut.status_code == 200:
            # Zkusíme různé kódování, občas je to UTF-8, občas Latin-1
            try:
                df_fut = pd.read_csv(io.StringIO(r_fut.text))
            except:
                df_fut = pd.read_csv(io.StringIO(r_fut.content.decode('latin-1')))
        else:
            df_fut = None
    except Exception:
        df_fut = None
        
    return df_hist, df_fut

# --- VÝPOČET SÍLY TÝMŮ ---
def analyzuj_silu(df_hist):
    if df_hist is None: return {}
    tymy = {}
    
    for index, row in df_hist.iterrows():
        if pd.isna(row['FTR']): continue 
        
        domaci = normalizuj_nazev(row['HomeTeam'])
        hoste = normalizuj_nazev(row['AwayTeam'])
        vysledek = row['FTR'] 
        
        if domaci not in tymy: tymy[domaci] = {"Body": 0, "Z": 0, "Forma": []}
        if hoste not in tymy: tymy[hoste] = {"Body": 0, "Z": 0, "Forma": []}
        
        tymy[domaci]["Z"] += 1
        tymy[hoste]["Z"] += 1
        
        if vysledek == 'H':
            tymy[domaci]["Body"] += 3
            tymy[domaci]["Forma"].append("W")
            tymy[hoste]["Forma"].append("L")
        elif vysledek == 'A':
            tymy[hoste]["Body"] += 3
            tymy[hoste]["Forma"].append("W")\
            tymy[domaci]["Forma"].append("L")
        else:
            tymy[domaci]["Body"] += 1
            tymy[hoste]["Body"] += 1
            tymy[domaci]["Forma"].append("D")
            tymy[hoste]["Forma"].append("D")
            
    databaze_sily = {}
    for nazev, data in tymy.items():
        forma_list = data["Forma"][-5:] 
        forma_str = "".join(forma_list)
        bonus = forma_str.count("W") * 3 + forma_str.count("D") * 1
        sila = data["Body"] + bonus
        
        databaze_sily[nazev] = {
            "sila": sila,
            "forma": forma_str.replace("W", "🟢").replace("L", "🔴").replace("D", "⚪"),
            "body": data["Body"]
        }
    return databaze_sily

# --- UI APLIKACE ---
st.title("⚽ Hybridní Analytik (Debug Mode)")

# Sidebar
vybrana_liga = st.sidebar.selectbox("Vyber ligu:", list(LIGY_CONFIG.keys()))
zobrazit_raw = st.sidebar.checkbox("Zobrazit surová data (Debug)", value=True)

# Načtení dat
with st.spinner("Stahuji data..."):
    df_hist, df_fut, error = nacti_data(vybrana_liga), None, None
    df_hist, df_fut = df_hist # Rozbalení tuple

# 1. Analýza historie
db_sily = analyzuj_silu(df_hist)

# 2. Zpracování budoucnosti
if df_fut is not None:
    # DIAGNOSTIKA: Zobrazíme surová data, pokud je zaškrtnuto
    if zobrazit_raw:
        st.subheader("🛠️ Diagnostika: Surová data z rozpisu")
        st.write(f"Počet řádků v souboru: {len(df_fut)}")
        st.dataframe(df_fut.head())

    # Pokus o převod data - vylepšený
    # Zkusíme najít sloupec s datem
    col_date = None
    for c in df_fut.columns:
        if "Date" in c or "Time" in c:
            col_date = c
            break
            
    if col_date:
        # Převedeme na datetime, ignorujeme chyby (coerce)
        df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], dayfirst=True, errors='coerce')
        
        # Pokud to selhalo, zkusíme jiný formát
        if df_fut['DateObj'].isnull().all():
             df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], errors='coerce')

        dnes = datetime.now()
        
        # Filtr: Zápasy od dneška dál
        budouci_zapasy = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj')
        
        if budouci_zapasy.empty:
            st.warning("⚠️ Soubor s rozpisem existuje, ale neobsahuje žádné zápasy s datem v budoucnosti.")
            st.write(f"Dnešní datum: {dnes}")
            st.write("Poslední datum v souboru:")
            if not df_fut['DateObj'].isnull().all():
                st.write(df_fut['DateObj'].max())
        else:
            st.subheader(f"🔮 Predikce: {vybrana_liga}")
            
            for index, row in budouci_zapasy.head(10).iterrows():
                # Dynamické hledání sloupců pro týmy
                col_home = [c for c in df_fut.columns if "Home" in c][0]
                col_away = [c for c in df_fut.columns if "Away" in c][0]
                
                domaci_raw = row[col_home]
                hoste_raw = row[col_away]
                datum = row[col_date]
                
                domaci_norm = normalizuj_nazev(domaci_raw)
                hoste_norm = normalizuj_nazev(hoste_raw)
                
                info_d = db_sily.get(domaci_norm)
                info_h = db_sily.get(hoste_norm)
                
                # Fallback vyhledávání
                if not info_d:
                    for k in db_sily:
                        if domaci_norm in k or k in domaci_norm: info_d = db_sily[k]; break
                if not info_h:
                    for k in db_sily:
                        if hoste_norm in k or k in hoste_norm: info_h = db_sily[k]; break

                with st.container():
                    c1, c2, c3 = st.columns([3, 2, 3])
                    
                    if info_d and info_h:
                        sila_d = info_d['sila'] + 10 
                        sila_h = info_h['sila']
                        celkova = sila_d + sila_h
                        proc_d = (sila_d / celkova) * 100
                        proc_h = (sila_h / celkova) * 100
                        
                        with c1:
                            st.markdown(f"<h3 style='text-align: right'>{domaci_raw}</h3>", unsafe_allow_html=True)
                            st.markdown(f"<p style='text-align: right'>{info_d['forma']}</p>", unsafe_allow_html=True)
                        
                        with c2:
                            st.markdown(f"<p style='text-align: center'><b>{datum}</b></p>", unsafe_allow_html=True)
                            st.markdown(f"<h4 style='text-align: center'>{int(proc_d)}% : {int(proc_h)}%</h4>", unsafe_allow_html=True)
                            if proc_d > 60: st.success(f"Tip: {domaci_raw}")
                            elif proc_h > 60: st.error(f"Tip: {hoste_raw}")
                            else: st.warning("Tip: Remíza")
                            
                        with c3:
                            st.markdown(f"<h3 style='text-align: left'>{hoste_raw}</h3>", unsafe_allow_html=True)
                            st.markdown(f"<p style='text-align: left'>{info_h['forma']}</p>", unsafe_allow_html=True)
                    else:
                        with c2: 
                            st.write(f"{domaci_raw} vs {hoste_raw}")
                            st.caption("Chybí historická data (konec sezóny nebo rozdílné názvy)")
                    
                    st.markdown("---")
    else:
        st.error("Nepodařilo se najít sloupec s datem v souboru rozpisu.")
else:
    st.error("Nepodařilo se stáhnout soubor s rozpisem (možná ještě není vytvořen pro novou sezónu).")

with st.expander("📊 Tabulka formy (Historie)"):
    df_tabulka = pd.DataFrame.from_dict(db_sily, orient='index').sort_values(by='body', ascending=False)
    st.dataframe(df_tabulka)
