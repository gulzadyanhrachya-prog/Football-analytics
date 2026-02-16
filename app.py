import streamlit as st
import pandas as pd
import cloudscraper
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Vitibet Master", layout="wide")

# ==============================================================================\n# 1. SCRAPING ENGINE (VITIBET)\n# ==============================================================================\n
@st.cache_data(ttl=3600) # Cache 1 hodina
def scrape_vitibet():
    # Vitibet má stránku s tipy na příštích 7 dní
    url = "https://www.vitibet.com/index.php?lang=en&clanek=quicktips&sekce=fotbal"
    
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(url)
        if r.status_code != 200: return None, f"Chyba připojení: {r.status_code}"
        
        # Přečteme všechny tabulky
        dfs = pd.read_html(r.text)
        
        matches = []
        current_league = "Ostatní"
        
        # Vitibet má jednu obří tabulku, kde se střídají hlavičky lig a zápasy
        # Musíme najít tu největší tabulku
        main_df = max(dfs, key=len)
        
        # Převedeme na string
        main_df = main_df.astype(str)
        
        # Iterace
        for idx, row in main_df.iterrows():
            try:
                col0 = str(row.iloc[0]) # Datum
                col1 = str(row.iloc[1]) # Domácí
                col2 = str(row.iloc[2]) # Skóre/Predikce
                col3 = str(row.iloc[3]) # Hosté
                
                # 1. DETEKCE LIGY
                # Pokud je řádek krátký nebo má specifickou barvu (v HTML), je to liga.
                # V pandas to poznáme tak, že chybí datum (col0) nebo je divné.
                if len(col0) > 5 and "." not in col0: 
                    # Pravděpodobně název ligy
                    current_league = col0
                    continue
                
                # 2. DETEKCE ZÁPASU
                # Musí mít datum ve formátu DD.MM
                if "." in col0 and len(col0) <= 5:
                    # Je to zápas!
                    
                    # Vitibet formát predikce: "2:1" nebo "1:0"
                    pred_score = col2
                    
                    # Index (Pravděpodobnost) bývá ve sloupci 4 nebo 5
                    # Hledáme číslo, které vypadá jako tip (1, 0, 2)
                    tip = "N/A"
                    if len(row) > 5:
                        tip_raw = str(row.iloc[5])
                        if tip_raw in ["1", "0", "2", "10", "02"]:
                            tip = tip_raw
                    
                    # Pokud nemáme tip z tabulky, odvodíme ho ze skóre
                    if tip == "N/A" and ":" in pred_score:
                        try:
                            g1, g2 = map(int, pred_score.split(":"))
                            if g1 > g2: tip = "1"
                            elif g2 > g1: tip = "2"
                            else: tip = "0"
                        except: pass

                    matches.append({
                        "Datum": col0,
                        "Liga": current_league,
                        "Domácí": col1,
                        "Hosté": col3,
                        "Predikce Skóre": pred_score,
                        "Tip": tip
                    })
            except: continue
            
        return matches, None

    except Exception as e:
        return None, str(e)

# ==============================================================================\n# 2. ANALÝZA SÁZEK\n# ==============================================================================\n
def analyze_bet(match):
    score = match["Predikce Skóre"]
    tip = match["Tip"]
    
    recommendations = []
    
    # 1. Hlavní tip
    if tip == "1": recommendations.append(f"Výhra {match['Domácí']}")
    elif tip == "2": recommendations.append(f"Výhra {match['Hosté']}")
    elif tip == "0": recommendations.append("Remíza")
    elif tip == "10": recommendations.append(f"Neprohra {match['Domácí']}")
    elif tip == "02": recommendations.append(f"Neprohra {match['Hosté']}")
    
    # 2. Góly (podle predikovaného skóre)
    if ":" in score:
        try:
            g1, g2 = map(int, score.split(":"))
            total = g1 + g2
            
            if total >= 3: recommendations.append("Over 2.5 Gólů")
            if total < 3: recommendations.append("Under 3.5 Gólů")
            if g1 > 0 and g2 > 0: recommendations.append("BTTS (Oba dají gól)")
            
            # Handicap
            if g1 - g2 >= 2: recommendations.append(f"Handicap {match['Domácí']} -1.5")
            if g2 - g1 >= 2: recommendations.append(f"Handicap {match['Hosté']} -1.5")
            
        except: pass
        
    return ", ".join(recommendations)

# ==============================================================================\n# 3. UI APLIKACE\n# ==============================================================================\n
st.title("🔮 Vitibet Master Analyst")
st.caption("Zdroj: Vitibet.com (Kompletní přehled na 7 dní)")

with st.spinner("Stahuji kompletní nabídku zápasů..."):
    data, error = scrape_vitibet()

if error:
    st.error(f"Chyba: {error}")
    st.write("Zkus obnovit stránku za chvíli.")
elif not data:
    st.warning("Nebyly nalezeny žádné zápasy. Web může mít výpadek.")
else:
    df = pd.DataFrame(data)
    
    # --- FILTRY ---
    st.sidebar.header("🔍 Filtry")
    
    # 1. Filtr Ligy
    all_leagues = sorted(df["Liga"].unique())
    # Zkusíme najít oblíbené
    favorites = ["ENGLAND", "GERMANY", "SPAIN", "ITALY", "FRANCE", "CZECH", "POLAND", "DENMARK", "PORTUGAL", "NETHERLANDS"]
    
    # Vytvoříme seznam, kde jsou oblíbené nahoře
    sorted_leagues = []
    for fav in favorites:
        for l in all_leagues:
            if fav in l.upper(): sorted_leagues.append(l)
    
    # Přidáme zbytek
    for l in all_leagues:
        if l not in sorted_leagues: sorted_leagues.append(l)
        
    selected_leagues = st.sidebar.multiselect("Vyber ligy:", sorted_leagues)
    
    # 2. Filtr Data
    all_dates = sorted(df["Datum"].unique())
    selected_dates = st.sidebar.multiselect("Vyber datum:", all_dates, default=all_dates[:2]) # Defaultně první 2 dny
    
    # 3. Hledání týmu
    search_team = st.sidebar.text_input("Hledat tým (např. Sparta):")
    
    # --- APLIKACE FILTRŮ ---
    df_show = df.copy()
    
    if selected_leagues:
        df_show = df_show[df_show["Liga"].isin(selected_leagues)]
        
    if selected_dates:
        df_show = df_show[df_show["Datum"].isin(selected_dates)]
        
    if search_team:
        df_show = df_show[
            df_show["Domácí"].str.contains(search_team, case=False) | 
            df_show["Hosté"].str.contains(search_team, case=False)
        ]
        
    # --- ZOBRAZENÍ ---
    st.success(f"Zobrazeno {len(df_show)} zápasů.")
    
    # Seskupení podle ligy pro hezčí výpis
    grouped = df_show.groupby("Liga")
    
    for league, group in grouped:
        with st.expander(f"🏆 {league} ({len(group)} zápasů)", expanded=True):
            for idx, row in group.iterrows():
                analysis = analyze_bet(row)
                
                c1, c2, c3, c4 = st.columns([1, 3, 1, 3])
                
                with c1:
                    st.write(f"**{row['Datum']}**")
                
                with c2:
                    st.write(f"**{row['Domácí']}**")
                    st.write(f"**{row['Hosté']}**")
                    
                with c3:
                    st.metric("Predikce", row["Predikce Skóre"])
                    
                with c4:
                    if "Výhra" in analysis:
                        st.success(analysis)
                    elif "Remíza" in analysis:
                        st.warning(analysis)
                    else:
                        st.info(analysis)
                
                st.markdown("---")
