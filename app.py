import streamlit as st
import pandas as pd
import cloudscraper # TOTO JE TA NOVÁ KNIHOVNA
import time

st.set_page_config(page_title="FBref Scraper Pro", layout="wide")

# --- KONFIGURACE URL (FBref) ---
LIGY_URL = {
    "🇬🇧 Premier League": "https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures",
    "🇬🇧 Championship": "https://fbref.com/en/comps/10/schedule/Championship-Scores-and-Fixtures",
    "🇪🇸 La Liga": "https://fbref.com/en/comps/12/schedule/La-Liga-Scores-and-Fixtures",
    "🇩🇪 Bundesliga": "https://fbref.com/en/comps/20/schedule/Bundesliga-Scores-and-Fixtures",
    "🇮🇹 Serie A": "https://fbref.com/en/comps/11/schedule/Serie-A-Scores-and-Fixtures",
    "🇫🇷 Ligue 1": "https://fbref.com/en/comps/13/schedule/Ligue-1-Scores-and-Fixtures",
    "🇳🇱 Eredivisie": "https://fbref.com/en/comps/23/schedule/Eredivisie-Scores-and-Fixtures",
    "🇵🇹 Primeira Liga": "https://fbref.com/en/comps/32/schedule/Primeira-Liga-Scores-and-Fixtures",
    "🇧🇪 Pro League (Belgie)": "https://fbref.com/en/comps/37/schedule/Belgian-Pro-League-Scores-and-Fixtures",
    "🇨🇿 Fortuna Liga": "https://fbref.com/en/comps/38/schedule/Czech-First-League-Scores-and-Fixtures"
}

# --- SIDEBAR ---
st.sidebar.title("Nastavení")
vybrana_liga = st.sidebar.selectbox("Soutěž:", list(LIGY_URL.keys()))
url = LIGY_URL[vybrana_liga]

st.sidebar.info("Používám Cloudscraper pro obejití ochrany 403.")

# --- FUNKCE PRO SCRAPING ---
@st.cache_data(ttl=3600) 
def scrape_fbref_pro(url):
    # Vytvoříme scraper, který se tváří jako Chrome
    scraper = cloudscraper.create_scraper()
    
    try:
        # Zkusíme stáhnout stránku
        response = scraper.get(url)
        
        if response.status_code == 429:
            return None, None, "⛔ Too Many Requests (429). FBref nás dočasně zablokoval. Zkus to za hodinu."
        if response.status_code == 403:
            return None, None, "⛔ Access Denied (403). Ani Cloudscraper neprošel přes ochranu FBref."
        if response.status_code != 200:
            return None, None, f"Chyba připojení: {response.status_code}"

        # Pandas najde tabulky
        dfs = pd.read_html(response.text)
        df = dfs[0]
        
        # Vyčištění dat (odstranění mezititulků)
        df = df[df["Wk"] != "Wk"]
        
        # Kontrola sloupce Score
        if "Score" not in df.columns:
            return None, None, "Tabulka nemá sloupec Score. Struktura webu se změnila."
            
        # Rozdělení na odehrané a budoucí
        odehrane = df[df["Score"].notna()].copy()
        budouci = df[df["Score"].isna()].copy()
        
        return odehrane, budouci, None

    except Exception as e:
        return None, None, f"Chyba scrapingu: {e}"

# --- VÝPOČET TABULKY ---
def vypocitej_tabulku(df_odehrane):
    tymy = {}
    
    for index, row in df_odehrane.iterrows():
        domaci = row["Home"]
        hoste = row["Away"]
        skore = row["Score"]
        
        if pd.isna(skore) or "–" not in str(skore): continue
        
        # FBref používá pomlčku "–", ne mínus "-"
        try:
            goly_d, goly_h = map(int, str(skore).split("–")[:2])
        except ValueError:
            continue # Přeskočíme řádky, kde nejde přečíst skóre
        
        if domaci not in tymy: tymy[domaci] = {"Body": 0, "Z": 0, "Forma": []}
        if hoste not in tymy: tymy[hoste] = {"Body": 0, "Z": 0, "Forma": []}
        
        tymy[domaci]["Z"] += 1
        tymy[hoste]["Z"] += 1
        
        if goly_d > goly_h: 
            tymy[domaci]["Body"] += 3
            tymy[domaci]["Forma"].append("W")
            tymy[hoste]["Forma"].append("L")
        elif goly_h > goly_d: 
            tymy[hoste]["Body"] += 3
            tymy[hoste]["Forma"].append("W")
            tymy[domaci]["Forma"].append("L")
        else: 
            tymy[domaci]["Body"] += 1
            tymy[hoste]["Body"] += 1
            tymy[domaci]["Forma"].append("D")
            tymy[hoste]["Forma"].append("D")
            
    seznam = []
    for nazev, data in tymy.items():
        forma_list = data["Forma"][-5:]
        forma_str = "".join(forma_list)
        bonus = forma_str.count("W") * 3 + forma_str.count("D") * 1
        sila = data["Body"] + bonus
        
        seznam.append({
            "Tým": nazev,
            "Zápasy": data["Z"],
            "Body": data["Body"],
            "Forma": forma_str,
            "Síla": sila
        })
        
    df_tab = pd.DataFrame(seznam).sort_values(by="Body", ascending=False).reset_index(drop=True)
    df_tab.index += 1
    return df_tab

# --- UI APLIKACE ---
st.title(f"⚽ {vybrana_liga}")
st.caption("Zdroj dat: FBref.com (Bypassing 403 Protection)")

with st.spinner("Stahuji data (Cloudscraper)..."):
    df_odehrane, df_budouci, error = scrape_fbref_pro(url)

if error:
    st.error(error)
    st.write("Pokud vidíš chybu 403 i s Cloudscraperem, FBref má extrémně silnou ochranu.")
else:
    df_tabulka = vypocitej_tabulku(df_odehrane)
    sila_db = df_tabulka.set_index("Tým")["Síla"].to_dict()
    forma_db = df_tabulka.set_index("Tým")["Forma"].to_dict()

    tab1, tab2 = st.tabs(["🔮 Predikce", "📊 Tabulka"])
    
    with tab1:
        if df_budouci is not None and not df_budouci.empty:
            st.write(f"Nalezeno {len(df_budouci)} budoucích zápasů.")
            
            for index, row in df_budouci.head(20).iterrows():
                domaci = row["Home"]
                hoste = row["Away"]
                datum = row["Date"]
                cas = row["Time"]
                
                sila_d = sila_db.get(domaci, 0)
                sila_h = sila_db.get(hoste, 0)
                forma_d = forma_db.get(domaci, "")
                forma_h = forma_db.get(hoste, "")
                
                def viz_forma(f): return f.replace("W", "🟢").replace("L", "🔴").replace("D", "⚪")
                
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
                    
                    if sila_d > 0 and sila_h > 0:
                        sila_d_total = sila_d + 10 
                        celkova = sila_d_total + sila_h
                        proc_d = (sila_d_total / celkova) * 100
                        proc_h = (sila_h / celkova) * 100
                        
                        with c2: 
                            st.write(f"**{domaci}**")
                            st.caption(viz_forma(forma_d))
                        with c3:
                            st.write(f"{datum} {cas}")
                            st.markdown(f"#### {int(proc_d)}% : {int(proc_h)}%")
                            if proc_d > 60: st.success(f"Tip: {domaci}")
                            elif proc_h > 60: st.error(f"Tip: {hoste}")
                            else: st.warning("Tip: Remíza")
                        with c4:
                            st.write(f"**{hoste}**")
                            st.caption(viz_forma(forma_h))
                    else:
                        with c3: st.write(f"{domaci} vs {hoste}")
                    
                    st.markdown("---")
        else:
            st.info("Žádné budoucí zápasy nenalezeny.")

    with tab2:
        st.dataframe(df_tabulka, use_container_width=True)
