import streamlit as st
import numpy_financial as npf
import pandas as pd


def _kc(x):
    return f"{x:,.0f} Kč".replace(",", " ")


def _anuitni_rozpad(uver, rocni_sazba_pct, splatka, safety_cap=1200):
    """Sestaví měsíční anuitní rozpad: splátka = úrok + jistina (úmor), + zůstatek.
    Vrátí list řádků, nebo None když splátka nepokryje ani úrok (úvěr by se nikdy nesplatil)."""
    r = (rocni_sazba_pct / 100) / 12
    zust = uver
    rows = []
    kum_urok = 0.0
    kum_jistina = 0.0
    m = 0
    while zust > 0.005 and m < safety_cap:
        m += 1
        urok = zust * r
        umor = splatka - urok
        if umor <= 0:
            return None  # splátka nepokryje úrok → nekonečné splácení
        if umor > zust:
            umor = zust  # poslední (menší) splátka doplatí zbytek
        skutecna_splatka = urok + umor
        zust -= umor
        kum_urok += urok
        kum_jistina += umor
        rows.append({
            "Měsíc": m,
            "Rok": (m - 1) // 12 + 1,
            "Splátka": skutecna_splatka,
            "Úrok": urok,
            "Jistina": umor,
            "Úrok celkem": kum_urok,
            "Jistina celkem": kum_jistina,
            "Zůstatek": max(0.0, zust),
        })
    return rows


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

        # Kanonické hodnoty pro anuitní rozpad (doplní se podle zvolené neznámé)
        r_uver = r_sazba = r_splatka = None
        with col_vystup:
            try:
                if cil == "Měsíční splátka":
                    res = -npf.pmt((tvm_sazba / 100) / 12, tvm_roky * 12, tvm_uver)
                    st.metric("Vypočítaná splátka", _kc(res))
                    r_uver, r_sazba, r_splatka = tvm_uver, tvm_sazba, res
                elif cil == "Maximální výše úvěru":
                    res = npf.pv((tvm_sazba / 100) / 12, tvm_roky * 12, -tvm_splatka)
                    st.metric("Můžete si půjčit", _kc(res))
                    r_uver, r_sazba, r_splatka = res, tvm_sazba, tvm_splatka
                elif cil == "Doba splácení":
                    mesice = npf.nper((tvm_sazba / 100) / 12, -tvm_splatka, tvm_uver)
                    st.metric("Budete splácet", f"{mesice / 12:.1f} let ({mesice:.0f} měsíců)")
                    r_uver, r_sazba, r_splatka = tvm_uver, tvm_sazba, tvm_splatka
                elif cil == "Úroková sazba":
                    res = npf.rate(tvm_roky * 12, -tvm_splatka, tvm_uver) * 12 * 100
                    st.metric("Odpovídající úrok", f"{res:.2f} % p.a.")
                    r_uver, r_sazba, r_splatka = tvm_uver, res, tvm_splatka
            except Exception:
                st.error("Nemá matematické řešení.")

        # --- ANUITNÍ PRŮBĚH (rozpad splátka → úrok / jistina / zůstatek) ---
        st.markdown("---")
        st.subheader("📉 Anuitní průběh – rozpad po měsících")

        valid = (
            r_uver is not None and r_sazba is not None and r_splatka is not None
            and pd.notna(r_uver) and pd.notna(r_sazba) and pd.notna(r_splatka)
            and r_uver > 0 and r_splatka > 0
        )
        if not valid:
            st.info("Zadej kladnou výši úvěru, sazbu a splátku – rozpad se dopočítá automaticky.")
            return

        rows = _anuitni_rozpad(r_uver, r_sazba, r_splatka)
        if not rows:
            st.warning("Splátka nepokryje ani měsíční úrok – úvěr by se při těchto hodnotách nikdy nesplatil. "
                       "Zvyš splátku nebo sniž sazbu.")
            return

        df = pd.DataFrame(rows)
        celkem_zaplaceno = df["Splátka"].sum()
        celkem_uroky = df["Úrok"].sum()
        pocet_mesicu = len(df)

        # Souhrn nad tabulkou
        s1, s2, s3 = st.columns(3)
        s1.metric("💰 Celkem zaplaceno", _kc(celkem_zaplaceno))
        s2.metric("🏦 Z toho úroky bance", _kc(celkem_uroky),
                  help="Kolik z celkové sumy jde bance na úrocích (přeplatek nad půjčenou jistinu).")
        preplaceni_pct = (celkem_uroky / r_uver * 100) if r_uver else 0.0
        s3.metric("📈 Přeplacení", f"{preplaceni_pct:.1f} %",
                  help=f"Úroky jako podíl z půjčené jistiny ({_kc(r_uver)}). "
                       f"Splácíš {pocet_mesicu} měsíců ({pocet_mesicu / 12:.1f} let).")

        st.caption("Na začátku jde větší část splátky na úrok, ke konci na jistinu. "
                   "Sloupce *Úrok celkem* / *Jistina celkem* ukazují narůstající součet.")

        # Formátovaná tabulka pro zobrazení
        df_fmt = df.copy()
        for sl in ["Splátka", "Úrok", "Jistina", "Úrok celkem", "Jistina celkem", "Zůstatek"]:
            df_fmt[sl] = df_fmt[sl].apply(_kc)
        st.dataframe(df_fmt, use_container_width=True, hide_index=True, height=360)

        # Export do CSV (surová čísla pro Excel)
        st.download_button(
            "📥 Stáhnout rozpad do tabulky (CSV pro Excel)",
            df.round(2).to_csv(index=False).encode("utf-8"),
            "anuitni_rozpad.csv", "text/csv", key="btn_tvm_rozpad_csv"
        )
