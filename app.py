import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

st.set_page_config(page_title="PredictZ Cleaner", layout="wide")

# ==============================================================================\n# 1. ROBUSTNÍ SCRAPER (PredictZ)\n# ==============================================================================\n
@st.cache_data(ttl=1800)
def scrape_predictz_robust(day="today"):
    base_url = "https://www.predictz.com/predictions/"
    if day == "tomorrow":
        base_url += "tomorrow/"
    
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(base_url)
        if r.status_code != 200: return None, f"Chyba připojení: {r.status_code}"
        
        soup = BeautifulSoup(r.text, 'html.parser')
        matches = []
        
        # PredictZ má zápasy v blocích. Musíme najít kontejnery.
        # Hledáme všechny řádky s třídou "ptable-row"
        rows = soup.find_all("div", class_="ptable-row")
        
        current_league = "Ostatní"
        
        for row in rows:
            try:
                # 1. Zkusíme najít jména týmů
                home_div = row.find("div", class_="ptable-home")
                away_div = row.find("div", class_="ptable-away")
                
                # Pokud řádek nemá týmy, může to být hlavička ligy
                if not home_div or not away_div:
                    # Zkusíme zjistit, jestli to není název ligy
                    text = row.get_text(strip=True)
                    if len(text) > 3 and not any(char.isdigit() for char in text):
                        current_league = text
                    continue

                home = home_div.get_text(strip=True)
                away = away_div.get_text(strip=True)
                
                # Ochrana proti prázdným názvům
                if not home or not away: continue

                # 2. Zkusíme najít předpovídané skóre
                score_div = row.find("div", class_="ptable-score")
                pred_score = score_div.get_text(strip=True) if score_div else ""
                
                # 3. Vypočítáme TIP z předpovídaného skóre (Spolehlivější než číst text)
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
                    except:
                        pass # Pokud skóre není čitelné (např. "?-?")
                
                # Pokud se nepodařilo určit tip ze skóre, zkusíme textový tip
                if tip_code == "":
                    result_div = row.find("div", class_="ptable-result")
                    if result_div:
                        res_text = result_div.get_text(strip=True).lower()
                        if "home" in res_text: tip_code = "1"; tip = f"Výhra {home}"
                        elif "away" in res_text: tip_code = "2"; tip = f"Výhra {away}"
                        elif "draw" in res_text: tip_code = "0"; tip = "Remíza"

                # Pokud stále nemáme tip, přeskočíme (nechceme zobrazovat "nan")
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
st.title("⚽ Fotbalový Přehled (PredictZ)")
st.caption("Čistá data, žádné chyby, seskupeno podle lig.")

# Výběr dne
day_sel = st.radio("Vyber den:", ["Dnes", "Zítra"], horizontal=True)
day_param = "today" if day_sel == "Dnes" else "tomorrow"

with st.spinner("Stahuji a čistím data..."):
    data, error = scrape_predictz_robust(day_param)

if error:
    st.error(f"Chyba: {error}")
elif not data:
    st.warning("Nebyly nalezeny žádné zápasy.")
else:
    df = pd.DataFrame(data)
    
    # --- FILTRY ---
    col_search, col_tip = st.columns(2)
    with col_search:
        search = st.text_input("Hledat tým nebo ligu:")
    with col_tip:
        filter_tip = st.multiselect("Filtrovat tip:", ["Výhra Domácích (1)", "Remíza (0)", "Výhra Hostů (2)"], default=["Výhra Domácích (1)", "Výhra Hostů (2)"])
    
    # Aplikace filtrů
    if search:
        df = df[df["Liga"].str.contains(search, case=False) | df["Domácí"].str.contains(search, case=False) | df["Hosté"].str.contains(search, case=False)]
    
    # Filtr podle typu sázky
    codes_allowed = []
    if "Výhra Domácích (1)" in filter_tip: codes_allowed.append("1")
    if "Remíza (0)" in filter_tip: codes_allowed.append("0")
    if "Výhra Hostů (2)" in filter_tip: codes_allowed.append("2")
    
    df = df[df["Kód"].isin(codes_allowed)]
    
    # --- ZOBRAZENÍ PODLE LIG ---
    # Získáme unikátní ligy
    ligy = df["Liga"].unique()
    
    st.success(f"Zobrazeno {len(df)} zápasů v {len(ligy)} ligách.")
    
    for liga in ligy:
        # Zápasy v dané lize
        league_matches = df[df["Liga"] == liga]
        
        # Vytvoříme kontejner pro ligu
        with st.expander(f"🏆 {liga} ({len(league_matches)} zápasů)", expanded=True):
            for idx, row in league_matches.iterrows():
                c1, c2, c3, c4 = st.columns([3, 1, 3, 2])
                
                with c1:
                    st.markdown(f"<div style='text-align:right; font-weight:bold'>{row['Domácí']}</div>", unsafe_allow_html=True)
                
                with c2:
                    st.markdown(f"<div style='text-align:center; background-color:#f0f2f6; border-radius:5px'>{row['Skóre']}</div>", unsafe_allow_html=True)
                
                with c3:
                    st.markdown(f"<div style='text-align:left; font-weight:bold'>{row['Hosté']}</div>", unsafe_allow_html=True)
                
                with c4:
                    # Barva tipu
                    color = "green" if row["Kód"] == "1" else ("red" if row["Kód"] == "2" else "orange")
                    st.markdown(f":{color}[**{row['Tip']}**]")
