import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta

st.set_page_config(page_title="Fotmob Pro v38", layout="wide")

# ==============================================================================
# 1. KONFIGURACE A VESTAVĚNÁ DATA (ZÁCHRANA)
# ==============================================================================

# Pokud API selže, použijeme tuto databázi pro manuální kalkulačku
INTERNAL_DB = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Man City": 2050, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Liverpool": 2000, "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Arsenal": 1980,
    "🇪🇸 Real Madrid": 1990, "🇪🇸 Barcelona": 1950, "🇪🇸 Atletico": 1880,
    "🇩🇪 Bayern": 1960, "🇩🇪 Leverkusen": 1920, "🇩🇪 Dortmund": 1850,
    "🇮🇹 Inter": 1940, "🇮🇹 Juventus": 1860, "🇮🇹 Milan": 1850,
    "🇫🇷 PSG": 1880, "🇫🇷 Monaco": 1780,
    "🇨🇿 Sparta Praha": 1680, "🇨🇿 Slavia Praha": 1690, "🇨🇿 Plzeň": 1620,
    "🇵🇹 Benfica": 1810, "🇵🇹 Sporting": 1800, "🇵🇹 Porto": 1790,
    "🇳🇱 PSV": 1800, "🇳🇱 Feyenoord": 1780
}

LEAGUES_ID = {
    "🇬🇧 Premier League": 47, "🇬🇧 Championship": 48,
    "🇪🇸 La Liga": 87, "🇩🇪 Bundesliga": 54, "🇮🇹 Serie A": 55,
    "🇫🇷 Ligue 1": 53, "🇨🇿 Fortuna Liga": 66, "🇵🇱 Ekstraklasa": 69,
    "🇳🇱 Eredivisie": 57, "🇵🇹 Liga Portugal": 61, "🇹🇷 Super Lig": 71,
    "🇪🇺 Liga Mistrů": 42, "🇪🇺 Evropská Liga": 73
}

# ==============================================================================
# 2. NOVÉ API VOLÁNÍ (PRODUKČNÍ ENDPOINT)
# ==============================================================================

@st.cache_data(ttl=300)
def get_fotmob_data(date_str):
    # POUŽÍVÁME NOVÝ ENDPOINT (pub.fotmob.com)
    url = f"https://pub.fotmob.com/prod/pub/api/matches?date={date_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200: return None, f"Chyba {r.status_code}"
        return r.json(), None
    except Exception as e:
        return None, str(e)

def parse_fotmob(json_data, league_filter_id):
    matches = []
    if not json_data or "leagues" not in json_data: return []
    
    for league in json_data["leagues"]:
        # Filtr ligy
        if league_filter_id != "Vše" and league["id"] != league_filter_id: continue
        # Pokud Vše, bereme jen ty z našeho seznamu
        if league_filter_id == "Vše" and league["id"] not in LEAGUES_ID.values(): continue
        
        league_name = league["name"]
        ccode = league["ccode"]
        
        for m in league["matches"]:
            try:
                home = m["home"]["name"]
                away = m["away"]["name"]
                m_time = m["time"]
                status = m["status"]
                
                # Skóre / Čas
                score_str = status.get("scoreStr", "vs")
                if status.get("started") and not status.get("finished"):
                    live_time = status.get("liveTime", "Live")
                    score_str = f"{live_time} | {score_str}"
                
                matches.append({
                    "Liga": f"{ccode} {league_name}",
                    "Čas": m_time,
                    "Domácí": home,
                    "Hosté": away,
                    "Skóre": score_str,
                    "Id": m["id"]
                })
            except: continue
    return matches

# ==============================================================================
# 3. MATEMATICKÝ MODEL (POISSON)
# ==============================================================================

def calculate_prediction(elo_h, elo_a):
    elo_diff = elo_h - elo_a + 100 # Domácí výhoda
    
    # xG Model
    xg_h = max(0.5, 1.45 + (elo_diff / 500))
    xg_a = max(0.5, 1.15 - (elo_diff / 500))
    
    # Poisson
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
            
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    
    prob_over_25 = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            
    return {
        "1": prob_h, "0": prob_d, "2": prob_a,
        "Over 2.5": prob_over_25,
        "xG_H": xg_h, "xG_A": xg_a,
        "Matrix": matrix
    }

# ==============================================================================
# 4. UI APLIKACE
# ==============================================================================

st.title("⚡ Fotmob Pro Analyst")

# TABS
tab1, tab2 = st.tabs(["📅 Live Rozpis (API)", "🧮 Ruční Kalkulačka (Vždy funkční)"])

# --- TAB 1: API DATA ---
with tab1:
    c1, c2 = st.columns([2, 1])
    with c1: league_sel = st.selectbox("Vyber ligu:", ["Vše"] + list(LEAGUES_ID.keys()))
    with c2: day_sel = st.selectbox("Den:", ["Dnes", "Zítra", "Včera"])
    
    target_date = datetime.now()
    if day_sel == "Zítra": target_date += timedelta(days=1)
    elif day_sel == "Včera": target_date -= timedelta(days=1)
    date_str = target_date.strftime("%Y%m%d")
    
    lid = LEAGUES_ID[league_sel] if league_sel != "Vše" else "Vše"
    
    with st.spinner("Stahuji data z nového endpointu..."):
        raw, err = get_fotmob_data(date_str)
        
    if err:
        st.error(f"API Error: {err}")
        st.info("⚠️ Pokud API nejde, přepni se na záložku 'Ruční Kalkulačka' a spočítej si zápas sám.")
    else:
        matches = parse_fotmob(raw, lid)
        if not matches:
            st.warning("Žádné zápasy v této lize.")
        else:
            st.success(f"Nalezeno {len(matches)} zápasů.")
            for m in matches:
                with st.container():
                    c1, c2, c3, c4 = st.columns([1, 3, 1, 3])
                    with c1: st.caption(m["Liga"]); st.write(m["Čas"])
                    with c2: st.markdown(f"<div style='text-align:right'><b>{m['Domácí']}</b></div>", unsafe_allow_html=True)
                    with c3: st.markdown(f"<div style='text-align:center; background:#eee; border-radius:4px'>{m['Skóre']}</div>", unsafe_allow_html=True)
                    with c4: st.markdown(f"<div style='text-align:left'><b>{m['Hosté']}</b></div>", unsafe_allow_html=True)
                    
                    # Tlačítko pro rychlou analýzu (použije fuzzy match z DB)
                    if st.button("Analyzovat tento zápas", key=m["Id"]):
                        # Zkusíme najít Elo v naší DB
                        elo_h = 1500 # Default
                        elo_a = 1500
                        
                        # Jednoduché hledání v DB
                        for name, elo in INTERNAL_DB.items():
                            if name.split(" ")[1] in m["Domácí"]: elo_h = elo
                            if name.split(" ")[1] in m["Hosté"]: elo_a = elo
                        
                        res = calculate_prediction(elo_h, elo_a)
                        
                        st.info(f"Odhadovaná síla: {elo_h} vs {elo_a}")
                        cols = st.columns(3)
                        cols[0].metric("Výhra D", f"{res['1']*100:.0f}%")
                        cols[1].metric("Remíza", f"{res['0']*100:.0f}%")
                        cols[2].metric("Výhra H", f"{res['2']*100:.0f}%")
                        st.progress(res['1'])
                st.markdown("---")

# --- TAB 2: KALKULAČKA ---
with tab2:
    st.header("🧮 Nezničitelná Kalkulačka")
    st.write("Vyber si týmy z databáze a model vypočítá predikci, i když API nefunguje.")
    
    col_h, col_a = st.columns(2)
    
    teams_list = sorted(list(INTERNAL_DB.keys()))
    
    with col_h:
        t1 = st.selectbox("Domácí tým:", teams_list, index=0)
    with col_a:
        t2 = st.selectbox("Hostující tým:", teams_list, index=1)
        
    if st.button("Vypočítat Predikci"):
        elo1 = INTERNAL_DB[t1]
        elo2 = INTERNAL_DB[t2]
        
        res = calculate_prediction(elo1, elo2)
        
        st.subheader("Výsledek Analýzy")
        
        # 1. Hlavní tip
        best_prob = max(res['1'], res['0'], res['2'])
        if res['1'] == best_prob: tip = f"Výhra {t1}"; color="green"
        elif res['2'] == best_prob: tip = f"Výhra {t2}"; color="red"
        else: tip = "Remíza"; color="orange"
        
        st.markdown(f"### Doporučení: :{color}[{tip}]")
        
        # 2. Metriky
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("1 (Domácí)", f"{res['1']*100:.1f}%", f"Kurz: {1/res['1']:.2f}")
        m2.metric("0 (Remíza)", f"{res['0']*100:.1f}%", f"Kurz: {1/res['0']:.2f}")
        m3.metric("2 (Hosté)", f"{res['2']*100:.1f}%", f"Kurz: {1/res['2']:.2f}")
        m4.metric("Over 2.5", f"{res['Over 2.5']*100:.1f}%", f"Kurz: {1/res['Over 2.5']:.2f}")
        
        # 3. xG
        st.write(f"**Očekávané góly (xG):** {res['xG_H']:.2f} - {res['xG_A']:.2f}")
        
        # 4. Heatmapa
        fig, ax = plt.subplots(figsize=(6, 3))
        sns.heatmap(res['Matrix'], annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
        ax.set_xlabel(t2)
        ax.set_ylabel(t1)
        st.pyplot(fig)
