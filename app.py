import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="Football Ultimate Analyst", layout="wide")

# ==============================================================================
# 1. NAČÍTÁNÍ DAT (ClubElo - Stabilní zdroj)
# ==============================================================================

@st.cache_data(ttl=3600)
def get_data():
    # A) Rozpis zápasů (Fixtures)
    url_fixtures = "http://api.clubelo.com/Fixtures"
    # B) Databáze síly týmů (Elo Ratings)
    url_ratings = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    
    df_fix, df_elo = None, None
    
    try:
        s_fix = requests.get(url_fixtures).content
        df_fix = pd.read_csv(io.StringIO(s_fix.decode('utf-8')))
        # Konverze data
        df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
    except: pass
    
    try:
        s_elo = requests.get(url_ratings).content
        df_elo = pd.read_csv(io.StringIO(s_elo.decode('utf-8')))
    except: pass
    
    return df_fix, df_elo

# ==============================================================================
# 2. MATEMATICKÉ MODELY (Jádro aplikace)
# ==============================================================================

def calculate_match_stats(elo_h, elo_a):
    """
    Vypočítá kompletní pravděpodobnosti pro zápas na základě Elo.
    Vrací slovník se všemi trhy.
    """
    # 1. Elo Probabilities (Výhra/Remíza/Prohra)
    elo_diff = elo_h - elo_a + 100 # +100 bodů výhoda domácího prostředí
    
    # Sigmoidní funkce pro výpočet šance na výhru
    prob_h_win = 1 / (10**(-elo_diff/400) + 1)
    prob_a_win = 1 - prob_h_win
    
    # Korekce na remízu (empirický model)
    # Čím jsou týmy vyrovnanější (prob blíže 0.5), tím vyšší šance na remízu
    prob_draw = 0.24 
    if abs(prob_h_win - 0.5) < 0.15: prob_draw = 0.29
    
    real_h = prob_h_win * (1 - prob_draw)
    real_a = prob_a_win * (1 - prob_draw)
    
    # 2. xG Model (Očekávané góly)
    # Průměr ligy je cca 1.35 gólu na tým. Upravujeme podle rozdílu síly.
    # Každých 100 bodů rozdílu Elo přidává/ubírá cca 0.2 xG
    base_xg = 1.35
    xg_diff = elo_diff / 500
    
    exp_xg_h = max(0.2, base_xg + xg_diff)
    exp_xg_a = max(0.2, base_xg - xg_diff)
    
    # 3. Poissonova simulace (Přesné skóre)
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
            
    # 4. Odvozené trhy z matice
    prob_over_25 = 0
    prob_btts = 0
    
    for i in range(max_g):
        for j in range(max_g):
            p = matrix[i, j]
            if i + j > 2.5: prob_over_25 += p
            if i > 0 and j > 0: prob_btts += p
            
    return {
        "1": real_h,
        "0": prob_draw,
        "2": real_a,
        "10": real_h + prob_draw,
        "02": real_a + prob_draw,
        "Over 2.5": prob_over_25,
        "Under 2.5": 1 - prob_over_25,
        "BTTS Yes": prob_btts,
        "BTTS No": 1 - prob_btts,
        "xG_Home": exp_xg_h,
        "xG_Away": exp_xg_a,
        "Matrix": matrix
    }

def get_best_bet(stats):
    """
    Najde statisticky nejpravděpodobnější sázku z daného zápasu.
    """
    candidates = [
        ("Výhra Domácích (1)", stats["1"]),
        ("Výhra Hostů (2)", stats["2"]),
        ("Neprohra Domácích (10)", stats["10"]),
        ("Neprohra Hostů (02)", stats["02"]),
        ("Over 2.5 Gólů", stats["Over 2.5"]),
        ("Under 2.5 Gólů", stats["Under 2.5"]),
        ("Oba dají gól (BTTS)", stats["BTTS Yes"])
    ]
    # Seřadíme podle pravděpodobnosti
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    # Vracíme tu nejlepší, ale ignorujeme "Neprohry", pokud jsou pod 65% (to je moc riskantní na tak nízký kurz)
    # Chceme najít balanc mezi vysokou šancí a smysluplnou sázkou
    
    best_name, best_prob = candidates[0]
    return best_name, best_prob

# ==============================================================================
# 3. UI APLIKACE
# ==============================================================================

st.title("⚽ Football Ultimate Analyst")
st.markdown("Profesionální nástroj pro analýzu fotbalových zápasů pomocí Elo ratingu a Poissonova modelu.")

# Načtení dat
with st.spinner("Skenuji evropské ligy..."):
    df_fix, df_elo = get_data()

if df_fix is None or df_elo is None:
    st.error("Nepodařilo se načíst data. Zkus obnovit stránku.")
    st.stop()

# --- SIDEBAR FILTRY ---
st.sidebar.header("🔍 Filtrování Zápasů")

# 1. Filtr času
dnes = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
max_days = st.sidebar.slider("Zobrazit zápasy na (dny):", 1, 7, 3)
limit_date = dnes + timedelta(days=max_days)

# 2. Filtr Ligy/Země
all_countries = sorted(df_fix['Country'].unique().astype(str))
selected_country = st.sidebar.selectbox("Země / Soutěž:", ["Všechny"] + all_countries)

# 3. Filtr Důvěry
min_confidence = st.sidebar.slider("Minimální důvěra modelu (%):", 50, 90, 60)

# 4. Filtr Typu sázky
bet_type_filter = st.sidebar.multiselect(
    "Hledat typ sázky:", 
    ["Výhra (1/2)", "Neprohra (10/02)", "Góly (Over/Under)", "BTTS"],
    default=["Výhra (1/2)", "Góly (Over/Under)"]
)

st.sidebar.markdown("---")
st.sidebar.info("💡 **Tip:** Pro nejbezpečnější sázky nastav důvěru nad 75%. Pro Value Betting hledej okolo 60%.")

# --- ZPRACOVÁNÍ DAT ---
mask = (df_fix['DateObj'] >= dnes) & (df_fix['DateObj'] <= limit_date)
if selected_country != "Všechny":
    mask = mask & (df_fix['Country'] == selected_country)

upcoming = df_fix[mask].copy()

# Vytvoření slovníku Elo pro rychlé hledání
elo_dict = df_elo.set_index('Club')['Elo'].to_dict()

analyzed_matches = []

# Hlavní smyčka přes zápasy
for idx, row in upcoming.iterrows():
    try:
        home, away = row['Home'], row['Away']
        
        # Získání Elo (buď z rozpisu, nebo z DB)
        elo_h = row.get('EloHome')
        elo_a = row.get('EloAway')
        
        if pd.isna(elo_h): elo_h = elo_dict.get(home)
        if pd.isna(elo_a): elo_a = elo_dict.get(away)
        
        if elo_h is None or elo_a is None: continue # Nemáme data, přeskakujeme
        
        # Výpočet statistik
        stats = calculate_match_stats(elo_h, elo_a)
        best_bet, confidence = get_best_bet(stats)
        
        # Aplikace filtrů
        if confidence * 100 < min_confidence: continue
        
        # Filtr typu sázky
        show_match = False
        if "Výhra (1/2)" in bet_type_filter and ("Výhra" in best_bet): show_match = True
        if "Neprohra (10/02)" in bet_type_filter and ("Neprohra" in best_bet): show_match = True
        if "Góly (Over/Under)" in bet_type_filter and ("Over" in best_bet or "Under" in best_bet): show_match = True
        if "BTTS" in bet_type_filter and ("BTTS" in best_bet): show_match = True
        
        if not show_match: continue
        
        analyzed_matches.append({
            "Datum": row['DateObj'],
            "Soutěž": row.get('Country', 'EU'),
            "Domácí": home,
            "Hosté": away,
            "Elo H": elo_h,
            "Elo A": elo_a,
            "Tip": best_bet,
            "Důvěra": confidence,
            "Férový kurz": 1/confidence,
            "Stats": stats # Uložíme si celá data pro detailní pohled
        })
        
    except: continue

# --- ZOBRAZENÍ VÝSLEDKŮ ---

# TABS
tab1, tab2 = st.tabs(["📋 Seznam Tipů (Auto-Pilot)", "🔬 Detailní Analyzátor"])

with tab1:
    if not analyzed_matches:
        st.warning("Nebyly nalezeny žádné zápasy odpovídající tvým filtrům.")
    else:
        # Seřadíme podle důvěry
        df_res = pd.DataFrame(analyzed_matches).sort_values(by="Důvěra", ascending=False)
        
        st.success(f"Nalezeno {len(df_res)} zápasů splňujících kritéria.")
        
        for idx, match in df_res.iterrows():
            with st.container():
                # Layout karty zápasu
                c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                
                with c1:
                    st.caption(f"{match['Datum'].strftime('%d.%m. %H:%M')} | {match['Soutěž']}")
                    # Vizuální Elo bar
                    diff = match['Elo H'] - match['Elo A']
                    if diff > 0: st.markdown(f"<span style='color:green'>Domácí +{int(diff)} Elo</span>", unsafe_allow_html=True)
                    else: st.markdown(f"<span style='color:red'>Hosté +{int(abs(diff))} Elo</span>", unsafe_allow_html=True)
                
                with c2:
                    st.markdown(f"### {match['Domácí']} vs {match['Hosté']}")
                    
                with c3:
                    st.metric("Doporučená sázka", match['Tip'])
                    
                with c4:
                    color = "normal"
                    if match['Důvěra'] > 0.75: color = "off" # Streamlit hack pro zelenou
                    st.metric("Důvěra / Kurz", f"{match['Důvěra']*100:.1f} %", f"{match['Férový kurz']:.2f}", delta_color=color)
                
                # Expandér pro rychlý náhled detailů
                with st.expander("📊 Zobrazit detaily (xG, Pravděpodobnosti)"):
                    s = match['Stats']
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.write(f"**xG Domácí:** {s['xG_Home']:.2f}")
                    sc1.write(f"**xG Hosté:** {s['xG_Away']:.2f}")
                    
                    sc2.write(f"**1 (Výhra D):** {s['1']*100:.1f}%")
                    sc2.write(f"**0 (Remíza):** {s['0']*100:.1f}%")
                    sc2.write(f"**2 (Výhra H):** {s['2']*100:.1f}%")
                    
                    sc3.write(f"**Over 2.5:** {s['Over 2.5']*100:.1f}%")
                    sc3.write(f"**BTTS:** {s['BTTS Yes']*100:.1f}%")
                
                st.markdown("---")

with tab2:
    st.header("🔬 Laboratoř Zápasu")
    st.caption("Vyber si jakýkoliv zápas z nalezených a podívej se mu pod kapotu.")
    
    if not analyzed_matches:
        st.info("Nejdřív musíš najít nějaké zápasy v prvním tabu.")
    else:
        # Výběr zápasu pro analýzu
        match_options = [f"{m['Domácí']} vs {m['Hosté']}" for m in analyzed_matches]
        selected_match_name = st.selectbox("Vyber zápas:", match_options)
        
        # Najdeme data vybraného zápasu
        sel_match = next(m for m in analyzed_matches if f"{m['Domácí']} vs {m['Hosté']}" == selected_match_name)
        stats = sel_match['Stats']
        
        # 1. Grafické porovnání xG
        st.subheader("Očekávaný průběh (xG)")
        col_g1, col_g2 = st.columns(2)
        col_g1.metric(sel_match['Domácí'], f"{stats['xG_Home']:.2f} gólů")
        col_g2.metric(sel_match['Hosté'], f"{stats['xG_Away']:.2f} gólů")
        
        # 2. Heatmapa přesného výsledku
        st.subheader("🔥 Nejpravděpodobnější přesný výsledek")
        
        # Matplotlib graf
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.heatmap(stats['Matrix'], annot=True, fmt=".1%", cmap="YlGnBu", ax=ax,
                   xticklabels=[0,1,2,3,4,5], yticklabels=[0,1,2,3,4,5])
        ax.set_xlabel(f"Góly {sel_match['Hosté']}")
        ax.set_ylabel(f"Góly {sel_match['Domácí']}")
        ax.set_title("Pravděpodobnost skóre (Poisson)")
        st.pyplot(fig)
        
        # 3. Value Calculator
        st.subheader("💰 Value Calculator")
        st.info("Zadej kurz sázkové kanceláře (např. Fortuna) a zjisti, jestli se vyplatí vsadit.")
        
        vc1, vc2 = st.columns(2)
        with vc1:
            market_type = st.selectbox("Typ sázky:", ["Výhra Domácích", "Remíza", "Výhra Hostů", "Over 2.5", "BTTS Ano"])
            
            # Mapování názvu na klíč ve stats
            key_map = {
                "Výhra Domácích": "1", "Remíza": "0", "Výhra Hostů": "2",
                "Over 2.5": "Over 2.5", "BTTS Ano": "BTTS Yes"
            }
            my_prob = stats[key_map[market_type]]
            fair_odd = 1 / my_prob if my_prob > 0 else 0
            
            st.write(f"Náš model dává šanci: **{my_prob*100:.1f} %**")
            st.write(f"Férový kurz: **{fair_odd:.2f}**")
            
        with vc2:
            bookie_odd = st.number_input("Kurz sázkovky:", value=2.0, step=0.01)
            
            if bookie_odd > fair_odd:
                roi = ((bookie_odd * my_prob) - 1) * 100
                st.success(f"✅ **VALUE BET!** (Výhodnost: +{roi:.1f} %)")
                st.write("Doporučení: **VSADIT**")
            else:
                st.error("❌ **NEVSÁZET** (Kurz je podhodnocený)")
