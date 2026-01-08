import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

# --- KONFIGURACE ---
st.set_page_config(page_title="Finanční Centrum", page_icon="🏦", layout="wide")

# --- CSS PRO LEPŠÍ VZHLED ---
st.markdown("""
<style>
    .big-font { font-size:24px !important; font-weight: bold; }
    .metric-container { background-color: #262730; padding: 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

st.title("🏦 Profesionální Finanční Plánovač 3.0")

# --- HLAVNÍ NAVIGACE (ZÁLOŽKY) ---
tab_kalkulacka, tab_porovnani = st.tabs(["🧮 Rychlá TVM Kalkulačka", "⚔️ Porovnání Strategií & Investic"])

# ==========================================
# ZÁLOŽKA 1: RYCHLÁ KALKULAČKA (SOLVER)
# ==========================================
with tab_kalkulacka:
    st.header("Co potřebujete vypočítat?")
    
    # Výběr cílové proměnné
    cil = st.selectbox("Vyberte neznámou:", 
                       ["Měsíční splátka", "Maximální výše úvěru", "Doba splácení", "Úroková sazba"])
    
    col_vstup, col_vystup = st.columns([1, 1])
    
    with col_vstup:
        st.subheader("Zadejte známé parametry:")
        
        # Logika zobrazování polí podle toho, co počítáme
        
        # 1. Pokud nepočítáme ÚVĚR, musíme ho zadat
        if cil != "Maximální výše úvěru":
            tvm_uver = st.number_input("Výše úvěru (Kč)", value=2000000, step=10000)
        
        # 2. Pokud nepočítáme SPLÁTKU, musíme ji zadat
        if cil != "Měsíční splátka":
            tvm_splatka = st.number_input("Měsíční splátka (Kč)", value=12000, step=500)
            
        # 3. Pokud nepočítáme SAZBU, musíme ji zadat
        if cil != "Úroková sazba":
            tvm_sazba = st.number_input("Úroková sazba (% p.a.)", value=4.9, step=0.1)
            
        # 4. Pokud nepočítáme DOBU, musíme ji zadat
        if cil != "Doba splácení":
            tvm_roky = st.number_input("Doba splácení (roky)", value=20, step=1)

    with col_vystup:
        st.subheader("Výsledek:")
        st.markdown("---")
        
        try:
            if cil == "Měsíční splátka":
                res = -npf.pmt((tvm_sazba/100)/12, tvm_roky*12, tvm_uver)
                st.metric("Vypočítaná splátka", f"{res:,.0f} Kč".replace(",", " "))
                
            elif cil == "Maximální výše úvěru":
                # PV (Rate, Nper, Pmt)
                res = npf.pv((tvm_sazba/100)/12, tvm_roky*12, -tvm_splatka)
                st.metric("Můžete si půjčit", f"{res:,.0f} Kč".replace(",", " "))
                
            elif cil == "Doba splácení":
                # NPER (Rate, Pmt, Pv)
                mesice = npf.nper((tvm_sazba/100)/12, -tvm_splatka, tvm_uver)
                roky = mesice / 12
                st.metric("Budete splácet", f"{roky:.1f} let ({mesice:.0f} měsíců)")
                
            elif cil == "Úroková sazba":
                # RATE (Nper, Pmt, Pv) * 12 * 100
                res = npf.rate(tvm_roky*12, -tvm_splatka, tvm_uver) * 12 * 100
                st.metric("Odpovídající úrok", f"{res:.2f} % p.a.")
                
        except:
            st.error("Zadané parametry nemají matematické řešení (např. splátka je nižší než úroky).")

# ==========================================
# ZÁLOŽKA 2: POROVNÁNÍ STRATEGIÍ (DUEL)
# ==========================================
with tab_porovnani:
    st.markdown("### ⚔️ Porovnání dvou úvěrových scénářů")
    
    # --- VSTUPY PRO DVA ÚVĚRY ---
    c_a, c_b, c_inv = st.columns(3)
    
    with c_a:
        st.error("🟥 SCÉNÁŘ A (Úvěr 1)")
        nazev_a = st.text_input("Název varianty A", "Krátká splatnost")
        uver_a = st.number_input("Výše úvěru A", value=2000000, key="ua")
        sazba_a = st.number_input("Sazba A (%)", value=4.9, key="sa")
        roky_a = st.number_input("Doba A (let)", value=15, key="ra")
        # Výpočet splátky A
        splatka_a = -npf.pmt((sazba_a/100)/12, roky_a*12, uver_a)
        st.markdown(f"Splátka: **{splatka_a:,.0f} Kč**")

    with c_b:
        st.warning("🟧 SCÉNÁŘ B (Úvěr 2)")
        nazev_b = st.text_input("Název varianty B", "Dlouhá splatnost")
        uver_b = st.number_input("Výše úvěru B", value=2000000, key="ub")
        sazba_b = st.number_input("Sazba B (%)", value=4.9, key="sb")
        roky_b = st.number_input("Doba B (let)", value=30, key="rb")
        # Výpočet splátky B
        splatka_b = -npf.pmt((sazba_b/100)/12, roky_b*12, uver_b)
        st.markdown(f"Splátka: **{splatka_b:,.0f} Kč**")
        
        rozdil_splatek = splatka_a - splatka_b
        if rozdil_splatek > 0:
            st.success(f"Rozdíl: {rozdil_splatek:,.0f} Kč")

    with c_inv:
        st.success("🟩 INVESTICE (Offset)")
        st.markdown("Investujeme rozdíl ve splátkách?")
        auto_invest = st.checkbox("Použít rozdíl splátek (A - B)", value=True)
        
        if auto_invest:
            inv_mesicni = max(0, rozdil_splatek)
            st.info(f"Investujeme: {inv_mesicni:,.0f} Kč")
        else:
            inv_mesicni = st.number_input("Vlastní částka investice", value=3000)
            
        inv_urok = st.number_input("Výnos investice (% p.a.)", value=7.0)
        inv_doba = st.slider("Doba investování (let)", 1, 30, 15)

    st.markdown("---")

    # --- VÝPOČTOVÉ JÁDRO PRO GRAFY ---
    # Potřebujeme společnou časovou osu (nejdelší z variant)
    max_mesicu = max(roky_a * 12, roky_b * 12)
    
    data_all = []
    
    # Startovní hodnoty
    zustatek_a = uver_a
    zustatek_b = uver_b
    hodnota_inv = 0
    zaplaceno_a_urok = 0
    zaplaceno_b_urok = 0

    for m in range(1, max_mesicu + 12): # +1 rok rezerva pro graf
        curr_rok = m / 12
        
        # --- A ---
        if m <= roky_a * 12:
            urok = zustatek_a * (sazba_a/100)/12
            umor = splatka_a - urok
            zustatek_a -= umor
            zaplaceno_a_urok += urok
            if zustatek_a < 0: zustatek_a = 0
        
        # --- B ---
        if m <= roky_b * 12:
            urok = zustatek_b * (sazba_b/100)/12
            umor = splatka_b - urok
            zustatek_b -= umor
            zaplaceno_b_urok += urok
            if zustatek_b < 0: zustatek_b = 0
            
        # --- INV ---
        hodnota_inv = hodnota_inv * (1 + (inv_urok/100)/12)
        if m <= inv_doba * 12:
            hodnota_inv += inv_mesicni
            
        data_all.append({
            "Měsíc": m,
            "Rok": curr_rok,
            "Zůstatek A": round(zustatek_a),
            "Zůstatek B": round(zustatek_b),
            "Investice": round(hodnota_inv),
            "Úrok A Kumul": round(zaplaceno_a_urok),
            "Úrok B Kumul": round(zaplaceno_b_urok)
        })

    df = pd.DataFrame(data_all)

    # --- VIZUALIZACE GRAFU ---
    st.subheader("📈 Porovnání vývoje v čase")
    
    fig = go.Figure()
    
    # Linka A
    fig.add_trace(go.Scatter(x=df["Rok"], y=df["Zůstatek A"], name=f"Dluh: {nazev_a}", line=dict(color='#ff4b4b', width=3)))
    # Linka B
    fig.add_trace(go.Scatter(x=df["Rok"], y=df["Zůstatek B"], name=f"Dluh: {nazev_b}", line=dict(color='#ffa500', width=3)))
    # Linka Investice
    fig.add_trace(go.Scatter(x=df["Rok"], y=df["Investice"], name="Hodnota Investice", line=dict(color='#2ecc71', width=3, dash='dot')))

    fig.update_layout(template="plotly_dark", xaxis_title="Roky", yaxis_title="Hodnota (Kč)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # --- INTERAKTIVNÍ ANALÝZA (SLIDERY) ---
    st.subheader("⏱️ Cestování časem: Detailní analýza")
    
    col_anal_1, col_anal_2 = st.columns(2)
    
    with col_anal_1:
        st.caption(f"Analýza pro: {nazev_a}")
        rok_anal_a = st.slider("Časový bod A (roky)", 1, int(roky_a), 5, key="slider_a")
        row_a = df.iloc[(rok_anal_a * 12) - 1]
        
        st.metric("Zůstatek dluhu", f"{row_a['Zůstatek A']:,.0f} Kč".replace(",", " "))
        st.metric("Zaplacené úroky", f"{row_a['Úrok A Kumul']:,.0f} Kč".replace(",", " "))

    with col_anal_2:
        st.caption(f"Analýza pro: {nazev_b} + Investice")
        rok_anal_b = st.slider("Časový bod B (roky)", 1, int(roky_b), 10, key="slider_b")
        # Ošetření indexu
        idx_b = (rok_anal_b * 12) - 1
        if idx_b >= len(df): idx_b = len(df) - 1
        row_b = df.iloc[idx_b]
        
        c1, c2 = st.columns(2)
        c1.metric("Zůstatek dluhu", f"{row_b['Zůstatek B']:,.0f} Kč".replace(",", " "))
        c2.metric("Hodnota Investice", f"{row_b['Investice']:,.0f} Kč".replace(",", " "))
        
        bilance = row_b['Investice'] - row_b['Zůstatek B']
        st.metric("ČISTÁ BILANCE (Majetek - Dluh)", f"{bilance:,.0f} Kč".replace(",", " "), delta="V Plusu" if bilance > 0 else "V Mínusu")

    # Závěrečné tlačítko na export
    with st.expander("📋 Data pro Excel"):
        st.dataframe(df)