import streamlit as st
import requests

st.set_page_config(page_title="Key Cracker", layout="wide")
st.title("🔐 Hledání správného způsobu přihlášení")

# 1. Načtení klíče
try:
    API_KEY = st.secrets["SGO_KEY"]
    st.info(f"Testuji klíč: {API_KEY[:5]}...*****")
except:
    st.error("Chybí SGO_KEY v Secrets!")
    st.stop()

# 2. Adresa pro test (Seznam sportů - to by mělo fungovat vždy)
TEST_URL = "https://api.sportsgameodds.com/v1/sports"

# 3. Definice metod přihlášení
methods = [
    {
        "name": "Header: X-Api-Key",
        "headers": {"X-Api-Key": API_KEY},
        "params": {}
    },
    {
        "name": "Header: x-api-key (malá písmena)",
        "headers": {"x-api-key": API_KEY},
        "params": {}
    },
    {
        "name": "Header: Authorization Bearer",
        "headers": {"Authorization": f"Bearer {API_KEY}"},
        "params": {}
    },
    {
        "name": "Header: apikey",
        "headers": {"apikey": API_KEY},
        "params": {}
    },
    {
        "name": "URL Parametr: ?key=...",
        "headers": {},
        "params": {"key": API_KEY}
    },
    {
        "name": "URL Parametr: ?api_key=...",
        "headers": {},
        "params": {"api_key": API_KEY}
    }
]

# 4. Spuštění testu
if st.button("SPUSTIT TEST PŘIHLÁŠENÍ"):
    success = False
    
    for method in methods:
        st.write(f"Zkouším metodu: **{method['name']}**...")
        
        try:
            r = requests.get(TEST_URL, headers=method["headers"], params=method["params"])
            
            if r.status_code == 200:
                st.success(f"🎉 ÚSPĚCH! Funguje metoda: {method['name']}")
                st.json(r.json())
                success = True
                break # Našli jsme to, končíme
            else:
                st.warning(f"❌ Neúspěch (Kód {r.status_code})")
                
        except Exception as e:
            st.error(f"Chyba spojení: {e}")
            
    if not success:
        st.error("⛔ Žádná metoda nefungovala. Zkontroluj, zda je klíč správně zkopírovaný (bez mezer) a zda je aktivní.")
