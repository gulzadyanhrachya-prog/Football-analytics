import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="Fortuna Pro Analyst", layout="wide")

# ==============================================================================\n# 1. NAČÍTÁNÍ DAT (ClubElo)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_data():
    url_fixtures = "http://api.clubelo.com/Fixtures"
    url_ratings = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    
    df_fix, df_elo = None, None
    
    try:
        s_fix = requests.get(url_fixtures).content
        df_fix = pd.read_csv(io.StringIO(s_fix.decode('utf-8')))
        df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
    except: pass
    
    try:
        s_elo = requests.get(url_ratings).content
        df_elo = pd.read_csv(io.StringIO(s_elo.decode('utf-8')))
    except: pass
    
    return df_fix, df_elo

# ==============================================================================\n# 2. MATEMATICKÉ MODELY (Rozšířené o Fortuna trhy)\n# ==============================================================================\n
def calculate_match_stats(elo_h, elo_a):
    # 1. Elo Probabilities
    elo_diff = elo_h - elo_a + 100 
    prob_h_win = 1 / (10**(-elo_diff/400) + 1)
    prob_a_win = 1 - prob_h_win
    
    # Korekce na remízu
    prob_draw = 0.24 
    if abs(prob_h_win - 0.5) < 0.15: prob_draw = 0.29
    
    real_h = prob_h_win * (1 - prob_draw)
    real_a = prob_a_win * (1 - prob_draw)
    
    # 2. xG Model
    base_xg = 1.35
    xg_diff = elo_diff / 500
    exp_xg_h = max(0.2, base_xg + xg_diff)
    exp_xg_a = max(0.2, base_xg - xg_diff)
    
    # 3. Poisson Matrix
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    # 4. Výpočet trhů
    prob_over_25 = 0
    prob_btts = 0
    prob_h_handicap = 0 # Home -1.5
    prob_a_handicap = 0 # Away -1.5
    
    most_likely_score = ""
    max_score_prob = 0
    
    for i in range(max_g):
        for j in range(max_g):
            p = matrix[i, j]
            if i + j > 2.5: prob_over_25 += p
            if i > 0 and j > 0: prob_btts += p
            if i > j + 1.5: prob_h_handicap += p
            if j > i + 1.5: prob_a_handicap += p
            
            if p > max_score_prob:
                max_score_prob = p
                most_likely_score = f"{i}:{j}"
    
    # Sázka bez remízy (DNB)
    # P(Home) / (P(Home) + P(Away))
    prob_dnb_h = real_h / (real_h + real_a)
    prob_dnb_a = real_a / (real_h + real_a)

    return {
        "1": real_h, "0": prob_draw, "2": real_a,
        "10": real_h + prob_draw, "02": real_a + prob_draw,
        "SBR 1": prob_dnb_h, "SBR 2": prob_dnb_a,
        "Over 2.5": prob_over_25, "Under 2.5": 1 - prob_over_25,
        "BTTS Ano": prob_btts, "BTTS Ne": 1 - prob_btts,
        "Hcp -1.5 (1)": prob_h_handicap, "Hcp -1.5 (2)": prob_a_handicap,
        "Přesný výsledek": max_score_prob,
        "Score_Txt": most_likely_score,
        "xG_Home": exp_xg_h, "xG_Away": exp_xg_a, "Matrix": matrix
    }

def get_best_bet_filtered(stats, allowed_types):
    """
    Vybere nejlepší sázku pouze z povolených typů.
    """
    candidates = []
    
    # Hlavní
    if "Zápas (1/0/2)" in allowed_types:
        candidates.append(("Výhra Domácích (1)", stats["1"]))
        candidates.append(("Výhra Hostů (2)", stats["2"]))
        candidates.append(("Remíza (0)", stats["0"]))
        
    # Dvojitá
    if "Dvojitá šance (10/02)" in allowed_types:
        candidates.append(("Neprohra Domácích (10)", stats["10"]))
        candidates.append(("Neprohra Hostů (02)", stats["02"]))
        
    # SBR
    if "Sázka bez remízy (SBR)" in allowed_types:
        candidates.append(("SBR Domácí (1)", stats["SBR 1"]))
        candidates.append(("SBR Hosté (2)", stats["SBR 2"]))
        
    # Góly
    if "Počet gólů (Over/Under)" in allowed_types:
        candidates.append(("Over 2.5 Gólů", stats["Over 2.5"]))
        candidates.append(("Under 2.5 Gólů", stats["Under 2.5"]))
        
    # BTTS
    if "Oba dají gól (BTTS)" in allowed_types:
        candidates.append(("BTTS Ano", stats["BTTS Ano"]))
        candidates.append(("BTTS Ne", stats["BTTS Ne"]))
        
    # Handicap
    if "Handicap (-1.5)" in allowed_types:
        candidates.append(("Handicap Domácí -1.5", stats["Hcp -1.5 (1)"]))
        candidates.append(("Handicap Hosté -1.5", stats["Hcp -1.5 (2)"]))
        
    # Přesný výsledek
    if "Přesný výsledek" in allowed_types:
        candidates.append((f"Skóre {stats['Score_Txt']}", stats["Přesný výsledek"]))

    if not candidates: return "Žádný filtr", 0

    # Seřadíme podle pravděpodobnosti
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    # Logika pro výběr "hodnotné" sázky, ne jen té s největší pravděpodobností (protože 10 je vždy 80%+)
    # Pokud je vybrána "Neprohra" a má pod 70%, raději ji nebrat.
    
    return candidates[0][0], candidates[0][1]

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("⚽ Fortuna Pro Analyst")
st.markdown("Pokročilá filtrace zápasů a typů sázek.")

with st.spinner("Načítám data..."):
    df_fix, df_elo = get_data()

if df_fix is None or df_elo is None:
    st.error("Chyba dat.")
    st.stop()

# --- SIDEBAR FILTRY ---
st.sidebar.header("📅 Kdy se hraje?")
dnes = datetime.now().date()

# 1. Filtr Dne
date_option = st.sidebar.radio(
    "Vyber den:",
    ["Dnes", "Zítra", "Víkend (So+Ne)", "Vše (3 dny)", "Konkrétní datum"]
)

target_dates = []
if date_option == "Dnes":
    target_dates = [dnes]
elif date_option == "Zítra":
    target_dates = [dnes + timedelta(days=1)]
elif date_option == "Víkend (So+Ne)":
    # Najdeme nejbližší sobotu a neděli
    days_ahead = 5 - dnes.weekday() # 5 = Sobota
    if days_ahead < 0: days_ahead += 7
    sobota = dnes + timedelta(days=days_ahead)
    nedele = sobota + timedelta(days=1)
    target_dates = [sobota, nedele]
elif date_option == "Vše (3 dny)":
    target_dates = [dnes, dnes + timedelta(days=1), dnes + timedelta(days=2)]
else:
    custom_date = st.sidebar.date_input("Vyber datum:", dnes)
    target_dates = [custom_date]

# 2. Filtr Ligy
st.sidebar.header("🌍 Kde se hraje?")
all_countries = sorted(df_fix['Country'].unique().astype(str))
selected_country = st.sidebar.selectbox("Země / Soutěž:", ["Všechny"] + all_countries)

# 3. Filtr Typu Sázky (Fortuna)
st.sidebar.header("💰 Na co chceš sázet?")
bet_types = st.sidebar.multiselect(
    "Povolené typy sázek:",
    [
        "Zápas (1/0/2)",
        "Dvojitá šance (10/02)",
        "Sázka bez remízy (SBR)",
        "Počet gólů (Over/Under)",
        "Oba dají gól (BTTS)",
        "Handicap (-1.5)",
        "Přesný výsledek"
    ],
    default=["Zápas (1/0/2)", "Počet gólů (Over/Under)", "Sázka bez remízy (SBR)"]
)

# 4. Filtr Důvěry
min_confidence = st.sidebar.slider("Minimální důvěra modelu (%):", 50, 95, 60)

# --- ZPRACOVÁNÍ DAT ---
# Filtr data
df_fix['JustDate'] = df_fix['DateObj'].dt.date
mask_date = df_fix['JustDate'].isin(target_dates)
upcoming = df_fix[mask_date].copy()

# Filtr země
if selected_country != "Všechny":
    upcoming = upcoming[upcoming['Country'] == selected_country]

elo_dict = df_elo.set_index('Club')['Elo'].to_dict()
analyzed_matches = []

# Hlavní smyčka
for idx, row in upcoming.iterrows():
    try:
        home, away = row['Home'], row['Away']
        elo_h = row.get('EloHome')
        elo_a = row.get('EloAway')
        
        if pd.isna(elo_h): elo_h = elo_dict.get(home)
        if pd.isna(elo_a): elo_a = elo_dict.get(away)
        
        if elo_h is None or elo_a is None: continue 
        
        # Výpočet
        stats = calculate_match_stats(elo_h, elo_a)
        
        # Výběr nejlepší sázky podle filtrů
        best_bet, confidence = get_best_bet_filtered(stats, bet_types)
        
        if confidence * 100 < min_confidence: continue
        
        analyzed_matches.append({
            "Datum": row['DateObj'],
            "Soutěž": row.get('Country', 'EU'),
            "Domácí": home,
            "Hosté": away,
            "Tip": best_bet,
            "Důvěra": confidence,
            "Férový kurz": 1/confidence if confidence > 0 else 0,
            "Stats": stats
        })
    except: continue

# --- ZOBRAZENÍ VÝSLEDKŮ ---
if not analyzed_matches:
    st.warning(f"Pro vybraný den ({date_option}) a filtry nebyly nalezeny žádné vhodné sázky.")
else:
    df_res = pd.DataFrame(analyzed_matches).sort_values(by="Důvěra", ascending=False)
    st.success(f"Nalezeno {len(df_res)} příležitostí.")
    
    for idx, match in df_res.iterrows():
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
            
            with c1:
                st.caption(f"{match['Datum'].strftime('%d.%m. %H:%M')} | {match['Soutěž']}")
                st.write(f"**{match['Domácí']}**")
                st.write(f"**{match['Hosté']}**")
            
            with c2:
                st.markdown(f"#### {match['Tip']}")
                st.caption("Doporučená sázka")
                
            with c3:
                color = "normal"
                if match['Důvěra'] > 0.75: color = "off"
                st.metric("Důvěra", f"{match['Důvěra']*100:.1f} %", delta_color=color)
                
            with c4:
                st.metric("Férový kurz", f"{match['Férový kurz']:.2f}")
            
            # Detailní rozbalovátko
            with st.expander(f"📊 Detaily: {match['Domácí']} vs {match['Hosté']}"):
                s = match['Stats']
                col_a, col_b, col_c = st.columns(3)
                
                with col_a:
                    st.write("**Hlavní trhy**")
                    st.write(f"1: {s['1']*100:.0f}% (Kurz {1/s['1']:.2f})")
                    st.write(f"0: {s['0']*100:.0f}% (Kurz {1/s['0']:.2f})")
                    st.write(f"2: {s['2']*100:.0f}% (Kurz {1/s['2']:.2f})")
                
                with col_b:
                    st.write("**Góly & SBR**")
                    st.write(f"Over 2.5: {s['Over 2.5']*100:.0f}%")
                    st.write(f"BTTS Ano: {s['BTTS Ano']*100:.0f}%")
                    st.write(f"SBR 1: {s['SBR 1']*100:.0f}%")
                
                with col_c:
                    st.write("**xG & Skóre**")
                    st.write(f"xG Dom: {s['xG_Home']:.2f}")
                    st.write(f"xG Hos: {s['xG_Away']:.2f}")
                    st.write(f"Top skóre: {s['Score_Txt']}")
            
            st.markdown("---")
