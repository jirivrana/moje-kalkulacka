import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

from moduly.utils import zobraz_tabulku_s_prepinacem


def render(tab):
    with tab:
        st.header("🏖️ Renta a Finanční nezávislost (FIRE)")
        f1, f2 = st.columns(2)
        with f1:
            st.subheader("1. Požadavky na Rentu")
            vek_dnes = st.number_input("Váš věk dnes", value=30, step=1)
            vek_cil = st.number_input("Věk odchodu do renty", value=55, step=1)
            vek_konec = st.number_input("Věk dožití (konec simulace)", value=90, step=1)
            cilova_renta = st.number_input("Požadovaná měsíční renta (Kč)", value=40000.0, step=5000.0)
            renta_urok = st.number_input("Očekávaný úrok ve fázi Renty (% p.a.)", value=5.0, step=0.1)
        with f2:
            st.subheader("2. Fáze Budování (Spoření)")
            uz_mam = st.number_input("Už mám naspořeno (Kč)", value=500000.0, step=50000.0)
            sporeni_urok = st.number_input("Úrok ve fázi spoření (% p.a.)", value=8.0, step=0.1)

            potrebny_kapital = (cilova_renta * 12) / (renta_urok / 100) if renta_urok > 0 else 0
            roky_do_cile = vek_cil - vek_dnes

            if roky_do_cile > 0 and potrebny_kapital > 0:
                nutna_ulozka = -npf.pmt(
                    (sporeni_urok / 100) / 12, roky_do_cile * 12, uz_mam, -potrebny_kapital
                )
                st.success(f"Cílový kapitál pro NEKONEČNOU rentu: **{potrebny_kapital:,.0f} Kč**".replace(",", " "))
                st.info(f"K dosažení cíle musíte měsíčně investovat: **{nutna_ulozka:,.0f} Kč**".replace(",", " "))

                majetek = uz_mam
                data_fire = []
                for m in range(1, int(vek_konec - vek_dnes) * 12 + 1):
                    akt_vek = vek_dnes + (m / 12)
                    if akt_vek <= vek_cil:
                        majetek = majetek * (1 + (sporeni_urok / 100) / 12) + nutna_ulozka
                    else:
                        majetek = majetek * (1 + (renta_urok / 100) / 12) - cilova_renta
                        if majetek < 0:
                            majetek = 0
                    data_fire.append({"Měsíc": m, "Věk": akt_vek, "Hodnota Portfolia": majetek})

                df_fire = pd.DataFrame(data_fire)
                st.markdown("---")
                st.subheader("Graf Životního cyklu (Budování vs. Renta)")
                fig_f = go.Figure()
                fig_f.add_trace(go.Scatter(
                    x=df_fire["Věk"], y=df_fire["Hodnota Portfolia"],
                    name="Majetek", fill='tozeroy', line=dict(color='#3498db')
                ))
                fig_f.add_vline(
                    x=vek_cil, line_width=2, line_dash="dash",
                    line_color="red", annotation_text="Odchod do renty"
                )
                fig_f.update_layout(template="plotly_dark", xaxis_title="Věk (roky)", yaxis_title="Kč")
                st.plotly_chart(fig_f, use_container_width=True)

                with st.expander("📊 Tabulka růstu a čerpání majetku v čase"):
                    zobraz_tabulku_s_prepinacem(df_fire, "fire_renta.csv")
            else:
                st.error("Zkontrolujte věk (cílový věk musí být vyšší než současný) a zadaný úrok.")
