import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import io
import requests

st.set_page_config(page_title="Pro Betting Model & Tips", layout="wide")

# --- 1. ZÍSKÁNÍ DAT (ClubElo API) ---
@st.cache_data(ttl=3600)
def get_elo_data():
    # Stáhne aktuální Elo ratingy pro detailní analýzu
    url = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    try:
        df = pd.read_csv(url)
        return df
    except:
        return None

@st.cache_data(ttl=3600)
def get_fixtures_data():
    # Stáhne rozpis zápasů s předpočítanými pravděpodobnostmi od ClubElo
    url = "http://api.clubelo.com/Fixtures"
    try:
        df = pd.read_csv(url)
        return df
    except:
        return None

# --- 2. MATEMATICKÉ MODELY (Pro detailní analýzu) ---
def calculate_win_prob_elo(elo_home, elo_away):
    dr = elo_home - elo_away + 100 
    we = 1 / (10**(-dr/400) + 1)
    return we

def simulate_match_poisson(home_exp_goals, away_exp_goals):
    max_goals = 6
    probs = np.zeros((max_goals, max_goals))
    for i in range(max_goals):
        for j in range(max_goals):
            prob_h = poisson.pmf(i, home_exp_goals)
            prob_a = poisson.pmf(j, away_exp_goals)
            probs[i, j] = prob_h * prob_a
    return probs

def calculate_markets(probs):
    prob_home = np.sum(np.tril(probs, -1))
    prob_draw = np.sum(np.diag(probs))
    prob_away = np.sum(np.triu(probs, 1))
    
    def get_odd(p): return 1/p if p > 0 else 0
    
    # Over/Under 2.5
    prob_over_25 = 0
    for i in range(probs.shape[0]):
        for j in range(probs.shape[1]):
            if i + j > 2.5: prob_over_25 += probs[i, j]
            
    return {
        "1": get_odd(prob_home), "0": get_odd(prob_draw), "2": get_odd(prob_away),
        "10": get_odd(prob_home + prob_draw), "02": get_odd(prob_away + prob_draw),
        "Over 2.5": get_odd(prob_over_25), "Under 2.5": get_odd(1 - prob_over_25)
    }

# --- UI APLIKACE ---

st.title("⚽ Pro Football Analytics (Elo + Poisson)")

# ==========================================
# SEKCE 1: TOP 15 TIPŮ (NOVÉ)
# ==========================================
st.header("🔥 TOP 15: Nejzajímavější sázky (3 dny)")
st.caption("Výběr zápasů s nejvyšší pravděpodobností výhry favorita podle modelu ClubElo.")

with st.spinner("Hledám nejlepší příležitosti v Evropě..."):
    df_fix = get_fixtures_data()

if df_fix is not None:
    # 1. Zpracování data
    df_fix['DateObj'] = pd.to_datetime(df_fix['Date'])
    dnes = datetime.now()
    limit_datum = dnes + timedelta(days=3)
    
    # 2. Filtr na nadcházející 3 dny
    # ClubElo má čas v UTC, takže bereme dnešek a další 3 dny
    mask = (df_fix['DateObj'] >= dnes.replace(hour=0, minute=0, second=0)) & (df_fix['DateObj'] <= limit_datum)
    upcoming = df_fix[mask].copy()
    
    if not upcoming.empty:
        # 3. Identifikace favorita a důvěry
        # ClubElo Fixtures má sloupce: Date, Home, Away, GD (Goal Diff), ProbH, ProbD, ProbA (někdy se názvy liší)
        # Pokud API nevrací ProbH, musíme si je dopočítat z Elo, ale ClubElo Fixtures obvykle má Elo Home a Elo Away
        
        tips = []
        for idx, row in upcoming.iterrows():
            # Zkusíme najít Elo
            try:
                elo_h = row['EloHome']
                elo_a = row['EloAway']
                country = row['Country'] if 'Country' in row else "EU"
                competition = row['Competition'] if 'Competition' in row else ""
                
                # Výpočet pravděpodobnosti
                prob_h = calculate_win_prob_elo(elo_h, elo_a)
                prob_a = 1 - prob_h # Zjednodušeně bez remízy pro sorting, ale pro tip použijeme přesnější
                
                # Přesnější s remízou (odhad)
                # Remíza je častější, když jsou týmy vyrovnané
                draw_prob = 0.25 # Základ
                if abs(prob_h - 0.5) < 0.1: draw_prob = 0.30
                
                real_h = prob_h * (1 - draw_prob)
                real_a = (1 - prob_h) * (1 - draw_prob)
                
                # Hledáme "tutovky"
                max_prob = max(real_h, real_a)
                
                tip = "1" if real_h > real_a else "2"
                team_tip = row['Home'] if tip == "1" else row['Away']
                fair_odd = 1 / max_prob
                
                tips.append({
                    "Datum": row['DateObj'].strftime("%d.%m. %H:%M"),
                    "Soutěž": f"{country} {competition}",
                    "Zápas": f"{row['Home']} vs {row['Away']}",
                    "Tip": f"Výhra {team_tip}",
                    "Důvěra": max_prob * 100,
                    "Férový kurz": fair_odd,
                    "Elo Rozdíl": abs(elo_h - elo_a)
                })
            except: continue
            
        # 4. Seřazení a výběr TOP 15
        df_tips = pd.DataFrame(tips)
        if not df_tips.empty:
            # Řadíme podle Důvěry (nejvyšší procenta)
            top_15 = df_tips.sort_values(by="Důvěra", ascending=False).head(15)
            
            # Zobrazení jako hezká tabulka
            st.dataframe(
                top_15.style.format({
                    "Důvěra": "{:.1f} %",
                    "Férový kurz": "{:.2f}",
                    "Elo Rozdíl": "{:.0f}"
                }),
                hide_index=True,
                use_container_width=True
            )
            st.info("💡 **Jak číst tabulku:** 'Férový kurz' je hranice. Pokud sázkovka nabízí kurz VYŠŠÍ, je to výhodná sázka (Value Bet).")
        else:
            st.warning("V datech chybí Elo ratingy pro výpočet.")
    else:
        st.warning("V následujících 3 dnech nejsou v databázi ClubElo žádné zápasy.")
else:
    st.error("Nepodařilo se stáhnout rozpis zápasů.")

st.markdown("---")

# ==========================================
# SEKCE 2: DETAILNÍ ANALYZÁTOR (Původní)
# ==========================================
st.header("🔬 Detailní Analyzátor Zápasu")
st.caption("Vyber si konkrétní zápas pro hloubkovou analýzu (xG, Poisson, Přesný výsledek).")

with st.spinner("Načítám databázi týmů..."):
    df_elo = get_elo_data()

if df_elo is not None:
    countries = sorted(df_elo['Country'].unique())
    
    c1, c2, c3 = st.columns(3)
    with c1:
        country_h = st.selectbox("Země (Domácí):", countries, index=countries.index("ENG") if "ENG" in countries else 0)
        teams_h = sorted(df_elo[df_elo['Country'] == country_h]['Club'].unique())
        home_team = st.selectbox("Tým (Domácí):", teams_h)
    with c2:
        country_a = st.selectbox("Země (Hosté):", countries, index=countries.index("ENG") if "ENG" in countries else 0)
        teams_a = sorted(df_elo[df_elo['Country'] == country_a]['Club'].unique())
        away_team = st.selectbox("Tým (Hosté):", teams_a)
    with c3:
        elo_h = df_elo[df_elo['Club'] == home_team]['Elo'].values[0]
        elo_a = df_elo[df_elo['Club'] == away_team]['Elo'].values[0]
        elo_diff = elo_h - elo_a + 100 
        
        exp_xg_h = max(0.1, 1.45 + (elo_diff / 600))
        exp_xg_a = max(0.1, 1.15 - (elo_diff / 600))
        
        st.write("📊 **Modelované xG**")
        xg_h = st.number_input(f"xG {home_team}:", value=float(round(exp_xg_h, 2)), step=0.1)
        xg_a = st.number_input(f"xG {away_team}:", value=float(round(exp_xg_a, 2)), step=0.1)

    probs_matrix = simulate_match_poisson(xg_h, xg_a)
    odds = calculate_markets(probs_matrix)

    col_res, col_odds = st.columns([1, 2])
    
    with col_res:
        st.subheader("Predikce")
        st.write(f"**{home_team}** vs **{away_team}**")
        delta = int(elo_h - elo_a)
        if delta > 0: st.success(f"Favorit: Domácí (+{delta} Elo)")
        else: st.error(f"Favorit: Hosté (+{abs(delta)} Elo)")
        
        # Top 3 výsledky
        st.write("**Nejpravděpodobnější skóre:**")
        flat_indices = np.argsort(probs_matrix.ravel())[::-1]
        for idx in flat_indices[:3]:
            sh, sa = np.unravel_index(idx, probs_matrix.shape)
            prob = probs_matrix[sh, sa] * 100
            st.write(f"🎯 **{sh}:{sa}** ({prob:.1f}%)")

    with col_odds:
        st.subheader("💰 Férové Kurzy (Fortuna Style)")
        k1, k2, k3 = st.columns(3)
        k1.metric("1 (Domácí)", f"{odds['1']:.2f}")
        k2.metric("0 (Remíza)", f"{odds['0']:.2f}")
        k3.metric("2 (Hosté)", f"{odds['2']:.2f}")
        
        k4, k5, k6 = st.columns(3)
        k4.metric("10 (Neprohra D)", f"{odds['10']:.2f}")
        k5.metric("Over 2.5 gólu", f"{odds['Over 2.5']:.2f}")
        k6.metric("02 (Neprohra H)", f"{odds['02']:.2f}")

    with st.expander("Zobrazit Heatmapu pravděpodobností"):
        fig, ax = plt.subplots(figsize=(6, 4))
        sns.heatmap(probs_matrix, annot=True, fmt=".1%", cmap="YlGnBu", ax=ax)
        ax.set_xlabel(away_team); ax.set_ylabel(home_team)
        st.pyplot(fig)
