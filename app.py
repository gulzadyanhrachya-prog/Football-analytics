import streamlit as st
import requests

# --- DIAGNOSTIKA ---
st.title("🛠️ Diagnostika připojení")

# 1. Kontrola, zda Streamlit vidí klíč
if "FOOTBALL_API_KEY" in st.secrets:
    st.success("✅ Klíč v Secrets nalezen.")
    api_key = st.secrets["FOOTBALL_API_KEY"]
    # Ukážeme jen první 4 znaky pro kontrolu, zbytek hvězdičky
    st.write(f"Načtený klíč: `{api_key[:4]}...`")
else:
    st.error("❌ Klíč 'FOOTBALL_API_KEY' v Secrets chybí!")
    st.stop()

# 2. Testovací připojení na API
st.write("Zkouším se připojit k serveru football-data.org...")

url = "https://api.football-data.org/v4/competitions/PL/standings"
headers = {'X-Auth-Token': api_key}

try:
    response = requests.get(url, headers=headers)
    
    # Vypíšeme návratový kód (200 = OK, 403 = Zakázáno, 404 = Nenalezeno)
    st.write(f"Status kód: **{response.status_code}**")
    
    if response.status_code == 200:
        st.success("🎉 PŘIPOJENÍ ÚSPĚŠNÉ! Data se stáhla.")
        st.json(response.json()) # Ukáže surová data
    else:
        st.error("⚠️ Chyba připojení!")
        st.write("Server odpověděl tímto textem:")
        st.code(response.text) # Toto je důležité - text chyby od serveru

except Exception as e:
    st.error(f"Kritická chyba v Pythonu: {e}")
