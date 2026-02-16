import streamlit as st
import pandas as pd
import cloudscraper
from datetime import datetime, timedelta
import io

st.set_page_config(page_title="Feedinco Hunter", layout="wide")

# ==============================================================================\n# 1. SCRAPING ENGINE (Feedinco)\n# ==============================================================================\n
@st.cache_data(ttl=1800) # Cache 30 minut
def scrape_feedinco(day="today"):
    # Feedinco má jednoduché URL
    if day == "today":
        url = "https://feedinco.com/betting-tips-for-today"
    else:
        url = "https://feedinco.com/betting-tips-for-tomorrow"
    
    # Použijeme Cloudscraper, abychom vypadali jako člověk
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(url)
        if r.status_code != 200:
            return None, f"Chyba připojení: {r.status_code}"
        
        # Feedinco je skvělé v tom, že má data v tabulce.
        # Pandas umí číst tabulky přímo z HTML textu.
        dfs = pd.read_html(r.text)
        
        if not dfs:
            return None, "Na stránce nebyla nalezena žádná tabulka."
            
        # Obvykle je to ta největší tabulka na stránce
        df = max(dfs, key=len)
        
        # Vyčistíme data
        # Feedinco sloupce se mohou měnit, ale obvykle obsahují:
        # Match, Prediction, Odds, Result...
        
        return df, None

    except Exception as e:
        return None, str(e)

# ==============================================================================\n# 2. ZPRACOVÁNÍ DAT\n# ==============================================================================\n
def process_feedinco_data(df):
    matches = []
    
    # Převedeme vše na string
    df = df.astype(str)
    
    # Zkusíme identifikovat sloupce
    # Hledáme sloupec, který obsahuje "vs" (Zápas) a sloupec s tipem
    
    col_match = None
    col_tip = None
    col_league = None
    
    for col in df.columns:
        col_lower = col.lower()
        if "match" in col_lower: col_match = col
        if "tip" in col_lower or "prediction" in col_lower: col_tip = col
        if "league" in col_lower or "country" in col_lower: col_league = col
        
    # Pokud jsme nenašli podle názvu, zkusíme podle obsahu prvního řádku
    if not col_match and not df.empty:
        for col in df.columns:
            if "vs" in str(df.iloc[0][col]):
                col_match = col
                break
                
    if not col_match:
        return []

    for idx, row in df.iterrows():
        try:
            match_str = row[col_match]
            
            # Pokud to není zápas, přeskočíme
            if "vs" not in match_str: continue
            
            # Rozdělení týmů
            parts = match_str.split("vs")
            home = parts[0].strip()
            away = parts[1].strip()
            
            # Tip
            tip = row[col_tip] if col_tip else "N/A"
            
            # Liga (pokud existuje)
            liga = row[col_league] if col_league else "Svět"
            
            # Čištění tipu (Feedinco má někdy divné znaky)
            tip = tip.replace("Tip:", "").strip()
            
            matches.append({
                "Liga": liga,
                "Domácí": home,
                "Hosté": away,
                "Tip": tip,
                "Zápas": f"{home} vs {away}"
            })
        except: continue
        
    return matches

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("🎯 Feedinco Betting Tips")
st.caption("Zdroj: Feedinco.com (Agregátor tipů)")

# Výběr dne
col_day, col_status = st.columns([1, 3])
with col_day:
    day_sel = st.radio("Vyber den:", ["Dnes", "Zítra"])
    day_param = "today" if day_sel == "Dnes" else "tomorrow"

with st.spinner("Stahuji tipy z Feedinco..."):
    raw_df, error = scrape_feedinco(day_param)

if error:
    st.error(f"Chyba: {error}")
    st.write("Zkus obnovit stránku.")
elif raw_df is None:
    st.warning("Nepodařilo se načíst tabulku.")
else:
    # Zpracování
    data = process_feedinco_data(raw_df)
    
    if not data:
        st.warning("Tabulka byla stažena, ale nepodařilo se rozpoznat zápasy.")
        with st.expander("Zobrazit surová data (Debug)"):
            st.dataframe(raw_df)
    else:
        df_final = pd.DataFrame(data)
        
        # --- FILTRY ---
        with st.expander("🛠️ Filtrování", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                search = st.text_input("Hledat tým nebo ligu:")
            with c2:
                # Získáme unikátní typy tipů pro filtr
                unique_tips = sorted(df_final["Tip"].unique())
                # Předvybereme běžné tipy
                default_tips = [t for t in unique_tips if t in ["1", "2", "X", "Over 2.5", "BTS", "1X", "X2"]]
                if not default_tips: default_tips = unique_tips # Pokud nic nenajde, vybere vše
                
                filter_tip = st.multiselect("Filtrovat typ sázky:", unique_tips, default=default_tips)
        
        # Aplikace filtrů
        if search:
            df_final = df_final[
                df_final["Liga"].str.contains(search, case=False) | 
                df_final["Domácí"].str.contains(search, case=False) | 
                df_final["Hosté"].str.contains(search, case=False)
            ]
            
        if filter_tip:
            df_final = df_final[df_final["Tip"].isin(filter_tip)]
            
        st.success(f"Nalezeno {len(df_final)} tipů.")
        
        # --- ZOBRAZENÍ ---
        # Seskupení podle ligy
        ligy = df_final["Liga"].unique()
        
        for liga in ligy:
            league_matches = df_final[df_final["Liga"] == liga]
            
            with st.expander(f"🏆 {liga} ({len(league_matches)})", expanded=True):
                for idx, row in league_matches.iterrows():
                    c1, c2, c3, c4 = st.columns([3, 1, 3, 2])
                    
                    with c1:
                        st.markdown(f"<div style='text-align:right; font-weight:bold'>{row['Domácí']}</div>", unsafe_allow_html=True)
                    
                    with c2:
                        st.markdown("<div style='text-align:center'>vs</div>", unsafe_allow_html=True)
                    
                    with c3:
                        st.markdown(f"<div style='text-align:left; font-weight:bold'>{row['Hosté']}</div>", unsafe_allow_html=True)
                    
                    with c4:
                        # Barva a formátování tipu
                        tip_text = row['Tip']
                        color = "blue"
                        if tip_text == "1": color = "green"; tip_text = "Výhra Domácí (1)"
                        elif tip_text == "2": color = "red"; tip_text = "Výhra Hosté (2)"
                        elif tip_text == "X": color = "orange"; tip_text = "Remíza (X)"
                        elif "Over" in tip_text: color = "purple"
                        elif "BTS" in tip_text: color = "purple"
                        
                        st.markdown(f":{color}[**{tip_text}**]")
