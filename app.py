rowse files". Nahraj tam ten stažený soubor.import streamlit as st
import json
import yaml # Pro jistotu, kdyby to bylo YAML

st.set_page_config(page_title="OpenAPI Reader", layout="wide")
st.title("📂 Analyzátor OpenAPI Dokumentu")

st.write("Nahraj sem ten soubor, co jsi stáhl (obvykle swagger.json nebo openapi.yaml).")

uploaded_file = st.file_uploader("Vyber soubor", type=["json", "yaml", "yml", "txt"])

if uploaded_file is not None:
    try:
        # Zkusíme načíst jako JSON
        content = json.load(uploaded_file)
        st.success("✅ Soubor načten jako JSON.")
    except:
        try:
            # Pokud ne, zkusíme jako YAML
            uploaded_file.seek(0)
            content = yaml.safe_load(uploaded_file)
            st.success("✅ Soubor načten jako YAML.")
        except Exception as e:
            st.error(f"Nepodařilo se přečíst soubor: {e}")
            st.stop()

    # --- HLEDÁNÍ PŘIHLAŠOVACÍCH ÚDAJŮ ---
    st.header("🔐 Jak se přihlásit?")
    
    security_schemes = content.get("components", {}).get("securitySchemes", {})
    if not security_schemes:
        # Starší verze Swaggeru
        security_schemes = content.get("securityDefinitions", {})
        
    if security_schemes:
        st.json(security_schemes)
        
        # Analýza pro člověka
        for name, details in security_schemes.items():
            typ = details.get("type")
            in_loc = details.get("in") # header / query
            key_name = details.get("name") # To je to, co hledáme!
            
            st.info(f"👉 **Musíme poslat klíč v: {in_loc}**")
            st.info(f"👉 **Název parametru musí být: `{key_name}`**")
    else:
        st.warning("V dokumentu nebyla nalezena sekce 'securitySchemes'.")

    # --- HLEDÁNÍ ADRESY SERVERU ---
    st.header("🌍 Adresa serveru (Base URL)")
    servers = content.get("servers", [])
    if servers:
        st.write(servers)
    else:
        host = content.get("host")
        basePath = content.get("basePath", "")
        if host:
            st.write(f"Host: https://{host}{basePath}")

    # --- ZOBRAZENÍ CELÉHO SOUBORU (PRO KONTROLU) ---
    with st.expander("Zobrazit celý obsah souboru"):
        st.json(content)
