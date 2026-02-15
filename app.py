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
    
    # --- KONFIGURACE ---\n    LIGY_KODY = {
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
        
        url_hist = f"https://www.football-data.co.uk/mmz4281/{sezona_short}/{kody['hist']}.csv"
        url_fut = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-UTC.csv"
        
        try:
            r_h = requests.get(url_hist)
            df_h = pd.read_csv(io.StringIO(r_h.text)) if r_h.status_code == 200 else None
        except: df_h = None

        try:
            r_f = requests.get(url_fut)
            if r_f.status_code == 200:
                try: df_f = pd.read_csv(io.StringIO(r_f.text))
                except: df_f = pd.read_csv(io.StringIO(r_f.content.decode('latin-1')))
            else: 
                url_fut_alt = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-GMTStandardTime.csv"
                r_f = requests.get(url_fut_alt)
                df_f = pd.read_csv(io.StringIO(r_f.text)) if r_f.status_code == 200 else None
        except: df_f = None
        
        return df_h, df_f

    def analyzuj_silu(df_hist):
        if df_hist is None: return {}
        tymy = {}\n        for index, row in df_hist.iterrows():
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
        
        with st.expander("📊 Tabulka formy a bodů"):
            df_form = pd.DataFrame.from_dict(db_sily, orient='index').sort_values(by='body', ascending=False)
            st.dataframe(df_form)

        if df_fut is not None:
            st.subheader(f"📅 Rozpis zápasů: {vybrana_liga}")
            col_date = next((c for c in df_fut.columns if "Date" in c or "Time" in c), None)
            
            if col_date:
                df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], dayfirst=True, errors='coerce')
                if df_fut['DateObj'].isnull().all():
                     df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], errors='coerce')
                
                dnes = datetime.now()
                budouci = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj').head(15)
                
                if budouci.empty:
                    st.warning("Žádné budoucí zápasy v rozpisu.")
                else:
                    for index, row in budouci.iterrows():
                        col_home = [c for c in df_fut.columns if "Home" in c][0]
                        col_away = [c for c in df_fut.columns if "Away" in c][0]
                        domaci = row[col_home]
                        hoste = row[col_away]
                        datum_str = row[col_date]
                        
                        info_d = db_sily.get(normalizuj_nazev(domaci))
                        info_h = db_sily.get(normalizuj_nazev(hoste))
                        
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
                                    st.markdown(f"<div style='text-align:center'>{datum_str}<br><h4>{int(pd)}% : {int(ph)}%</h4></div>", unsafe_allow_html=True)
                                    if pd > 60: st.success(f"Tip: {domaci}")
                                    elif ph > 60: st.error(f"Tip: {hoste}")
                                    else: st.warning("Remíza / Risk")
                                with c3: st.markdown(f"<div style='text-align:left'><b>{hoste}</b><br>{info_h['forma']}</div>", unsafe_allow_html=True)
                            else:
                                with c2: st.write(f"{domaci} vs {hoste}")
                            st.markdown("---")
    else:
        st.error(f"Historická data pro sezónu {rok} nejsou dostupná.")


# ==========================================
# 2. MODUL: TENIS (Robustní Scraping)
# ==========================================

def app_tenis():
    st.header("🎾 Tenisový Prediktor")
    st.caption("Zdroj: TennisExplorer.com (Dnešek + Zítřek)")

    @st.cache_data(ttl=1800)
    def scrape_tennis_day(date_obj):
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day
        url = f"https://www.tennisexplorer.com/matches/?type=all&year={year}&month={month}&day={day}"
        
        # Vylepšená hlavička
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200: return [], f"Chyba HTTP {r.status_code}"
            
            # Použijeme lxml pro lepší parsování
            try:
                dfs = pd.read_html(r.text, flavor='lxml')
            except:
                dfs = pd.read_html(r.text) # Fallback
            
            matches = []
            current_tournament = "Neznámý turnaj"
            
            # Hledáme správnou tabulku - ne podle velikosti, ale podle obsahu
            target_df = None
            for df in dfs:
                # Tabulka s kurzy má obvykle hodně sloupců a obsahuje čas
                if len(df.columns) > 4:
                    # Převedeme na string pro kontrolu
                    sample = str(df.head(5))
                    if ":" in sample: # Čas
                        target_df = df
                        break
            
            if target_df is None:
                return [], f"Nenalezena tabulka zápasů. (Nalezeno {len(dfs)} jiných tabulek)"

            # Iterace přes řádky nalezené tabulky
            for idx, row in target_df.iterrows():
                try:
                    col0 = str(row.iloc[0])
                    
                    # 1. Je to název turnaje? (Nemá čas a je dlouhý)
                    if ":" not in col0 and len(col0) > 3:
                        current_tournament = col0
                        continue
                    
                    # 2. Je to zápas? (Má čas)
                    if ":" in col0:
                        # TennisExplorer: Time | Player | Score | Sets | Odds1 | Odds2
                        # Kurzy jsou obvykle poslední dva sloupce
                        odds1 = row.iloc[-2]
                        odds2 = row.iloc[-1]
                        
                        # Kontrola, zda jsou to čísla
                        try:
                            o1 = float(odds1)
                            o2 = float(odds2)
                        except:
                            continue # Nejsou to kurzy (např. prázdné pole)
                            
                        players = str(row.iloc[1])
                        if " - " in players:
                            p1, p2 = players.split(" - ", 1)
                            
                            matches.append({
                                "Datum": date_obj.strftime("%d.%m."),
                                "Čas": col0,
                                "Turnaj": current_tournament,
                                "Hráč 1": p1,
                                "Hráč 2": p2,
                                "Kurz 1": o1,
                                "Kurz 2": o2
                            })
                except:
                    continue
                    
            return matches, None
        except Exception as e:
            return [], str(e)

    # --- LOGIKA TENIS ---
    dnes = datetime.now()
    zitra = dnes + timedelta(days=1)
    
    with st.spinner("Stahuji tenisové zápasy (Dnešek + Zítřek)..."):
        zapasy_dnes, err1 = scrape_tennis_day(dnes)
        zapasy_zitra, err2 = scrape_tennis_day(zitra)
        vsechny_zapasy = zapasy_dnes + zapasy_zitra

    # Diagnostika, pokud se nic nenašlo
    if not vsechny_zapasy:
        st.error("Nepodařilo se stáhnout žádné zápasy.")
        with st.expander("🔍 Zobrazit detaily chyby"):
            st.write(f"Dnešek: {err1}")
            st.write(f"Zítřek: {err2}")
            st.write("Tip: Ujisti se, že jsi přidal 'lxml' do requirements.txt")
    else:
        # Filtr turnajů
        turnaje = sorted(list(set([z["Turnaj"] for z in vsechny_zapasy])))
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtr_turnaj = st.selectbox("Filtrovat Turnaj:", ["Vše"] + turnaje)
        with col_f2:
            jen_atp = st.checkbox("Ukázat jen ATP/WTA", value=True)

        st.subheader(f"Nalezeno {len(vsechny_zapasy)} zápasů")
        
        count = 0
        for z in vsechny_zapasy:
            # Filtrování
            if jen_atp and ("ATP" not in z["Turnaj"] and "WTA" not in z["Turnaj"]): continue
            if filtr_turnaj != "Vše" and z["Turnaj"] != filtr_turnaj: continue
            
            count += 1
            
            # Výpočet predikce
            prob1 = (1 / z["Kurz 1"])
            prob2 = (1 / z["Kurz 2"])
            margin = prob1 + prob2 
            
            real_prob1 = (prob1 / margin) * 100
            real_prob2 = (prob2 / margin) * 100
            
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([2, 3, 2, 3, 2])
                
                with c1: 
                    st.caption(f"{z['Datum']} {z['Čas']}")
                    st.caption(z["Turnaj"][:25])
                
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
        
        if count == 0:
            st.info("Žádné zápasy neodpovídají filtru.")

# ==========================================
# HLAVNÍ ROZCESTNÍK
# ==========================================

st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🎾 Tenis"])

if sport == "⚽ Fotbal":
    app_fotbal()
elif sport == "🎾 Tenis":
    app_tenis()
