import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime

st.set_page_config(page_title="League Master Analyst", layout="wide")

# ==============================================================================\n# 1. KONFIGURACE LIG (FOTMOB ID)\n# ==============================================================================\n# Toto jsou ID, která používá Fotmob. Jsou velmi stabilní.\n
LEAGUES = {
    "🇬🇧 Premier League (Anglie)": 47,
    "🇬🇧 Championship (Anglie 2)": 48,
    "🇪🇸 La Liga (Španělsko)": 87,
    "🇩🇪 Bundesliga (Německo)": 54,
    "🇮🇹 Serie A (Itálie)": 55,
    "🇫🇷 Ligue 1 (Francie)": 53,
    "🇨🇿 Fortuna Liga (Česko)": 66,
    "🇵🇱 Ekstraklasa (Polsko)": 69,
    "🇵🇹 Liga Portugal (Portugalsko)": 61,
    "🇳🇱 Eredivisie (Holandsko)": 57,
    "🇹🇷 Super Lig (Turecko)": 71,
    "🇩🇰 Superliga (Dánsko)": 70,
    "🇬🇷 Super League (Řecko)": 72,
    "🇷🇴 Liga 1 (Rumunsko)": 116,
    "🇮🇱 Ligat Ha'Al (Izrael)": 122,
    "🇧🇬 First League (Bulharsko)": 113,
    "🇦🇹 Bundesliga (Rakousko)": 60,
    "🇨🇭 Super League (Švýcarsko)": 59,
    "🇧🇪 Pro League (Belgie)": 50,
    "🇺🇸 MLS (USA)": 130,
    "🇪🇺 Liga Mistrů": 42,
    "🇪🇺 Evropská Liga": 73
}

# ==============================================================================\n# 2. STAHOVÁNÍ DAT (FOTMOB LEAGUE ENDPOINT)\n# ==============================================================================\n
@st.cache_data(ttl=3600)
def get_league_data(league_id):
    # Tento endpoint vrací tabulku I nadcházející zápasy v jednom JSONu
    url = f"https://www.fotmob.com/api/leagues?id={league_id}&tab=overview"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200: return None, f"Chyba {r.status_code}"
        return r.json(), None
    except Exception as e:
        return None, str(e)

# ==============================================================================\n# 3. ANALYTICKÉ MODELY (POISSON)\n# ==============================================================================\n
def process_table_stats(json_data):
    """Vytáhne z JSONu tabulku a vypočítá sílu útoku/obrany pro každý tým."""
    if not json_data or "table" not in json_data: return None, 0
    
    # Fotmob má tabulku často vnořenou v "data" -> "table" -> "all"
    try:
        # Struktura se může lišit podle typu ligy (skupiny vs tabulka)
        table_data = json_data["table"][0]["data"]["table"]["all"]
    except:
        return None, 0

    stats = {}
    total_goals = 0
    total_games = 0
    
    for row in table_data:
        team_id = row["id"]
        name = row["name"]
        played = row["played"]
        gf = int(row["scoresStr"].split("-")[0])
        ga = int(row["scoresStr"].split("-")[1])
        pts = row["pts"]
        
        if played > 0:
            stats[team_id] = {
                "name": name,
                "gf_avg": gf / played,
                "ga_avg": ga / played,
                "points": pts
            }
            total_goals += gf
            total_games += played
            
    if total_games == 0: return None, 0
    
    league_avg = total_goals / total_games
    
    # Normalizace síly
    for tid, data in stats.items():
        data["att"] = data["gf_avg"] / league_avg
        data["def"] = data["ga_avg"] / league_avg
        
    return stats, league_avg

def calculate_probabilities(home_id, away_id, stats, league_avg):
    """Vypočítá pravděpodobnosti pro všechny trhy."""
    if home_id not in stats or away_id not in stats: return None
    
    h = stats[home_id]
    a = stats[away_id]
    
    # xG Model
    # Domácí xG = Domácí Útok * Hostující Obrana * Průměr Ligy * Výhoda Domácích
    xg_h = h["att"] * a["def"] * league_avg * 1.15
    xg_a = a["att"] * h["def"] * league_avg
    
    # Poisson
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, xg_h) * poisson.pmf(j, xg_a)
            
    # Trhy
    prob_1 = np.sum(np.tril(matrix, -1))
    prob_0 = np.sum(np.diag(matrix))
    prob_2 = np.sum(np.triu(matrix, 1))
    
    prob_over_15 = 0; prob_over_25 = 0; prob_over_35 = 0
    prob_btts = 0
    
    for i in range(max_g):
        for j in range(max_g):
            total = i + j
            p = matrix[i, j]
            if total > 1.5: prob_over_15 += p
            if total > 2.5: prob_over_25 += p
            if total > 3.5: prob_over_35 += p
            if i > 0 and j > 0: prob_btts += p
            
    return {
        "1": prob_1, "0": prob_0, "2": prob_2,
        "10": prob_1 + prob_0, "02": prob_2 + prob_0,
        "Over 1.5": prob_over_15, "Over 2.5": prob_over_25, "Over 3.5": prob_over_35,
        "BTTS": prob_btts,
        "xG_H": xg_h, "xG_A": xg_a,
        "Home": h["name"], "Away": a["name"]
    }

# ==============================================================================\n# 4. UI APLIKACE\n# ==============================================================================\n
st.title("⚽ League Master Analyst")
st.caption("Analýza budoucích zápasů na základě aktuální formy a tabulky.")

# --- VÝBĚR LIGY ---
selected_league = st.selectbox("Vyber ligu:", list(LEAGUES.keys()))
league_id = LEAGUES[selected_league]

with st.spinner("Stahuji data z Fotmobu..."):
    data, err = get_league_data(league_id)

if err:
    st.error(f"Chyba API: {err}")
elif not data:
    st.warning("Data nejsou k dispozici.")
else:
    # 1. Zpracování statistik
    stats_db, league_avg = process_table_stats(data)
    
    if not stats_db:
        st.warning("Nepodařilo se načíst tabulku (možná začátek sezóny nebo pohárový systém).")
    else:
        # 2. Získání budoucích zápasů
        # Fotmob vrací "matches" -> "allMatches" nebo "nextMatches"
        matches_raw = []
        if "matches" in data and "allMatches" in data["matches"]:
            matches_raw = data["matches"]["allMatches"]
        elif "nextMatches" in data:
            matches_raw = data["nextMatches"]
            
        # Filtrujeme jen budoucí zápasy (ty, co nemají výsledek)
        future_matches = [m for m in matches_raw if not m["status"]["finished"] and not m["status"]["cancelled"]]
        
        # Seřadíme podle času
        # Fotmob time je string nebo timestamp, musíme opatrně
        # Pro jednoduchost bereme tak, jak jsou (obvykle jsou seřazené)
        
        if not future_matches:
            st.info("V této lize nejsou naplánovány žádné další zápasy.")
        else:
            st.success(f"Analyzováno {len(future_matches)} nadcházejících zápasů.")
            
            # --- FILTRY ---
            with st.expander("🛠️ Filtrování sázek", expanded=True):
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    min_conf = st.slider("Minimální pravděpodobnost (%):", 50, 90, 60)
                with c_f2:
                    bet_type = st.selectbox("Typ sázky:", ["Vše", "Výhra (1/2)", "Góly (Over)", "BTTS"])
            
            # --- VÝPIS ZÁPASŮ ---
            for m in future_matches[:20]: # Limit 20 zápasů
                try:
                    home_id = m["home"]["id"]
                    away_id = m["away"]["id"]
                    time_str = m["status"].get("utcTime") # Timestamp
                    
                    # Převod času
                    if time_str:
                        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                        date_display = dt.strftime("%d.%m. %H:%M")
                    else:
                        date_display = "Neznámý čas"

                    # Výpočet
                    res = calculate_probabilities(home_id, away_id, stats_db, league_avg)
                    
                    if not res: continue # Chybí data o týmu
                    
                    # Logika doporučení
                    tips = []
                    
                    # 1. Výhra
                    if res["1"] * 100 >= min_conf: tips.append((f"Výhra {res['Home']}", res["1"], "green"))
                    elif res["2"] * 100 >= min_conf: tips.append((f"Výhra {res['Away']}", res["2"], "red"))
                    
                    # 2. Góly
                    if res["Over 2.5"] * 100 >= min_conf: tips.append(("Over 2.5 Gólů", res["Over 2.5"], "blue"))
                    
                    # 3. BTTS
                    if res["BTTS"] * 100 >= min_conf: tips.append(("BTTS (Oba dají)", res["BTTS"], "orange"))
                    
                    # 4. Dvojitá šance (pokud není čistá výhra)
                    if not tips and res["10"] * 100 >= min_conf + 10: tips.append((f"Neprohra {res['Home']}", res["10"], "gray"))
                    if not tips and res["02"] * 100 >= min_conf + 10: tips.append((f"Neprohra {res['Away']}", res["02"], "gray"))

                    # Filtr zobrazení
                    if bet_type == "Výhra (1/2)" and not any("Výhra" in t[0] for t in tips): continue
                    if bet_type == "Góly (Over)" and not any("Over" in t[0] for t in tips): continue
                    if bet_type == "BTTS" and not any("BTTS" in t[0] for t in tips): continue
                    
                    # Pokud nemáme silný tip a je nastaven vysoký filtr, přeskočíme
                    if not tips and min_conf > 50: continue

                    # VYKRESLENÍ KARTY
                    with st.container():
                        c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                        
                        with c1:
                            st.write(f"**{date_display}**")
                            
                        with c2:
                            st.write(f"**{res['Home']}**")
                            st.write(f"**{res['Away']}**")
                            
                        with c3:
                            if tips:
                                best_tip = max(tips, key=lambda x: x[1])
                                st.markdown(f"#### :{best_tip[2]}[{best_tip[0]}]")
                                st.caption(f"Důvěra: {int(best_tip[1]*100)}%")
                            else:
                                st.write("Bez silného signálu")
                                
                        with c4:
                            with st.popover("Detailní analýza"):
                                st.write("**Pravděpodobnosti:**")
                                st.write(f"1: {int(res['1']*100)}% | X: {int(res['0']*100)}% | 2: {int(res['2']*100)}%")
                                st.write("**Góly:**")
                                st.write(f"Over 2.5: {int(res['Over 2.5']*100)}%")
                                st.write(f"BTTS: {int(res['BTTS']*100)}%")
                                st.write("**xG Model:**")
                                st.write(f"{res['xG_H']:.2f} : {res['xG_A']:.2f}")
                                st.write(f"Férový kurz (Tip): {1/best_tip[1]:.2f}" if tips else "")

                        st.markdown("---")
                        
                except Exception as e:
                    continue
