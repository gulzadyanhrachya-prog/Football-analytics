import streamlit as st
import pandas as pd
import cloudscraper
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Daily Soccer Scraper", layout="wide")

# ==============================================================================
# 1. SCRAPING ENGINE (SoccerStats.com)
# ==============================================================================

@st.cache_data(ttl=1800) # Cache 30 minut
def scrape_soccerstats(day="today"):
    # day: "today" nebo "tomorrow"
    base_url = "https://www.soccerstats.com/matches.asp"
    if day == "tomorrow":
        base_url += "?matchday=2"
    
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(base_url)
        if r.status_code != 200: return None, f"Chyba připojení: {r.status_code}"
        
        # Pandas read_html je nejmocnější nástroj na tabulky
        dfs = pd.read_html(r.text)
        
        matches = []
        current_league = "Neznámá liga"
        
        # SoccerStats má divnou strukturu: Tabulky jsou rozsekané.
        # Musíme iterovat přes všechny nalezené tabulky a hledat vzory.
        
        for df in dfs:
            # Převedeme na string pro analýzu
            df = df.astype(str)
            
            # 1. DETEKCE LIGY (Hlavička tabulky)
            # Obvykle má 1 nebo 2 sloupce a obsahuje název země
            if len(df.columns) < 3 and len(df) == 1:
                text = df.iloc[0, 0]
                if len(text) > 3 and not "Match" in text:
                    current_league = text
                    continue
            
            # 2. DETEKCE ZÁPASŮ
            # Tabulka se zápasy má obvykle hodně sloupců (Stats, Home, Away, PPG...)
            if len(df.columns) >= 8:
                for idx, row in df.iterrows():
                    try:
                        # Hledáme řádek se zápasem
                        # SoccerStats formát: Time | Stat | Home | ... | Away | ... | PPG Home | PPG Away
                        
                        # Čas je obvykle v prvním sloupci
                        cas = row.iloc[0]
                        if ":" not in cas: continue # Není to čas
                        
                        # Týmy jsou obvykle ve sloupci 2 a 4 (nebo podobně, liší se to)
                        # Hledáme textové hodnoty
                        home = row.iloc[2]
                        away = row.iloc[4]
                        
                        # Statistiky (PPG - Points Per Game)
                        # Často jsou ve sloupcích s procenty nebo čísly x.xx
                        # Musíme najít sloupce, které vypadají jako PPG (např. "1.50", "2.10")
                        ppg_h = 0.0
                        ppg_a = 0.0
                        
                        # Projdeme řádek a zkusíme najít PPG hodnoty
                        # Obvykle jsou to floaty v závorkách nebo samostatně
                        vals = [str(x) for x in row.values]
                        floats = []
                        for v in vals:
                            try:
                                f = float(v)
                                if 0 <= f <= 3.0: floats.append(f)
                            except: pass
                        
                        # Pokud najdeme vhodné floaty, předpokládáme, že to jsou PPG
                        if len(floats) >= 2:
                            ppg_h = floats[0] # První číslo bývá domácí
                            ppg_a = floats[1] # Druhé hosté
                        
                        # Uložíme zápas
                        matches.append({
                            "Liga": current_league,
                            "Čas": cas,
                            "Domácí": home,
                            "Hosté": away,
                            "PPG_H": ppg_h,
                            "PPG_A": ppg_a
                        })
                    except: continue
                    
        return matches, None

    except Exception as e:
        return None, str(e)

# ==============================================================================
# 2. ANALYTICKÝ MODEL (PPG + Form)
# ==============================================================================

def analyze_match(ppg_h, ppg_a):
    # PPG (Points Per Game) je nejlepší jednoduchý ukazatel síly
    # Rozsah 0.00 až 3.00
    
    # Přidáme výhodu domácího prostředí (+0.25 PPG)
    adj_ppg_h = ppg_h + 0.25
    
    diff = adj_ppg_h - ppg_a
    
    tip = ""
    confidence = 0
    bet_type = ""
    
    # Logika predikce
    if diff > 0.75:
        tip = "Výhra Domácích"
        bet_type = "1"
        confidence = 75 + (diff * 10)
    elif diff < -0.75:
        tip = "Výhra Hostů"
        bet_type = "2"
        confidence = 75 + (abs(diff) * 10)
    elif diff > 0.3:
        tip = "Domácí bez remízy (SBR)"
        bet_type = "1 (SBR)"
        confidence = 60
    elif diff < -0.3:
        tip = "Hosté bez remízy (SBR)"
        bet_type = "2 (SBR)"
        confidence = 60
    else:
        tip = "Remíza / Under 2.5"
        bet_type = "X / Under"
        confidence = 50
        
    # Gólový potenciál (pokud mají oba vysoké PPG, asi dávají góly)
    # To je hrubý odhad, protože PPG zahrnuje i obranu
    goals_pred = "Normal"
    if ppg_h > 1.8 and ppg_a > 1.8:
        goals_pred = "Over 2.5"
    elif ppg_h < 1.0 and ppg_a < 1.0:
        goals_pred = "Under 2.5"
        
    return {
        "Tip": tip,
        "Kód": bet_type,
        "Důvěra": min(95, confidence),
        "Góly": goals_pred
    }

# ==============================================================================
# 3. UI APLIKACE
# ==============================================================================

st.title("🌍 Global Soccer Scraper")
st.caption("Stahuje data z SoccerStats.com. Žádné API limity. Všechny ligy.")

# TABS
tab_live, tab_calc = st.tabs(["📅 Dnešní/Zítřejší Zápasy", "🧮 Manuální Kalkulačka"])

# --- TAB 1: SCRAPER ---
with tab_live:
    col_day, col_filter = st.columns(2)
    with col_day:
        day_sel = st.radio("Vyber den:", ["Dnes", "Zítra"], horizontal=True)
        day_param = "today" if day_sel == "Dnes" else "tomorrow"
    
    with st.spinner(f"Skenuji internet pro zápasy ({day_sel})..."):
        matches, error = scrape_soccerstats(day_param)
        
    if error:
        st.error(f"Chyba scrapingu: {error}")
    elif not matches:
        st.warning("Nebyly nalezeny žádné zápasy. Web může být nedostupný.")
    else:
        # Převedeme na DataFrame
        df = pd.DataFrame(matches)
        
        # Čištění dat (odstranění prázdných řádků nebo nesmyslů)
        df = df[df["Domácí"] != "nan"]
        
        # --- FILTRY ---
        with col_filter:
            # Získáme seznam lig
            ligy = sorted(df["Liga"].unique())
            # Předvybereme zajímavé ligy (pokud tam jsou)
            popular = ["England", "Germany", "Spain", "Italy", "France", "Czech", "Netherlands", "Portugal"]
            default_ligy = [l for l in ligy if any(p in l for p in popular)]
            
            sel_ligy = st.multiselect("Filtrovat ligy:", ligy, default=default_ligy)
            
        # Aplikace filtru
        if sel_ligy:
            df_show = df[df["Liga"].isin(sel_ligy)].copy()
        else:
            df_show = df.copy() # Zobrazit vše, pokud nic není vybráno
            
        st.success(f"Zobrazeno {len(df_show)} zápasů (z celkových {len(df)}).")
        
        # --- VÝPOČET A ZOBRAZENÍ ---
        for idx, row in df_show.iterrows():
            analysis = analyze_match(row["PPG_H"], row["PPG_A"])
            
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                
                with c1:
                    st.caption(row["Liga"])
                    st.write(f"**{row['Čas']}**")
                    
                with c2:
                    st.write(f"**{row['Domácí']}**")
                    st.write(f"**{row['Hosté']}**")
                    
                with c3:
                    # Zobrazení síly (PPG)
                    st.write("Síla (PPG):")
                    st.progress(min(1.0, row["PPG_H"] / 3))
                    st.progress(min(1.0, row["PPG_A"] / 3))
                    
                with c4:
                    # Predikce
                    st.metric("Tip", analysis["Kód"])
                    if analysis["Důvěra"] > 70:
                        st.success(f"{analysis['Důvěra']:.0f}% Důvěra")
                    else:
                        st.warning(f"{analysis['Důvěra']:.0f}% Důvěra")
                        
                    if analysis["Góly"] != "Normal":
                        st.info(analysis["Góly"])
                        
                st.markdown("---")

# --- TAB 2: KALKULAČKA (ZÁLOHA) ---
with tab_calc:
    st.header("🧮 Manuální Kalkulačka")
    st.write("Pokud scraper nenajde tvůj zápas (nebo jsi v roce 2026), zadej data ručně.")
    
    c1, c2 = st.columns(2)
    with c1:
        h_name = st.text_input("Domácí tým:", "Domácí")
        # PPG = Points Per Game (Body / Zápasy)
        h_ppg = st.slider("Domácí - Body na zápas (PPG):", 0.0, 3.0, 1.8, 0.01)
        st.caption("0.5 = Slabý, 1.5 = Průměr, 2.5 = Elita")
        
    with c2:
        a_name = st.text_input("Hostující tým:", "Hosté")
        a_ppg = st.slider("Hosté - Body na zápas (PPG):", 0.0, 3.0, 1.2, 0.01)
        
    if st.button("Analyzovat"):
        res = analyze_match(h_ppg, a_ppg)
        
        st.subheader(f"Výsledek: {h_name} vs {a_name}")
        
        m1, m2 = st.columns(2)
        m1.metric("Doporučený Tip", res["Tip"])
        m2.metric("Důvěra", f"{res['Důvěra']:.1f} %")
        
        if res["Góly"] != "Normal":
            st.info(f"Doporučená sázka na góly: **{res['Góly']}**")
