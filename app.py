import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="Sport Betting Hub", layout="wide")

# ==========================================
# 1. MODUL: FOTBAL (Hybrid CSV)
# ==========================================

def app_fotbal():
    st.header("⚽ Fotbalový Expert")
    st.caption("Data: Historie (Football-Data.co.uk) + Budoucnost (FixtureDownload.com)")
    
    # --- KONFIGURACE ---
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
        # Formát sezóny pro historii: "2425"
        sezona_short = f"{str(rok_start)[-2:]}{str(rok_konec)[-2:]}"
        
        # Zde byla chyba - odstraněna zpětná lomítka
        url_hist = f"https://www.football-data.co.uk/mmz4281/{sezona_short}/{kody['hist']}.csv"
        url_fut = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-UTC.csv"
        
        # Stažení historie
        try:
            r_h = requests.get(url_hist)
            df_h = pd.read_csv(io.StringIO(r_h.text)) if r_h.status_code == 200 else None
        except: df_h = None

        # Stažení budoucnosti
        try:
            r_f = requests.get(url_fut)
            if r_f.status_code == 200:
                try: df_f = pd.read_csv(io.StringIO(r_f.text))
                except: df_f = pd.read_csv(io.StringIO(r_f.content.decode('latin-1')))
            else: 
                # Zkusíme alternativní název
                url_fut_alt = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-GMTStandardTime.csv"
                r_f = requests.get(url_fut_alt)
                df_f = pd.read_csv(io.StringIO(r_f.text)) if r_f.status_code == 200 else None
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
            db[nazev] = {
                "sila": sila, 
                "forma": forma_str.replace("W", "🟢").replace("L", "🔴").replace("D", "⚪"),
                "body": data["Body"]
            }
        return db

    # --- UI FOTBAL ---
    c1, c2 = st.columns([2, 1])
    with c1: vybrana_liga = st.selectbox("Vyber ligu:", list(LIGY_KODY.keys()))
    with c2: rok = st.selectbox("Sezóna:", [2025, 2024, 2023], index=1)

    with st.spinner("Analyzuji fotbalová data..."):
        df_hist, df_fut = nacti_fotbal_data(vybrana_liga, rok)
    
    if df_hist is not None:
        db_sily = analyzuj_silu(df_hist)
        
        # Zobrazení tabulky formy
        with st.expander("📊 Tabulka formy a bodů"):
            df_form = pd.DataFrame.from_dict(db_sily, orient='index').sort_values(by='body', ascending=False)
            st.dataframe(df_form)

        if df_fut is not None:
            st.subheader(f"📅 Rozpis zápasů: {vybrana_liga}")
            
            # Hledání sloupce s datem
            col_date = next((c for c in df_fut.columns if "Date" in c or "Time" in c), None)
            
            if col_date:
                df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], dayfirst=True, errors='coerce')
                if df_fut['DateObj'].isnull().all():
                     df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], errors='coerce')
                
                dnes = datetime.now()
                # Zobrazíme zápasy od dneška dál (limit 15)
                budouci = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj').head(15)
                
                if budouci.empty:
                    st.warning("Žádné budoucí zápasy v rozpisu (možná konec sezóny).")
                else:
                    for index, row in budouci.iterrows():
                        col_home = [c for c in df_fut.columns if "Home" in c][0]
                        col_away = [c for c in df_fut.columns if "Away" in c][0]
                        domaci = row[col_home]
                        hoste = row[col_away]
                        datum_str = row[col_date]
                        
                        info_d = db_sily.get(normalizuj_nazev(domaci))
                        info_h = db_sily.get(normalizuj_nazev(hoste))
                        
                        # Fallback vyhledávání
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
                                pd_val = (sila_d / celk) * 100
                                ph_val = (sila_h / celk) * 100
                                
                                with c1: st.markdown(f"<div style='text-align:right'><b>{domaci}</b><br>{info_d['forma']}</div>", unsafe_allow_html=True)
                                with c2: 
                                    st.markdown(f"<div style='text-align:center'>{datum_str}<br><h4>{int(pd_val)}% : {int(ph_val)}%</h4></div>", unsafe_allow_html=True)
                                    if pd_val > 60: st.success(f"Tip: {domaci}")
                                    elif ph_val > 60: st.error(f"Tip: {hoste}")
                                    else: st.warning("Remíza / Risk")
                                with c3: st.markdown(f"<div style='text-align:left'><b>{hoste}</b><br>{info_h['forma']}</div>", unsafe_allow_html=True)
                            else:
                                with c2: st.write(f"{domaci} vs {hoste}")
                            st.markdown("---")
    else:
        st.error(f"Historická data pro sezónu {rok} nejsou dostupná. Zkus změnit rok.")


# ==========================================
# 2. MODUL: TENIS (Scraping 2 dny)
# ==========================================

def app_tenis():
    st.header("🎾 Tenisový Prediktor")
    st.caption("Zdroj: TennisExplorer.com (Dnešek + Zítřek)")

    @st.cache_data(ttl=1800)
    def scrape_tennis_day(date_obj):
        # Sestavení URL pro konkrétní den
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day
        url = f"https://www.tennisexplorer.com/matches/?type=all&year={year}&month={month}&day={day}"
        
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200: return []
            
            dfs = pd.read_html(r.text)
            # Hledáme největší tabulku
            df = max(dfs, key=len)
            
            matches = []
            current_tournament = "Unknown"
            
            for idx, row in df.iterrows():
                col0 = str(row[0])
                # Detekce turnaje (řádek bez času)
                if ":" not in col0 and len(col0) > 3:
                    current_tournament = col0
                    continue
                
                # Detekce zápasu
                if ":" in col0:
                    try:
                        # TennisExplorer formát: Time, Player, Score, Sets, Odds1, Odds2
                        # Kurzy jsou obvykle na konci
                        odds1 = float(row.iloc[-2])
                        odds2 = float(row.iloc[-1])
                        
                        players = str(row[1])
                        if " - " in players:
                            p1, p2 = players.split(" - ", 1)
                            
                            matches.append({
                                "Datum": date_obj.strftime("%d.%m."),
                                "Čas": col0,
                                "Turnaj": current_tournament,
                                "Hráč 1": p1,
                                "Hráč 2": p2,
                                "Kurz 1": odds1,
                                "Kurz 2": odds2
                            })
                    except:
                        continue
            return matches
        except:
            return []

    # --- LOGIKA TENIS ---
    dnes = datetime.now()
    zitra = dnes + timedelta(days=1)
    
    with st.spinner("Stahuji tenisové zápasy na 48 hodin..."):
        zapasy_dnes = scrape_tennis_day(dnes)
        zapasy_zitra = scrape_tennis_day(zitra)
        vsechny_zapasy = zapasy_dnes + zapasy_zitra

    if not vsechny_zapasy:
        st.error("Nepodařilo se stáhnout žádné tenisové zápasy s kurzy.")
    else:
        # Filtr turnajů
        turnaje = sorted(list(set([z["Turnaj"] for z in vsechny_zapasy])))
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtr_turnaj = st.selectbox("Filtrovat Turnaj:", ["Vše"] + turnaje)
        with col_f2:
            jen_atp = st.checkbox("Ukázat jen ATP/WTA (skrýt malé turnaje)", value=True)

        st.subheader(f"Nalezeno {len(vsechny_zapasy)} zápasů")
        
        for z in vsechny_zapasy:
            # Filtrování
            if jen_atp and ("ATP" not in z["Turnaj"] and "WTA" not in z["Turnaj"]): continue
            if filtr_turnaj != "Vše" and z["Turnaj"] != filtr_turnaj: continue
            
            # Výpočet predikce z kurzů
            # Implied Probability = 1 / Decimal Odds
            prob1 = (1 / z["Kurz 1"])
            prob2 = (1 / z["Kurz 2"])
            margin = prob1 + prob2 # Sázkovky mají marži nad 100%
            
            real_prob1 = (prob1 / margin) * 100
            real_prob2 = (prob2 / margin) * 100
            
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([2, 3, 2, 3, 2])
                
                with c1: 
                    st.caption(f"{z['Datum']} {z['Čas']}")
                    st.caption(z["Turnaj"][:20] + "...")
                
                with c2:
                    st.write(f"**{z['Hráč 1']}**")
                    st.write(f"Kurz: {z['Kurz 1']}")
                
                with c3:
                    st.markdown(f"<h4 style='text-align: center'>{int(real_prob1)}% : {int(real_prob2)}%</h4>", unsafe_allow_html=True)
                    if real_prob1 > 60: st.success(f"Tip: {z['Hráč 1']}")
                    elif real_prob2 > 60: st.error(f"Tip: {z['Hráč 2']}")
                    else: st.warning("Vyrovnané")
                    
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
