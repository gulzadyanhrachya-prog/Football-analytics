import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

st.set_page_config(page_title="Time Travel Analyzer", layout="wide")

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
        "newcastle": "newcastle united",
        "sheffield utd": "sheffield united",
        "luton": "luton town"
    }
    return mapping.get(nazev, nazev)

# --- KONFIGURACE LIG (Kódy pro CSV) ---
# E0 = Premier League, D1 = Bundesliga, atd.
LIGY_KODY = {
    "🇬🇧 Premier League": {"hist": "E0", "fut": "epl"},
    "🇬🇧 Championship": {"hist": "E1", "fut": "championship"},
    "🇩🇪 Bundesliga": {"hist": "D1", "fut": "bundesliga"},
    "🇪🇸 La Liga": {"hist": "SP1", "fut": "la-liga"},
    "🇮🇹 Serie A": {"hist": "I1", "fut": "serie-a"},
    "🇫🇷 Ligue 1": {"hist": "F1", "fut": "ligue-1"}
}

# --- SIDEBAR ---
st.sidebar.title("Nastavení Času")
vybrana_liga = st.sidebar.selectbox("Soutěž:", list(LIGY_KODY.keys()))

# Výběr sezóny - Dynamicky generujeme možnosti
aktualni_rok = datetime.now().year
# Pokud je únor 2026, chceme primárně sezónu 25/26 (začala 2025)
moznosti_sezon = range(aktualni_rok + 1, 2020, -1) 
rok_start = st.sidebar.selectbox("Začátek sezóny (Rok):", moznosti_sezon, index=1) # Defaultně minulý rok (aktuální sezóna)

# Generování kódů sezóny
# Příklad: Rok 2025 -> Sezóna 25/26 -> Kód "2526"
rok_konec = rok_start + 1
sezona_short = f"{str(rok_start)[-2:]}{str(rok_konec)[-2:]}" # "2526"
sezona_long = f"{rok_start}" # "2025"

st.sidebar.info(f"Hledám data pro sezónu {rok_start}/{rok_konec}")
st.sidebar.caption(f"Kód historie: {sezona_short} | Kód budoucnosti: {sezona_long}")

# --- FUNKCE PRO STAŽENÍ DAT ---
@st.cache_data(ttl=3600)
def nacti_data_dynamicky(liga_nazev, kod_sezony_hist, kod_sezony_fut):
    kody = LIGY_KODY[liga_nazev]
    
    # 1. URL HISTORIE (football-data.co.uk)
    url_hist = f"https://www.football-data.co.uk/mmz4281/{kod_sezony_hist}/{kody['hist']}.csv"
    
    # 2. URL BUDOUCNOSTI (fixturedownload.com)
    # Tento web používá formát "epl-2025-UTC.csv"
    url_fut = f"https://fixturedownload.com/download/{kody['fut']}-{kod_sezony_fut}-UTC.csv"
    
    # Stažení historie
    try:
        r_h = requests.get(url_hist)
        if r_h.status_code == 200:
            df_h = pd.read_csv(io.StringIO(r_h.text))
        else:
            df_h = None
    except: df_h = None

    # Stažení budoucnosti
    try:
        r_f = requests.get(url_fut)
        if r_f.status_code == 200:
            try:
                df_f = pd.read_csv(io.StringIO(r_f.text))
            except:
                df_f = pd.read_csv(io.StringIO(r_f.content.decode('latin-1')))
        else:
            # Zkusíme alternativní název (někdy mají GMTStandardTime místo UTC)
            url_fut_alt = f"https://fixturedownload.com/download/{kody['fut']}-{kod_sezony_fut}-GMTStandardTime.csv"
            r_f = requests.get(url_fut_alt)
            if r_f.status_code == 200:
                df_f = pd.read_csv(io.StringIO(r_f.text))
            else:
                df_f = None
    except: df_f = None
    
    return df_h, df_f, url_hist, url_fut

# --- VÝPOČET SÍLY ---
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
            tymy[hoste]["Forma"].append("W")
            tymy[domaci]["Forma"].append("L")
        else:
            tymy[domaci]["Body"] += 1
            tymy[hoste]["Body"] += 1
            tymy[domaci]["Forma"].append("D")
            tymy[hoste]["Forma"].append("D")
            
    db = {}
    for nazev, data in tymy.items():
        forma_list = data["Forma"][-5:] 
        forma_str = "".join(forma_list)
        bonus = forma_str.count("W") * 3 + forma_str.count("D") * 1
        sila = data["Body"] + bonus
        
        db[nazev] = {
            "sila": sila,
            "forma": forma_str.replace("W", "🟢").replace("L", "🔴").replace("D", "⚪"),
            "body": data["Body"],
            "zapasy": data["Z"]
        }
    return db

# --- UI APLIKACE ---
st.title(f"⚽ Analytik: {vybrana_liga}")

with st.spinner("Hledám data na serverech..."):
    df_hist, df_fut, url_h, url_f = nacti_data_dynamicky(vybrana_liga, sezona_short, sezona_long)

# Diagnostika odkazů (pro kontrolu)
with st.expander("🔍 Zobrazit zdroje dat (Debug)"):
    st.write(f"Historie: {url_h}")
    st.write(f"Budoucnost: {url_f}")
    if df_hist is None: st.error("❌ Soubor historie nenalezen (sezóna možná neexistuje).")
    else: st.success(f"✅ Historie načtena ({len(df_hist)} zápasů).")
    if df_fut is None: st.error("❌ Soubor budoucnosti nenalezen.")
    else: st.success(f"✅ Rozpis načten ({len(df_fut)} zápasů).")

# Logika aplikace
if df_hist is not None:
    db_sily = analyzuj_silu(df_hist)
    
    # Tabulka formy
    df_tabulka = pd.DataFrame.from_dict(db_sily, orient='index').sort_values(by='body', ascending=False)
    st.subheader("📊 Aktuální tabulka formy")
    st.dataframe(df_tabulka, use_container_width=True)
    
    # Predikce
    if df_fut is not None:
        st.subheader("🔮 Predikce nadcházejících zápasů")
        
        # Najdeme sloupec s datem
        col_date = next((c for c in df_fut.columns if "Date" in c or "Time" in c), None)
        
        if col_date:
            # Převod data
            df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], dayfirst=True, errors='coerce')
            if df_fut['DateObj'].isnull().all():
                 df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], errors='coerce')
            
            # Filtr: Zápasy od dneška dál
            dnes = datetime.now()
            # Pokud je únor 2026, chceme zápasy od února 2026 dál
            # Pokud testuješ na starých datech, můžeš tento filtr zakomentovat
            budouci = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj')
            
            if budouci.empty:
                st.warning(f"V rozpisu nejsou žádné zápasy po datu {dnes.strftime('%d.%m.%Y')}.")
                st.write("Zobrazuji posledních 10 zápasů v rozpisu (pro kontrolu):")
                budouci = df_fut.sort_values(by='DateObj', ascending=False).head(10)
            
            for index, row in budouci.head(10).iterrows():
                col_home = [c for c in df_fut.columns if "Home" in c][0]
                col_away = [c for c in df_fut.columns if "Away" in c][0]
                
                domaci = row[col_home]
                hoste = row[col_away]
                datum = row[col_date]
                
                d_norm = normalizuj_nazev(domaci)
                h_norm = normalizuj_nazev(hoste)
                
                info_d = db_sily.get(d_norm)
                info_h = db_sily.get(h_norm)
                
                # Fallback
                if not info_d:
                    for k in db_sily: 
                        if d_norm in k or k in d_norm: info_d = db_sily[k]; break
                if not info_h:
                    for k in db_sily: 
                        if h_norm in k or k in h_norm: info_h = db_sily[k]; break
                
                with st.container():
                    c1, c2, c3 = st.columns([3, 2, 3])
                    if info_d and info_h:
                        sila_d = info_d['sila'] + 10
                        sila_h = info_h['sila']
                        celk = sila_d + sila_h
                        pd_proc = (sila_d / celk) * 100
                        ph_proc = (sila_h / celk) * 100
                        
                        with c1: 
                            st.markdown(f"<div style='text-align:right'><b>{domaci}</b><br>{info_d['forma']}</div>", unsafe_allow_html=True)
                        with c2:
                            st.markdown(f"<div style='text-align:center'>{datum}<br><h4>{int(pd_proc)}% : {int(ph_proc)}%</h4></div>", unsafe_allow_html=True)
                        with c3:
                            st.markdown(f"<div style='text-align:left'><b>{hoste}</b><br>{info_h['forma']}</div>", unsafe_allow_html=True)
                    else:
                        with c2: st.write(f"{domaci} vs {hoste}")
                    st.markdown("---")
else:
    st.error(f"Data pro sezónu {rok_start}/{rok_konec} nejsou dostupná.")
    st.write("Možné příčiny:")
    st.write("1. Sezóna ještě nezačala (soubor na serveru neexistuje).")
    st.write("2. Pokud jsi v budoucnosti (2026), ujisti se, že football-data.co.uk už nahrál soubor '2526'.")
