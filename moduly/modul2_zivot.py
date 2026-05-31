import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

from moduly.utils import zobraz_tabulku_s_prepinacem

# --- VÝCHOZÍ HODNOTY ---
VYCHOZI_HODNOTY = {
    "sm": 1, "sr": 2024, "z1": 3000000.0, "z2": 5.5, "z3": 30,
    "z_typ_uveru": "Anuita (klasická)",
    "z9": 0.0, "z10": 3000.0, "z11": 6.0,        # Portfolio A
    "z_odkup": 0.0,                               # pravidelný přesun A -> B
    "z12": 0.0, "z13": 0.0, "z14": 8.0,           # Portfolio B
    "z_odkup_ac": 0.0,                            # pravidelný přesun A -> C
    "z15": 0.0, "z16": 0.0, "z17": 10.0,          # Portfolio C (FKI)
    "z_infl": 3.0
}

TYP_UVERU_OPTIONS = ["Anuita (klasická)", "Americká (jen úrok)"]

TYPY_UDALOSTI = [
    # — Úvěr —
    "🏦 Refixace úvěru (Nová sazba %)",
    "💰 Mimořádka úvěru z vlastní kapsy (Kč)",
    "💸 Mimořádka úvěru stržená z Portfolia A (Kč)",
    # — Jednorázové vklady —
    "📈 Jednorázový vklad do Portfolia A (Kč)",
    "📈 Jednorázový vklad do Portfolia B (Kč)",
    "📈 Jednorázový vklad do Portfolia C (Kč)",
    # — Jednorázové odkupy (na účet / spotřeba) —
    "💸 Jednorázový odkup z Portfolia A (Kč)",
    "💸 Jednorázový odkup z Portfolia B (Kč)",
    "💸 Jednorázový odkup z Portfolia C (Kč)",
    # — Jednorázové přesuny mezi portfolii (realokace) —
    "💼 Jednorázový přesun z A do B (Kč)",
    "💼 Jednorázový přesun z A do C (Kč)",
    "💼 Jednorázový přesun z B do C (Kč)",
    # — Začít / změnit pravidelnou rentu na účet —
    "▶️ Začít/změnit rentu z A na účet (Kč)",
    "▶️ Začít/změnit rentu z B na účet (Kč)",
    "▶️ Začít/změnit rentu z C na účet (Kč)",
    # — Změna pravidelné investice —
    "🔄 Změna pravidelné investice do A (Kč)",
    "🔄 Změna pravidelné investice do B (Kč)",
    "🔄 Změna pravidelné investice do C (Kč)",
    # — Změna měsíčního přesunu mezi portfolii —
    "🔄 Změna měsíčního přesunu z A do B (Kč)",
    "🔄 Změna měsíčního přesunu z A do C (Kč)",
    "🔄 Změna měsíčního přesunu z B do C (Kč)",
    # — Změna úroku —
    "📉 Změna úroku Portfolia A (%)",
    "📉 Změna úroku Portfolia B (%)",
    "📉 Změna úroku Portfolia C (%)"
]


def _init_state():
    for k, v in VYCHOZI_HODNOTY.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if 'zivot_events' not in st.session_state:
        st.session_state.zivot_events = []
    if 'zivot_event_id' not in st.session_state:
        st.session_state.zivot_event_id = 0


def _pridat_udalost():
    start_r = st.session_state.get("sr", 2024)
    start_m = st.session_state.get("sm", 1)
    st.session_state.zivot_events.append({
        "id": st.session_state.zivot_event_id,
        "kal_mesic": start_m,
        "kal_rok": start_r + 1,
        "typ": "🏦 Refixace úvěru (Nová sazba %)",
        "hodnota": 4.5,
        "akce": "Zkrátit dobu",
        "cil": "Obě cesty"
    })
    st.session_state.zivot_event_id += 1


def _smazat_udalost(event_id):
    st.session_state.zivot_events = [
        ev for ev in st.session_state.zivot_events if ev['id'] != event_id
    ]


def _novy_stav(u_vyse, u_sazba, spl0, typ_uveru,
               ia, pa_reg, ra, ib, pb_reg, rb, ic, pc_reg, rc,
               presun_ab0, presun_ac0):
    return {
        "z": u_vyse, "saz": u_sazba, "spl": spl0, "typ_uveru": typ_uveru,
        "pa": ia, "pb": ib, "pc": ic,
        "prav_a": pa_reg, "prav_b": pb_reg, "prav_c": pc_reg,
        "ur_a": ra, "ur_b": rb, "ur_c": rc,
        "presun_ab": presun_ab0, "presun_ac": presun_ac0, "presun_bc": 0.0,
        "renta_a": 0.0, "renta_b": 0.0, "renta_c": 0.0,
        "vloz": ia + ib + ic,
        "vybrano_mim": 0.0, "renta_celkem": 0.0,
        "uroky_celkem": 0.0, "doba_splaceni": 0,
        "crossover": None,
    }


def _splatka_pro_typ(s, max_months, m):
    """Vrátí měsíční splátku podle typu úvěru z aktuálního zůstatku/sazby."""
    if s["typ_uveru"].startswith("Americká"):
        return s["z"] * (s["saz"] / 100) / 12
    return -npf.pmt((s["saz"] / 100) / 12, max(1, max_months - m + 1), s["z"])


def _aplikuj(s, ev, t, v, max_months, m):
    """Aplikuje jednu událost na stav cesty (mutuje slovník s).
    Vrací novou splátku (pro zobrazení), jinak None."""
    if t == "🏦 Refixace úvěru (Nová sazba %)":
        s["saz"] = v
        if s["z"] > 0:
            s["spl"] = _splatka_pro_typ(s, max_months, m)
            return s["spl"]
    elif t == "💰 Mimořádka úvěru z vlastní kapsy (Kč)":
        s["z"] = max(0, s["z"] - v)
        if ev.get("akce", "") == "Snížit splátku" and s["z"] > 0:
            s["spl"] = _splatka_pro_typ(s, max_months, m)
            return s["spl"]
    elif t == "💸 Mimořádka úvěru stržená z Portfolia A (Kč)":
        skut = min(s["pa"], v)
        s["pa"] -= skut
        s["z"] = max(0, s["z"] - skut)
        s["vybrano_mim"] += skut
        if ev.get("akce", "") == "Snížit splátku" and s["z"] > 0:
            s["spl"] = _splatka_pro_typ(s, max_months, m)
            return s["spl"]
    elif t == "📈 Jednorázový vklad do Portfolia A (Kč)":
        s["pa"] += v; s["vloz"] += v
    elif t == "📈 Jednorázový vklad do Portfolia B (Kč)":
        s["pb"] += v; s["vloz"] += v
    elif t == "📈 Jednorázový vklad do Portfolia C (Kč)":
        s["pc"] += v; s["vloz"] += v
    elif t == "💸 Jednorázový odkup z Portfolia A (Kč)":
        skut = min(s["pa"], v); s["pa"] -= skut; s["renta_celkem"] += skut
    elif t == "💸 Jednorázový odkup z Portfolia B (Kč)":
        skut = min(s["pb"], v); s["pb"] -= skut; s["renta_celkem"] += skut
    elif t == "💸 Jednorázový odkup z Portfolia C (Kč)":
        skut = min(s["pc"], v); s["pc"] -= skut; s["renta_celkem"] += skut
    elif t == "💼 Jednorázový přesun z A do B (Kč)":
        skut = min(s["pa"], v); s["pa"] -= skut; s["pb"] += skut
    elif t == "💼 Jednorázový přesun z A do C (Kč)":
        skut = min(s["pa"], v); s["pa"] -= skut; s["pc"] += skut
    elif t == "💼 Jednorázový přesun z B do C (Kč)":
        skut = min(s["pb"], v); s["pb"] -= skut; s["pc"] += skut
    elif t == "▶️ Začít/změnit rentu z A na účet (Kč)":
        s["renta_a"] = v
    elif t == "▶️ Začít/změnit rentu z B na účet (Kč)":
        s["renta_b"] = v
    elif t == "▶️ Začít/změnit rentu z C na účet (Kč)":
        s["renta_c"] = v
    elif t == "🔄 Změna pravidelné investice do A (Kč)":
        s["prav_a"] = v
    elif t == "🔄 Změna pravidelné investice do B (Kč)":
        s["prav_b"] = v
    elif t == "🔄 Změna pravidelné investice do C (Kč)":
        s["prav_c"] = v
    elif t == "🔄 Změna měsíčního přesunu z A do B (Kč)":
        s["presun_ab"] = v
    elif t == "🔄 Změna měsíčního přesunu z A do C (Kč)":
        s["presun_ac"] = v
    elif t == "🔄 Změna měsíčního přesunu z B do C (Kč)":
        s["presun_bc"] = v
    elif t == "📉 Změna úroku Portfolia A (%)":
        s["ur_a"] = v
    elif t == "📉 Změna úroku Portfolia B (%)":
        s["ur_b"] = v
    elif t == "📉 Změna úroku Portfolia C (%)":
        s["ur_c"] = v
    return None


def _krok_mesice(s, m):
    """Jeden měsíc: růst, přesuny, renty, splátka úvěru. Vrací měsíční rentu na účet."""
    # 1. Růst portfolií + pravidelná investice
    s["pa"] = s["pa"] * (1 + (s["ur_a"] / 100) / 12) + s["prav_a"]
    s["pb"] = s["pb"] * (1 + (s["ur_b"] / 100) / 12) + s["prav_b"]
    s["pc"] = s["pc"] * (1 + (s["ur_c"] / 100) / 12) + s["prav_c"]
    s["vloz"] += s["prav_a"] + s["prav_b"] + s["prav_c"]

    # 2. Pravidelné přesuny mezi portfolii (realokace toku)
    t_ab = min(s["pa"], s["presun_ab"]); s["pa"] -= t_ab; s["pb"] += t_ab
    t_ac = min(s["pa"], s["presun_ac"]); s["pa"] -= t_ac; s["pc"] += t_ac
    t_bc = min(s["pb"], s["presun_bc"]); s["pb"] -= t_bc; s["pc"] += t_bc

    # 3. Pravidelná renta na účet (čerpání)
    r_a = min(s["pa"], s["renta_a"]); s["pa"] -= r_a; s["renta_celkem"] += r_a
    r_b = min(s["pb"], s["renta_b"]); s["pb"] -= r_b; s["renta_celkem"] += r_b
    r_c = min(s["pc"], s["renta_c"]); s["pc"] -= r_c; s["renta_celkem"] += r_c

    # 4. Splátka úvěru
    if s["z"] > 0.01:
        s["doba_splaceni"] += 1
        ur_m = s["z"] * (s["saz"] / 100) / 12
        s["uroky_celkem"] += ur_m
        if s["typ_uveru"].startswith("Americká"):
            s["spl"] = ur_m  # jen úrok, jistina stojí (balónová splatnost na konci)
        else:
            um = s["spl"] - ur_m
            if um > s["z"]: um = s["z"]
            s["z"] -= um
    else:
        s["z"] = 0; s["spl"] = 0

    # 5. Crossover (investice překonaly dluh)
    invest = s["pa"] + s["pb"] + s["pc"]
    if s["crossover"] is None and invest >= s["z"] and s["z"] > 0.01:
        s["crossover"] = m

    return r_a + r_b + r_c


def _vyhodnot_udrzitelnost(serie_nom, serie_real):
    """Posoudí trend majetku na základě posledního roku simulace.
    Vrací (stav, rocni_nom, rocni_real, runway_let)."""
    n = len(serie_nom)
    if n < 2:
        return "green", 0.0, 0.0, None
    okno = 12 if n >= 13 else n - 1
    d_nom = serie_nom[-1] - serie_nom[-1 - okno]
    d_real = serie_real[-1] - serie_real[-1 - okno]
    rocni_nom = d_nom / okno * 12
    rocni_real = d_real / okno * 12

    if rocni_real > 0:
        stav = "green"
    elif rocni_nom > 0:
        stav = "yellow"
    else:
        stav = "red"

    runway_let = None
    if rocni_nom < 0 and serie_nom[-1] > 0:
        runway_let = serie_nom[-1] / (-rocni_nom)
    return stav, rocni_nom, rocni_real, runway_let


def _kc(x):
    return f"{x:,.0f} Kč".replace(",", " ")


def render(tab):
    _init_state()

    with tab:
        st.header("⏳ Život úvěru: Duel dvou strategií v čase")

        # --- VSTUPY ---
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Výchozí stav úvěru (Počátek)")
            col_m, col_r = st.columns(2)
            start_mesic = col_m.number_input("Měsíc čerpání", min_value=1, max_value=12, step=1, key="sm")
            start_rok = col_r.number_input("Rok čerpání", min_value=1990, max_value=2100, step=1, key="sr")

            akt_typ = st.session_state.get("z_typ_uveru", TYP_UVERU_OPTIONS[0])
            typ_idx = TYP_UVERU_OPTIONS.index(akt_typ) if akt_typ in TYP_UVERU_OPTIONS else 0
            typ_uveru = st.selectbox(
                "Typ úvěru", TYP_UVERU_OPTIONS, index=typ_idx, key="z_typ_uveru",
                help="Anuita = splácíte úrok i jistinu. Americká = platíte jen úrok, jistina stojí (páka do investic)."
            )

            u_vyse = st.number_input("Původní úvěr", step=50000.0, key="z1")
            u_sazba = st.number_input("Původní sazba (%)", step=0.1, key="z2")
            u_roky = st.number_input("Doba (let)", step=1, key="z3")

            if typ_uveru.startswith("Americká"):
                puvodni_splatka = u_vyse * (u_sazba / 100) / 12 if u_vyse > 0 else 0
                st.info(f"Měsíční úrok (americká): **{_kc(puvodni_splatka)}** — jistina {_kc(u_vyse)} stojí.")
            else:
                puvodni_splatka = -npf.pmt((u_sazba / 100) / 12, u_roky * 12, u_vyse) if u_roky > 0 else 0
                st.info(f"Původní splátka úvěru: **{_kc(puvodni_splatka)}**")

        with c2:
            st.subheader("Výchozí stav Investic a Inflace")
            i2_1a = st.number_input("Počáteční stav Portfolia A (Public/Konzervativní)", step=50000.0, key="z9")
            i2_pa = st.number_input("Počáteční pravidelka do A", step=500.0, key="z10")
            i2_ra = st.number_input("Počáteční úrok A (% p.a.)", step=0.1, key="z11")
            inflace_zivot = st.number_input(
                "Očekávaná inflace (% p.a.)", step=0.1, key="z_infl",
                help="Pro výpočet reálné kupní síly (majetek očištěný o inflaci)."
            )
            with st.expander("📊 Portfolio B (Dynamické / Reality)"):
                odkup_a_zivot = st.number_input("Měsíční přesun z A do B (Fázování)", step=1000.0, key="z_odkup")
                i2_1b = st.number_input("Počáteční stav Portfolia B", step=50000.0, key="z12")
                i2_pb = st.number_input("Počáteční pravidelka do B", step=500.0, key="z13")
                i2_rb = st.number_input("Počáteční úrok B (% p.a.)", step=0.1, key="z14")
            with st.expander("🏛️ Portfolio C (FKI — kvalifikovaní investoři)"):
                odkup_ac_zivot = st.number_input("Měsíční přesun z A do C (Fázování)", step=1000.0, key="z_odkup_ac")
                i2_1c = st.number_input("Počáteční stav Portfolia C", step=50000.0, key="z15")
                i2_pc = st.number_input("Počáteční pravidelka do C", step=500.0, key="z16")
                i2_rc = st.number_input("Počáteční úrok C (% p.a.)", step=0.1, key="z17")

        # --- DYNAMICKÉ UDÁLOSTI ---
        st.markdown("---")
        st.subheader("⏱️ Události v průběhu času (Zadávejte reálné datum)")
        st.button("➕ Přidat událost", on_click=_pridat_udalost)

        for ev in st.session_state.zivot_events:
            with st.container():
                col_date, col_t, col_v, col_c, col_a, col_i, col_d = st.columns([1.5, 3, 1.5, 2, 2, 2, 1])

                d1, d2 = col_date.columns(2)
                ev["kal_mesic"] = d1.number_input(
                    "Měs.", min_value=1, max_value=12,
                    value=int(ev.get("kal_mesic", 1)), step=1, key=f"ev_m_{ev['id']}"
                )
                ev["kal_rok"] = d2.number_input(
                    "Rok", min_value=1990, max_value=2100,
                    value=int(ev.get("kal_rok", 2026)), step=1, key=f"ev_r_{ev['id']}"
                )

                idx = TYPY_UDALOSTI.index(ev["typ"]) if ev["typ"] in TYPY_UDALOSTI else 0
                ev["typ"] = col_t.selectbox("Typ události", TYPY_UDALOSTI, index=idx, key=f"ev_t_{ev['id']}")

                popisek = "Sazba (%)" if "(%)" in ev["typ"] else "Částka (Kč)"
                krok = 0.1 if "(%)" in ev["typ"] else 5000.0
                ev["hodnota"] = col_v.number_input(
                    popisek, value=float(ev.get("hodnota", 0.0)), step=krok, key=f"ev_val_{ev['id']}"
                )

                moznosti_cilu = ["Obě cesty", "Jen Cesta 1", "Jen Cesta 2"]
                idx_cil = moznosti_cilu.index(ev.get("cil", "Obě cesty")) if ev.get("cil", "Obě cesty") in moznosti_cilu else 0
                ev["cil"] = col_c.selectbox("Aplikovat pro:", moznosti_cilu, index=idx_cil, key=f"ev_c_{ev['id']}")

                if "Mimořádka" in ev["typ"]:
                    idx_a = 0 if ev.get("akce", "Zkrátit").startswith("Zkrátit") else 1
                    ev["akce"] = col_a.selectbox(
                        "Po mimořádce:", ["Zkrátit dobu", "Snížit splátku"],
                        index=idx_a, key=f"ev_a_{ev['id']}"
                    )
                else:
                    col_a.write("")

                ev["ui_info"] = col_i.empty()
                col_d.button("🗑️ Smazat", key=f"ev_d_{ev['id']}", on_click=_smazat_udalost, args=(ev["id"],))

        # --- ENGINE: ZPRACOVÁNÍ ČASOVÉ OSY ---
        max_months = int(u_roky * 12) if u_roky > 0 else 360

        s1 = _novy_stav(u_vyse, u_sazba, puvodni_splatka, typ_uveru,
                        i2_1a, i2_pa, i2_ra, i2_1b, i2_pb, i2_rb, i2_1c, i2_pc, i2_rc,
                        odkup_a_zivot, odkup_ac_zivot)
        s2 = _novy_stav(u_vyse, u_sazba, puvodni_splatka, typ_uveru,
                        i2_1a, i2_pa, i2_ra, i2_1b, i2_pb, i2_rb, i2_1c, i2_pc, i2_rc,
                        odkup_a_zivot, odkup_ac_zivot)

        data_zivot = []

        for ev in st.session_state.zivot_events:
            ev.pop("vysledek_c1", None)
            ev.pop("vysledek_c2", None)

        for m in range(1, max_months + 1):
            kalendarni_rok = int(start_rok + ((start_mesic + m - 2) // 12))
            kalendarni_mesic = int(((start_mesic + m - 2) % 12) + 1)

            for ev in st.session_state.zivot_events:
                if ev.get("kal_mesic") == kalendarni_mesic and ev.get("kal_rok") == kalendarni_rok:
                    t = ev["typ"]
                    v = float(ev["hodnota"])
                    cil = ev["cil"]
                    if cil in ["Obě cesty", "Jen Cesta 1"]:
                        nova = _aplikuj(s1, ev, t, v, max_months, m)
                        if nova is not None:
                            ev["vysledek_c1"] = nova
                    if cil in ["Obě cesty", "Jen Cesta 2"]:
                        nova = _aplikuj(s2, ev, t, v, max_months, m)
                        if nova is not None:
                            ev["vysledek_c2"] = nova

            renta1_m = _krok_mesice(s1, m)
            renta2_m = _krok_mesice(s2, m)

            inflacni_koef = (1 + (inflace_zivot / 100)) ** (m / 12)
            inv1 = s1["pa"] + s1["pb"] + s1["pc"]
            inv2 = s2["pa"] + s2["pb"] + s2["pc"]
            vynos1 = (inv1 + s1["vybrano_mim"] + s1["renta_celkem"]) - s1["vloz"]
            vynos2 = (inv2 + s2["vybrano_mim"] + s2["renta_celkem"]) - s2["vloz"]
            jmeni1 = inv1 - max(0, s1["z"])
            jmeni2 = inv2 - max(0, s2["z"])
            datum_str = f"{kalendarni_mesic:02d}/{kalendarni_rok}"

            data_zivot.append({
                "Datum": datum_str, "Rok": kalendarni_rok, "Měsíc": m,
                # Cesta 1
                "Jistina C1": s1["z"], "Splátka C1": s1["spl"], "Úroky C1": s1["uroky_celkem"],
                "Portfolio A C1": s1["pa"], "Portfolio B C1": s1["pb"], "Portfolio C C1": s1["pc"],
                "Investice C1": inv1, "Investice C1 (Reálně)": inv1 / inflacni_koef,
                "Čisté jmění C1": jmeni1, "Čisté jmění C1 (Reálně)": jmeni1 / inflacni_koef,
                "Renta C1 (měs)": renta1_m, "Renta C1 (Celkem)": s1["renta_celkem"],
                "Vloženo C1": s1["vloz"], "Výnos C1": vynos1,
                # Cesta 2
                "Jistina C2": s2["z"], "Splátka C2": s2["spl"], "Úroky C2": s2["uroky_celkem"],
                "Portfolio A C2": s2["pa"], "Portfolio B C2": s2["pb"], "Portfolio C C2": s2["pc"],
                "Investice C2": inv2, "Investice C2 (Reálně)": inv2 / inflacni_koef,
                "Čisté jmění C2": jmeni2, "Čisté jmění C2 (Reálně)": jmeni2 / inflacni_koef,
                "Renta C2 (měs)": renta2_m, "Renta C2 (Celkem)": s2["renta_celkem"],
                "Vloženo C2": s2["vloz"], "Výnos C2": vynos2,
            })

        # Výsledky událostí (refixace / mimořádka) do UI
        for ev in st.session_state.zivot_events:
            if ev.get("ui_info"):
                msg = ""
                if "vysledek_c1" in ev and "vysledek_c2" in ev:
                    if ev["vysledek_c1"] == ev["vysledek_c2"]:
                        msg = f"Nová splátka: **{_kc(ev['vysledek_c1'])}**"
                    else:
                        msg = f"C1: **{_kc(ev['vysledek_c1'])}** | C2: **{_kc(ev['vysledek_c2'])}**"
                elif "vysledek_c1" in ev:
                    msg = f"Nová splátka C1: **{_kc(ev['vysledek_c1'])}**"
                elif "vysledek_c2" in ev:
                    msg = f"Nová splátka C2: **{_kc(ev['vysledek_c2'])}**"
                if msg:
                    ev["ui_info"].success(msg)

        df_zivot = pd.DataFrame(data_zivot)
        df_zivot['Osa_Casu'] = pd.to_datetime(df_zivot['Datum'], format='%m/%Y')

        inv1 = s1["pa"] + s1["pb"] + s1["pc"]
        inv2 = s2["pa"] + s2["pb"] + s2["pc"]
        vynos1_celkem = (inv1 + s1["vybrano_mim"] + s1["renta_celkem"]) - s1["vloz"]
        vynos2_celkem = (inv2 + s2["vybrano_mim"] + s2["renta_celkem"]) - s2["vloz"]
        ciste_jmeni1 = inv1 - max(0, s1["z"])
        ciste_jmeni2 = inv2 - max(0, s2["z"])

        # --- VERDIKT ---
        st.markdown("---")
        st.markdown("### ⚖️ Duel Strategií a Vyhodnocení")

        colR1, colR2 = st.columns(2)
        for col, s, jmeni, vynos, znak, nadpis in [
            (colR1, s1, ciste_jmeni1, vynos1_celkem, "🟩", "CESTA 1 (Hlavní scénář)"),
            (colR2, s2, ciste_jmeni2, vynos2_celkem, "🟧", "CESTA 2 (Alternativní scénář)"),
        ]:
            with col:
                if znak == "🟩":
                    st.success(f"**{znak} {nadpis}**")
                else:
                    st.warning(f"**{znak} {nadpis}**")
                st.write(f"Doba splácení: **{s['doba_splaceni'] / 12:.1f} let**")
                st.write(f"Celkem na úrocích bance: **{_kc(s['uroky_celkem'])}**")
                st.write(f"Vybráno na rentě/odkupech na účet: **{_kc(s['renta_celkem'])}**")
                st.write(f"Čistý výnos z investic: **{_kc(vynos)}**")
                st.info(f"Čisté jmění na konci: **{_kc(jmeni)}**")

        rozdil_cest = ciste_jmeni2 - ciste_jmeni1
        if rozdil_cest > 0:
            st.markdown(
                f'<div class="big-verdict verdict-yes">✅ CESTA 2 JE VÍTĚZ!<br>'
                f'Strategie nastavená v Cestě 2 vám vygeneruje o {_kc(rozdil_cest)} více čistého jmění.</div>',
                unsafe_allow_html=True
            )
        elif rozdil_cest < 0:
            st.markdown(
                f'<div class="big-verdict verdict-no">❌ CESTA 1 JE VÍTĚZ!<br>'
                f'Kroky v Cestě 2 se nevyplatí. Strategie Cesty 1 vám udrží o {_kc(-rozdil_cest)} více.</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="big-verdict verdict-yes">Vyjde to finančně úplně nastejno (rozdíl 0 Kč). '
                'Rozhodněte se podle osobní preference.</div>',
                unsafe_allow_html=True
            )

        # --- HLÍDAČ UDRŽITELNOSTI ČERPÁNÍ ---
        if not df_zivot.empty:
            st.markdown("#### 🚦 Hlídač udržitelnosti čerpání (poslední rok simulace)")
            hu1, hu2 = st.columns(2)
            for col, suff, znak in [(hu1, "C1", "🟩"), (hu2, "C2", "🟧")]:
                stav, rocni_nom, rocni_real, runway = _vyhodnot_udrzitelnost(
                    df_zivot[f"Investice {suff}"].tolist(),
                    df_zivot[f"Investice {suff} (Reálně)"].tolist()
                )
                with col:
                    tempo = (f"Tempo: **{_kc(rocni_nom)}/rok** nominálně, "
                             f"**{_kc(rocni_real)}/rok** reálně.")
                    if stav == "green":
                        st.success(f"{znak} **Udržitelné** — majetek roste i po inflaci.\n\n{tempo}")
                    elif stav == "yellow":
                        st.warning(f"{znak} **Stagnace** — nominálně rostete, ale inflace majetek ujídá.\n\n{tempo}")
                    else:
                        zbytek = f" Při tomto tempu vydrží ~**{runway:.1f} let**." if runway else ""
                        st.error(f"{znak} **Projídání** — čerpáte rychleji, než portfolio vydělá.\n\n{tempo}{zbytek}")

        if s1["crossover"] or s2["crossover"]:
            st.markdown("💡 **Kdy budete teoreticky bez dluhu (Investice > Zůstatek úvěru):**")
            for s, znak, nazev in [(s1, "🟩", "Cesta 1"), (s2, "🟧", "Cesta 2")]:
                if s["crossover"]:
                    rr = int(start_rok + ((start_mesic + s["crossover"] - 2) // 12))
                    mm = int(((start_mesic + s["crossover"] - 2) % 12) + 1)
                    st.write(f"{znak} {nazev}: V **{mm:02d}/{rr}** (za {s['crossover']} měsíců)")

        # --- STROJ ČASU ---
        st.markdown("---")
        st.subheader("⏱️ Stroj času (Cestování skutečným kalendářem s přesností na měsíc)")

        konecny_rok = int(start_rok + (max_months // 12))

        if not df_zivot.empty:
            c_stroj1, c_stroj2 = st.columns(2)
            with c_stroj1:
                rok_analyzy = st.slider(
                    "1. Vyberte rok:", int(start_rok), konecny_rok,
                    min(int(start_rok) + 1, konecny_rok), key="sl_stroj_casu"
                )

            df_vybrany_rok = df_zivot[df_zivot['Rok'] == rok_analyzy]
            dostupne_mesice = df_vybrany_rok['Datum'].apply(lambda x: int(x.split('/')[0])).tolist()

            with c_stroj2:
                if dostupne_mesice:
                    mesic_analyzy = st.slider(
                        "2. Vyberte přesný měsíc:", min(dostupne_mesice), max(dostupne_mesice),
                        max(dostupne_mesice), key="sl_stroj_mesic"
                    )
                else:
                    mesic_analyzy = 1

            datum_hledane = f"{mesic_analyzy:02d}/{rok_analyzy}"
            df_presny_cas = df_zivot[df_zivot['Datum'] == datum_hledane]

            if not df_presny_cas.empty:
                row = df_presny_cas.iloc[-1]
                relativni_mesic = row['Měsíc']

                ca1, ca2 = st.columns(2)
                for col, suff, znak, nazev in [(ca1, "C1", "🟩", "CESTA 1"), (ca2, "C2", "🟧", "CESTA 2")]:
                    with col:
                        st.markdown(
                            f"#### {znak} {nazev}<br><small>Stav k datu: **{datum_hledane}** "
                            f"(Uplynulo celkem {relativni_mesic} měsíců)</small>",
                            unsafe_allow_html=True
                        )
                        st.metric("Zůstatek dluhu", _kc(row[f'Jistina {suff}']))
                        st.metric("Zaplacené úroky celkem", _kc(row[f'Úroky {suff}']))
                        st.markdown("—")
                        st.metric("Hodnota investic (Nominál)", _kc(row[f'Investice {suff}']))
                        st.caption(f"🔵 A: {_kc(row[f'Portfolio A {suff}'])}  |  "
                                   f"🟢 B: {_kc(row[f'Portfolio B {suff}'])}  |  "
                                   f"🏛️ C (FKI): {_kc(row[f'Portfolio C {suff}'])}")
                        st.write(f"Reálná kupní síla: **{_kc(row[f'Investice {suff} (Reálně)'])}**")
                        st.write(f"Z toho čistý výnos: **{_kc(row[f'Výnos {suff}'])}**")
                        st.write(f"Aktuální měsíční renta na účet: **{_kc(row[f'Renta {suff} (měs)'])}**")
                        st.write(f"💰 **Celkem vybráno: {_kc(row[f'Renta {suff} (Celkem)'])}**")
                        bilance = row[f'Investice {suff}'] - row[f'Jistina {suff}']
                        duel_uroky = row[f'Výnos {suff}'] - row[f'Úroky {suff}']
                        st.info(f"**Čistá bilance (Investice − Dluh):** {_kc(bilance)}")
                        if duel_uroky > 0:
                            st.success(f"Investice už překonaly zaplacené úroky o: **{_kc(duel_uroky)}**")
                        else:
                            st.error(f"Zatím vedou úroky nad výnosy o: **{_kc(-duel_uroky)}**")

        # --- GRAF ---
        st.markdown("---")
        st.subheader("Interaktivní Graf (Kliknutím do legendy zapínáte/vypínáte čáry)")

        if not df_zivot.empty:
            fig_z = go.Figure()
            # Dluh
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Jistina C1"],
                                       name="Dluh (Cesta 1)", line=dict(color='#ff4b4b', dash='dash')))
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Jistina C2"],
                                       name="Dluh (Cesta 2)", line=dict(color='#ffa500', width=3)))
            # Investice celkem
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Investice C1"],
                                       name="Investice celkem (Cesta 1)", line=dict(color='#2ecc71', dash='dash')))
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Investice C2"],
                                       name="Investice celkem (Cesta 2)", line=dict(color='#3498db', width=3)))
            # Reálná kupní síla
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Investice C1 (Reálně)"],
                                       name="Investice C1 (Reálně, po inflaci)",
                                       line=dict(color='#e74c3c', dash='dot'), visible='legendonly'))
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Investice C2 (Reálně)"],
                                       name="Investice C2 (Reálně, po inflaci)",
                                       line=dict(color='#9b59b6', dash='dot'), visible='legendonly'))
            # Rozpad portfolií Cesta 1 (skryté v legendě)
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Portfolio A C1"],
                                       name="Portfolio A (C1)", line=dict(color='#1abc9c', dash='dot'), visible='legendonly'))
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Portfolio B C1"],
                                       name="Portfolio B (C1)", line=dict(color='#16a085', dash='dot'), visible='legendonly'))
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Portfolio C C1"],
                                       name="Portfolio C / FKI (C1)", line=dict(color='#f1c40f', dash='dot'), visible='legendonly'))
            # Vloženo a vybráno (Cesta 1)
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Vloženo C1"],
                                       name="Vloženo z vlastního (C1)", line=dict(color='#95a5a6'), visible='legendonly'))
            fig_z.add_trace(go.Scatter(x=df_zivot["Osa_Casu"], y=df_zivot["Renta C1 (Celkem)"],
                                       name="Vybráno na rentě (C1)", line=dict(color='#bdc3c7', dash='dot'), visible='legendonly'))

            fig_z.update_layout(
                template="plotly_dark",
                title="Srovnání Cesty 1 a Cesty 2 v čase (dluh, investice, reálná kupní síla)",
                xaxis_title="Kalendář", yaxis_title="Kč", hovermode="x unified"
            )
            st.plotly_chart(fig_z, use_container_width=True)

            with st.expander("📊 Detailní tabulka & Export (Obě cesty)"):
                df_export_zivot = df_zivot.drop(columns=['Osa_Casu'])
                zobraz_tabulku_s_prepinacem(df_export_zivot, "zivot_uveru_duel.csv")
