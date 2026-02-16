import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import io

st.set_page_config(page_title="Betting Auto-Pilot v31", layout="wide")

# ==============================================================================\n# 1. MATEMATICKÉ MODELY (Jádro)\n# ==============================================================================\n
def calculate_probs(elo_h, elo_a):
    # Výhra (Elo)
    elo_diff = elo_h - elo_a + 100 
    prob_h_win = 1 / (10**(-elo_diff/400) + 1)
    prob_a_win = 1 - prob_h_win
    
    # Korekce na remízu
    prob_draw = 0.25 
    if abs(prob_h_win - 0.5) < 0.1: prob_draw = 0.30 
    
    real_h = prob_h_win * (1 - prob_draw)
    real_a = prob_a_win * (1 - prob_draw)
    
    # Góly (Poisson)
    exp_xg_h = max(0.5, 1.45 + (elo_diff / 500))
    exp_xg_a = max(0.5, 1.15 - (elo_diff / 500))
    
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    prob_over_25 = 0
    prob_btts = 0
    for i in range(max_g):
        for j in range(max_g):
            if i + j > 2.5: prob_over_25 += matrix[i, j]
            if i > 0 and j > 0: prob_btts += matrix[i, j]
            
    return {
        "1": real_h, "0": prob_draw, "2": real_a,
        "Over 2.5": prob_over_25, "BTTS Yes": prob_btts,
        "xG_Home": exp_xg_h, "xG_Away": exp_xg_a, "Matrix": matrix
    }

def pick_best_bet(probs):
    candidates = [
        ("Výhra Domácích (1)", probs["1"]),
        ("Výhra Hostů (2)", probs["2"]),
        ("Over 2.5 Gólů", probs["Over 2.5"]),
        ("Oba dají gól (BTTS)", probs["BTTS Yes"])
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0], candidates[0][1]

# ==============================================================================\n# 2. UI APLIKACE\n# ==============================================================================\n
st.title("🤖 Betting Auto-Pilot (Manual Data)")

# --- SEKCE PRO NAHRÁNÍ DAT ---
st.info("ℹ️ Server ClubElo blokuje přímé stahování. Pro získání aktuálních dat postupuj takto:")

col_inst, col_upload = st.columns([1, 2])

with col_inst:
    st.markdown("""
    1. Klikni na tento odkaz: **[api.clubelo.com/Fixtures](http://api.clubelo.com/Fixtures)**
    2. Otevře se ti stránka s textem.
    3. Klikni pravým tlačítkem a dej **"Uložit jako..."** (ulož to jako `Fixtures.csv`).
    4. Tento soubor nahraj vedle 👉
    """)

with col_upload:
    uploaded_file = st.file_uploader("Nahraj soubor Fixtures.csv zde:", type=["csv", "txt"])

# --- ZPRACOVÁNÍ DAT ---
df = None

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        df['DateObj'] = pd.to_datetime(df['Date'])
        st.success(f"✅ Úspěšně načteno {len(df)} zápasů z tvého souboru!")
    except Exception as e:
        st.error(f"Chyba při čtení souboru: {e}")
else:
    # DEMO DATA (Pokud nic nenahrál)
    st.warning("⚠️ Zatím jsi nic nenahrál. Zobrazuji DEMO data.")
    dnes = datetime.now()
    data = {
        "Date": [dnes.strftime("%Y-%m-%d")] * 5,
        "Country": ["ENG", "ESP", "ITA", "GER", "FRA"],
        "Home": ["Manchester City", "Real Madrid", "Inter", "Bayern", "PSG"],
        "Away": ["Liverpool", "Barcelona", "Milan", "Dortmund", "Lyon"],
        "EloHome": [2050, 1980, 1950, 1920, 1850],
        "EloAway": [2000, 1970, 1940, 1880, 1800]
    }
    df = pd.DataFrame(data)
    df['DateObj'] = pd.to_datetime(df['Date'])

# --- VÝPOČTY A ZOBRAZENÍ ---
if df is not None:
    # Filtry
    dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Pokud je to Demo, nefiltrujeme podle data
    if uploaded_file is not None:
        limit = dnes + timedelta(days=5) 
        mask = (df['DateObj'] >= dnes) & (df['DateObj'] <= limit)
        upcoming = df[mask].copy()
    else:
        upcoming = df.copy()
    
    if upcoming.empty:
        st.warning("V nahraném souboru nejsou žádné zápasy pro nadcházející dny.")
    else:
        results = []
        
        for i, (idx, row) in enumerate(upcoming.iterrows()):
            try:
                home, away = row['Home'], row['Away']
                elo_h = row.get('EloHome')
                elo_a = row.get('EloAway')
                
                if pd.isna(elo_h) or pd.isna(elo_a): continue

                probs = calculate_probs(elo_h, elo_a)
                bet_name, confidence = pick_best_bet(probs)
                fair_odd = 1 / confidence if confidence > 0 else 0
                
                results.append({
                    "Datum": row['DateObj'].strftime("%d.%m."),
                    "Soutěž": row.get('Country', 'EU'),
                    "Zápas": f"{home} vs {away}",
                    "DOPORUČENÁ SÁZKA": bet_name,
                    "Důvěra": confidence * 100,
                    "Férový kurz": fair_odd,
                    "Stats": probs,
                    "Domácí": home, "Hosté": away
                })
            except: continue
        
        df_res = pd.DataFrame(results)
        
        if not df_res.empty:
            # TABS
            tab1, tab2 = st.tabs(["📋 Seznam Tipů", "🔬 Detailní Analyzátor"])
            
            with tab1:
                st.subheader("🔥 TOP TIPY (Seřazeno podle důvěry)")
                df_show = df_res.sort_values(by="Důvěra", ascending=False)
                
                for idx, match in df_show.iterrows():
                    with st.container():
                        c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
                        with c1: st.write(f"**{match['Datum']}**"); st.caption(match['Soutěž'])
                        with c2: st.write(f"**{match['Zápas']}**")
                        with c3: 
                            st.write(f"**{match['DOPORUČENÁ SÁZKA']}**")
                            st.progress(match['Důvěra']/100)
                        with c4: st.metric("Kurz", f"{match['Férový kurz']:.2f}")
                        st.markdown("---")

            with tab2:
                st.subheader("🔬 Laboratoř")
                selected_match = st.selectbox("Vyber zápas:", df_res['Zápas'].unique())
                match_data = df_res[df_res['Zápas'] == selected_match].iloc[0]
                stats = match_data['Stats']
                
                c1, c2 = st.columns(2)
                with c1:
                    st.metric(f"xG {match_data['Domácí']}", f"{stats['xG_Home']:.2f}")
                    st.metric(f"xG {match_data['Hosté']}", f"{stats['xG_Away']:.2f}")
                with c2:
                    st.write("Pravděpodobnosti:")
                    st.write(f"1: {stats['1']*100:.1f}%")
                    st.write(f"0: {stats['0']*100:.1f}%")
                    st.write(f"2: {stats['2']*100:.1f}%")
                
                fig, ax = plt.subplots(figsize=(6, 4))
                sns.heatmap(stats['Matrix'], annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
                st.pyplot(fig)

        else: st.warning("Nepodařilo se vypočítat predikce.")
