import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

from moduly.utils import zobraz_tabulku_s_prepinacem


def render(tab):
    with tab:
        st.header("⚔️ Porovnání 2 Úvěrů (a investice rozdílu)")
        cd1, cd2, cd3 = st.columns(3)
        with cd1:
            st.error("🟥 ÚVĚR A (Krátký)")
            ua_vyse = st.number_input("Výše úvěru A", value=600000.0, step=10000.0, key="ua1")
            ua_sazba = st.number_input("Sazba A (%)", value=6.9, step=0.1, key="ua2")
            ua_roky = st.number_input("Doba A (let)", value=8, step=1, key="ua3")
            spl_a = -npf.pmt((ua_sazba / 100) / 12, ua_roky * 12, ua_vyse) if ua_roky > 0 else 0
            st.write(f"Splátka A: **{spl_a:,.0f} Kč**".replace(",", " "))

        with cd2:
            st.warning("🟧 ÚVĚR B (Roztažený)")
            ub_vyse = st.number_input("Výše úvěru B", value=600000.0, step=10000.0, key="ub1")
            ub_sazba = st.number_input("Sazba B (%)", value=5.9, step=0.1, key="ub2")
            ub_roky = st.number_input("Doba B (let)", value=20, step=1, key="ub3")
            spl_b = -npf.pmt((ub_sazba / 100) / 12, ub_roky * 12, ub_vyse) if ub_roky > 0 else 0
            st.write(f"Splátka B: **{spl_b:,.0f} Kč**".replace(",", " "))
            rozdil_ab = max(0, spl_a - spl_b)

        with cd3:
            st.success("🟩 INVESTIČNÍ MOTOR")
            if rozdil_ab > 0:
                st.info(f"💡 Rozdíl splátek je **{rozdil_ab:,.0f} Kč**. Můžete ho (nebo jeho část) investovat níže.".replace(",", " "))
            i3_1a = st.number_input("Jednorázovka A", value=0.0, step=10000.0, key="i3a1")
            i3_pa = st.number_input("Pravidelně do A", value=0.0, step=500.0, key="i3a2")
            i3_ra = st.number_input("Úrok Portfolia A (%)", value=4.0, step=0.1, key="i3a3")
            st.markdown("---")
            odk_a = st.number_input("Odkup z A do B", value=0.0, step=1000.0, key="i3o")
            st.markdown("---")
            i3_1b = st.number_input("Jednorázovka B", value=0.0, step=10000.0, key="i3b1")
            i3_pb = st.number_input("Pravidelně do B", value=3000.0, step=500.0, key="i3b2")
            i3_rb = st.number_input("Úrok Portfolia B (%)", value=8.0, step=0.1, key="i3b3")

        max_m = int(max(ua_roky, ub_roky)) * 12
        za, zb = ua_vyse, ub_vyse
        pa, pb = i3_1a, i3_1b
        vlozeno = i3_1a + i3_1b
        urok_a_celkem, urok_b_celkem = 0, 0
        data_duel = []

        for m in range(1, max_m + 1):
            aktualni_spl_a, aktualni_spl_b = 0, 0
            if za > 0:
                ua_m = za * (ua_sazba / 100) / 12
                uma = spl_a - ua_m
                if uma > za: uma = za
                za -= uma; urok_a_celkem += ua_m; aktualni_spl_a = uma + ua_m
            if zb > 0:
                ub_m = zb * (ub_sazba / 100) / 12
                umb = spl_b - ub_m
                if umb > zb: umb = zb
                zb -= umb; urok_b_celkem += ub_m; aktualni_spl_b = umb + ub_m

            pa = pa * (1 + (i3_ra / 100) / 12) + i3_pa
            pb = pb * (1 + (i3_rb / 100) / 12) + i3_pb
            vlozeno += i3_pa + i3_pb
            skut_odk = min(pa, odk_a)
            pa -= skut_odk; pb += skut_odk

            data_duel.append({
                "Měsíc": m, "Rok": m / 12,
                "Zůstatek A": za, "Splátka A": aktualni_spl_a, "Úroky A": urok_a_celkem,
                "Zůstatek B": zb, "Splátka B": aktualni_spl_b, "Úroky B": urok_b_celkem,
                "Portfolio A": pa, "Portfolio B": pb, "Čistý Výnos B+Inv": (pa + pb) - vlozeno
            })

        df_duel2 = pd.DataFrame(data_duel)
        st.markdown("---")
        max_rok_duel = int(max(ua_roky, ub_roky)) if max(ua_roky, ub_roky) > 0 else 30
        rok_duel = st.slider("Porovnat v roce:", 1, max_rok_duel, min(8, max_rok_duel), key="sl_d")

        if not df_duel2.empty:
            idx = min((rok_duel * 12) - 1, len(df_duel2) - 1)
            if idx >= 0:
                row_d = df_duel2.iloc[idx]
                r1, r2 = st.columns(2)
                r1.error(
                    f"**STRATEGIE A (Krátká)**\n\n"
                    f"Zůstatek dluhu: {row_d['Zůstatek A']:,.0f} Kč\n"
                    f"Zaplacené úroky: {row_d['Úroky A']:,.0f} Kč\n\n"
                    f"Čisté jmění: {-row_d['Zůstatek A']:,.0f} Kč".replace(",", " ")
                )
                r2.success(
                    f"**STRATEGIE B (Roztažení + Investice)**\n\n"
                    f"Zůstatek dluhu: {row_d['Zůstatek B']:,.0f} Kč\n"
                    f"Zaplacené úroky: {row_d['Úroky B']:,.0f} Kč\n"
                    f"Hodnota Investic: {(row_d['Portfolio A'] + row_d['Portfolio B']):,.0f} Kč "
                    f"(z toho výnos: {row_d['Čistý Výnos B+Inv']:,.0f} Kč)\n\n"
                    f"Čisté jmění: {(row_d['Portfolio A'] + row_d['Portfolio B'] - row_d['Zůstatek B']):,.0f} Kč".replace(",", " ")
                )

            fig_d2 = go.Figure()
            fig_d2.add_trace(go.Scatter(x=df_duel2["Rok"], y=df_duel2["Zůstatek A"],
                                        name="Dluh A", line=dict(color='#ff4b4b')))
            fig_d2.add_trace(go.Scatter(x=df_duel2["Rok"], y=df_duel2["Zůstatek B"],
                                        name="Dluh B", line=dict(color='#ffa500')))
            fig_d2.add_trace(go.Scatter(x=df_duel2["Rok"], y=df_duel2["Portfolio A"] + df_duel2["Portfolio B"],
                                        name="Investice (A+B)", line=dict(color='#2ecc71')))
            fig_d2.update_layout(template="plotly_dark", title="Srovnání zůstatků a investic")
            st.plotly_chart(fig_d2, use_container_width=True)

            with st.expander("📊 Detailní tabulka & Export"):
                zobraz_tabulku_s_prepinacem(df_duel2, "porovnani.csv")
