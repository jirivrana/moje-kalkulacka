import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

# --- VÝCHOZÍ HODNOTY (živé posuvníky) ---
VYCHOZI_PAKA = {
    "pl_hypo": 3000000.0,
    "pl_sazba": 4.69,
    "pl_doba": 20,
    "pl_public": 1500000.0,
    "pl_fki": 1500000.0,
    "pl_vyn_public": 7.0,
    "pl_vyn_fki": 10.0,
    "pl_spoluucast": 7000.0,
    "pl_inflace": 3.0,
    "pl_po_vycerpani": "Doplácet z vlastní kapsy",
    # Fáze 2 – renta z vybudovaného majetku
    "pl_renta_on": False,
    "pl_renta_roky": 10,
    "pl_renta_vynos": 8.0,
    "pl_renta_castka": 50000.0,
}

PO_VYCERPANI_OPTIONS = [
    "Doplácet z vlastní kapsy",
    "Doplácet z FKI fondu",
    "Jednorázově doplatit úvěr z FKI",
]


def _init_state():
    for k, v in VYCHOZI_PAKA.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # Ošetření zastaralé hodnoty z dřívějších verzí (jinak by selectbox spadl)
    if st.session_state.get("pl_po_vycerpani") not in PO_VYCERPANI_OPTIONS:
        st.session_state["pl_po_vycerpani"] = PO_VYCERPANI_OPTIONS[0]


def _kc(x):
    return f"{x:,.0f} Kč".replace(",", " ")


def _simulace(hypo, sazba, doba, public0, fki0, vyn_public, vyn_fki,
              spoluucast, inflace, po_vycerpani,
              renta_on, renta_roky, renta_vynos, renta_castka):
    """Dvoufázová simulace páky.
    Fáze 1: splácení hypotéky, sanace z PUBLIC + kapsy, FKI roste.
    Fáze 2 (volitelně): čerpání renty z vybudovaného majetku."""
    mesice_p1 = int(doba * 12)
    mesice_p2 = int(renta_roky * 12) if renta_on else 0
    mesice_celkem = mesice_p1 + mesice_p2

    splatka = -npf.pmt((sazba / 100) / 12, mesice_p1, hypo) if (mesice_p1 > 0 and hypo > 0) else 0.0

    zust = hypo
    public = public0
    fki = fki0

    public_vycerpan_mesic = None
    jednorazovy_doplatek_mesic = None
    celkem_z_kapsy = 0.0
    celkem_z_fki = 0.0
    celkem_uroky = 0.0

    renta_vyplaceno = 0.0
    renta_dosla_mesic = None
    faze2_pool = None
    pool_start_faze2 = None
    majetek_konec_p1 = public0 + fki0
    majetek_real_konec_p1 = public0 + fki0

    xs, h, pub, f, maj, maj_real, zust_real = [], [], [], [], [], [], []
    rok_rows = [{
        "Rok": 0, "Zůstatek hypotéky": zust, "PUBLIC složka": public,
        "FKI složka": fki, "Majetek celkem": public + fki,
        "Majetek reálně": public + fki
    }]

    for m in range(1, mesice_celkem + 1):
        coef = (1 + (inflace / 100)) ** (m / 12)

        if m <= mesice_p1:
            # ===== FÁZE 1: SPLÁCENÍ + BUDOVÁNÍ =====
            public = public * (1 + (vyn_public / 100) / 12)
            fki = fki * (1 + (vyn_fki / 100) / 12)

            if zust > 0.01:
                urok = zust * (sazba / 100) / 12
                celkem_uroky += urok
                umor = splatka - urok
                if umor > zust:
                    umor = zust
                zust -= umor
                platba = urok + umor
            else:
                zust = 0.0
                platba = 0.0

            if platba > 0:
                potreba = platba
                z_kapsy = min(spoluucast, potreba)
                potreba -= z_kapsy
                z_public = min(public, potreba)
                public -= z_public
                potreba -= z_public

                if potreba > 0:
                    if public_vycerpan_mesic is None and public <= 0.01:
                        public_vycerpan_mesic = m

                    if po_vycerpani == "Jednorázově doplatit úvěr z FKI" \
                            and jednorazovy_doplatek_mesic is None and fki >= zust:
                        fki -= zust
                        celkem_z_fki += zust
                        jednorazovy_doplatek_mesic = m
                        zust = 0.0
                        potreba = 0.0
                    elif po_vycerpani == "Doplácet z FKI fondu":
                        z_fki = min(fki, potreba)
                        fki -= z_fki
                        potreba -= z_fki
                        celkem_z_fki += z_fki
                        z_kapsy += potreba
                        potreba = 0.0
                    else:
                        z_kapsy += potreba
                        potreba = 0.0
                celkem_z_kapsy += z_kapsy

            majetek = public + fki
            if m == mesice_p1:
                majetek_konec_p1 = majetek
                majetek_real_konec_p1 = majetek / coef
        else:
            # ===== FÁZE 2: ČERPÁNÍ RENTY Z MAJETKU =====
            if faze2_pool is None:
                faze2_pool = public + fki
                pool_start_faze2 = faze2_pool
            faze2_pool = faze2_pool * (1 + (renta_vynos / 100) / 12)
            vyber = min(faze2_pool, renta_castka)
            faze2_pool -= vyber
            renta_vyplaceno += vyber
            if renta_dosla_mesic is None and renta_castka > 0 and vyber < renta_castka - 0.01:
                renta_dosla_mesic = m
            public = 0.0
            fki = faze2_pool
            zust = 0.0
            majetek = faze2_pool

        xs.append(m / 12)
        h.append(max(0.0, zust))
        pub.append(public)
        f.append(fki)
        maj.append(majetek)
        maj_real.append(majetek / coef)
        zust_real.append(max(0.0, zust) / coef)

        if m % 12 == 0:
            rok_rows.append({
                "Rok": m // 12, "Zůstatek hypotéky": max(0.0, zust),
                "PUBLIC složka": public, "FKI složka": fki,
                "Majetek celkem": majetek, "Majetek reálně": majetek / coef
            })

    df_rok = pd.DataFrame(rok_rows)
    df_mesic = pd.DataFrame({
        "Rok": xs, "Zůstatek hypotéky": h, "PUBLIC složka": pub, "FKI složka": f,
        "Majetek celkem": maj, "Majetek reálně": maj_real, "Dluh reálně": zust_real
    })

    # Udržitelnost renty (fáze 2)
    renta_udrzitelna = None
    if renta_on and pool_start_faze2:
        rocni_vyber = renta_castka * 12
        rocni_vynos_pool = pool_start_faze2 * (renta_vynos / 100)
        renta_udrzitelna = rocni_vyber <= rocni_vynos_pool

    souhrn = {
        "splatka": splatka,
        "majetek_konec": maj[-1] if maj else (public0 + fki0),
        "majetek_konec_p1": majetek_konec_p1,
        "majetek_real_konec_p1": majetek_real_konec_p1,
        "arbitraz": majetek_konec_p1 - celkem_z_kapsy,
        "celkem_z_kapsy": celkem_z_kapsy,
        "celkem_z_fki": celkem_z_fki,
        "celkem_uroky": celkem_uroky,
        "public_vycerpan_mesic": public_vycerpan_mesic,
        "jednorazovy_doplatek_mesic": jednorazovy_doplatek_mesic,
        "public_konec_p1": pub[mesice_p1 - 1] if mesice_p1 > 0 and len(pub) >= mesice_p1 else 0.0,
        "mesice_p1": mesice_p1,
        "mesice_celkem": mesice_celkem,
        "pool_start_faze2": pool_start_faze2,
        "renta_vyplaceno": renta_vyplaceno,
        "renta_dosla_mesic": renta_dosla_mesic,
        "renta_udrzitelna": renta_udrzitelna,
        "dluh_real_konec_p1": zust_real[mesice_p1 - 1] if mesice_p1 > 0 and len(zust_real) >= mesice_p1 else 0.0,
    }
    return df_rok, df_mesic, souhrn


def render(tab):
    _init_state()

    with tab:
        st.header("⚡ Páka LIVE: Hypotéka jako investiční nástroj")
        st.caption(
            "Rychlá živá modelace. Vezmeme hypotéku, peníze investujeme (PUBLIC + FKI) a "
            "splátku sanujeme z PUBLIC fondu + vlastní kapsy. **Tahej posuvníky** a sleduj, "
            "jestli to vychází. FKI necháváme růst jako motor majetku."
        )

        # --- ZÁKLADNÍ PARAMETRY ---
        c1, c2, c3 = st.columns(3)
        hypo = c1.number_input("💰 Výše hypotéky (Kč)", min_value=0.0, step=100000.0, key="pl_hypo")
        sazba = c2.number_input("🏦 Sazba hypotéky (% p.a.)", min_value=0.0, step=0.1, key="pl_sazba")
        doba = c3.number_input("📅 Doba splácení (let)", min_value=1, max_value=40, step=1, key="pl_doba")

        cc1, cc2, cc3 = st.columns(3)
        public0 = cc1.number_input("🔵 Vklad do PUBLIC fondu (Kč)", min_value=0.0, step=100000.0, key="pl_public")
        fki0 = cc2.number_input("🟢 Vklad do FKI fondu (Kč)", min_value=0.0, step=100000.0, key="pl_fki")
        po_idx = PO_VYCERPANI_OPTIONS.index(
            st.session_state.get("pl_po_vycerpani", PO_VYCERPANI_OPTIONS[0])
        ) if st.session_state.get("pl_po_vycerpani") in PO_VYCERPANI_OPTIONS else 0
        po_vycerpani = cc3.selectbox(
            "Po vyčerpání PUBLIC fondu:", PO_VYCERPANI_OPTIONS, index=po_idx, key="pl_po_vycerpani",
            help="Až PUBLIC dojde: doplácíš splátku z kapsy / postupně z FKI / nebo rovnou jednorázově "
                 "doplatíš celý zbytek úvěru z FKI (majetek už je dost velký)."
        )

        # Výpočet splátky (potřeba předem kvůli dynamickému max posuvníku spoluúčasti)
        mesice_p1 = int(doba * 12)
        splatka = -npf.pmt((sazba / 100) / 12, mesice_p1, hypo) if (mesice_p1 > 0 and hypo > 0) else 0.0

        if splatka <= 0:
            st.error("Zadej kladnou výši hypotéky a dobu splácení.")
            return

        # Spoluúčast nemůže být vyšší než celá splátka → ořízneme dřív, než vykreslíme posuvník
        max_spol = float(int(splatka) + 1)
        if st.session_state.get("pl_spoluucast", 0.0) > max_spol:
            st.session_state["pl_spoluucast"] = max_spol

        rozdil_vkladu = (public0 + fki0) - hypo
        if abs(rozdil_vkladu) > 1:
            if rozdil_vkladu > 0:
                st.caption(f"ℹ️ Investuješ o {_kc(rozdil_vkladu)} víc, než je hypotéka (přidáváš vlastní kapitál).")
            else:
                st.caption(f"ℹ️ Investuješ o {_kc(-rozdil_vkladu)} míň, než je hypotéka (část si necháváš stranou).")

        # --- ŽIVÉ POSUVNÍKY ---
        st.markdown("#### 🎛️ Živé posuvníky")
        s1, s2 = st.columns(2)
        vyn_public = s1.slider("🔵 Výnos PUBLIC (% p.a.)", 0.0, 15.0, step=0.1, key="pl_vyn_public",
                               help="Semi-nájem: dluhopisy + nemovitostní fondy. Konzervativně ~7 % včetně volatility.")
        vyn_fki = s2.slider("🟢 Výnos FKI (% p.a.)", 0.0, 20.0, step=0.1, key="pl_vyn_fki")
        s3, s4 = st.columns(2)
        spoluucast = s3.slider(
            "💸 Spoluúčast z kapsy (Kč/měs)", 0.0, max_spol, step=500.0, key="pl_spoluucast",
            help=f"Kolik splátky platíš z vlastní kapsy. Maximum = celá splátka ({_kc(splatka)})."
        )
        inflace = s4.slider(
            "📈 Inflace (% p.a.)", 0.0, 12.0, step=0.1, key="pl_inflace",
            help="Inflace rozpouští reálnou hodnotu dluhu (dobré pro dlužníka), ale i reálnou hodnotu majetku."
        )

        # --- FÁZE 2: RENTA Z MAJETKU (MRKVIČKA) ---
        renta_on = st.checkbox(
            "🥕 Po splacení hypotéky čerpat rentu z vybudovaného majetku", key="pl_renta_on"
        )
        # Posuvníky renderujeme vždy (jen zašedlé, když není renta aktivní) — jinak Streamlit
        # u podmíněně zobrazených posuvníků nepřebírá výchozí hodnotu ze session_state.
        r1, r2, r3 = st.columns(3)
        renta_castka = r1.slider("💰 Měsíční renta (Kč)", 0.0, 200000.0, step=5000.0,
                                 key="pl_renta_castka", disabled=not renta_on)
        renta_vynos = r2.slider("📊 Výnos v rentě (% p.a.)", 0.0, 15.0, step=0.1,
                                key="pl_renta_vynos", disabled=not renta_on,
                                help="Mix FKI private equity / public. Stabilně ~8 %.")
        renta_roky = r3.slider("⏳ Roky čerpání renty", 1, 50, step=1,
                               key="pl_renta_roky", disabled=not renta_on)

        # --- SIMULACE ---
        df_rok, df_mesic, S = _simulace(
            hypo, sazba, doba, public0, fki0, vyn_public, vyn_fki,
            spoluucast, inflace, po_vycerpani,
            renta_on, renta_roky, renta_vynos, renta_castka
        )

        # Splátka se "rozsvítí"
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("📌 Měsíční splátka hypotéky", _kc(S["splatka"]))
        m2.metric("Z toho z kapsy", _kc(min(spoluucast, S["splatka"])))
        m3.metric("Z toho z PUBLIC (zpočátku)", _kc(max(0.0, S["splatka"] - spoluucast)))

        # --- GRAF ---
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["Zůstatek hypotéky"],
                                 name="Hypotéka", line=dict(color="#ff4b4b", width=2)))
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["PUBLIC složka"],
                                 name="PUBLIC fond", line=dict(color="#3498db", width=2)))
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["FKI složka"],
                                 name="FKI fond", line=dict(color="#2ecc71", width=3)))
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["Majetek celkem"],
                                 name="Majetek celkem", line=dict(color="#ecf0f1", width=2, dash="dot")))
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["Majetek reálně"],
                                 name="Majetek reálně (po inflaci)",
                                 line=dict(color="#9b59b6", dash="dot"), visible="legendonly"))
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["Dluh reálně"],
                                 name="Dluh reálně (po inflaci)",
                                 line=dict(color="#e67e22", dash="dot"), visible="legendonly"))

        # Svislé čáry událostí. Pozor: při "Jednorázově doplatit z FKI" padne vyčerpání PUBLIC
        # a doplacení úvěru do stejného měsíce → sloučíme do jedné čáry, popisky dáme na opačné
        # strany, ať se text nepřekrývá.
        dop = S["jednorazovy_doplatek_mesic"]
        vyc = S["public_vycerpan_mesic"]
        if dop:
            fig.add_vline(x=dop / 12, line_width=2, line_dash="dot", line_color="#f1c40f",
                          annotation_text="💸 Úvěr doplacen z FKI", annotation_position="top left",
                          annotation_font_color="#f1c40f")
        elif vyc:
            fig.add_vline(x=vyc / 12, line_width=2, line_dash="dash", line_color="#e74c3c",
                          annotation_text="PUBLIC vyčerpán", annotation_position="top left",
                          annotation_font_color="#e74c3c")
        if renta_on:
            fig.add_vline(x=S["mesice_p1"] / 12, line_width=2, line_dash="dash", line_color="#1abc9c",
                          annotation_text="🥕 Start renty", annotation_position="top right",
                          annotation_font_color="#1abc9c")

        fig.update_layout(
            template="plotly_dark", title="Analýza finanční páky a rentability",
            xaxis_title="Rok", yaxis_title="Hodnota (Kč)", hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- VERDIKT FÁZE 1 ---
        vyc_m = S["public_vycerpan_mesic"]
        if S["jednorazovy_doplatek_mesic"]:
            rok_dop = (S["jednorazovy_doplatek_mesic"] + 11) // 12
            st.markdown(
                f'<div class="big-verdict verdict-yes">🟢 PÁKA VYŠLA — v {rok_dop}. roce už byl majetek '
                f'tak velký, že se zbytek úvěru ({_kc(S["celkem_z_fki"])}) jednorázově doplatil z FKI. '
                f'Dál ti roste čistý majetek bez dluhu.</div>',
                unsafe_allow_html=True
            )
        elif vyc_m is None:
            st.markdown(
                f'<div class="big-verdict verdict-yes">🟢 UDRŽITELNÉ — PUBLIC fond celou dobu pokryl sanaci '
                f'splátky a na konci splácení ti ještě zbývá {_kc(S["public_konec_p1"])}.</div>',
                unsafe_allow_html=True
            )
        else:
            rok_vyc = (vyc_m + 11) // 12
            podil = vyc_m / S["mesice_p1"]
            zbyva_let = (S["mesice_p1"] - vyc_m) / 12
            if po_vycerpani == "Doplácet z FKI fondu":
                dovysvetleni = (f"Od {rok_vyc}. roku se zbytek splátky tahá z FKI "
                                f"(celkem {_kc(S['celkem_z_fki'])}) — ukrajuješ z růstového motoru.")
            else:
                dovysvetleni = (f"Od {rok_vyc}. roku doplácíš celou splátku (~{_kc(S['splatka'])}/měs) "
                                f"z vlastní kapsy ještě {zbyva_let:.1f} let.")
            if podil >= 0.75:
                st.markdown(
                    f'<div class="big-verdict verdict-yes">🟡 NA HRANĚ — PUBLIC vydrží až do {rok_vyc}. roku '
                    f'(většinu doby). {dovysvetleni}</div>', unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="big-verdict verdict-no">🔴 POZOR, VYBÍRÁŠ MOC — PUBLIC se vyčerpá už v '
                    f'{rok_vyc}. roce. {dovysvetleni}<br>Zvyš spoluúčast nebo přidej do PUBLIC fondu.</div>',
                    unsafe_allow_html=True
                )

        # --- VERDIKT FÁZE 2: RENTA (MRKVIČKA) ---
        if renta_on and S["pool_start_faze2"]:
            st.markdown(
                f"#### 🥕 A teď ta odměna: po {int(doba)} letech máš vybudováno "
                f"**{_kc(S['pool_start_faze2'])}** a začínáš čerpat rentu."
            )
            if S["renta_udrzitelna"]:
                st.markdown(
                    f'<div class="big-verdict verdict-yes">🟢 RENTA JE PRAKTICKY NEVYČERPATELNÁ — '
                    f'čerpáš {_kc(renta_castka)}/měs a majetek i tak roste (výnos {renta_vynos:.1f} % > čerpání). '
                    f'Žiješ z výnosů, jistina zůstává.</div>', unsafe_allow_html=True
                )
            elif S["renta_dosla_mesic"]:
                rok_dosla = (S["renta_dosla_mesic"] - S["mesice_p1"]) / 12
                st.markdown(
                    f'<div class="big-verdict verdict-no">🔴 RENTA JE PŘÍLIŠ VYSOKÁ — '
                    f'majetek se při čerpání {_kc(renta_castka)}/měs vyčerpá za ~{rok_dosla:.1f} let. '
                    f'Sniž rentu, ať čerpáš jen výnosy.</div>', unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="big-verdict verdict-yes">🟡 ČERPÁŠ I JISTINU — renta {_kc(renta_castka)}/měs '
                    f'je vyšší než výnos, majetek pomalu ubývá, ale za zvolených {int(renta_roky)} let nedojde.</div>',
                    unsafe_allow_html=True
                )

        # --- TABULKA PO 5 LETECH ---
        total_years = int(doba) + (int(renta_roky) if renta_on else 0)
        roky_k_zobrazeni = sorted(set([0] + list(range(5, total_years + 1, 5)) + [int(doba), total_years]))
        df_tab = df_rok[df_rok["Rok"].isin(roky_k_zobrazeni)].copy()
        df_fmt = df_tab.copy()
        for sl in ["Zůstatek hypotéky", "PUBLIC složka", "FKI složka", "Majetek celkem", "Majetek reálně"]:
            df_fmt[sl] = df_fmt[sl].apply(_kc)
        st.dataframe(df_fmt, use_container_width=True, hide_index=True)

        # --- SOUHRNNÉ METRIKY ---
        st.markdown("---")
        f1, f2, f3 = st.columns(3)
        f1.metric("🏆 Vybudovaný majetek (konec splácení)", _kc(S["majetek_konec_p1"]))
        f2.metric("📈 Čistý zisk z arbitráže", _kc(S["arbitraz"]),
                  help="Vybudovaný majetek minus vše vložené z vlastní kapsy (půjčená jistina se splatí).")
        if S["jednorazovy_doplatek_mesic"]:
            f3.metric("🔵 Status PUBLIC fondu", f"Úvěr doplacen z FKI v {(S['jednorazovy_doplatek_mesic'] + 11) // 12}. roce")
        elif vyc_m is None:
            f3.metric("🔵 Status PUBLIC fondu", "Nevyčerpán")
        else:
            f3.metric("🔵 Status PUBLIC fondu", f"Vyčerpán v {(vyc_m + 11) // 12}. roce")

        g1, g2, g3 = st.columns(3)
        g1.metric("💎 Reálný majetek (dnešní Kč)", _kc(S["majetek_real_konec_p1"]),
                  help="Vybudovaný majetek očištěný o inflaci — kolik to je v dnešní kupní síle.")
        g2.metric("🏦 Reálný zbytek dluhu (po inflaci)", _kc(S["dluh_real_konec_p1"]),
                  help="Inflace ti dluh v čase 'rozpouští' — toto je jeho reálná tíha na konci.")
        g3.metric("💸 Celkem z kapsy / úroky bance", f"{_kc(S['celkem_z_kapsy'])} / {_kc(S['celkem_uroky'])}")

        if renta_on and S["pool_start_faze2"]:
            st.metric("🥕 Celkem vyčerpáno na rentě", _kc(S["renta_vyplaceno"]))

        with st.expander("📊 Detailní tabulka po letech & Export"):
            df_rok_fmt = df_rok.copy()
            for sl in ["Zůstatek hypotéky", "PUBLIC složka", "FKI složka", "Majetek celkem", "Majetek reálně"]:
                df_rok_fmt[sl] = df_rok_fmt[sl].apply(_kc)
            st.dataframe(df_rok_fmt, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Stáhnout CSV pro Excel",
                df_rok.round(2).to_csv(index=False).encode("utf-8"),
                "paka_live.csv", "text/csv", key="btn_paka_live_csv"
            )
