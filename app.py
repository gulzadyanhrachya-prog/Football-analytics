import streamlit as st
import pandas as pd
import numpy as np

# 1. Nadpis stránky
st.title("⚽ Můj Sportovní Analytik")
st.header("Analýza zápasů a predikce")

# 2. Textový úvod
st.write("""
Vítej v mé aplikaci! Zde budeme sledovat statistiky a předpovídat výsledky.
Zatím je to jen ukázka, ale brzy sem napojíme živá data.
""")

# 3. Vytvoření fiktivních dat (jako tabulka v Excelu)
data = pd.DataFrame({
    'Tým': ['Sparta Praha', 'Slavia Praha', 'Viktoria Plzeň', 'Baník Ostrava'],
    'Pravděpodobnost výhry (%)': [65, 60, 45, 30],
    'Forma (body)': [12, 10, 13, 7],
    'Zranění': [1, 2, 0, 3]
})

# 4. Zobrazení tabulky na webu
st.subheader("Aktuální přehled týmů")
st.dataframe(data)

# 5. Vykreslení grafu
st.subheader("Graf šancí na výhru")
st.bar_chart(data.set_index('Tým')['Pravděpodobnost výhry (%)'])

# 6. Interaktivní prvek (tlačítko)
if st.button('Aktualizovat data'):
    st.success('Data byla úspěšně načtena! (Simulace)')
