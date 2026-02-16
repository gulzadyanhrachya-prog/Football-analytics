import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Fotmob Underground", layout="wide")

# ==============================================================================\n# 1. FOTMOB API WRAPPER (Unofficial)\n# ==============================================================================\n
# Mapování ID lig na Fotmobu
LEAGUES = {
    "🇬🇧 Premier League": 47,
    "🇬🇧 Championship": 48,
    "🇩🇪 Bundesliga": 54,
    "🇩🇪 2. Bundesliga": 146,
    "🇪🇸 La Liga": 87,
    "🇮🇹 Serie A": 55,
    "🇫🇷 Ligue 1": 53,
    "🇳🇱 Eredivisie": 57,
    "🇵🇹 Liga Portugal": 61,
    "🇨🇿 Fortuna Liga": 66,
    "🇵🇱 Ekstraklasa": 69,
    "🇩🇰 Superliga": 70,
    "🇹🇷 Super Lig": 71,
    "🇺🇸 MLS": 130,
    "🇪🇺 Liga Mistrů": 42,
    "🇪🇺 Evropská Liga": 73
}

@st.cache_data(ttl=300) # Cache 5 minut (aby to bylo skoro live)
def get_fotmob_matches(date_str):
    """
    Stáhne všechny zápasy pro daný den z Fotmobu.
    """
    url = f"https://www.fotmob.com/api/matches?date={date_str}"
    
    # Fotmob vyžaduje User-Agent, jinak vrátí 403
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, f"Chyba {r.status_code}"
        return r.json(), None
    except Exception as e:
        return None, str(e)

def parse_matches(json_data, selected_league_id):
    """
    Vytáhne z JSONu jen to podstatné pro vybranou ligu.
    """
    if not json_data or "leagues" not in json_data:
        return []
        
    parsed = []
    
    for league in json_data["leagues"]:
        # Filtr ligy (pokud je vybrána konkrétní)
        if selected_league_id != "Vše" and league["id"] != selected_league_id:
            continue
            
        # Pokud je vybráno "Vše", bereme jen ty z našeho seznamu LEAGUES
        if selected_league_id == "Vše" and league["id"] not in LEAGUES.values():
            continue

        league_name = league["name"]
        country = league["ccode"]
        
        for match in league["matches"]:
            try:
                home = match["home"]["name"]
                away = match["away"]["name"]
                home_id = match["home"]["id"]
                away_id = match["away"]["id"]
                
                # Skóre a čas
                status = match["status"]
                score = status.get("scoreStr", "? - ?")
                started = status.get("started", False)
                finished = status.get("finished", False)
                live = status.get("liveTime", None)
                
                # Čas výkopu
                time_str = match["time"] # Např. "18:30"
                
                # xG (Expected Goals) - Fotmob to má jen u některých zápasů
                xg_h = None
                xg_a = None
                # Fotmob xG bývá v detailech, v přehledu někdy chybí. 
                # Zkusíme se podívat, jestli to JSON obsahuje (struktura se mění)
                
                # Kurzy (Odds) - Fotmob často posílá "preMatchOdds"
                odds = match.get("status", {}).get("reason", {}) # Někdy jsou tady
                # Nebo přímo v objektu match
                # Pro jednoduchost budeme hledat indikátor favorita
                
                parsed.append({
                    "Liga": f"{country} {league_name}",
                    "Čas": time_str,
                    "Live": live if live else ("FT" if finished else ""),
                    "Domácí": home,
                    "Hosté": away,
                    "Skóre": score,
                    "Id": match["id"],
                    "Url": f"https://www.fotmob.com/match/{match['id']}"
                })
            except: continue
            
    return parsed

@st.cache_data(ttl=3600)
def get_match_details(match_id):
    """
    Stáhne detail zápasu (xG, statistiky, predikce)
    """
    url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        return r.json()
    except: return None

# ==============================================================================\n# 2. UI APLIKACE\n# ==============================================================================\n
st.title("⚡ Fotmob Underground Analyst")
st.caption("Data přímo ze zdroje, který používají miliony fanoušků. Real-time, xG, Statistiky.")

# --- FILTRY ---
c1, c2 = st.columns([2, 1])
with c1:
    league_select = st.selectbox("Vyber ligu:", ["Vše"] + list(LEAGUES.keys()))
    league_id = LEAGUES[league_select] if league_select != "Vše" else "Vše"

with c2:
    day_select = st.selectbox("Den:", ["Dnes", "Zítra", "Včera"])
    
target_date = datetime.now()
if day_select == "Zítra": target_date += timedelta(days=1)
elif day_select == "Včera": target_date -= timedelta(days=1)
date_str = target_date.strftime("%Y%m%d")

# --- NAČTENÍ DAT ---
with st.spinner("Napojuji se na Fotmob API..."):
    raw_data, error = get_fotmob_matches(date_str)

if error:
    st.error(f"Chyba připojení: {error}")
    st.info("Zkus obnovit stránku. Fotmob občas vyžaduje \'čistý\' request.")
else:
    matches = parse_matches(raw_data, league_id)
    
    if not matches:
        st.warning(f"Pro {day_select} nebyly v této lize nalezeny žádné zápasy.")
    else:
        st.success(f"Nalezeno {len(matches)} zápasů.")
        
        for m in matches:
            with st.container():
                # Hlavní řádek zápasu
                c1, c2, c3, c4, c5 = st.columns([1, 3, 1, 3, 1])
                
                with c1:
                    st.caption(m["Liga"])
                    if m["Live"]:
                        st.markdown(f"<span style='color:red; font-weight:bold'>⏱ {m['Live']}</span>", unsafe_allow_html=True)
                    else:
                        st.write(m["Čas"])
                
                with c2:
                    st.markdown(f"<div style='text-align:right; font-weight:bold'>{m['Domácí']}</div>", unsafe_allow_html=True)
                
                with c3:
                    st.markdown(f"<div style='text-align:center; font-size:1.2em; background-color:#f0f2f6; border-radius:5px'>{m['Skóre']}</div>", unsafe_allow_html=True)
                
                with c4:
                    st.markdown(f"<div style='text-align:left; font-weight:bold'>{m['Hosté']}</div>", unsafe_allow_html=True)
                
                with c5:
                    # Tlačítko pro detailní analýzu
                    if st.button("Analýza", key=m["Id"]):
                        st.session_state["selected_match"] = m["Id"]
                        st.session_state["selected_match_name"] = f"{m['Domácí']} vs {m['Hosté']}"

            st.markdown("---")

# --- DETAILNÍ ANALÝZA (POKUD JE VYBRÁNO) ---
if "selected_match" in st.session_state:
    match_id = st.session_state["selected_match"]
    match_name = st.session_state["selected_match_name"]
    
    st.header(f"🔬 Detailní Analýza: {match_name}")
    
    with st.spinner("Stahuji detailní statistiky (xG, H2H, Forma)..."):
        details = get_match_details(match_id)
        
    if details:
        # 1. STATISTIKY (xG)
        content = details.get("content", {})
        stats = content.get("stats", {}).get("Periods", {}).get("All", {}).get("stats", [])
        
        # Hledání xG v datech
        xg_h = 0
        xg_a = 0
        has_xg = False
        
        # Fotmob struktura statistik je pole
        for item in stats:
            for stat_item in item.get("stats", []):
                if stat_item.get("key") == "expected_goals":
                    xg_h = stat_item["stats"][0]
                    xg_a = stat_item["stats"][1]
                    has_xg = True
        
        # 2. PREDIKCE (Fotmob SuperComputer)
        # Někdy je v "predict" nebo "insights"
        prediction = content.get("matchFacts", {}).get("infoBox", {})
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.subheader("📊 Statistiky Zápasu")
            if has_xg:
                st.metric("Expected Goals (xG)", f"{xg_h} - {xg_a}")
                
                # Vizualizace xG
                total_xg = float(xg_h) + float(xg_a)
                if total_xg > 0:
                    st.progress(float(xg_h) / total_xg)
            else:
                st.info("xG data zatím nejsou k dispozici (zápas asi ještě nezačal nebo liga nepodporuje xG).")
                
            # Další stats (Střely)
            # (Zjednodušený výpis, struktura je složitá)
            
        with col_b:
            st.subheader("🔮 Predikce & Kurzy")
            # Zkusíme najít kurzy v hlavičce
            header = details.get("header", {})
            teams = header.get("teams", [])
            
            # Fotmob často nemá explicitní predikci v API zdarma, 
            # ale můžeme se podívat na formu
            
            st.write("**Forma (Posledních 5):**")
            # Toto by vyžadovalo další parsování, pro teď odkážeme na web
            st.markdown(f"[Otevřít kompletní statistiky na Fotmob.com](https://www.fotmob.com/match/{match_id})")
            
            # Vlastní mini-predikce na základě tabulky (pokud je v datech)
            table = content.get("table", [])
            if table:
                st.success("Tabulka načtena (interní výpočet...)")
                # Zde by šla implementovat logika z minulé verze
            else:
                st.write("Detailní predikce vyžaduje live data.")

    else:
        st.error("Nepodařilo se načíst detaily zápasu.")
