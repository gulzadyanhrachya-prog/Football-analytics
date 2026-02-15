import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
import io

st.set_page_config(page_title="Sport Betting Hub v21", layout="wide")

# ==============================================================================\n# MODUL 1: FOTBAL (ClubElo - Stabilní)\n# ==============================================================================\n
def app_fotbal():
    st.header("⚽ Fotbalový Auto-Pilot")
    st.caption("Zdroj: ClubElo API (Elo + Poisson)")

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

    def calculate_match_stats(elo_h, elo_a):
        elo_diff = elo_h - elo_a + 100 
        prob_h_win = 1 / (10**(-elo_diff/400) + 1)
        prob_a_win = 1 - prob_h_win
        prob_draw = 0.24 
        if abs(prob_h_win - 0.5) < 0.15: prob_draw = 0.29
        real_h = prob_h_win * (1 - prob_draw)
        real_a = prob_a_win * (1 - prob_draw)
        
        base_xg = 1.35
        xg_diff = elo_diff / 500
        exp_xg_h = max(0.2, base_xg + xg_diff)
        exp_xg_a = max(0.2, base_xg - xg_diff)
        
        max_g = 6
        matrix = np.zeros((max_g, max_g))
        for i in range(max_g):
            for j in range(max_g):
                matrix[i, j] = poisson.pmf(i, exp_xg_h) * poisson.pmf(j, exp_xg_a)
                
        prob_over_25 = 0
        prob_btts = 0
        prob_h_handicap = 0 
        prob_a_handicap = 0 
        
        for i in range(max_g):
            for j in range(max_g):
                p = matrix[i, j]
                if i + j > 2.5: prob_over_25 += p
                if i > 0 and j > 0: prob_btts += p
                if i > j + 1.5: prob_h_handicap += p
                if j > i + 1.5: prob_a_handicap += p
        
        prob_dnb_h = real_h / (real_h + real_a)
        prob_dnb_a = real_a / (real_h + real_a)

        return {
            "1": real_h, "0": prob_draw, "2": real_a,
            "10": real_h + prob_draw, "02": real_a + prob_draw,
            "SBR 1": prob_dnb_h, "SBR 2": prob_dnb_a,
            "Over 2.5": prob_over_25, "Under 2.5": 1 - prob_over_25,
            "BTTS Ano": prob_btts, "BTTS Ne": 1 - prob_btts,
            "Hcp -1.5 (1)": prob_h_handicap, "Hcp -1.5 (2)": prob_a_handicap,
        }

    def get_best_bet_filtered(stats, allowed_types):
        candidates = []
        if "Zápas (1/0/2)" in allowed_types:
            candidates.append(("Výhra Domácích (1)", stats["1"]))
            candidates.append(("Výhra Hostů (2)", stats["2"]))
        if "Dvojitá šance (10/02)" in allowed_types:
            candidates.append(("Neprohra Domácích (10)", stats["10"]))
            candidates.append(("Neprohra Hostů (02)", stats["02"]))
        if "Sázka bez remízy (SBR)" in allowed_types:
            candidates.append(("SBR Domácí (1)", stats["SBR 1"]))
            candidates.append(("SBR Hosté (2)", stats["SBR 2"]))
        if "Počet gólů (Over/Under)" in allowed_types:
            candidates.append(("Over 2.5 Gólů", stats["Over 2.5"]))
            candidates.append(("Under 2.5 Gólů", stats["Under 2.5"]))
        if "Oba dají gól (BTTS)" in allowed_types:
            candidates.append(("BTTS Ano", stats["BTTS Ano"]))
        if "Handicap (-1.5)" in allowed_types:
            candidates.append(("Handicap Domácí -1.5", stats["Hcp -1.5 (1)"]))
            candidates.append(("Handicap Hosté -1.5", stats["Hcp -1.5 (2)"]))

        if not candidates: return "Žádný filtr", 0
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0], candidates[0][1]

    # --- UI FOTBAL ---
    with st.spinner("Načítám fotbalová data..."):
        df_fix, df_elo = get_data()

    if df_fix is None or df_elo is None:
        st.error("Chyba dat."); st.stop()

    st.sidebar.header("📅 Kdy se hraje?")
    dnes = datetime.now().date()
    date_option = st.sidebar.radio("Vyber den:", ["Dnes", "Zítra", "Víkend", "Vše (3 dny)"])
    
    target_dates = []
    if date_option == "Dnes": target_dates = [dnes]
    elif date_option == "Zítra": target_dates = [dnes + timedelta(days=1)]
    elif date_option == "Víkend": 
        days_ahead = 5 - dnes.weekday()
        if days_ahead < 0: days_ahead += 7
        target_dates = [dnes + timedelta(days=days_ahead), dnes + timedelta(days=days_ahead+1)]
    else: target_dates = [dnes, dnes + timedelta(days=1), dnes + timedelta(days=2)]

    st.sidebar.header("🌍 Kde se hraje?")
    all_countries = sorted(df_fix['Country'].unique().astype(str))
    selected_country = st.sidebar.selectbox("Země / Soutěž:", ["Všechny"] + all_countries)

    st.sidebar.header("💰 Na co chceš sázet?")
    bet_types = st.sidebar.multiselect("Typy sázek:", 
        ["Zápas (1/0/2)", "Dvojitá šance (10/02)", "Sázka bez remízy (SBR)", "Počet gólů (Over/Under)", "Oba dají gól (BTTS)", "Handicap (-1.5)"],
        default=["Zápas (1/0/2)", "Počet gólů (Over/Under)", "Sázka bez remízy (SBR)"])
    
    min_confidence = st.sidebar.slider("Minimální důvěra (%):", 50, 95, 60)

    df_fix['JustDate'] = df_fix['DateObj'].dt.date
    mask_date = df_fix['JustDate'].isin(target_dates)
    upcoming = df_fix[mask_date].copy()
    if selected_country != "Všechny": upcoming = upcoming[upcoming['Country'] == selected_country]

    elo_dict = df_elo.set_index('Club')['Elo'].to_dict()
    analyzed_matches = []

    for idx, row in upcoming.iterrows():
        try:
            home, away = row['Home'], row['Away']
            elo_h = row.get('EloHome')
            elo_a = row.get('EloAway')
            if pd.isna(elo_h): elo_h = elo_dict.get(home)
            if pd.isna(elo_a): elo_a = elo_dict.get(away)
            if elo_h is None or elo_a is None: continue 
            
            stats = calculate_match_stats(elo_h, elo_a)
            best_bet, confidence = get_best_bet_filtered(stats, bet_types)
            
            if confidence * 100 < min_confidence: continue
            
            analyzed_matches.append({
                "Datum": row['DateObj'], "Soutěž": row.get('Country', 'EU'),
                "Domácí": home, "Hosté": away, "Tip": best_bet,
                "Důvěra": confidence, "Férový kurz": 1/confidence if confidence > 0 else 0
            })
        except: continue

    if not analyzed_matches:
        st.warning("Žádné zápasy nenalezeny.")
    else:
        df_res = pd.DataFrame(analyzed_matches).sort_values(by="Důvěra", ascending=False)
        st.success(f"Nalezeno {len(df_res)} příležitostí.")
        for idx, match in df_res.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                with c1: st.caption(f"{match['Datum'].strftime('%d.%m. %H:%M')} | {match['Soutěž']}"); st.write(f"**{match['Domácí']}**"); st.write(f"**{match['Hosté']}**")
                with c2: st.markdown(f"#### {match['Tip']}"); st.caption("Doporučená sázka")
                with c3: 
                    color = "normal"
                    if match['Důvěra'] > 0.75: color = "off"
                    st.metric("Důvěra", f"{match['Důvěra']*100:.1f} %", delta_color=color)
                with c4: st.metric("Férový kurz", f"{match['Férový kurz']:.2f}")
                st.markdown("---")


# ==============================================================================\n# MODUL 2: HOKEJ (NHL API - Official)\n# ==============================================================================\n
def app_hokej():
    st.header("🏒 NHL Auto-Pilot")
    st.caption("Zdroj: Official NHL API (Stats + Schedule)")

    # --- 1. STAŽENÍ DAT Z NHL API ---
    @st.cache_data(ttl=3600)
    def get_nhl_data():
        # A) Tabulka (Standings) - pro sílu týmů
        try:
            r = requests.get("https://api-web.nhle.com/v1/standings/now")
            data = r.json()
            standings = data['standings']
            
            team_stats = {}
            for team in standings:
                name = team['teamName']['default']
                abbrev = team['teamAbbrev']['default']
                gp = team['gamesPlayed']
                gf = team['goalFor']
                ga = team['goalAgainst']
                points = team['points']
                
                # Výpočet metrik síly
                # GF/GP (Góly na zápas) a GA/GP (Obdržené na zápas)
                gf_per_game = gf / gp if gp > 0 else 0
                ga_per_game = ga / gp if gp > 0 else 0
                point_pct = points / (gp * 2) if gp > 0 else 0
                
                team_stats[name] = {
                    "Abbrev": abbrev,
                    "GF_PG": gf_per_game,
                    "GA_PG": ga_per_game,
                    "PointPct": point_pct
                }
                # Mapování zkratek na celá jména (pro rozpis)
                team_stats[abbrev] = team_stats[name] 
                
            # Průměr ligy (pro xG model)
            avg_gf = np.mean([t['GF_PG'] for t in team_stats.values()])
            
            return team_stats, avg_gf
        except Exception as e:
            return None, str(e)

    @st.cache_data(ttl=3600)
    def get_nhl_schedule():
        # B) Rozpis na tento týden
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            r = requests.get(f"https://api-web.nhle.com/v1/schedule/{today}")
            data = r.json()
            return data['gameWeek']
        except: return None

    # --- 2. HOKEJOVÝ MODEL (xG + Poisson) ---
    def calculate_hockey_probs(home_stats, away_stats, league_avg):
        # Modelování xG pro hokej
        # Home xG = (Home Attack * Away Defense) / League Avg
        
        home_attack = home_stats['GF_PG']
        home_defense = home_stats['GA_PG']
        away_attack = away_stats['GF_PG']
        away_defense = away_stats['GA_PG']
        
        # Přidáme malou výhodu domácího prostředí (+5% k útoku)
        xg_home = (home_attack * away_defense) / league_avg * 1.05
        xg_away = (away_attack * home_defense) / league_avg
        
        # Poisson
        max_g = 10 # V hokeji padá víc gólů
        matrix = np.zeros((max_g, max_g))
        for i in range(max_g):
            for j in range(max_g):
                matrix[i, j] = poisson.pmf(i, xg_home) * poisson.pmf(j, xg_away)
                
        # Trhy
        prob_home_reg = np.sum(np.tril(matrix, -1)) # Výhra v 60 min
        prob_draw_reg = np.sum(np.diag(matrix))     # Remíza
        prob_away_reg = np.sum(np.triu(matrix, 1))  # Prohra v 60 min
        
        # Moneyline (Vítěz do rozhodnutí)
        # Remízu rozdělíme 50/50 (zjednodušeně, v reálu záleží na prodloužení)
        prob_home_ml = prob_home_reg + (prob_draw_reg * 0.5)
        prob_away_ml = prob_away_reg + (prob_draw_reg * 0.5)
        
        # Over/Under 6.5
        prob_over_65 = 0
        for i in range(max_g):
            for j in range(max_g):
                if i + j > 6.5: prob_over_65 += matrix[i, j]
                
        return {
            "1 (60 min)": prob_home_reg,
            "0 (Remíza)": prob_draw_reg,
            "2 (60 min)": prob_away_reg,
            "Vítěz (ML) 1": prob_home_ml,
            "Vítěz (ML) 2": prob_away_ml,
            "Over 6.5": prob_over_65,
            "Under 6.5": 1 - prob_over_65,
            "xG_H": xg_home,
            "xG_A": xg_away
        }

    # --- UI HOKEJ ---
    with st.spinner("Stahuji data z NHL..."):
        stats_db, league_avg = get_nhl_data()
        schedule = get_nhl_schedule()

    if stats_db is None:
        st.error("Nepodařilo se načíst statistiky NHL.")
    elif schedule is None:
        st.error("Nepodařilo se načíst rozpis NHL.")
    else:
        # Filtry
        st.sidebar.header("🏒 Nastavení Hokeje")
        bet_type = st.sidebar.selectbox("Preferovaný typ sázky:", ["Vítěz do rozhodnutí (Moneyline)", "Zápas (60 min)", "Góly (Over/Under 6.5)"])
        
        matches_found = []
        
        # Procházíme dny v týdnu
        for day in schedule:
            date_str = day['date']
            games = day['games']
            
            for game in games:
                try:
                    # Získání týmů (NHL API používá zkratky nebo jména)
                    h_team_data = game['homeTeam']
                    a_team_data = game['awayTeam']
                    
                    # Názvy týmů (někdy je to 'abbrev', někdy 'placeName' + 'commonName')
                    # Pro jednoduchost zkusíme najít v naší DB podle abbrev
                    h_abbr = h_team_data.get('abbrev', 'UNK')
                    a_abbr = a_team_data.get('abbrev', 'UNK')
                    
                    # Pokud nemáme statistiky, zkusíme najít podle jména
                    if h_abbr not in stats_db: continue
                    
                    h_stats = stats_db[h_abbr]
                    a_stats = stats_db[a_abbr]
                    
                    # Výpočet
                    probs = calculate_hockey_probs(h_stats, a_stats, league_avg)
                    
                    # Výběr tipu
                    tip = ""
                    conf = 0
                    
                    if bet_type == "Vítěz do rozhodnutí (Moneyline)":
                        if probs["Vítěz (ML) 1"] > probs["Vítěz (ML) 2"]:
                            tip = f"Výhra {h_abbr} (ML)"
                            conf = probs["Vítěz (ML) 1"]
                        else:
                            tip = f"Výhra {a_abbr} (ML)"
                            conf = probs["Vítěz (ML) 2"]
                            
                    elif bet_type == "Zápas (60 min)":
                        # Hledáme nejvyšší pravděpodobnost z 1, 0, 2
                        opts = [("1", probs["1 (60 min)"]), ("0", probs["0 (Remíza)"]), ("2", probs["2 (60 min)"])]
                        opts.sort(key=lambda x: x[1], reverse=True)
                        tip = f"Tip: {opts[0][0]}"
                        conf = opts[0][1]
                        
                    elif bet_type == "Góly (Over/Under 6.5)":
                        if probs["Over 6.5"] > probs["Under 6.5"]:
                            tip = "Over 6.5 Gólů"
                            conf = probs["Over 6.5"]
                        else:
                            tip = "Under 6.5 Gólů"
                            conf = probs["Under 6.5"]
                            
                    matches_found.append({
                        "Datum": date_str,
                        "Zápas": f"{h_abbr} vs {a_abbr}",
                        "Tip": tip,
                        "Důvěra": conf,
                        "Férový kurz": 1/conf if conf > 0 else 0,
                        "xG": f"{probs['xG_H']:.1f} : {probs['xG_A']:.1f}"
                    })
                except: continue

        # Zobrazení
        if matches_found:
            df_res = pd.DataFrame(matches_found).sort_values(by="Důvěra", ascending=False)
            
            st.subheader(f"🔥 NHL Predikce ({len(df_res)} zápasů)")
            
            # Top 3 Tutovky
            top3 = df_res.head(3)
            c1, c2, c3 = st.columns(3)
            for i, (idx, row) in enumerate(top3.iterrows()):
                col = [c1, c2, c3][i]
                with col:
                    st.info(f"⭐ TOP {i+1}")
                    st.write(f"**{row['Zápas']}**")
                    st.write(f"{row['Tip']}")
                    st.metric("Důvěra", f"{row['Důvěra']*100:.1f}%")
            
            st.markdown("---")
            st.dataframe(df_res.style.format({"Důvěra": "{:.1f} %", "Férový kurz": "{:.2f}"}), hide_index=True, use_container_width=True)
        else:
            st.info("Žádné zápasy NHL v nejbližších dnech.")

# ==============================================================================\n# HLAVNÍ ROZCESTNÍK\n# ==============================================================================\n
st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🏒 Hokej (NHL)"])

if sport == "⚽ Fotbal":
    app_fotbal()
elif sport == "🏒 Hokej (NHL)":
    app_hokej()
