import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

st.set_page_config(page_title="Sport Betting AI", layout="wide")

# ==========================================
# 1. ČÁST: FOTBALOVÁ LOGIKA (CSV Hybrid)
# ==========================================

def app_fotbal():
    st.header("⚽ Fotbalový Analytik")
    
    # --- KONFIGURACE LIG ---
    LIGY_KODY = {
        "🇬🇧 Premier League": {"hist": "E0", "fut": "epl"},
        "🇬🇧 Championship": {"hist": "E1", "fut": "championship"},
        "🇩🇪 Bundesliga": {"hist": "D1", "fut": "bundesliga"},
        "🇪🇸 La Liga": {"hist": "SP1", "fut": "la-liga"},
        "🇮🇹 Serie A": {"hist": "I1", "fut": "serie-a"},
        "🇫🇷 Ligue 1": {"hist": "F1", "fut": "ligue-1"}
    }

    def normalizuj_nazev(nazev):
        if not isinstance(nazev, str): return ""
        nazev = nazev.lower().strip()
        mapping = {
            "man city": "manchester city", "man utd": "manchester united",
            "man united": "manchester united", "leicester": "leicester city",
            "leeds": "leeds united", "notts forest": "nottingham forest",
            "wolves": "wolverhampton wanderers", "brighton": "brighton & hove albion",
            "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
            "west ham": "west ham united", "newcastle": "newcastle united"
        }
        return mapping.get(nazev, nazev)

    @st.cache_data(ttl=3600)
    def nacti_fotbal_data(liga_nazev, rok_start):
        kody = LIGY_KODY[liga_nazev]
        rok_konec = rok_start + 1
        sezona_short = f"{str(rok_start)[-2:]}{str(rok_konec)[-2:]}"
        
        # URL
        url_hist = f"https://www.football-data.co.uk/mmz4281/{sezona_short}/{kody['hist']}.csv"
        url_fut = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-UTC.csv"
        
        # Stažení
        try:
            r_h = requests.get(url_hist)
            df_h = pd.read_csv(io.StringIO(r_h.text)) if r_h.status_code == 200 else None
        except: df_h = None

        try:
            r_f = requests.get(url_fut)
            if r_f.status_code == 200:
                try: df_f = pd.read_csv(io.StringIO(r_f.text))
                except: df_f = pd.read_csv(io.StringIO(r_f.content.decode('latin-1')))
            else: df_f = None
        except: df_f = None
        
        return df_h, df_f

    def analyzuj_silu(df_hist):
        if df_hist is None: return {}
        tymy = {}
        for index, row in df_hist.iterrows():
            if pd.isna(row['FTR']): continue 
            domaci = normalizuj_nazev(row['HomeTeam'])
            hoste = normalizuj_nazev(row['AwayTeam'])
            vysledek = row['FTR'] 
            
            if domaci not in tymy: tymy[domaci] = {"Body": 0, "Forma": []}
            if hoste not in tymy: tymy[hoste] = {"Body": 0, "Forma": []}
            
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
            forma_str = "".join(data["Forma"][-5:])
            bonus = forma_str.count("W") * 3 + forma_str.count("D") * 1
            sila = data["Body"] + bonus
            db[nazev] = {"sila": sila, "forma": forma_str.replace("W", "🟢").replace("L", "🔴").replace("D", "⚪")}
        return db

    # --- UI FOTBAL ---
    col1, col2 = st.columns(2)
    with col1:
        vybrana_liga = st.selectbox("Soutěž:", list(LIGY_KODY.keys()))
    with col2:
        rok = st.selectbox("Sezóna (Rok startu):", [2025, 2024, 2023], index=1)

    df_hist, df_fut = nacti_fotbal_data(vybrana_liga, rok)
    
    if df_hist is not None:
        db_sily = analyzuj_silu(df_hist)
        
        if df_fut is not None:
            st.subheader("🔮 Predikce zápasů")
            # Hledání sloupce s datem
            col_date = next((c for c in df_fut.columns if "Date" in c or "Time" in c), None)
            
            if col_date:
                df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], dayfirst=True, errors='coerce')
                if df_fut['DateObj'].isnull().all():
                     df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], errors='coerce')
                
                dnes = datetime.now()
                budouci = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj').head(10)
                
                if budouci.empty:
                    st.info("Žádné budoucí zápasy v rozpisu.")
                else:
                    for index, row in budouci.iterrows():
                        col_home = [c for c in df_fut.columns if "Home" in c][0]
                        col_away = [c for c in df_fut.columns if "Away" in c][0]
                        domaci = row[col_home]
                        hoste = row[col_away]
                        datum = row[col_date]
                        
                        info_d = db_sily.get(normalizuj_nazev(domaci))
                        info_h = db_sily.get(normalizuj_nazev(hoste))
                        
                        # Fallback
                        if not info_d:
                            for k in db_sily: 
                                if normalizuj_nazev(domaci) in k: info_d = db_sily[k]; break
                        if not info_h:
                            for k in db_sily: 
                                if normalizuj_nazev(hoste) in k: info_h = db_sily[k]; break

                        with st.container():
                            c1, c2, c3 = st.columns([3, 2, 3])
                            if info_d and info_h:
                                sila_d = info_d['sila'] + 10
                                sila_h = info_h['sila']
                                celk = sila_d + sila_h
                                pd = (sila_d / celk) * 100
                                ph = (sila_h / celk) * 100
                                
                                with c1: st.markdown(f"<div style='text-align:right'><b>{domaci}</b><br>{info_d['forma']}</div>", unsafe_allow_html=True)
                                with c2: 
                                    st.markdown(f"<div style='text-align:center'>{datum}<br><h4>{int(pd)}% : {int(ph)}%</h4></div>", unsafe_allow_html=True)
                                    if pd > 60: st.success(f"Tip: {domaci}")
                                    elif ph > 60: st.error(f"Tip: {hoste}")
                                    else: st.warning("Remíza")
                                with c3: st.markdown(f"<div style='text-align:left'><b>{hoste}</b><br>{info_h['forma']}</div>", unsafe_allow_html=True)
                            else:
                                with c2: st.write(f"{domaci} vs {hoste} (Chybí data)")
                            st.markdown("---")
    else:
        st.error("Historická data pro tuto sezónu nejsou dostupná.")


# ==========================================
# 2. ČÁST: TENISOVÁ LOGIKA (Scraping)
# ==========================================

def app_tenis():
    st.header("🎾 Tenisový Analytik")
    st.caption("Zdroj: TennisExplorer.com (Dnešní zápasy)")

    @st.cache_data(ttl=1800) # Cache na 30 minut
    def nacti_tenis_dnes():
        url = "https://www.tennisexplorer.com/matches/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200: return None, f"Chyba: {response.status_code}"
            
            dfs = pd.read_html(response.text)
            
            # TennisExplorer má jednu velkou tabulku. Musíme ji najít.
            # Hledáme tabulku, která má sloupec "Player" nebo obsahuje kurzy
            df_matches = None
            for df in dfs:
                if len(df.columns) >= 5:
                    df_matches = df
                    break
            
            if df_matches is None: return None, "Tabulka nenalezena."
            
            return df_matches, None
            
        except Exception as e:
            return None, str(e)

    with st.spinner("Stahuji dnešní tenisové zápasy..."):
        df, error = nacti_tenis_dnes()

    if error:
        st.error(f"Nepodařilo se stáhnout data: {error}")
    else:
        st.success("✅ Data úspěšně stažena.")
        
        # Filtrace a čištění
        # TennisExplorer tabulka je trochu "špinavá", obsahuje řádky s názvy turnajů
        # Zkusíme najít řádky, kde jsou kurzy
        
        zapasy_list = []
        aktualni_turnaj = "Neznámý turnaj"
        
        # Procházíme řádky (je to trochu hack, protože struktura je složitá)
        for index, row in df.iterrows():
            sloupec_0 = str(row[0])
            
            # Pokud řádek neobsahuje čas (např. 14:30), je to pravděpodobně název turnaje
            if ":" not in sloupec_0 and len(sloupec_0) > 5:
                aktualni_turnaj = sloupec_0
                continue
                
            # Pokud je to zápas
            if ":" in sloupec_0:
                cas = sloupec_0
                hrac = str(row[1])
                
                # Hledání kurzů (jsou obvykle v posledních sloupcích)
                # TennisExplorer má sloupce: Time, Match, Score, Sets, Odds1, Odds2
                try:
                    # Zkusíme najít kurzy. Obvykle jsou to float čísla
                    kurz_1 = float(row[len(row)-2])
                    kurz_2 = float(row[len(row)-1])
                    
                    # Rozdělení jmen hráčů (jsou v jednom sloupci oddělené " - ")
                    if " - " in hrac:
                        p1, p2 = hrac.split(" - ", 1)
                    else:
                        continue # Divný formát
                        
                    zapasy_list.append({
                        "Turnaj": aktualni_turnaj,
                        "Čas": cas,
                        "Hráč 1": p1,
                        "Hráč 2": p2,
                        "Kurz 1": kurz_1,
                        "Kurz 2": kurz_2
                    })
                except:
                    continue # Řádek bez kurzů nebo výsledků

        if not zapasy_list:
            st.warning("Nebyly nalezeny žádné zápasy s vypsanými kurzy.")
            st.dataframe(df.head()) # Debug
        else:
            # Zobrazení karet zápasů
            st.subheader(f"Dnešní nabídka ({len(zapasy_list)} zápasů)")
            
            # Filtr turnajů
            turnaje = sorted(list(set([z["Turnaj"] for z in zapasy_list])))
            vybrany_turnaj = st.selectbox("Filtrovat turnaj:", ["Vše"] + turnaje)
            
            for z in zapasy_list:
                if vybrany_turnaj != "Vše" and z["Turnaj"] != vybrany_turnaj:
                    continue
                    
                # Výpočet pravděpodobnosti z kurzů
                # P = 1 / Kurz
                prob_1 = (1 / z["Kurz 1"]) * 100
                prob_2 = (1 / z["Kurz 2"]) * 100
                total_prob = prob_1 + prob_2
                
                # Normalizace na 100% (odstranění marže sázkovky)
                real_prob_1 = (prob_1 / total_prob) * 100
                real_prob_2 = (prob_2 / total_prob) * 100
                
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([2, 3, 2, 3, 2])
                    
                    with c1: st.caption(z["Turnaj"])
                    
                    with c2: 
                        st.write(f"**{z['Hráč 1']}**")
                        st.write(f"Kurz: {z['Kurz 1']}")
                        
                    with c3:
                        st.markdown(f"<h4 style='text-align: center'>{int(real_prob_1)}% : {int(real_prob_2)}%</h4>", unsafe_allow_html=True)
                        if real_prob_1 > 55: st.success(f"Tip: {z['Hráč 1']}")
                        elif real_prob_2 > 55: st.error(f"Tip: {z['Hráč 2']}")
                        else: st.warning("Vyrovnané")
                        st.caption(f"Čas: {z['Čas']}")
                        
                    with c4:
                        st.write(f"**{z['Hráč 2']}**")
                        st.write(f"Kurz: {z['Kurz 2']}")
                        
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
