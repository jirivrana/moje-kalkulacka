import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from moduly.utils import zobraz_tabulku_s_prepinacem

# --- VÝCHOZÍ HODNOTY ---
VYCHOZI_HODNOTY = {
    "ia1": 1000000.0, "ia2": 5000.0, "ia3": 8.0,
    "infl": 3.0, "inv_idx": True, "io_b": 0.0, "io_v": 0.0,
    "ib1": 0.0, "ib2": 0.0, "ib3": 4.0, "sl_i": 20
}

TYPY_INV_UDALOSTI = [
    "📈 Jednorázový vklad do A (Kč)",
    "📈 Jednorázový vklad do B (Kč)",
    "💸 Jednorázový výběr z A (Spotřeba) (Kč)",
    "💸 Jednorázový výběr z B (Spotřeba) (Kč)",
    "🔄 Změna pravidelné investice do A (Kč)",
    "🔄 Změna pravidelné investice do B (Kč)",
    "🔄 Změna pravidelné renty z A na účet (Kč)",
    "🔄 Změna pravidelné renty z B na účet (Kč)",
    "🔄 Změna měsíčního přesunu z A do B (Kč)",
    "📉 Změna úroku Portfolia A (%)",
    "📉 Změna úroku Portfolia B (%)"
]


def _init_state():
    for k, v in VYCHOZI_HODNOTY.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if 'inv_events' not in st.session_state:
        st.session_state.inv_events = []
    if 'inv_event_id' not in st.session_state:
        st.session_state.inv_event_id = 0


def _pridat_inv_udalost():
    st.session_state.inv_events.append({
        "id": st.session_state.inv_event_id,
        "rok": 10,
        "mesic": 1,
        "typ": "🔄 Změna pravidelné renty z A na účet (Kč)",
        "hodnota": 15000.0
    })
    st.session_state.inv_event_id += 1


def _smazat_inv_udalost(event_id):
    st.session_state.inv_events = [
        ev for ev in st.session_state.inv_events if ev['id'] != event_id
    ]


def render(tab):
    _init_state()

    with tab:
        st.header("📈 Čisté Investice: Generační simulátor (Budování a Čerpání)")

        ci1, ci2, ci3 = st.columns(3)
        with ci1:
            st.subheader("Portfolio A (Konzervativní)")
            st.write("*Např. Dluhopisy, Reality, Hotovost*")
            ia_1 = st.number_input("Jednorázovka A", step=50000.0, key="ia1")
            ia_p = st.number_input("Pravidelka A", step=1000.0, key="ia2")
            ia_r = st.number_input("Úrok A (% p.a.)", step=0.1, key="ia3")

        with ci2:
            st.subheader("Inflace a Indexace")
            inflace_pa = st.number_input("Očekávaná inflace (% p.a.)", step=0.1, key="infl")
            indexovat = st.checkbox(
                "Indexovat pravidelné úložky o inflaci?",
                help="Každý rok se pravidelná investice automaticky navýší o zadanou inflaci.",
                key="inv_idx"
            )
            st.markdown("---")
            st.subheader("Pravidelné Odkupy z Portfolia A (od 1. měsíce)")
            odkup_do_b = st.number_input("Přesun z A do B (Fázování)", step=1000.0, key="io_b")
            odkup_ven = st.number_input("Výběr z A na účet (Renta/Spotřeba)", step=1000.0, key="io_v")

        with ci3:
            st.subheader("Portfolio B (Dynamické)")
            st.write("*Např. Akcie, ETF*")
            ib_1 = st.number_input("Jednorázovka B", step=50000.0, key="ib1")
            ib_p = st.number_input("Pravidelka B (navíc)", step=1000.0, key="ib2")
            ib_r = st.number_input("Úrok B (% p.a.)", step=0.1, key="ib3")

        roky_inv = st.slider("Délka simulace investic (roky)", 1, 50, key="sl_i")

        # --- DYNAMICKÉ UDÁLOSTI ---
        st.markdown("---")
        st.subheader("⏱️ Životní události (Začátek renty, nákupy aut, změny strategií)")
        st.button("➕ Přidat událost do investic", on_click=_pridat_inv_udalost)

        for ev in st.session_state.inv_events:
            with st.container():
                col_d, col_t, col_v, col_del = st.columns([2, 3, 2, 1])

                d1, d2 = col_d.columns(2)
                ev["rok"] = d1.number_input(
                    "Rok simulace", min_value=1, max_value=80,
                    value=int(ev.get("rok", 10)), step=1, key=f"iev_r_{ev['id']}"
                )
                ev["mesic"] = d2.number_input(
                    "Měsíc", min_value=1, max_value=12,
                    value=int(ev.get("mesic", 1)), step=1, key=f"iev_m_{ev['id']}"
                )

                idx = TYPY_INV_UDALOSTI.index(ev["typ"]) if ev["typ"] in TYPY_INV_UDALOSTI else 0
                ev["typ"] = col_t.selectbox("Typ události", TYPY_INV_UDALOSTI, index=idx, key=f"iev_t_{ev['id']}")

                popisek = "Sazba (%)" if "(%)" in ev["typ"] else "Částka (Kč)"
                krok = 0.1 if "(%)" in ev["typ"] else 5000.0
                ev["hodnota"] = col_v.number_input(
                    popisek, value=float(ev.get("hodnota", 0.0)), step=krok, key=f"iev_v_{ev['id']}"
                )
                col_del.button("🗑️ Smazat", key=f"iev_d_{ev['id']}", on_click=_smazat_inv_udalost, args=(ev["id"],))

        # --- ENGINE INVESTIC ---
        pa, pb = ia_1, ib_1
        prav_a, prav_b = ia_p, ib_p
        ur_a, ur_b = ia_r, ib_r

        bezny_odkup_ven_a = odkup_ven
        bezny_odkup_ven_b = 0
        bezny_odkup_do_b = odkup_do_b

        vlozeno = ia_1 + ib_1
        spotrebovano = 0
        vybrano_jednorazove = 0
        celkovy_zisk_a = 0
        celkovy_zisk_b = 0
        data_inv = []

        for m in range(1, (roky_inv * 12) + 1):
            akt_rok = ((m - 1) // 12) + 1
            akt_mes = ((m - 1) % 12) + 1

            if indexovat and akt_mes == 1 and akt_rok > 1:
                prav_a = prav_a * (1 + (inflace_pa / 100))
                prav_b = prav_b * (1 + (inflace_pa / 100))

            for ev in st.session_state.inv_events:
                if ev["rok"] == akt_rok and ev["mesic"] == akt_mes:
                    t = ev["typ"]
                    v = float(ev["hodnota"])
                    if t == "📈 Jednorázový vklad do A (Kč)":
                        pa += v; vlozeno += v
                    elif t == "📈 Jednorázový vklad do B (Kč)":
                        pb += v; vlozeno += v
                    elif t == "💸 Jednorázový výběr z A (Spotřeba) (Kč)":
                        skutecny_vyber = min(pa, v)
                        pa -= skutecny_vyber; spotrebovano += skutecny_vyber; vybrano_jednorazove += skutecny_vyber
                    elif t == "💸 Jednorázový výběr z B (Spotřeba) (Kč)":
                        skutecny_vyber = min(pb, v)
                        pb -= skutecny_vyber; spotrebovano += skutecny_vyber; vybrano_jednorazove += skutecny_vyber
                    elif t == "🔄 Změna pravidelné investice do A (Kč)":
                        prav_a = v
                    elif t == "🔄 Změna pravidelné investice do B (Kč)":
                        prav_b = v
                    elif t == "🔄 Změna pravidelné renty z A na účet (Kč)":
                        bezny_odkup_ven_a = v
                    elif t == "🔄 Změna pravidelné renty z B na účet (Kč)":
                        bezny_odkup_ven_b = v
                    elif t == "🔄 Změna měsíčního přesunu z A do B (Kč)":
                        bezny_odkup_do_b = v
                    elif t == "📉 Změna úroku Portfolia A (%)":
                        ur_a = v
                    elif t == "📉 Změna úroku Portfolia B (%)":
                        ur_b = v

            zisk_a_m = pa * (ur_a / 100) / 12
            zisk_b_m = pb * (ur_b / 100) / 12
            celkovy_zisk_a += zisk_a_m
            celkovy_zisk_b += zisk_b_m

            pa += zisk_a_m + prav_a
            pb += zisk_b_m + prav_b
            vlozeno += prav_a + prav_b

            skut_do_b = min(pa, bezny_odkup_do_b)
            pa -= skut_do_b; pb += skut_do_b

            skut_ven_a = min(pa, bezny_odkup_ven_a)
            pa -= skut_ven_a; spotrebovano += skut_ven_a

            skut_ven_b = min(pb, bezny_odkup_ven_b)
            pb -= skut_ven_b; spotrebovano += skut_ven_b

            inflacni_koeficient = (1 + (inflace_pa / 100)) ** (m / 12)
            celkem_nom = pa + pb
            celkem_real = celkem_nom / inflacni_koeficient
            vynos_nom = (celkem_nom + spotrebovano) - vlozeno

            data_inv.append({
                "Měsíc": m, "Rok": m / 12,
                "Měsíční úložka do A": prav_a, "Měsíční úložka do B": prav_b,
                "Měsíční Renta z A": bezny_odkup_ven_a, "Měsíční Renta z B": bezny_odkup_ven_b,
                "Měsíční přesun A->B": bezny_odkup_do_b,
                "Portfolio A (Nominální)": pa, "Portfolio B (Nominální)": pb,
                "Celkový zisk A": celkovy_zisk_a, "Celkový zisk B": celkovy_zisk_b,
                "Celkem Majetek (Nominální)": celkem_nom,
                "Celkem Majetek (REÁLNÁ KUPNÍ SÍLA)": celkem_real,
                "Spotřebováno / Vybráno ven": spotrebovano,
                "Vloženo z vlastního": vlozeno,
                "Čistý nominální výnos": vynos_nom
            })

        df_inv = pd.DataFrame(data_inv)

        # --- VÝSLEDKY ---
        st.markdown("---")
        st.subheader("Celkové výsledky na konci simulace")

        if not df_inv.empty:
            posledni = df_inv.iloc[-1]

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Nominální majetek celkem", f"{posledni['Celkem Majetek (Nominální)']:,.0f} Kč".replace(",", " "))
            r2.metric("REÁLNÁ kupní síla celkem", f"{posledni['Celkem Majetek (REÁLNÁ KUPNÍ SÍLA)']:,.0f} Kč".replace(",", " "))
            r3.metric("Vybraná Renta / Spotřeba", f"{posledni['Spotřebováno / Vybráno ven']:,.0f} Kč".replace(",", " "))
            r4.metric("Celkový čistý výnos", f"{posledni['Čistý nominální výnos']:,.0f} Kč".replace(",", " "))

            st.markdown("#### 🏦 Rozpad jednotlivých portfolií")
            ca, cb = st.columns(2)
            ca.info(
                f"**🔵 Portfolio A (Konzervativní)**\n\n"
                f"Konečný zůstatek: **{posledni['Portfolio A (Nominální)']:,.0f} Kč**\n"
                f"Vygenerovaný zisk na úrocích: **{posledni['Celkový zisk A']:,.0f} Kč**".replace(",", " ")
            )
            cb.success(
                f"**🟢 Portfolio B (Dynamické)**\n\n"
                f"Konečný zůstatek: **{posledni['Portfolio B (Nominální)']:,.0f} Kč**\n"
                f"Vygenerovaný zisk na úrocích: **{posledni['Celkový zisk B']:,.0f} Kč**".replace(",", " ")
            )

            realny_zisk = posledni['Celkem Majetek (REÁLNÁ KUPNÍ SÍLA)'] - posledni['Vloženo z vlastního']
            if realny_zisk > 0:
                st.markdown(
                    f'<div class="big-verdict verdict-yes">✅ PORAZILI JSTE INFLACI!<br>'
                    f'Vaše strategie funguje skvěle. Zhodnocení překonalo inflaci a vy jste '
                    f'<b>reálně zbohatli o {realny_zisk:,.0f} Kč</b> (v dnešních cenách).<br><br>'
                    f'<span style="font-size: 14px; font-weight: normal;">💡 <i>Vysvětlení grafu:</i> '
                    f'Modrá čára ukazuje číslo na výpisu, ale ta důležitá je červená (reálná kupní síla po inflaci). '
                    f'Všimněte si, že červená čára je bezpečně nad šedou čárou (to, co jste do toho vložili). '
                    f'Vydělali jste!</span></div>'.replace(",", " "),
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="big-verdict verdict-no">❌ INFLACE VÁS PORÁŽÍ!<br>'
                    f'Sice budete mít na účtu nominální zisk, ale reálně si za tyto peníze koupíte '
                    f'o <b>{-realny_zisk:,.0f} Kč méně</b>, než kolik jste do toho ze svého vložili.<br><br>'
                    f'<span style="font-size: 14px; font-weight: normal;">💡 <i>Krutá realita:</i> '
                    f'Inflace ({inflace_pa} % p.a.) je mnohem rychlejší než zhodnocení. '
                    f'Vaše reálná kupní síla (červená čára) se propadla pod hodnotu vašich vkladů (šedá čára).'
                    f'</span></div>'.replace(",", " "),
                    unsafe_allow_html=True
                )

            # --- STROJ ČASU ---
            st.markdown("---")
            st.subheader("⏱️ Stroj času (Analýza portfolií a renty v průběhu let)")
            rok_analyzy = st.slider(
                "Vyberte rok pro detailní rozpad portfolií:",
                1, int(roky_inv), min(10, int(roky_inv)), key="sl_stroj_inv"
            )

            df_rok = df_inv[df_inv['Rok'] == rok_analyzy]
            if not df_rok.empty:
                row_a = df_rok.iloc[-1]
                c_time1, c_time2 = st.columns(2)
                with c_time1:
                    st.markdown(f"#### 🔵 Portfolio A (Stav v {rok_analyzy}. roce)")
                    st.metric("Zůstatek Portfolia A", f"{row_a['Portfolio A (Nominální)']:,.0f} Kč".replace(",", " "))
                    st.write(f"Vyděláno na úrocích do tohoto roku: **{row_a['Celkový zisk A']:,.0f} Kč**".replace(",", " "))
                    st.write(f"Aktuální měsíční renta na účet z A: **{row_a['Měsíční Renta z A']:,.0f} Kč**".replace(",", " "))
                    st.write(f"Aktuální měsíční přesun A ➔ B: **{row_a['Měsíční přesun A->B']:,.0f} Kč**".replace(",", " "))
                with c_time2:
                    st.markdown(f"#### 🟢 Portfolio B (Stav v {rok_analyzy}. roce)")
                    st.metric("Zůstatek Portfolia B", f"{row_a['Portfolio B (Nominální)']:,.0f} Kč".replace(",", " "))
                    st.write(f"Vyděláno na úrocích do tohoto roku: **{row_a['Celkový zisk B']:,.0f} Kč**".replace(",", " "))
                    st.write(f"Aktuální měsíční renta na účet z B: **{row_a['Měsíční Renta z B']:,.0f} Kč**".replace(",", " "))

            # --- GRAF ---
            st.markdown("---")
            fig_i = go.Figure()
            fig_i.add_trace(go.Scatter(x=df_inv["Rok"], y=df_inv["Celkem Majetek (Nominální)"],
                                       name="Celkem (Nominál)", line=dict(color='#3498db', width=3)))
            fig_i.add_trace(go.Scatter(x=df_inv["Rok"], y=df_inv["Celkem Majetek (REÁLNÁ KUPNÍ SÍLA)"],
                                       name="Reálná kupní síla (Očištěno)", line=dict(color='#e74c3c', width=3, dash='dash')))
            fig_i.add_trace(go.Scatter(x=df_inv["Rok"], y=df_inv["Vloženo z vlastního"],
                                       name="Vloženo z vlastního", line=dict(color='#95a5a6')))
            fig_i.add_trace(go.Scatter(x=df_inv["Rok"], y=df_inv["Portfolio A (Nominální)"],
                                       name="Zůstatek Portfolia A", line=dict(color='#9b59b6', dash='dot')))
            fig_i.add_trace(go.Scatter(x=df_inv["Rok"], y=df_inv["Portfolio B (Nominální)"],
                                       name="Zůstatek Portfolia B", line=dict(color='#f1c40f', dash='dot')))
            if spotrebovano > 0:
                fig_i.add_trace(go.Scatter(x=df_inv["Rok"], y=df_inv["Spotřebováno / Vybráno ven"],
                                           name="Vybráno z investic (Renta)", line=dict(color='#2ecc71', dash='dot')))
            fig_i.update_layout(
                template="plotly_dark",
                title=f"Životní cyklus investice: Vliv {inflace_pa}% inflace, fázování a čerpání renty",
                xaxis_title="Roky simulace", yaxis_title="Kč",
                hovermode="x unified"
            )
            st.plotly_chart(fig_i, use_container_width=True)

            with st.expander("📊 Detailní tabulka & Přesný plán úložek a renty do Excelu"):
                zobraz_tabulku_s_prepinacem(df_inv, "investice_inflace_a_udalosti.csv")
