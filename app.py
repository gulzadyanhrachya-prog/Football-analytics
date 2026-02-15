import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="Sport Betting Hub v5", layout="wide")

# ==========================================
# 1. MODUL: FOTBAL (S Fallbackem)
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

    # Masivní překladač jmen pro spárování historie a budoucnosti
    def normalizuj_nazev(nazev):
        if not isinstance(nazev, str): return ""
        nazev = nazev.lower().strip()
        mapping = {
            # Anglie
            "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united",
            "leicester": "leicester city", "leeds": "leeds united", "notts forest": "nottingham forest",
            "wolves": "wolverhampton wanderers", "brighton": "brighton & hove albion",
            "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
            "west ham": "west ham united", "newcastle": "newcastle united", "luton": "luton town",
            # Itálie
            "inter": "inter milan", "internazionale": "inter milan", "milan": "ac milan",
            "juve": "juventus", "roma": "as roma", "lazio": "ss lazio", "napoli": "ssc napoli",
            # Španělsko
            "barca": "barcelona", "fc barcelona": "barcelona", "real madrid": "real madrid",
            "atletico": "atletico madrid", "athl bilbao": "athletic bilbao", "betis": "real betis",
            "sociedad": "real sociedad", "sevilla": "sevilla fc",
            # Německo
            "bayern": "bayern munich", "bayern munchen": "bayern munich", "dortmund": "borussia dortmund",
            "leverkusen": "bayer leverkusen", "leipzig": "rb leipzig", "mainz": "mainz 05",
            "frankfurt": "eintracht frankfurt", "stuttgart": "vfb stuttgart",
            # Francie
            "psg": "paris saint germain", "paris sg": "paris saint germain", "marseille": "olympique marseille",
            "lyon": "olympique lyon", "monaco": "as monaco", "lille": "lille osc"
        }
        # Pokud název obsahuje " fc", " cf", " ac", odstraníme to pro lepší shodu
        clean = nazev.replace(" fc", "").replace(" cf", "").replace(" ac", "").replace(" as", "")
        return mapping.get(nazev, mapping.get(clean, clean))

    @st.cache_data(ttl=3600)
    def nacti_fotbal_data(liga_nazev, rok_start):
        kody = LIGY_KODY[liga_nazev]
        
        # 1. Zkusíme stáhnout historii pro vybraný rok
        rok_konec = rok_start + 1
        sezona_short = f"{str(rok_start)[-2:]}{str(rok_konec)[-2:]}"
        url_hist = f"https://www.football-data.co.uk/mmz4281/{sezona_short}/{kody['hist']}.csv"
        
        df_h = None
        pouzity_rok_historie = rok_start
        
        try:
            r_h = requests.get(url_hist)
            if r_h.status_code == 200:
                df_h = pd.read_csv(io.StringIO(r_h.text))
            else:
                # FALLBACK: Pokud 2025 neexistuje, zkusíme 2024 (minulou sezónu)
                prev_start = rok_start - 1
                prev_end = rok_start
                sezona_prev = f"{str(prev_start)[-2:]}{str(prev_end)[-2:]}"
                url_hist_prev = f"https://www.football-data.co.uk/mmz4281/{sezona_prev}/{kody['hist']}.csv"
                r_h2 = requests.get(url_hist_prev)
                if r_h2.status_code == 200:
                    df_h = pd.read_csv(io.StringIO(r_h2.text))
                    pouzity_rok_historie = prev_start
        except: pass

        # 2. Stáhneme rozpis (Budoucnost)
        url_fut = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-UTC.csv"
        df_f = None
        try:
            r_f = requests.get(url_fut)
            if r_f.status_code == 200:
                try: df_f = pd.read_csv(io.StringIO(r_f.text))
                except: df_f = pd.read_csv(io.StringIO(r_f.content.decode('latin-1')))
            else:
                # Alternativa GMT
                url_fut_alt = f"https://fixturedownload.com/download/{kody['fut']}-{rok_start}-GMTStandardTime.csv"
                r_f2 = requests.get(url_fut_alt)
                if r_f2.status_code == 200:
                    df_f = pd.read_csv(io.StringIO(r_f2.text))
        except: pass
        
        return df_h, df_f, pouzity_rok_historie

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

    with st.spinner("Analyzuji fotbalová data..."):
        df_hist, df_fut, rok_hist = nacti_fotbal_data(vybrana_liga, rok)
    
    if df_hist is not None:
        if rok_hist != rok:
            st.warning(f"⚠️ Data pro sezónu {rok} nejsou kompletní. Používám data z roku {rok_hist} pro výpočet síly týmů.")
        
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
                # Zobrazíme zápasy od dneška dál (limit 20)
                budouci = df_fut[df_fut['DateObj'] >= dnes].sort_values(by='DateObj').head(20)
                
                if budouci.empty:
                    st.warning("Žádné budoucí zápasy v rozpisu.")
                else:
                    for index, row in budouci.iterrows():
                        col_home = [c for c in df_fut.columns if "Home" in c][0]
                        col_away = [c for c in df_fut.columns if "Away" in c][0]
                        domaci = row[col_home]
                        hoste = row[col_away]
                        datum_str = row[col_date]
                        
                        # Normalizace
                        d_norm = normalizuj_nazev(domaci)
                        h_norm = normalizuj_nazev(hoste)
                        
                        info_d = db_sily.get(d_norm)
                        info_h = db_sily.get(h_norm)
                        
                        # Fuzzy hledání (pokud přesná shoda selže)
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
                                    else: st.warning("Remíza / Risk")
                                with c3: st.markdown(f"<div style='text-align:left'><b>{hoste}</b><br>{info_h['forma']}</div>", unsafe_allow_html=True)
                            else:
                                with c2: 
                                    st.write(f"{domaci} vs {hoste}")
                                    st.caption("Chybí data o týmech")
                            st.markdown("---")
    else:
        st.error(f"Nepodařilo se načíst historická data ani pro rok {rok}, ani pro rok {rok-1}.")


# ==========================================
# 2. MODUL: TENIS (VitiSport - Spolehlivější)
# ==========================================

def app_tenis():
    st.header("🎾 Tenisový Prediktor (VitiSport)")
    st.caption("Zdroj: VitiSport.cz (Obsahuje hotové predikce)")

    @st.cache_data(ttl=1800)
    def scrape_vitisport():
        # VitiSport má tabulku s predikcemi přímo na webu
        url = "https://www.vitisport.cz/index.php?g=tenis&lang=en"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200: return None, f"Chyba {r.status_code}"
            
            # Pandas najde tabulky
            dfs = pd.read_html(r.text)
            
            # Hledáme tabulku, která má sloupec "Score" nebo "%"
            target_df = None
            for df in dfs:
                # Převedeme sloupce na string a hledáme klíčová slova
                cols = [str(c).lower() for c in df.columns]
                if len(cols) > 4 and any("home" in c for c in cols):
                    target_df = df
                    break
            
            if target_df is None: return None, "Tabulka nenalezena"
            
            return target_df, None
        except Exception as e:
            return None, str(e)

    with st.spinner("Stahuji tenisové tipy..."):
        df, error = scrape_vitisport()

    if error:
        st.error(f"Chyba: {error}")
    else:
        st.success(f"Načteno {len(df)} zápasů.")
        
        # VitiSport tabulka nemá pojmenované sloupce, musíme je odhadnout
        # Obvykle: Čas, Domácí, Hosté, Tip, %1, %2
        
        # Přejmenování sloupců (pokus)
        try:
            # VitiSport má často první sloupce prázdné nebo divné, vezmeme ty podstatné
            # Struktura se mění, ale obvykle index 0=Čas, 1=Domácí, 2=Hosté, ... 5=Tip
            
            for index, row in df.iterrows():
                try:
                    cas = str(row.iloc[0])
                    domaci = str(row.iloc[1])
                    hoste = str(row.iloc[2])
                    
                    # Pokud řádek vypadá jako nadpis, přeskočíme
                    if "Home" in domaci or "Date" in cas: continue
                    if pd.isna(domaci) or pd.isna(hoste): continue

                    # Zkusíme najít procenta (často jsou ve sloupcích 6 a 7 nebo podobně)
                    # Hledáme sloupce, které obsahují čísla
                    
                    # Jednoduché zobrazení řádku
                    with st.container():
                        c1, c2, c3 = st.columns([3, 2, 3])
                        
                        with c1: 
                            st.markdown(f"<div style='text-align:right'><b>{domaci}</b></div>", unsafe_allow_html=True)
                        
                        with c2:
                            st.markdown(f"<div style='text-align:center'>{cas}<br>VS</div>", unsafe_allow_html=True)
                            
                            # Pokus o nalezení tipu v řádku
                            # Projdeme buňky a hledáme něco co vypadá jako "1", "2" nebo procenta
                            tip = ""
                            for item in row:
                                s = str(item)
                                if s in ["1", "2"]: 
                                    tip = s
                                    break
                            
                            if tip == "1": st.success(f"Tip: {domaci}")
                            elif tip == "2": st.error(f"Tip: {hoste}")
                        
                        with c3:
                            st.markdown(f"<div style='text-align:left'><b>{hoste}</b></div>", unsafe_allow_html=True)
                        
                        st.markdown("---")
                except: continue
        except Exception as e:
            st.error(f"Chyba při zpracování tabulky: {e}")
            st.dataframe(df) # Debug

# ==========================================
# HLAVNÍ ROZCESTNÍK
# ==========================================

st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🎾 Tenis"])

if sport == "⚽ Fotbal":
    app_fotbal()
elif sport == "🎾 Tenis":
    app_tenis()
