import streamlit as st
import pandas as pd
import cloudscraper
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Betting Multi-Source", layout="wide")

# ==============================================================================\n# 1. ZDROJ A: VITISPORT (Nejlepší data, ale občas blokuje)\n# ==============================================================================\n
@st.cache_data(ttl=1800)
def scrape_vitisport(day="today"):
    # day: "today" nebo "tomorrow"
    base_url = "https://www.vitisport.cz/index.php?g=fotbal&lang=cs"
    if day == "tomorrow":
        base_url += "&p=1"
        
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(base_url)
        if r.status_code != 200: return None, f"VitiSport Error: {r.status_code}"
        
        dfs = pd.read_html(r.text)
        if not dfs: return None, "VitiSport: Žádná tabulka"
        
        main_df = max(dfs, key=len).astype(str)
        matches = []
        current_league = "Ostatní"
        
        for idx, row in main_df.iterrows():
            try:
                col0 = str(row.iloc[0])
                col1 = str(row.iloc[1])
                
                # Detekce ligy
                if len(col0) > 2 and ("nan" in str(row.iloc[2]).lower() or col1 == col0):
                    current_league = col0
                    continue
                
                # Detekce zápasu
                if ":" in col0 and len(col1) > 1:
                    if "Domácí" in col1 or "Čas" in col0: continue
                    
                    # Hledání procent (sloupce s čísly > 10)
                    probs = []
                    for val in row.iloc[5:].values:
                        try:
                            v = float(str(val).replace("%", ""))
                            if 10 <= v <= 100: probs.append(v)
                        except: pass
                    
                    prob_text = ""
                    if len(probs) >= 3:
                        prob_text = f"1: {int(probs[0])}% | 0: {int(probs[1])}% | 2: {int(probs[2])}%"
                    
                    matches.append({
                        "Zdroj": "VitiSport",
                        "Liga": current_league,
                        "Čas": col0,
                        "Zápas": f"{col1} vs {str(row.iloc[2])}",
                        "Tip": str(row.iloc[4]),
                        "Info": prob_text
                    })
            except: continue
            
        return matches, None
    except Exception as e:
        return None, str(e)

# ==============================================================================\n# 2. ZDROJ B: SPORTYTRADER (Záloha, velmi stabilní)\n# ==============================================================================\n
@st.cache_data(ttl=1800)
def scrape_sportytrader(day="today"):
    # SportyTrader má URL: /betting-tips/football/today/ nebo /tomorrow/
    base_url = "https://www.sportytrader.com/en/betting-tips/football/"
    url = base_url + ("tomorrow/" if day == "tomorrow" else "today/")
    
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(url)
        if r.status_code != 200: return None, f"SportyTrader Error: {r.status_code}"
        
        soup = BeautifulSoup(r.text, 'html.parser')
        matches = []
        
        # Hledáme karty zápasů
        cards = soup.find_all("div", class_="cursor-pointer")
        
        for card in cards:
            try:
                # Čas
                time_span = card.find("span", class_="flex-none")
                time_str = time_span.get_text(strip=True) if time_span else "??"
                
                # Týmy
                teams = card.find_all("span", class_="font-medium")
                if len(teams) < 2: continue
                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)
                
                # Tip
                tip_tag = card.find("span", class_="h-full")
                tip_text = tip_tag.get_text(strip=True) if tip_tag else "N/A"
                
                # Liga (někdy je v breadcrumbs nebo nadpisu, tady zjednodušíme)
                liga = "Svět / Evropa"
                
                matches.append({
                    "Zdroj": "SportyTrader",
                    "Liga": liga,
                    "Čas": time_str,
                    "Zápas": f"{home} vs {away}",
                    "Tip": tip_text,
                    "Info": "Doporučená sázka"
                })
            except: continue
            
        return matches, None
    except Exception as e:
        return None, str(e)

# ==============================================================================\n# 3. MANUÁLNÍ KALKULAČKA (Poslední záchrana)\n# ==============================================================================\n
def calculate_manual_prediction(elo_h, elo_a):
    elo_diff = elo_h - elo_a + 100
    exp_xg_h = max(0.2, 1.45 + (elo_diff / 500))
    exp_xg_a = max(0.2, 1.15 - (elo_diff / 500))
    
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    
    return prob_h, prob_d, prob_a, matrix

INTERNAL_DB = {
    "Man City": 2050, "Liverpool": 2000, "Arsenal": 1980, "Real Madrid": 1990,
    "Barcelona": 1950, "Bayern": 1960, "Leverkusen": 1920, "Inter": 1940,
    "Sparta Praha": 1680, "Slavia Praha": 1690, "Plzeň": 1620, "Baník Ostrava": 1500
}

# ==============================================================================\n# 4. UI APLIKACE\n# ==============================================================================\n
st.title("🛡️ Multi-Source Betting Hub")
st.caption("Automaticky přepíná zdroje dat, aby vždy zobrazil výsledky.")

# TABS
tab_live, tab_calc = st.tabs(["📅 Live Predikce (Auto)", "🧮 Manuální Kalkulačka"])

# --- TAB 1: LIVE DATA ---
with tab_live:
    col_day, col_filter = st.columns(2)
    with col_day:
        day_sel = st.radio("Vyber den:", ["Dnes", "Zítra"], horizontal=True)
        day_param = "today" if day_sel == "Dnes" else "tomorrow"
        
    # LOGIKA PŘEPÍNÁNÍ ZDROJŮ
    matches = []
    source_used = ""
    error_msg = ""
    
    with st.spinner("Zkouším VitiSport..."):
        matches, err = scrape_vitisport(day_param)
        if matches:
            source_used = "VitiSport (Nejlepší data)"
        else:
            error_msg += f"VitiSport selhal ({err}). "
            
    if not matches:
        with st.spinner("VitiSport neodpovídá. Přepínám na SportyTrader..."):
            matches, err = scrape_sportytrader(day_param)
            if matches:
                source_used = "SportyTrader (Záložní zdroj)"
            else:
                error_msg += f"SportyTrader selhal ({err})."

    # VÝPIS VÝSLEDKŮ
    if matches:
        st.success(f"✅ Data načtena ze zdroje: **{source_used}**")
        st.info(f"Nalezeno {len(matches)} zápasů.")
        
        df = pd.DataFrame(matches)
        
        # Filtr
        with col_filter:
            search = st.text_input("Hledat tým nebo ligu:")
            
        if search:
            df = df[df["Zápas"].str.contains(search, case=False) | df["Liga"].str.contains(search, case=False)]
            
        # Zobrazení
        for idx, row in df.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.caption(row["Liga"])
                    st.write(f"**{row['Zápas']}**")
                    st.caption(row["Čas"])
                with c2:
                    # Formátování tipu
                    tip = row["Tip"]
                    color = "gray"
                    if tip in ["1", "Home"]: color = "green"; tip = "Výhra Domácí"
                    elif tip in ["2", "Away"]: color = "red"; tip = "Výhra Hosté"
                    elif tip in ["0", "X", "Draw"]: color = "orange"; tip = "Remíza"
                    elif "Over" in tip: color = "blue"
                    
                    st.markdown(f"#### :{color}[{tip}]")
                with c3:
                    st.write(row["Info"])
                st.markdown("---")
    else:
        st.error("❌ Všechny zdroje selhaly.")
        st.write(f"Detaily chyb: {error_msg}")
        st.warning("Použij prosím záložku 'Manuální Kalkulačka'.")

# --- TAB 2: KALKULAČKA ---
with tab_calc:
    st.header("🧮 Nezničitelná Kalkulačka")
    c1, c2 = st.columns(2)
    teams = sorted(list(INTERNAL_DB.keys()))
    
    with c1: t1 = st.selectbox("Domácí:", teams, index=0)
    with c2: t2 = st.selectbox("Hosté:", teams, index=1)
    
    if st.button("Analyzovat"):
        ph, pd_raw, pa, matrix = calculate_manual_prediction(INTERNAL_DB[t1], INTERNAL_DB[t2])
        
        st.subheader("Výsledek")
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Výhra {t1}", f"{ph*100:.1f}%", f"Kurz: {1/ph:.2f}")
        m2.metric("Remíza", f"{pd_raw*100:.1f}%", f"Kurz: {1/pd_raw:.2f}")
        m3.metric(f"Výhra {t2}", f"{pa*100:.1f}%", f"Kurz: {1/pa:.2f}")
        
        fig, ax = plt.subplots(figsize=(6, 3))
        sns.heatmap(matrix, annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
        st.pyplot(fig)
