import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# 1. Nastavení stránky (Musí být první)
try:
    st.set_page_config(page_title="Rescue Mode", layout="wide")
    st.title("🛠️ Diagnostický Režim")
    st.write("✅ Krok 1: Streamlit běží.")
except Exception as e:
    st.error(f"Chyba v konfiguraci stránky: {e}")

# 2. Importy matematiky (Často způsobují pád, pokud chybí scipy)
try:
    from scipy.stats import poisson
    st.write("✅ Krok 2: Matematické knihovny (Scipy) načteny.")
except ImportError:
    st.error("❌ CHYBA: Chybí knihovna 'scipy'. Přidej ji do requirements.txt!")
    st.stop()

# --- FUNKCE PRO STAŽENÍ DAT (S Timeoutem) ---
@st.cache_data(ttl=3600)
def get_clubelo_data():
    url = "http://api.clubelo.com/Fixtures"
    try:
        # Přidán timeout 5 sekund, aby se to nezaseklo
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        return None
    except Exception as e:
        st.warning(f"ClubElo neodpovídá: {e}")
        return None

@st.cache_data(ttl=3600)
def get_nhl_data():
    try:
        url = f"https://api-web.nhle.com/v1/schedule/{datetime.now().strftime('%Y-%m-%d')}"
        response = requests.get(url, timeout=5)
        return response.json()
    except Exception as e:
        st.warning(f"NHL API neodpovídá: {e}")
        return None

# --- MATEMATICKÉ MODELY ---
def calculate_poisson_probs(home_xg, away_xg):
    max_g = 6
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg)
    
    prob_h = np.sum(np.tril(matrix, -1))
    prob_d = np.sum(np.diag(matrix))
    prob_a = np.sum(np.triu(matrix, 1))
    return prob_h, prob_d, prob_a

# --- HLAVNÍ ROZHRANÍ ---
st.write("✅ Krok 3: Funkce definovány. Spouštím rozhraní...")

sport = st.radio("Vyber modul:", ["⚽ Fotbal (ClubElo)", "🏒 Hokej (NHL)", "🔍 Test API"])

if sport == "⚽ Fotbal (ClubElo)":
    st.header("Fotbalový Auto-Pilot")
    
    with st.spinner("Stahuji data z ClubElo..."):
        df = get_clubelo_data()
        
    if df is not None:
        st.success(f"Staženo {len(df)} zápasů.")
        
        # Zpracování data
        try:
            df['DateObj'] = pd.to_datetime(df['Date'])
            dnes = datetime.now()
            limit = dnes + timedelta(days=3)
            mask = (df['DateObj'] >= dnes) & (df['DateObj'] <= limit)
            upcoming = df[mask].copy()
            
            if upcoming.empty:
                st.info("Žádné zápasy v příštích 3 dnech.")
            else:
                results = []
                for idx, row in upcoming.iterrows():
                    try:
                        elo_h = row.get('EloHome')
                        elo_a = row.get('EloAway')
                        
                        if pd.isna(elo_h) or pd.isna(elo_a): continue
                        
                        # Jednoduchý model
                        elo_diff = elo_h - elo_a + 100
                        xg_h = max(0.5, 1.35 + (elo_diff/500))
                        xg_a = max(0.5, 1.35 - (elo_diff/500))
                        
                        ph, pd_raw, pa = calculate_poisson_probs(xg_h, xg_a)
                        
                        # Výběr tipu
                        if ph > 0.6: tip = "1"; conf = ph
                        elif pa > 0.6: tip = "2"; conf = pa
                        else: tip = "Risk/Remíza"; conf = pd_raw
                        
                        results.append({
                            "Datum": row['DateObj'].strftime("%d.%m."),
                            "Zápas": f"{row['Home']} vs {row['Away']}",
                            "Tip": tip,
                            "Důvěra": f"{conf*100:.1f}%"
                        })
                    except: continue
                
                if results:
                    st.dataframe(pd.DataFrame(results))
                else:
                    st.warning("Nepodařilo se vypočítat predikce (chybí Elo data).")
                    
        except Exception as e:
            st.error(f"Chyba při zpracování dat: {e}")
    else:
        st.error("Data z ClubElo se nepodařilo stáhnout.")

elif sport == "🏒 Hokej (NHL)":
    st.header("NHL Auto-Pilot")
    
    with st.spinner("Stahuji data z NHL..."):
        data = get_nhl_data()
        
    if data and 'gameWeek' in data:
        games_list = []
        for day in data['gameWeek']:
            for game in day['games']:
                h = game['homeTeam']['abbrev']
                a = game['awayTeam']['abbrev']
                games_list.append(f"{day['date']}: {h} vs {a}")
        
        if games_list:
            st.write("Nalezené zápasy:")
            st.write(games_list)
        else:
            st.info("Žádné zápasy v tomto týdnu.")
    else:
        st.error("Chyba NHL API.")

elif sport == "🔍 Test API":
    st.header("Test připojení")
    if st.button("Ping Google.com"):
        try:
            r = requests.get("https://google.com", timeout=2)
            st.success(f"Internet funguje (Status: {r.status_code})")
        except Exception as e:
            st.error(f"Chyba připojení k internetu: {e}")

st.write("✅ Krok 4: Aplikace kompletně načtena.")
