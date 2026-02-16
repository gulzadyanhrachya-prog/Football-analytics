).import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import urllib.parse
import time
import random

st.set_page_config(page_title="PredictZ Proxy Hunter", layout="wide")

# ==============================================================================\n# 1. SCRAPING ENGINE (PŘES PROXY)\n# ==============================================================================\n
@st.cache_data(ttl=1800)
def scrape_predictz_proxy(day="today"):
    # 1. Cílová adresa
    base_url = "https://www.predictz.com/predictions/"
    if day == "tomorrow":
        base_url += "tomorrow/"
    
    # 2. Zakódování adresy pro proxy
    encoded_url = urllib.parse.quote(base_url)
    
    # 3. Náhodné číslo, aby se neukládala stará cache na straně proxy
    rand_num = random.randint(1, 10000)
    
    # 4. Použití AllOrigins (Stáhne stránku za nás)
    proxy_url = f"https://api.allorigins.win/get?url={encoded_url}&rand={rand_num}"
    
    try:
        # Stahujeme JSON, který obsahuje HTML stránky v poli "contents"
        r = requests.get(proxy_url, timeout=20)
        
        if r.status_code != 200:
            return None, f"Chyba proxy: {r.status_code}"
            
        data = r.json()
        html_content = data.get("contents")
        
        if not html_content:
            return None, "Proxy vrátila prázdný obsah."
            
        # --- PARSOVÁNÍ HTML ---
        soup = BeautifulSoup(html_content, 'html.parser')
        matches = []
        
        # Hledáme řádky zápasů
        rows = soup.find_all("div", class_="ptable-row")
        
        current_league = "Ostatní"
        
        for row in rows:
            try:
                # Hledáme jména týmů
                home_div = row.find("div", class_="ptable-home")
                away_div = row.find("div", class_="ptable-away")
                
                # Pokud řádek nemá týmy, je to pravděpodobně název ligy
                if not home_div or not away_div:
                    text = row.get_text(strip=True)
                    # Jednoduchá detekce: pokud text neobsahuje čísla a je delší
                    if len(text) > 3 and not any(char.isdigit() for char in text):
                        current_league = text
                    continue

                home = home_div.get_text(strip=True)
                away = away_div.get_text(strip=True)
                
                if not home or not away: continue

                # Hledáme předpovídané skóre
                score_div = row.find("div", class_="ptable-score")
                pred_score = score_div.get_text(strip=True) if score_div else ""
                
                # Vypočítáme TIP ze skóre (nejspolehlivější metoda)
                tip = "Neznámý"
                tip_code = ""
                
                if "-" in pred_score:
                    try:
                        parts = pred_score.split("-")
                        g1 = int(parts[0])
                        g2 = int(parts[1])
                        
                        if g1 > g2: 
                            tip = f"Výhra {home}"
                            tip_code = "1"
                        elif g2 > g1: 
                            tip = f"Výhra {away}"
                            tip_code = "2"
                        else: 
                            tip = "Remíza"
                            tip_code = "0"
                    except: pass
                
                # Pokud nemáme tip ze skóre, zkusíme textový tip
                if tip_code == "":
                    result_div = row.find("div", class_="ptable-result")
                    if result_div:
                        res_text = result_div.get_text(strip=True).lower()
                        if "home" in res_text: tip_code = "1"; tip = f"Výhra {home}"
                        elif "away" in res_text: tip_code = "2"; tip = f"Výhra {away}"
                        elif "draw" in res_text: tip_code = "0"; tip = "Remíza"

                if tip_code == "": continue

                matches.append({
                    "Liga": current_league,
                    "Domácí": home,
                    "Hosté": away,
                    "Skóre": pred_score,
                    "Tip": tip,
                    "Kód": tip_code
                })
                
            except: continue
            
        return matches, None

    except Exception as e:
        return None, str(e)

# ==============================================================================\n# 2. UI APLIKACE\n# ==============================================================================\n
st.title("🌍 Global Football Predictor")
st.caption("Zdroj: PredictZ (přes Proxy Tunel)")

# Výběr dne
col_day, col_status = st.columns([1, 3])
with col_day:
    day_sel = st.radio("Vyber den:", ["Dnes", "Zítra"])
    day_param = "today" if day_sel == "Dnes" else "tomorrow"

with st.spinner(f"Stahuji data přes proxy server ({day_sel})..."):
    data, error = scrape_predictz_proxy(day_param)

if error:
    st.error(f"Chyba připojení: {error}")
    st.write("Zkus to znovu za chvíli. Proxy server může být přetížený.")
elif not data:
    st.warning("Nebyly nalezeny žádné zápasy. Web PredictZ může být nedostupný.")
else:
    df = pd.DataFrame(data)
    
    # --- FILTRY ---
    with st.expander("🛠️ Filtrování", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            search = st.text_input("Hledat tým nebo ligu (např. Arsenal, Bosnia):")
        with c2:
            filter_tip = st.multiselect("Typ sázky:", ["Výhra Domácích (1)", "Remíza (0)", "Výhra Hostů (2)"], default=["Výhra Domácích (1)", "Výhra Hostů (2)"])
    
    # Aplikace filtrů
    if search:
        df = df[df["Liga"].str.contains(search, case=False) | df["Domácí"].str.contains(search, case=False) | df["Hosté"].str.contains(search, case=False)]
    
    codes_allowed = []
    if "Výhra Domácích (1)" in filter_tip: codes_allowed.append("1")
    if "Remíza (0)" in filter_tip: codes_allowed.append("0")
    if "Výhra Hostů (2)" in filter_tip: codes_allowed.append("2")
    
    df = df[df["Kód"].isin(codes_allowed)]
    
    # --- ZOBRAZENÍ ---
    st.success(f"Zobrazeno {len(df)} zápasů.")
    
    # Seskupení podle lig
    ligy = df["Liga"].unique()
    
    for liga in ligy:
        league_matches = df[df["Liga"] == liga]
        
        with st.expander(f"🏆 {liga} ({len(league_matches)})", expanded=True):
            for idx, row in league_matches.iterrows():
                c1, c2, c3, c4 = st.columns([3, 1, 3, 2])
                
                with c1:
                    st.markdown(f"<div style='text-align:right; font-weight:bold'>{row['Domácí']}</div>", unsafe_allow_html=True)
                
                with c2:
                    st.markdown(f"<div style='text-align:center; background-color:#f0f2f6; border-radius:5px; font-weight:bold'>{row['Skóre']}</div>", unsafe_allow_html=True)
                
                with c3:
                    st.markdown(f"<div style='text-align:left; font-weight:bold'>{row['Hosté']}</div>", unsafe_allow_html=True)
                
                with c4:
                    color = "green" if row["Kód"] == "1" else ("red" if row["Kód"] == "2" else "orange")
                    st.markdown(f":{color}[**{row['Tip']}**]")
