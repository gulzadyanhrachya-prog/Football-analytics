import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

st.set_page_config(page_title="Hybrid Analyzer", layout="wide")

# --- KONFIGURACE ZDROJŮ DAT (CSV) ---
# Zde definujeme odkazy na soubory pro různé ligy
# History: football-data.co.uk (E0 = Premier League, D1 = Bundesliga, atd.)
# Future: fixturedownload.com
LIGY_CONFIG = {
    "🇬🇧 Premier League": {
        "history": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
        "future": "https://fixturedownload.com/download/epl-2024-GMTStandardTime.csv"
    },
    "🇬🇧 Championship": {
        "history": "https://www.football-data.co.uk/mmz4281/2425/E1.csv",
        "future": "https://fixturedownload.com/download/championship-2024-GMTStandardTime.csv"
    },
    "🇩🇪 Bundesliga": {
        "history": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
        "future": "https://fixturedownload.com/download/bundesliga-2024-UTC.csv"
    },
    "🇪🇸 La Liga": {
        "history": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
        "future": "https://fixturedownload.com/download/la-liga-2024-UTC.csv"
    },
    "🇮🇹 Serie A": {
        "history": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
        "future": "https://fixturedownload.com/download/serie-a-2024-UTC.csv"
    },
    "🇫🇷 Ligue 1": {
        "history": "https://www.football-data.co.uk/mmz4281/2425/F1.csv",
        "future": "https://fixturedownload.com/download/ligue-1-2024-UTC.csv"
    }
}

# --- POMOCNÁ FUNKCE: PŘEKLADAČ TÝMŮ ---
# Protože každý zdroj má jiné názvy (Man City vs Manchester City), musíme je sjednotit.
# Toto je jednoduchá verze, která porovnává prvních 4-5 písmen.
def normalizuj_nazev(nazev):
    if not isinstance(nazev, str): return ""
    nazev = nazev.lower().strip()
    # Manuální opravy pro nejčastější rozdíly
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
    
    # 1. Stažení HISTORIE (Výsledky)
    try:
        r_hist = requests.get(urls["history"])
        r_hist.raise_for_status() # Ověří, že nenastala chyba
        df_hist = pd.read_csv(io.StringIO(r_hist.text))
    except Exception as e:
        return None, None, f"Chyba stahování historie: {e}"

    # 2. Stažení BUDOUCNOSTI (Rozpis)
    try:
        r_fut = requests.get(urls["future"])
        r_fut.raise_for_status()
        df_fut = pd.read_csv(io.StringIO(r_fut.text))
    except Exception as e:
        return None, None, f"Chyba stahování rozpisu: {e}"
        
    return df_hist, df_fut, None

# --- VÝPOČET SÍLY TÝMŮ ---
def analyzuj_silu(df_hist):
    tymy = {}
    
    # Projdeme všechny odehrané zápasy
    for index, row in df_hist.iterrows():
        # football-data.co.uk používá sloupce: HomeTeam, AwayTeam, FTR (Full Time Result), FTHG (Home Goals), FTAG (Away Goals)
        if pd.isna(row['FTR']): continue # Přeskočit neodehrané
        
        domaci = normalizuj_nazev(row['HomeTeam'])
        hoste = normalizuj_nazev(row['AwayTeam'])
        vysledek = row['FTR'] # H (Home), A (Away), D (Draw)
        
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
            tymy[hoste]["Forma"].append("W")
            tymy[domaci]["Forma"].append("L")
        else:
            tymy[domaci]["Body"] += 1
            tymy[hoste]["Body"] += 1
            tymy[domaci]["Forma"].append("D")
            tymy[hoste]["Forma"].append("D")
            
    # Finální výpočet síly
    databaze_sily = {}
    for nazev, data in tymy.items():
        forma_list = data["Forma"][-5:] # Posledních 5
        forma_str = "".join(forma_list)
        
        # Algoritmus síly: Body + Bonus za formu
        bonus = forma_str.count("W") * 3 + forma_str.count("D") * 1
        sila = data["Body"] + bonus
        
        databaze_sily[nazev] = {
            "sila": sila,
            "forma": forma_str.replace("W", "🟢").replace("L", "🔴").replace("D", "⚪"),
            "body": data["Body"],
            "zapasy": data["Z"]
        }
        
    return databaze_sily

# --- UI APLIKACE ---
st.title("⚽ Hybridní Analytik (CSV Metoda)")
st.caption("Data: football-data.co.uk (Historie) + fixturedownload.com (Budoucnost)")

# Sidebar
vybrana_liga = st.sidebar.selectbox("Vyber ligu:", list(LIGY_CONFIG.keys()))

# Načtení dat
with st.spinner("Stahuji a propojuji CSV soubory..."):
    df_hist, df_fut, error = nacti_data(vybrana_liga)

if error:
    st.error(error)
else:
    # 1. Analýza historie
    db_sily = analyzuj_silu(df_hist)
    
    # 2. Zpracování budoucnosti
    # fixturedownload.com má sloupce: Date, Home Team, Away Team
    
    # Filtrujeme jen budoucí zápasy (jednoduchý filtr: ty, co nejsou v historii)
    # Ale lepší je vzít prostě vše z "future" souboru a najít ty nejbližší podle data
    df_fut['DateObj'] = pd.to_datetime(df_fut['Date'], format='%d/%m/%Y %H:%M', errors='coerce')
    
    # Pokud formát data nesedí, zkusíme jiný (občas se mění)
    if df_fut['DateObj'].isnull().all():
         df_fut['DateObj'] = pd.to_datetime(df_fut['Date'], errors='coerce')

    dnes = datetime.now()
    # Bereme jen zápasy od dneška dál
    budouci_zapasy = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj')
    
    if budouci_zapasy.empty:
        st.warning("V souboru s rozpisem nebyly nalezeny žádné budoucí zápasy.")
    else:
        st.subheader(f"🔮 Predikce: {vybrana_liga}")
        st.write(f"Analyzováno {len(df_hist)} odehraných zápasů pro výpočet formy.")
        
        # Zobrazíme nejbližších 10 zápasů
        for index, row in budouci_zapasy.head(10).iterrows():
            domaci_raw = row['Home Team']
            hoste_raw = row['Away Team']
            datum = row['Date']
            
            # Normalizace názvů pro vyhledání v databázi
            domaci_norm = normalizuj_nazev(domaci_raw)
            hoste_norm = normalizuj_nazev(hoste_raw)
            
            # Vyhledání síly
            info_d = db_sily.get(domaci_norm)
            info_h = db_sily.get(hoste_norm)
            
            # Pokud nenajdeme přesnou shodu, zkusíme najít "podobný" název (fallback)
            if not info_d:
                for k in db_sily:
                    if domaci_norm in k or k in domaci_norm:
                        info_d = db_sily[k]; break
            if not info_h:
                for k in db_sily:
                    if hoste_norm in k or k in hoste_norm:
                        info_h = db_sily[k]; break

            with st.container():
                c1, c2, c3 = st.columns([3, 2, 3])
                
                # Máme data o obou týmech?
                if info_d and info_h:
                    sila_d = info_d['sila'] + 10 # Domácí výhoda
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
                    # Pokud se nepodařilo spárovat názvy týmů
                    with c2: 
                        st.write(f"{domaci_raw} vs {hoste_raw}")
                        st.caption("Chybí historická data (rozdílné názvy týmů)")
                
                st.markdown("---")

    # Tabulka pro kontrolu
    with st.expander("📊 Zobrazit tabulku formy"):
        df_tabulka = pd.DataFrame.from_dict(db_sily, orient='index').sort_values(by='body', ascending=False)
        st.dataframe(df_tabulka)
