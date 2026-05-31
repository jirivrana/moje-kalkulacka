import streamlit as st
import json

from moduly import modul1_tvm, modul2_zivot, modul3_duel, modul4_paka, modul5_investice, modul6_fire, modul7_paka_live

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Profi Finanční Simulátor 6.8", page_icon="🏦", layout="wide")

st.markdown("""
<style>
    .big-verdict { font-size: 18px; font-weight: bold; padding: 15px; border-radius: 8px; margin-top: 15px; margin-bottom: 15px;}
    .verdict-yes { background-color: rgba(46, 204, 113, 0.2); border-left: 5px solid #2ecc71; color: #2ecc71; }
    .verdict-no { background-color: rgba(255, 75, 75, 0.2); border-left: 5px solid #ff4b4b; color: #ff4b4b; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("🏦 Profi Finanční Simulátor 6.8")

# --- POSTRANNÍ PANEL: PAMĚŤ (SAVE/LOAD) ---
with st.sidebar:
    st.header("💾 Paměť klienta")
    st.write("Uložte si kompletní klientský profil (Modul 2 a Modul 5) do počítače na příště.")

    def ziskej_data_k_ulozeni():
        ciste_udalosti_zivot = []
        for ev in st.session_state.get("zivot_events", []):
            ciste_ev = {k: v for k, v in ev.items() if k not in ["ui_info"]}
            ciste_udalosti_zivot.append(ciste_ev)

        ciste_udalosti_inv = []
        for ev in st.session_state.get("inv_events", []):
            ciste_ev = {k: v for k, v in ev.items() if k not in ["ui_info"]}
            ciste_udalosti_inv.append(ciste_ev)

        data = {
            # Modul 2
            "sm": st.session_state.get("sm", 1),
            "sr": st.session_state.get("sr", 2024),
            "z1": st.session_state.get("z1", 3000000.0),
            "z2": st.session_state.get("z2", 5.5),
            "z3": st.session_state.get("z3", 30),
            "z_typ_uveru": st.session_state.get("z_typ_uveru", "Anuita (klasická)"),
            "z9": st.session_state.get("z9", 0.0),
            "z10": st.session_state.get("z10", 3000.0),
            "z11": st.session_state.get("z11", 6.0),
            "z_odkup": st.session_state.get("z_odkup", 0.0),
            "z12": st.session_state.get("z12", 0.0),
            "z13": st.session_state.get("z13", 0.0),
            "z14": st.session_state.get("z14", 8.0),
            "z_odkup_ac": st.session_state.get("z_odkup_ac", 0.0),
            "z15": st.session_state.get("z15", 0.0),
            "z16": st.session_state.get("z16", 0.0),
            "z17": st.session_state.get("z17", 10.0),
            "z_infl": st.session_state.get("z_infl", 3.0),
            "zivot_events": ciste_udalosti_zivot,
            "zivot_event_id": st.session_state.get("zivot_event_id", 0),
            # Modul 5
            "ia1": st.session_state.get("ia1", 1000000.0),
            "ia2": st.session_state.get("ia2", 5000.0),
            "ia3": st.session_state.get("ia3", 8.0),
            "infl": st.session_state.get("infl", 3.0),
            "inv_idx": st.session_state.get("inv_idx", True),
            "io_b": st.session_state.get("io_b", 0.0),
            "io_v": st.session_state.get("io_v", 0.0),
            "ib1": st.session_state.get("ib1", 0.0),
            "ib2": st.session_state.get("ib2", 0.0),
            "ib3": st.session_state.get("ib3", 4.0),
            "sl_i": st.session_state.get("sl_i", 20),
            "inv_events": ciste_udalosti_inv,
            "inv_event_id": st.session_state.get("inv_event_id", 0),
            # Modul 7 (Páka LIVE)
            "pl_klient_jmeno": st.session_state.get("pl_klient_jmeno", ""),
            "pl_klient_prijmeni": st.session_state.get("pl_klient_prijmeni", ""),
            "pl_klient_vek": st.session_state.get("pl_klient_vek", 40),
            "pl_hypo": st.session_state.get("pl_hypo", 3000000.0),
            "pl_sazba": st.session_state.get("pl_sazba", 4.69),
            "pl_doba": st.session_state.get("pl_doba", 20),
            "pl_doplatit_on": st.session_state.get("pl_doplatit_on", False),
            "pl_doplatit_rok": st.session_state.get("pl_doplatit_rok", 10),
            "pl_public": st.session_state.get("pl_public", 1500000.0),
            "pl_fki": st.session_state.get("pl_fki", 1500000.0),
            "pl_vyn_public": st.session_state.get("pl_vyn_public", 7.0),
            "pl_vyn_fki": st.session_state.get("pl_vyn_fki", 10.0),
            "pl_spoluucast": st.session_state.get("pl_spoluucast", 7000.0),
            "pl_inflace": st.session_state.get("pl_inflace", 3.0),
            "pl_po_vycerpani": st.session_state.get("pl_po_vycerpani", "Doplácet z vlastní kapsy"),
            "pl_renta_on": st.session_state.get("pl_renta_on", False),
            "pl_renta_roky": st.session_state.get("pl_renta_roky", 10),
            "pl_renta_vynos": st.session_state.get("pl_renta_vynos", 8.0),
            "pl_renta_castka": st.session_state.get("pl_renta_castka", 50000.0),
            "pl_pozn_uvod": st.session_state.get("pl_pozn_uvod", ""),
            "pl_pozn_zaver": st.session_state.get("pl_pozn_zaver", "")
        }
        return json.dumps(data)

    st.download_button(
        label="📥 Uložit scénář (Stáhnout .json)",
        data=ziskej_data_k_ulozeni(),
        file_name="klient_scenar.json",
        mime="application/json"
    )

    st.markdown("---")

    nahrat_soubor = st.file_uploader("📂 Nahrát scénář z PC", type="json")
    if nahrat_soubor is not None:
        if st.button("Načíst data a přepsat kalkulačku"):
            nactena_data = json.load(nahrat_soubor)
            for klic, hodnota in nactena_data.items():
                st.session_state[klic] = hodnota
            st.success("✅ Scénář nahrán! Data jsou aktualizována.")
            st.rerun()

    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("""
        <div style="text-align: center; color: #888888; font-size: 12px;">
            Vyvinuto s ❤️ pro špičkové poradenství.<br>
            <b>Developed by Jiří Vrána</b><br>
            © 2026 Všechna práva vyhrazena.
        </div>
    """, unsafe_allow_html=True)

# --- NAVIGACE A ZÁLOŽKY ---
tab_tvm, tab_zivot, tab_duel, tab_paka, tab_investice, tab_fire, tab_paka_live = st.tabs([
    "🧮 1. Rychlá TVM",
    "⏳ 2. Život úvěru (Duel)",
    "⚔️ 3. Porovnání 2 Úvěrů",
    "⚖️ 4. Páka (Cash vs Hypo)",
    "📈 5. Čisté Investice",
    "🏖️ 6. FIRE & Renta",
    "⚡ 7. Páka LIVE"
])

modul1_tvm.render(tab_tvm)
modul2_zivot.render(tab_zivot)
modul3_duel.render(tab_duel)
modul4_paka.render(tab_paka)
modul5_investice.render(tab_investice)
modul6_fire.render(tab_fire)
modul7_paka_live.render(tab_paka_live)
