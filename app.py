import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="Global Betting Hub", layout="wide")

# ==========================================
# 1. MODUL: FOTBAL (Rozšířený)
# ==========================================

def app_fotbal():
    st.header("⚽ Fotbalový Svět")
    st.caption("Data: Football-Data.co.uk (Top ligy) + FixtureDownload.com (Ostatní)")
    
    # --- KONFIGURACE LIG ---
    # hist = kód pro historii (pokud existuje), fut = slug pro budoucnost
    LIGY_KODY = {
        "🇬🇧 Premier League": {"hist": "E0", "fut": "epl"},
        "🇬🇧 Championship": {"hist": "E1", "fut": "championship"},
        "🇩🇪 Bundesliga": {"hist": "D1", "fut": "bundesliga"},
        "🇪🇸 La Liga": {"hist": "SP1", "fut": "la-liga"},
        "🇮🇹 Serie A": {"hist": "I1", "fut": "serie-a"},
        "🇫🇷 Ligue 1": {"hist": "F1", "fut": "ligue-1"},
        "🇵🇹 Primeira Liga (Portugalsko)": {"hist": "P1", "fut": "primeira-liga"},
        "🇬🇷 Super League (Řecko)": {"hist": "G1", "fut": "super-league"},
        "🇹🇷 Süper Lig (Turecko)": {"hist": "T1", "fut": "super-lig"},
        "🇳🇱 Eredivisie (Holandsko)": {"hist": "N1", "fut": "eredivisie"},
        "🇧🇪 Jupiler League (Belgie)": {"hist": "B1", "fut": "jupiler-league"},
        # Ligy, kde je historie obtížná, ale budoucnost půjde:
        "🇵🇱 Ekstraklasa (Polsko)": {"hist": "POL", "fut": "ekstraklasa"},
        "🇩🇰 Superliga (Dánsko)": {"hist": "DNK", "fut": "superliga"},
        "🇷🇴 Liga I (Rumunsko)": {"hist": "ROU", "fut": "liga-i"},
        "🇧🇬 First League (Bulharsko)": {"hist": "BUL", "fut": "first-professional-football-league"},
        "🇮🇱 Premier League (Izrael)": {"hist": "ISR", "fut": "ligat-haal"},
    }

    def normalizuj_nazev(nazev):
        if not isinstance(nazev, str): return ""
        nazev = nazev.lower().strip()
        # Základní čištění
        nazev = nazev.replace(" fc", "").replace(" cf", "").replace(" ac", "").replace(" as", "").replace(" sc", "")
        return nazev

    @st.cache_data(ttl=3600)
    def nacti_fotbal_data(liga_nazev, rok_start):
        kody = LIGY_KODY[liga_nazev]
        
        # 1. Historie
        rok_konec = rok_start + 1
        sezona_short = f"{str(rok_start)[-2:]}{str(rok_konec)[-2:]}"
        # Zkusíme standardní cestu
        url_hist = f"https://www.football-data.co.uk/mmz4281/{sezona_short}/{kody['hist']}.csv"
        
        df_h = None
        try:
            r_h = requests.get(url_hist)
            if r_h.status_code == 200:
                df_h = pd.read_csv(io.StringIO(r_h.text))
            else:
                # Fallback na minulý rok (pro výpočet síly stačí i starší data)
                prev_short = f"{str(rok_start-1)[-2:]}{str(rok_start)[-2:]}"
                url_hist_prev = f"https://www.football-data.co.uk/mmz4281/{prev_short}/{kody['hist']}.csv"
                r_h2 = requests.get(url_hist_prev)
                if r_h2.status_code == 200:
                    df_h = pd.read_csv(io.StringIO(r_h2.text))
        except: pass

        # 2. Budoucnost
        url_fut = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-UTC.csv"
        df_f = None
        try:
            r_f = requests.get(url_fut)
            if r_f.status_code == 200:
                try: df_f = pd.read_csv(io.StringIO(r_f.text))
                except: df_f = pd.read_csv(io.StringIO(r_f.content.decode('latin-1')))
            else:
                # Zkusíme GMT
                url_fut_alt = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-GMTStandardTime.csv"
                r_f2 = requests.get(url_fut_alt)
                if r_f2.status_code == 200:
                    df_f = pd.read_csv(io.StringIO(r_f2.text))
        except: pass
        
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
    with c2: rok = st.selectbox("Sezóna:", [2025, 2024, 2023], index=0)

    with st.spinner("Analyzuji data..."):
        df_hist, df_fut = nacti_fotbal_data(vybrana_liga, rok)
    
    db_sily = {}
    if df_hist is not None:
        db_sily = analyzuj_silu(df_hist)
        with st.expander("📊 Tabulka formy (z dostupných dat)"):
            st.dataframe(pd.DataFrame.from_dict(db_sily, orient='index').sort_values(by='body', ascending=False))
    else:
        st.warning("Pro tuto ligu/sezónu se nepodařilo stáhnout historická data. Predikce nebudou přesné.")

    if df_fut is not None:
        st.subheader(f"📅 Rozpis: {vybrana_liga}")
        col_date = next((c for c in df_fut.columns if "Date" in c or "Time" in c), None)
        
        if col_date:
            df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], dayfirst=True, errors='coerce')
            if df_fut['DateObj'].isnull().all():
                    df_fut['DateObj'] = pd.to_datetime(df_fut[col_date], errors='coerce')
            
            dnes = datetime.now()
            budouci = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj').head(20)
            
            if budouci.empty:
                st.info("Žádné budoucí zápasy v rozpisu.")
            else:
                for index, row in budouci.iterrows():
                    col_home = [c for c in df_fut.columns if "Home" in c][0]
                    col_away = [c for c in df_fut.columns if "Away" in c][0]
                    domaci = row[col_home]
                    hoste = row[col_away]
                    datum_str = row[col_date]
                    
                    # Normalizace a hledání
                    d_norm = normalizuj_nazev(domaci)
                    h_norm = normalizuj_nazev(hoste)
                    
                    info_d = db_sily.get(d_norm)
                    info_h = db_sily.get(h_norm)
                    
                    # Fuzzy hledání
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
                            pd_val = (sila_d / celk) * 100
                            ph_val = (sila_h / celk) * 100
                            
                            with c1: st.markdown(f"<div style='text-align:right'><b>{domaci}</b><br>{info_d['forma']}</div>", unsafe_allow_html=True)
                            with c2: 
                                st.markdown(f"<div style='text-align:center'>{datum_str}<br><h4>{int(pd_val)}% : {int(ph_val)}%</h4></div>", unsafe_allow_html=True)
                                if pd_val > 60: st.success(f"Tip: {domaci}")
                                elif ph_val > 60: st.error(f"Tip: {hoste}")
                                else: st.warning("Risk")
                            with c3: st.markdown(f"<div style='text-align:left'><b>{hoste}</b><br>{info_h['forma']}</div>", unsafe_allow_html=True)
                        else:
                            with c2: 
                                st.write(f"{domaci} vs {hoste}")
                                st.caption("Chybí historie")
                        st.markdown("---")
    else:
        st.error("Rozpis zápasů není dostupný.")


# ==========================================
# 2. MODUL: TENIS (Agresivní Scraping)
# ==========================================

def app_tenis():
    st.header("🎾 Tenisový Radar")
    st.caption("Zdroj: VitiSport.cz (Agresivní vyhledávání)")

    @st.cache_data(ttl=600)
    def scrape_vitisport_aggressive():
        url = "https://www.vitisport.cz/index.php?g=tenis&lang=en"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200: return [], f"Chyba {r.status_code}"
            
            # Zkusíme najít všechny tabulky
            try: dfs = pd.read_html(r.text)
            except: return [], "Pandas nenašel žádnou tabulku v HTML."
            
            matches = []
            
            # Projdeme VŠECHNY tabulky, co jsme našli
            for df in dfs:
                # Konvertujeme na string pro prohledávání
                df = df.astype(str)
                
                # Hledáme tabulku, která má alespoň 3 sloupce a obsahuje čas (:)
                if len(df.columns) < 3: continue
                
                for idx, row in df.iterrows():
                    # VitiSport struktura je divoká, musíme hádat
                    # Obvykle: Sloupec 0 = Čas, Sloupec 1 = Domácí, Sloupec 2 = Hosté
                    
                    try:
                        col0 = str(row.iloc[0]) # Čas?
                        col1 = str(row.iloc[1]) # Domácí?
                        col2 = str(row.iloc[2]) # Hosté?
                        
                        # Kontrola, zda to vypadá jako zápas
                        if ":" in col0 and len(col1) > 2 and len(col2) > 2:
                            # Ignorujeme řádky s nadpisy
                            if "Home" in col1 or "Date" in col0: continue
                            
                            # Hledáme tip (1 nebo 2) v celém řádku
                            tip = "N/A"
                            for item in row:
                                if item == "1": tip = col1; break
                                if item == "2": tip = col2; break
                            
                            matches.append({
                                "Čas": col0,
                                "Hráč 1": col1,
                                "Hráč 2": col2,
                                "Tip": tip
                            })
                    except: continue
            
            return matches, None
        except Exception as e:
            return [], str(e)

    with st.spinner("Prohledávám VitiSport..."):
        matches, error = scrape_vitisport_aggressive()

    if error:
        st.error(f"Chyba: {error}")
    elif not matches:
        st.warning("Nebyly nalezeny žádné zápasy. Web mohl změnit strukturu.")
    else:
        st.success(f"Nalezeno {len(matches)} zápasů.")
        
        for m in matches:
            with st.container():
                c1, c2, c3 = st.columns([3, 2, 3])
                with c1: st.markdown(f"<div style='text-align:right'><b>{m['Hráč 1']}</b></div>", unsafe_allow_html=True)
                with c2: 
                    st.markdown(f"<div style='text-align:center'>{m['Čas']}<br>VS</div>", unsafe_allow_html=True)
                    if m['Tip'] != "N/A":
                        if m['Tip'] == m['Hráč 1']: st.success(f"Tip: {m['Hráč 1']}")
                        else: st.error(f"Tip: {m['Hráč 2']}")
                with c3: st.markdown(f"<div style='text-align:left'><b>{m['Hráč 2']}</b></div>", unsafe_allow_html=True)
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
