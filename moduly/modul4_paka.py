import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

from moduly.utils import zobraz_tabulku_s_prepinacem


def render(tab):
    with tab:
        st.header("⚖️ Páka: Vlastní cash vs. Hypotéka")
        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            st.subheader("Parametry Nákupu")
            cena_nemov = st.number_input("Cena nemovitosti", value=5600000.0, step=100000.0)
            vlastni_cash = st.number_input("Mám k dispozici hotovost", value=4000000.0, step=100000.0)
            hypo_sazba = st.number_input("Sazba hypotéky (%)", value=5.5, step=0.1)
            hypo_roky = st.number_input("Doba hypotéky (let)", value=30, step=1)
        with cp2:
            st.subheader("Scénář A: Minimum dluhu")
            uver_konzerva = max(0, cena_nemov - vlastni_cash)
            st.write(f"Nutný úvěr: **{uver_konzerva:,.0f} Kč**".replace(",", " "))
        with cp3:
            st.subheader("Scénář B: Investiční Páka")
            ltv = st.slider("LTV (Kolik si půjčím % z ceny bytu)", 0, 100, 80)
            uver_paka = cena_nemov * (ltv / 100)
            zbytek_cash = vlastni_cash - (cena_nemov - uver_paka)
            st.write(f"Úvěr B: **{uver_paka:,.0f} Kč**".replace(",", " "))
            st.write(f"Volná hotovost pro investice: **{zbytek_cash:,.0f} Kč**".replace(",", " "))

        st.markdown("---")
        st.markdown("### Nastavení Investic (pro Scénář B)")
        ci1, ci2, ci3 = st.columns(3)
        with ci1:
            i_pa = st.number_input("Pravidelka navíc do A", value=0.0, step=1000.0)
            i_ra = st.number_input("Úrok A (%)", value=4.0, step=0.1, key="pr1")
        with ci2:
            i_odk = st.number_input("Odkup z A do B", value=15000.0, step=1000.0, key="pr2")
        with ci3:
            i_pb = st.number_input("Pravidelka navíc do B", value=0.0, step=1000.0)
            i_rb = st.number_input("Úrok B (%)", value=8.0, step=0.1, key="pr3")

        spl_konz = -npf.pmt((hypo_sazba / 100) / 12, hypo_roky * 12, uver_konzerva) if uver_konzerva > 0 and hypo_roky > 0 else 0
        spl_paka = -npf.pmt((hypo_sazba / 100) / 12, hypo_roky * 12, uver_paka) if hypo_roky > 0 else 0

        zk, zp = uver_konzerva, uver_paka
        pa, pb = zbytek_cash, 0
        vlozeno = zbytek_cash
        data_paka = []

        for m in range(1, int(hypo_roky) * 12 + 1):
            if zk > 0: zk -= (spl_konz - (zk * (hypo_sazba / 100) / 12))
            if zp > 0: zp -= (spl_paka - (zp * (hypo_sazba / 100) / 12))

            pa = pa * (1 + (i_ra / 100) / 12) + i_pa
            pb = pb * (1 + (i_rb / 100) / 12) + i_pb
            vlozeno += i_pa + i_pb

            skut_odk = min(pa, i_odk)
            pa -= skut_odk; pb += skut_odk

            data_paka.append({
                "Měsíc": m, "Rok": m / 12,
                "Zůstatek Konzerva": max(0, zk), "Zůstatek Páka": max(0, zp),
                "Investice A+B": pa + pb, "Čistý Výnos": (pa + pb) - vlozeno
            })

        df_paka = pd.DataFrame(data_paka)
        max_rok_paka = int(hypo_roky) if hypo_roky > 0 else 30
        rok_p = st.slider("Analýza v roce:", 1, max_rok_paka, min(10, max_rok_paka), key="sl_p")

        if not df_paka.empty:
            row_p = df_paka.iloc[min((rok_p * 12) - 1, len(df_paka) - 1)]
            cista_konzerva = -row_p['Zůstatek Konzerva']
            cista_paka = row_p['Investice A+B'] - row_p['Zůstatek Páka']
            rozdil = cista_paka - cista_konzerva

            if rozdil > 0:
                st.markdown(
                    f'<div class="big-verdict verdict-yes">✅ PÁKA SE VYPLATÍ! '
                    f'Zvolením vyšší hypotéky a investováním volné hotovosti budete mít po {rok_p} letech '
                    f'o {rozdil:,.0f} Kč více.</div>'.replace(",", " "),
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    '<div class="big-verdict verdict-no">❌ KONZERVA JE LEPŠÍ. '
                    'Výnosy nepokryjí drahé úroky. Vložte peníze raději do bytu.</div>',
                    unsafe_allow_html=True
                )

            fig_p = go.Figure()
            fig_p.add_trace(go.Scatter(x=df_paka["Rok"], y=df_paka["Zůstatek Konzerva"],
                                       name="Dluh (Malý)", line=dict(color='orange', dash='dot')))
            fig_p.add_trace(go.Scatter(x=df_paka["Rok"], y=df_paka["Zůstatek Páka"],
                                       name="Dluh (Páka)", line=dict(color='red')))
            fig_p.add_trace(go.Scatter(x=df_paka["Rok"], y=df_paka["Investice A+B"],
                                       name="Investice (A+B)", line=dict(color='green')))
            fig_p.update_layout(template="plotly_dark", title="Srovnání majetku a dluhů v čase")
            st.plotly_chart(fig_p, use_container_width=True)

            with st.expander("📊 Detailní tabulka & Export"):
                zobraz_tabulku_s_prepinacem(df_paka, "paka.csv")
