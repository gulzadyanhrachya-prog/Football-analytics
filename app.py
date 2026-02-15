import streamlit as st
import pandas as pd
import cloudscraper
from datetime import datetime

st.set_page_config(page_title="VitiSport Analyzer", layout="wide")

# --- FUNKCE PRO STAŽENÍ DAT (VitiSport) ---
@st.cache_data(ttl=1800) # Cache na 30 minut
def scrape_vitisport(sport_type):
    # sport_type: "fotbal" nebo "tenis"
    url = f"https://www.vitisport.cz/index.php?g={sport_type}&lang=cs"
    
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(url)
        if r.status_code != 200:
            return None, f"Chyba připojení: {r.status_code}"
        
        # Pandas najde všechny tabulky
        dfs = pd.read_html(r.text)
        
        matches = []
        current_league = "Ostatní"
        
        # Projdeme tabulky. VitiSport má jednu velkou tabulku, kde se střídají nadpisy lig a zápasy.
        # Musíme najít tu hlavní tabulku (obvykle ta největší)
        main_df = max(dfs, key=len)
        
        # Převedeme na string pro zpracování
        main_df = main_df.astype(str)
        
        for idx, row in main_df.iterrows():
            # Zkusíme detekovat, co je v řádku
            col0 = str(row.iloc[0]) # Čas nebo Liga
            col1 = str(row.iloc[1]) # Domácí
            col2 = str(row.iloc[2]) # Hosté
            
            # 1. DETEKCE LIGY (Řádek, kde je jen jeden text nebo specifická barva na webu)
            # Na VitiSportu poznáme ligu tak, že v řádku chybí kurz/skóre
            if len(col0) > 2 and ("nan" in col1.lower() or col1 == col0):
                current_league = col0
                continue
                
            # 2. DETEKCE ZÁPASU
            # Musí obsahovat čas (:) a jména týmů
            if ":" in col0 and len(col1) > 1 and len(col2) > 1:
                # Ignorujeme hlavičky tabulky
                if "Domácí" in col1 or "Čas" in col0: continue
                
                # Hledání tipu (VitiSport má tipy ve sloupcích s barvou, v pandas to bývá sloupec 5, 6 nebo podobně)
                # Zkusíme najít sloupec, který obsahuje "1", "0", "2" nebo "10", "02"
                tip = "N/A"
                skore = ""
                
                # Projdeme celý řádek a hledáme tip
                row_values = row.values.tolist()
                
                # Hledáme predikci (často na konci řádku)
                for val in row_values:
                    v = str(val).replace(" ", "")
                    if v in ["1", "0", "2", "10", "02", "12"]:
                        tip = v
                    if ":" in v and len(v) < 6 and v != col0: # Skóre (pokud se už hrálo)
                        skore = v

                matches.append({
                    "Liga": current_league,
                    "Čas": col0,
                    "Domácí": col1,
                    "Hosté": col2,
                    "Tip": tip,
                    "Skóre": skore
                })
                
        return matches, None

    except Exception as e:
        return None, str(e)

# ==========================================
# 1. MODUL: FOTBAL
# ==========================================
def app_fotbal():
    st.header("⚽ Fotbalové Predikce (VitiSport)")
    
    with st.spinner("Stahuji fotbalové zápasy..."):
        matches, error = scrape_vitisport("fotbal")
        
    if error:
        st.error(f"Chyba: {error}")
    elif not matches:
        st.warning("Nebyly nalezeny žádné zápasy.")
    else:
        # Získání seznamu lig pro filtr
        vsechny_ligy = sorted(list(set([m["Liga"] for m in matches])))
        
        # Předdefinované oblíbené ligy (pro rychlý výběr)
        oblibene = [
            "Anglie - Premier League", "Německo - Bundesliga", "Španělsko - LaLiga",
            "Itálie - Serie A", "Francie - Ligue 1", "Česko - 1. Liga",
            "Polsko - Ekstraklasa", "Dánsko - Superliga", "Portugalsko - Liga Portugal",
            "Rumunsko - Liga 1", "Řecko - Super League", "Turecko - Super Lig",
            "Izrael - Ligat ha'Al", "Nizozemsko - Eredivisie", "Belgie - Jupiler Pro League",
            "Anglie - Championship", "Německo - 2. Bundesliga", "Itálie - Serie B",
            "Francie - Ligue 2", "Nizozemsko - Eerste Divisie"
        ]
        
        # Filtr ligy
        st.sidebar.subheader("Filtr Ligy")
        # Najdeme, které z oblíbených jsou dnes v nabídce
        dostupne_oblibene = [l for l in oblibene if any(l in m_liga for m_liga in vsechny_ligy)]
        
        vyber_ligy = st.sidebar.selectbox(
            "Vyber ligu:", 
            ["Všechny zápasy"] + dostupne_oblibene + ["--- Ostatní ---"] + vsechny_ligy
        )
        
        # Filtrování dat
        filtered_matches = []
        for m in matches:
            if vyber_ligy == "Všechny zápasy":
                filtered_matches.append(m)
            elif vyber_ligy == "--- Ostatní ---":
                pass
            elif vyber_ligy in m["Liga"] or m["Liga"] in vyber_ligy:
                filtered_matches.append(m)
        
        st.info(f"Zobrazeno {len(filtered_matches)} zápasů.")
        
        for m in filtered_matches:
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 3, 1, 3])
                
                with c1:
                    st.caption(m["Liga"])
                    st.write(f"**{m['Čas']}**")
                
                with c2:
                    st.markdown(f"<div style='text-align:right'><b>{m['Domácí']}</b></div>", unsafe_allow_html=True)
                
                with c3:
                    if m['Skóre']:
                        st.markdown(f"<div style='text-align:center; font-weight:bold'>{m['Skóre']}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='text-align:center'>vs</div>", unsafe_allow_html=True)
                        
                    # Zobrazení tipu
                    tip = m['Tip']
                    if tip == "1": st.success(f"Tip: 1")
                    elif tip == "2": st.error(f"Tip: 2")
                    elif tip == "0": st.warning(f"Tip: 0")
                    elif tip == "10": st.success(f"Tip: 10")
                    elif tip == "02": st.error(f"Tip: 02")
                
                with c4:
                    st.markdown(f"<div style='text-align:left'><b>{m['Hosté']}</b></div>", unsafe_allow_html=True)
                
                st.markdown("---")

# ==========================================
# 2. MODUL: TENIS
# ==========================================
def app_tenis():
    st.header("🎾 Tenisové Predikce (VitiSport)")
    
    with st.spinner("Stahuji tenisové zápasy..."):
        matches, error = scrape_vitisport("tenis")
        
    if error:
        st.error(f"Chyba: {error}")
    elif not matches:
        st.warning("Nebyly nalezeny žádné zápasy.")
    else:
        # Filtr turnajů
        turnaje = sorted(list(set([m["Liga"] for m in matches])))
        atp_wta = [t for t in turnaje if "ATP" in t or "WTA" in t or "Challenger" in t]
        
        st.sidebar.subheader("Filtr Turnaje")
        filtr_turnaj = st.sidebar.selectbox("Vyber turnaj:", ["Všechny ATP/WTA"] + ["Vše"] + turnaje)
        
        filtered_matches = []
        for m in matches:
            if filtr_turnaj == "Vše":
                filtered_matches.append(m)
            elif filtr_turnaj == "Všechny ATP/WTA":
                if "ATP" in m["Liga"] or "WTA" in m["Liga"] or "Challenger" in m["Liga"]:
                    filtered_matches.append(m)
            elif m["Liga"] == filtr_turnaj:
                filtered_matches.append(m)
                
        st.info(f"Zobrazeno {len(filtered_matches)} zápasů.")
        
        for m in filtered_matches:
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 3, 1, 3])
                
                with c1:
                    st.caption(m["Liga"])
                    st.write(f"**{m['Čas']}**")
                
                with c2:
                    st.markdown(f"<div style='text-align:right'><b>{m['Domácí']}</b></div>", unsafe_allow_html=True)
                
                with c3:
                    if m['Skóre']:
                        st.markdown(f"<div style='text-align:center; font-weight:bold'>{m['Skóre']}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='text-align:center'>vs</div>", unsafe_allow_html=True)
                    
                    tip = m['Tip']
                    if tip == "1": st.success("Tip: 1")
                    elif tip == "2": st.error("Tip: 2")
                    else: st.info(f"Tip: {tip}")
                
                with c4:
                    st.markdown(f"<div style='text-align:left'><b>{m['Hosté']}</b></div>", unsafe_allow_html=True)
                
                st.markdown("---")

# ==========================================
# HLAVNÍ ROZCESTNÍK
# ==========================================
st.sidebar.title("🏆 Sportovní Centrum")
sport = st.sidebar.radio("Vyber sport:", ["⚽ Fotbal", "🎾 Tenis"])

if sport == "⚽ Fotbal":
    app_fotbal()
elif sport == "🎾 Tenis":
    app_tenis()
