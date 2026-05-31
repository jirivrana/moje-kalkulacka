import streamlit as st
import numpy_financial as npf


def render(tab):
    with tab:
        st.header("🧮 Rychlý dopočet (Solver)")
        cil = st.selectbox("Vyberte neznámou:", [
            "Měsíční splátka", "Maximální výše úvěru", "Doba splácení", "Úroková sazba"
        ])
        col_vstup, col_vystup = st.columns([1, 1])
        with col_vstup:
            if cil != "Maximální výše úvěru":
                tvm_uver = st.number_input("Výše úvěru", value=2000000.0, step=50000.0)
            if cil != "Měsíční splátka":
                tvm_splatka = st.number_input("Splátka", value=12000.0, step=500.0)
            if cil != "Úroková sazba":
                tvm_sazba = st.number_input("Sazba (%)", value=4.9, step=0.1)
            if cil != "Doba splácení":
                tvm_roky = st.number_input("Doba (roky)", value=20, step=1)
        with col_vystup:
            try:
                if cil == "Měsíční splátka":
                    res = -npf.pmt((tvm_sazba / 100) / 12, tvm_roky * 12, tvm_uver)
                    st.metric("Vypočítaná splátka", f"{res:,.0f} Kč".replace(",", " "))
                elif cil == "Maximální výše úvěru":
                    res = npf.pv((tvm_sazba / 100) / 12, tvm_roky * 12, -tvm_splatka)
                    st.metric("Můžete si půjčit", f"{res:,.0f} Kč".replace(",", " "))
                elif cil == "Doba splácení":
                    mesice = npf.nper((tvm_sazba / 100) / 12, -tvm_splatka, tvm_uver)
                    st.metric("Budete splácet", f"{mesice / 12:.1f} let ({mesice:.0f} měsíců)")
                elif cil == "Úroková sazba":
                    res = npf.rate(tvm_roky * 12, -tvm_splatka, tvm_uver) * 12 * 100
                    st.metric("Odpovídající úrok", f"{res:.2f} % p.a.")
            except:
                st.error("Nemá matematické řešení.")
