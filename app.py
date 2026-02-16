).import streamlit as st
import pandas as pd
import cloudscraper
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Daily Soccer Scraper", layout="wide")

# ==============================================================================\n# 1. SCRAPING ENGINE (SoccerStats.com)\n# ==============================================================================\n
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
        current_country = "Svět"
        
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

# ==============================================================================\n# 2. ANALYTICKÝ MODEL (PPG + Form)\n# ==============================================================================\n
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
    if ppg_h > 1.8 and ppg_
