import io
import os
import re
from datetime import date

import streamlit as st
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go

# PDF výstup je volitelný — když balíček chybí (např. během deploye), appka poběží dál.
try:
    from fpdf import FPDF
    _PDF_OK = True
except Exception:
    _PDF_OK = False

# Graf do PDF kreslíme přes matplotlib (čistě serverový, bez prohlížeče → funguje na Streamlit Cloudu).
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    _MPL_OK = True
except Exception:
    _MPL_OK = False

# Fonty s českou diakritikou (přibalené v repu ve složce fonts/)
FONTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "fonts"))

# Investiční disclaimer pro klientskou nabídku
DISCLAIMER = (
    "Tento dokument je orientační modelací zpracovanou na základě analýzy fondů a jejich "
    "dlouhodobého průměrného zhodnocení. Nejde o závaznou nabídku, veřejný příslib ani investiční "
    "doporučení ve smyslu zákona. Uvedené výnosy nejsou garantované — skutečné zhodnocení se může "
    "lišit, hodnota investice v čase kolísá a kolísat může i návratnost vložených prostředků. "
    "Minulé výnosy nejsou zárukou výnosů budoucích a uvedená zhodnocení nezahrnují případné změny "
    "úrokové sazby hypotéky v čase. Vstupní poplatek za zprostředkování a nastavení strategie se "
    "řídí smlouvou s poradcem. Při splnění zákonného časového testu (u cenných papírů zpravidla "
    "3 roky držby) mohou být příjmy z prodeje osvobozeny od daně z příjmů; konkrétní podmínky, "
    "aktuální limity a daňové dopady ve své situaci konzultujte s poradcem. Před rozhodnutím se "
    "řiďte statuty a sděleními klíčových informací konkrétních fondů."
)

# --- VÝCHOZÍ HODNOTY (živé posuvníky) ---
VYCHOZI_PAKA = {
    # Klient (personalizace nabídky a věkové osy)
    "pl_klient_jmeno": "",
    "pl_klient_prijmeni": "",
    "pl_klient_vek": 40,
    "pl_hypo": 3000000.0,
    "pl_sazba": 4.69,
    "pl_doba": 20,
    # What-if: plánované jednorázové doplacení hypotéky z portfolia
    "pl_doplatit_on": False,
    "pl_doplatit_rok": 10,
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
    # Volné poznámky poradce do PDF nabídky (úvodní oslovení + závěrečné sdělení)
    "pl_pozn_uvod": "",
    "pl_pozn_zaver": "",
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
              renta_on, renta_roky, renta_vynos, renta_castka,
              vek=40, doplatit_on=False, doplatit_rok=0):
    """Dvoufázová simulace páky.
    Fáze 1: splácení hypotéky, sanace z PUBLIC + kapsy, FKI roste.
    Fáze 2 (volitelně): čerpání renty z vybudovaného majetku.
    Volitelně lze hypotéku plánovaně jednorázově doplatit z portfolia (what-if)."""
    mesice_p1 = int(doba * 12)
    mesice_p2 = int(renta_roky * 12) if renta_on else 0
    mesice_celkem = mesice_p1 + mesice_p2

    splatka = -npf.pmt((sazba / 100) / 12, mesice_p1, hypo) if (mesice_p1 > 0 and hypo > 0) else 0.0

    zust = hypo
    public = public0
    fki = fki0

    public_vycerpan_mesic = None
    jednorazovy_doplatek_mesic = None
    doplatek_plan_mesic = None
    celkem_z_kapsy = 0.0
    celkem_z_fki = 0.0
    celkem_uroky = 0.0
    odkup_kum = 0.0  # kumulativní odkupy z portfolia na sanaci splátky (fáze 1)

    renta_vyplaceno = 0.0
    renta_dosla_mesic = None
    faze2_pool = None
    pool_start_faze2 = None
    majetek_konec_p1 = public0 + fki0
    majetek_real_konec_p1 = public0 + fki0

    xs, h, pub, f, maj, maj_real, zust_real, odk, rnt = [], [], [], [], [], [], [], [], []
    rok_rows = [{
        "Rok": 0, "Věk": float(vek), "Zůstatek hypotéky": zust, "PUBLIC složka": public,
        "FKI složka": fki, "Majetek celkem": public + fki,
        "Majetek reálně": public + fki,
        "Odkupy na sanaci (kumul.)": 0.0, "Vyplacená renta (kumul.)": 0.0
    }]

    for m in range(1, mesice_celkem + 1):
        coef = (1 + (inflace / 100)) ** (m / 12)

        if m <= mesice_p1:
            # ===== FÁZE 1: SPLÁCENÍ + BUDOVÁNÍ =====
            public = public * (1 + (vyn_public / 100) / 12)
            fki = fki * (1 + (vyn_fki / 100) / 12)

            # What-if: plánované jednorázové doplacení hypotéky z portfolia (nejdřív FKI, pak PUBLIC)
            if doplatit_on and doplatek_plan_mesic is None \
                    and m == int(doplatit_rok) * 12 and zust > 0.01:
                k_dopl = zust
                z_fki = min(fki, k_dopl)
                fki -= z_fki
                k_dopl -= z_fki
                celkem_z_fki += z_fki
                z_pub = min(public, k_dopl)
                public -= z_pub
                k_dopl -= z_pub
                zust = max(0.0, k_dopl)
                if zust <= 0.01:
                    zust = 0.0
                    doplatek_plan_mesic = m

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
                odkup_kum += z_public  # odkup z PUBLIC fondu na sanaci splátky

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
                        odkup_kum += z_fki  # odkup z FKI na sanaci splátky
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
        odk.append(odkup_kum)
        rnt.append(renta_vyplaceno)

        if m % 12 == 0:
            rok_rows.append({
                "Rok": m // 12, "Věk": float(vek + m // 12), "Zůstatek hypotéky": max(0.0, zust),
                "PUBLIC složka": public, "FKI složka": fki,
                "Majetek celkem": majetek, "Majetek reálně": majetek / coef,
                "Odkupy na sanaci (kumul.)": odkup_kum,
                "Vyplacená renta (kumul.)": renta_vyplaceno
            })

    df_rok = pd.DataFrame(rok_rows)
    df_mesic = pd.DataFrame({
        "Rok": xs, "Věk": [vek + x for x in xs],
        "Zůstatek hypotéky": h, "PUBLIC složka": pub, "FKI složka": f,
        "Majetek celkem": maj, "Majetek reálně": maj_real, "Dluh reálně": zust_real,
        "Odkupy na sanaci (kumul.)": odk, "Vyplacená renta (kumul.)": rnt
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
        "doplatek_plan_mesic": doplatek_plan_mesic,
        "vek": vek,
        "vek_konec_p1": vek + doba,
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


# =========================================================================
#  PDF NABÍDKA PRO KLIENTA
# =========================================================================

# Barvy (RGB) pro verdikty
_ZELENA = (39, 174, 96)
_ZLUTA = (241, 196, 15)
_CERVENA = (231, 76, 60)
_NAVY = (31, 42, 68)


def _kc_osa(v, _pos=None):
    """Formátování hodnot osy Y (miliony / tisíce)."""
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f} M".replace(".", ",")
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f} k"
    return f"{v:.0f}"


def _graf_pro_pdf(df_mesic, S, renta_on):
    """Vykreslí graf přes matplotlib (serverově, bez prohlížeče) a vrátí PNG bytes.
    Nahoře sekundární osa s věkem klienta."""
    if not _MPL_OK:
        return None
    try:
        vek = S.get("vek")
        x = df_mesic["Rok"]
        fig, ax = plt.subplots(figsize=(11, 4.4), dpi=150)
        ax.plot(x, df_mesic["Zůstatek hypotéky"], color="#e74c3c", lw=1.8, label="Hypotéka")
        ax.plot(x, df_mesic["PUBLIC složka"], color="#2980b9", lw=1.8, label="PUBLIC fond")
        ax.plot(x, df_mesic["FKI složka"], color="#27ae60", lw=2.4, label="FKI fond")
        ax.plot(x, df_mesic["Majetek celkem"], color="#7f8c8d", lw=1.6, ls=":", label="Majetek celkem")
        ax.plot(x, df_mesic["Odkupy na sanaci (kumul.)"], color="#e67e22", lw=1.4, ls="-.",
                label="Odkupy na sanaci (kumul.)")
        if renta_on:
            ax.plot(x, df_mesic["Vyplacená renta (kumul.)"], color="#16a085", lw=2.0,
                    label="Vyplacená renta (kumul.)")
        ax.set_xlabel("Rok")
        ax.set_ylabel("Kč")
        ax.margins(x=0.01)
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.25)
        ax.yaxis.set_major_formatter(FuncFormatter(_kc_osa))

        def _udalost(rok, color, txt):
            ax.axvline(rok, color=color, ls="--", lw=1.2)
            ax.annotate(txt, xy=(rok, 0.97), xycoords=("data", "axes fraction"),
                        xytext=(4, 0), textcoords="offset points",
                        rotation=90, ha="left", va="top", fontsize=8, color=color)

        plan = S.get("doplatek_plan_mesic")
        dop = S["jednorazovy_doplatek_mesic"]
        vyc = S["public_vycerpan_mesic"]
        if plan:
            _udalost(plan / 12, "#8e44ad", "Plánované doplacení")
        elif dop:
            _udalost(dop / 12, "#f39c12", "Úvěr doplacen z FKI")
        elif vyc:
            _udalost(vyc / 12, "#e74c3c", "PUBLIC vyčerpán")
        if renta_on:
            _udalost(S["mesice_p1"] / 12, "#16a085", "Start renty")

        # Sekundární osa nahoře = věk klienta
        if vek is not None:
            secax = ax.secondary_xaxis("top", functions=(lambda r: r + vek, lambda a: a - vek))
            secax.set_xlabel("Věk klienta")

        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=4,
                  frameon=False, fontsize=8.5)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        plt.close("all")
        return None


def _vek_txt(S, rok):
    """Vrátí ' (ve věku N let)' pokud známe věk."""
    vek = S.get("vek")
    return f" (ve věku {int(vek + rok)} let)" if vek is not None else ""


def _verdikty_text(S, doba, splatka, po_vycerpani, renta_on, renta_castka, renta_vynos, renta_roky):
    """Vrátí seznam verdiktů jako (barva, nadpis, text) — textová obdoba boxů z appky."""
    out = []
    vyc_m = S["public_vycerpan_mesic"]
    if S.get("doplatek_plan_mesic"):
        rok_p = (S["doplatek_plan_mesic"] + 11) // 12
        out.append((_ZELENA, "Plánované doplacení hypotéky",
                    f"Podle plánu se hypotéka jednorázově doplatila z portfolia v {rok_p}. roce"
                    f"{_vek_txt(S, rok_p)}. Od té chvíle už není žádná splátka a roste čistý "
                    f"majetek bez dluhu."))
    elif S["jednorazovy_doplatek_mesic"]:
        rok_dop = (S["jednorazovy_doplatek_mesic"] + 11) // 12
        out.append((_ZELENA, "Páka vyšla",
                    f"V {rok_dop}. roce už byl majetek tak velký, že se zbytek úvěru "
                    f"({_kc(S['celkem_z_fki'])}) jednorázově doplatil z FKI fondu. "
                    f"Dál roste čistý majetek bez dluhu."))
    elif vyc_m is None:
        out.append((_ZELENA, "Udržitelné",
                    f"PUBLIC fond celou dobu pokryl sanaci splátky a na konci splácení "
                    f"ještě zbývá {_kc(S['public_konec_p1'])}."))
    else:
        rok_vyc = (vyc_m + 11) // 12
        podil = vyc_m / S["mesice_p1"]
        zbyva_let = (S["mesice_p1"] - vyc_m) / 12
        if po_vycerpani == "Doplácet z FKI fondu":
            dovysv = (f"Od {rok_vyc}. roku se zbytek splátky tahá z FKI "
                      f"(celkem {_kc(S['celkem_z_fki'])}) — ukrajuje se z růstového motoru.")
        else:
            dovysv = (f"Od {rok_vyc}. roku se doplácí celá splátka (~{_kc(splatka)}/měs) "
                      f"z vlastní kapsy ještě {zbyva_let:.1f} let.")
        if podil >= 0.75:
            out.append((_ZLUTA, "Na hraně",
                        f"PUBLIC vydrží až do {rok_vyc}. roku (většinu doby). {dovysv}"))
        else:
            out.append((_CERVENA, "Pozor, vybírá se moc",
                        f"PUBLIC se vyčerpá už v {rok_vyc}. roce. {dovysv} "
                        f"Doporučení: zvýšit spoluúčast nebo přidat do PUBLIC fondu."))

    if renta_on and S["pool_start_faze2"]:
        zaklad = f"Po {int(doba)} letech{_vek_txt(S, doba)} je vybudováno {_kc(S['pool_start_faze2'])}"
        if S["renta_udrzitelna"]:
            out.append((_ZELENA, "Renta prakticky nevyčerpatelná",
                        f"{zaklad}. Při čerpání {_kc(renta_castka)}/měs majetek i tak roste "
                        f"(výnos {renta_vynos:.1f} % > čerpání) — žije se z výnosů, jistina zůstává."))
        elif S["renta_dosla_mesic"]:
            rok_dosla = (S["renta_dosla_mesic"] - S["mesice_p1"]) / 12
            out.append((_CERVENA, "Renta je příliš vysoká",
                        f"{zaklad}, ale při čerpání {_kc(renta_castka)}/měs se majetek vyčerpá za "
                        f"~{rok_dosla:.1f} let{_vek_txt(S, doba + rok_dosla)}. "
                        f"Doporučení: snížit rentu na úroveň výnosů."))
        else:
            out.append((_ZLUTA, "Čerpá se i jistina",
                        f"{zaklad}. Renta {_kc(renta_castka)}/měs je vyšší než výnos, majetek pomalu "
                        f"ubývá, ale za zvolených {int(renta_roky)} let nedojde."))
    return out


def _vytvor_pdf(klient, poradce, hypo, sazba, doba, public0, fki0,
                vyn_public, vyn_fki, spoluucast, inflace, po_vycerpani,
                renta_on, renta_castka, renta_vynos, renta_roky, df_mesic, S,
                vek=None, doplatit_on=False, doplatit_rok=0,
                pozn_uvod="", pozn_zaver=""):
    """Sestaví klientskou nabídku jako PDF a vrátí bytes."""
    png = _graf_pro_pdf(df_mesic, S, renta_on)

    class _Nabidka(FPDF):
        def footer(self):
            self.set_y(-16)
            self.set_font("DejaVu", "", 7)
            self.set_text_color(150, 150, 150)
            zprac = getattr(self, "poradce_jmeno", "") or ""
            radek = ("Orientační propočet, nejde o závaznou nabídku ani investiční doporučení. "
                     "Skutečné výnosy a sazby se mohou lišit.")
            if zprac:
                radek += f"  •  Zpracoval: {zprac}"
            self.multi_cell(0, 3.5, radek, align="C")

    pdf = _Nabidka(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(15, 15, 15)
    pdf.add_font("DejaVu", "", os.path.join(FONTS_DIR, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf"))
    pdf.poradce_jmeno = poradce
    pdf.add_page()

    # ---- HLAVIČKA ----
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_xy(15, 7)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 17)
    pdf.cell(135, 8, "Finanční analýza páky")
    pdf.set_xy(15, 16)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(180, 190, 210)
    pdf.cell(135, 6, "Hypotéka jako investiční nástroj — nabídka")
    pdf.set_xy(150, 7)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(225, 230, 240)
    pdf.cell(45, 6, date.today().strftime("%d.%m.%Y"), align="R")
    klient_radek = ""
    if klient:
        klient_radek = f"Klient: {klient}"
        if vek is not None:
            klient_radek += f", {int(vek)} let"
    elif vek is not None:
        klient_radek = f"Věk klienta: {int(vek)} let"
    if klient_radek:
        pdf.set_xy(110, 16)
        pdf.cell(85, 6, klient_radek, align="R")

    pdf.set_y(34)
    pdf.set_text_color(30, 30, 30)

    # ---- ÚVODNÍ OSLOVENÍ PORADCE (volitelné) ----
    if pozn_uvod and pozn_uvod.strip():
        pdf.set_x(19)
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(45, 45, 45)
        y0 = pdf.get_y()
        pdf.multi_cell(176, 5.2, pozn_uvod.strip())
        y1 = pdf.get_y()
        pdf.set_fill_color(*_NAVY)
        pdf.rect(15, y0, 1.8, y1 - y0, "F")
        pdf.ln(3)
        pdf.set_text_color(30, 30, 30)

    # ---- SEKCE: ZADÁNÍ ----
    _pdf_nadpis(pdf, "Zadání")
    params = [
        ("Výše hypotéky", _kc(hypo)),
        ("Sazba hypotéky", f"{sazba:.2f} % p.a."),
        ("Doba splácení", f"{int(doba)} let"),
        ("Vklad do PUBLIC fondu", _kc(public0)),
        ("Vklad do FKI fondu", _kc(fki0)),
        ("Výnos PUBLIC", f"{vyn_public:.1f} % p.a."),
        ("Výnos FKI", f"{vyn_fki:.1f} % p.a."),
        ("Spoluúčast z kapsy", f"{_kc(spoluucast)} / měs"),
        ("Inflace", f"{inflace:.1f} % p.a."),
        ("Po vyčerpání PUBLIC", po_vycerpani),
    ]
    if doplatit_on:
        params.append(("Plánované doplacení úvěru", f"v {int(doplatit_rok)}. roce"))
    pdf.set_font("DejaVu", "", 9.5)
    for i in range(0, len(params), 2):
        y0 = pdf.get_y()
        pdf.set_text_color(110, 110, 110)
        pdf.cell(38, 6, params[i][0])
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("DejaVu", "B", 9.5)
        pdf.cell(52, 6, params[i][1])
        pdf.set_font("DejaVu", "", 9.5)
        if i + 1 < len(params):
            pdf.set_text_color(110, 110, 110)
            pdf.cell(38, 6, params[i + 1][0])
            pdf.set_text_color(20, 20, 20)
            pdf.set_font("DejaVu", "B", 9.5)
            pdf.cell(52, 6, params[i + 1][1])
            pdf.set_font("DejaVu", "", 9.5)
        pdf.set_xy(15, y0 + 7)

    # ---- SEKCE: KLÍČOVÉ VÝSLEDKY ----
    _pdf_nadpis(pdf, "Klíčové výsledky")
    boxy = [
        ("Měsíční splátka hypotéky", _kc(S["splatka"]), _NAVY),
        ("Vybudovaný majetek (konec splácení)", _kc(S["majetek_konec_p1"]), _NAVY),
        ("Čistý zisk z arbitráže", _kc(S["arbitraz"]), _ZELENA),
        ("Reálný majetek (dnešní Kč)", _kc(S["majetek_real_konec_p1"]), _NAVY),
        ("Reálný zbytek dluhu (po inflaci)", _kc(S["dluh_real_konec_p1"]), _NAVY),
        ("Zaplaceno z vlastní kapsy", _kc(S["celkem_z_kapsy"]), _NAVY),
    ]
    bw, bh, gap = 56.66, 18, 4
    y_start = pdf.get_y()
    for idx, (label, value, accent) in enumerate(boxy):
        col = idx % 3
        row = idx // 3
        x = 15 + col * (bw + gap)
        y = y_start + row * (bh + gap)
        _pdf_box(pdf, x, y, bw, bh, label, value, accent)
    pdf.set_y(y_start + 2 * (bh + gap) + 1)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 5, f"Z toho úroky zaplacené bance: {_kc(S['celkem_uroky'])}",
             new_x="LMARGIN", new_y="NEXT")
    if renta_on and S["pool_start_faze2"]:
        pdf.cell(0, 5, f"Celkem vyčerpáno na rentě: {_kc(S['renta_vyplaceno'])}",
                 new_x="LMARGIN", new_y="NEXT")

    # ---- GRAF ----
    _pdf_nadpis(pdf, "Vývoj majetku a dluhu v čase")
    if png:
        pdf.image(io.BytesIO(png), x=15, w=180)
    else:
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 6, "(Graf se nepodařilo vykreslit.)", new_x="LMARGIN", new_y="NEXT")

    # ---- VYHODNOCENÍ ----
    _pdf_nadpis(pdf, "Vyhodnocení")
    for barva, nadpis, text in _verdikty_text(
        S, doba, S["splatka"], po_vycerpani, renta_on, renta_castka, renta_vynos, renta_roky
    ):
        y0 = pdf.get_y()
        pdf.set_fill_color(*barva)
        pdf.rect(15, y0 + 0.5, 2, 9, "F")
        pdf.set_xy(19, y0)
        pdf.set_font("DejaVu", "B", 10.5)
        pdf.set_text_color(*barva)
        pdf.cell(0, 5, nadpis, new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(19)
        pdf.set_font("DejaVu", "", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(176, 4.6, text)
        pdf.ln(2.5)

    # ---- SDĚLENÍ PORADCE (volitelné) ----
    if pozn_zaver and pozn_zaver.strip():
        _pdf_nadpis(pdf, "Sdělení poradce")
        pdf.set_font("DejaVu", "", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(176, 4.8, pozn_zaver.strip())
        pdf.ln(1)

    # ---- UPOZORNĚNÍ (DISCLAIMER) ----
    _pdf_nadpis(pdf, "Upozornění")
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(95, 95, 95)
    pdf.multi_cell(180, 4, DISCLAIMER)

    out = pdf.output()
    return bytes(out)


def _pdf_nadpis(pdf, txt):
    pdf.ln(1.5)
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 7, txt, new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y()
    pdf.set_draw_color(*_NAVY)
    pdf.set_line_width(0.3)
    pdf.line(15, y, 195, y)
    pdf.ln(2)
    pdf.set_text_color(30, 30, 30)


def _pdf_box(pdf, x, y, w, h, label, value, accent):
    pdf.set_fill_color(246, 248, 250)
    pdf.set_draw_color(225, 228, 232)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, w, h, "DF")
    pdf.set_fill_color(*accent)
    pdf.rect(x, y, 1.8, h, "F")
    pdf.set_xy(x + 4, y + 3)
    pdf.set_font("DejaVu", "", 7.5)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(w - 6, 3.6, label)
    pdf.set_xy(x + 4, y + h - 9)
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*accent)
    pdf.cell(w - 6, 6, value)


def render(tab):
    _init_state()

    with tab:
        st.header("⚡ Páka LIVE: Hypotéka jako investiční nástroj")
        st.caption(
            "Rychlá živá modelace. Vezmeme hypotéku, peníze investujeme (PUBLIC + FKI) a "
            "splátku sanujeme z PUBLIC fondu + vlastní kapsy. **Tahej posuvníky** a sleduj, "
            "jestli to vychází. FKI necháváme růst jako motor majetku."
        )

        # --- KLIENT (personalizace nabídky a věkové osy) ---
        k1, k2, k3 = st.columns([2, 2, 1])
        klient_jmeno = k1.text_input("👤 Jméno klienta", key="pl_klient_jmeno")
        klient_prijmeni = k2.text_input("Příjmení", key="pl_klient_prijmeni")
        vek = k3.number_input("Věk dnes", min_value=18, max_value=90, step=1, key="pl_klient_vek")
        klient_cele = f"{klient_jmeno} {klient_prijmeni}".strip()

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

        # --- WHAT-IF: PLÁNOVANÉ DOPLACENÍ HYPOTÉKY Z PORTFOLIA ---
        doplatit_on = st.checkbox(
            "🔪 Co kdybych hypotéku v určitém roce jednorázově doplatil z portfolia?",
            key="pl_doplatit_on",
            help="Modelace pro klienta s dobrým cashflow: v daném roce uměle 'zabijeme' celý zbytek "
                 "hypotéky z portfolia (nejdřív FKI, pak PUBLIC) — i dřív, než by došel PUBLIC fond. "
                 "Od té chvíle není splátka a majetek roste bez dluhu."
        )
        # Rok doplacení nesmí přesáhnout dobu splácení → ořízneme dřív, než vykreslíme posuvník
        max_rok_dopl = max(1, int(doba))
        if st.session_state.get("pl_doplatit_rok", 1) > max_rok_dopl:
            st.session_state["pl_doplatit_rok"] = max_rok_dopl
        doplatit_rok = st.slider(
            "📅 V kterém roce doplatit úvěr", 1, max_rok_dopl, step=1,
            key="pl_doplatit_rok", disabled=not doplatit_on
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
            renta_on, renta_roky, renta_vynos, renta_castka,
            vek=int(vek), doplatit_on=doplatit_on, doplatit_rok=doplatit_rok
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
        # Kumulativní odkupy z portfolia na sanaci splátky (fáze 1)
        fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["Odkupy na sanaci (kumul.)"],
                                 name="Odkupy na sanaci (kumul.)",
                                 line=dict(color="#e67e22", width=2, dash="dashdot"),
                                 hovertemplate="Odkupy na sanaci: %{y:,.0f} Kč<extra></extra>"))
        # Kumulativní vyplacená renta (fáze 2) — roste od startu čerpání
        if renta_on:
            fig.add_trace(go.Scatter(x=df_mesic["Rok"], y=df_mesic["Vyplacená renta (kumul.)"],
                                     name="Vyplacená renta (kumul.)",
                                     line=dict(color="#1abc9c", width=2.5),
                                     hovertemplate="Vyplacená renta: %{y:,.0f} Kč<extra></extra>"))

        # Svislé čáry událostí. Pozor: při "Jednorázově doplatit z FKI" padne vyčerpání PUBLIC
        # a doplacení úvěru do stejného měsíce → sloučíme do jedné čáry, popisky dáme na opačné
        # strany, ať se text nepřekrývá.
        def _vek_popis(rok):
            return f" • {int(vek) + int(round(rok))} let"

        plan = S["doplatek_plan_mesic"]
        dop = S["jednorazovy_doplatek_mesic"]
        vyc = S["public_vycerpan_mesic"]
        if plan:
            r = plan / 12
            fig.add_vline(x=r, line_width=2, line_dash="dot", line_color="#9b59b6",
                          annotation_text=f"🔪 Plánované doplacení{_vek_popis(r)}",
                          annotation_position="top left", annotation_font_color="#9b59b6")
        elif dop:
            r = dop / 12
            fig.add_vline(x=r, line_width=2, line_dash="dot", line_color="#f1c40f",
                          annotation_text=f"💸 Úvěr doplacen z FKI{_vek_popis(r)}",
                          annotation_position="top left", annotation_font_color="#f1c40f")
        elif vyc:
            r = vyc / 12
            fig.add_vline(x=r, line_width=2, line_dash="dash", line_color="#e74c3c",
                          annotation_text=f"PUBLIC vyčerpán{_vek_popis(r)}",
                          annotation_position="top left", annotation_font_color="#e74c3c")
        if renta_on:
            r = S["mesice_p1"] / 12
            fig.add_vline(x=r, line_width=2, line_dash="dash", line_color="#1abc9c",
                          annotation_text=f"🥕 Start renty{_vek_popis(r)}",
                          annotation_position="top right", annotation_font_color="#1abc9c")

        # Osa X ukazuje rok i věk klienta (dvouřádkové popisky)
        celkem_let = int(round(S["mesice_celkem"] / 12))
        krok = 5 if celkem_let > 12 else 2
        tickvals = list(range(0, celkem_let + 1, krok))
        ticktext = [f"{rr}<br>{int(vek) + rr} let" for rr in tickvals]
        fig.update_layout(
            template="plotly_dark", title="Analýza finanční páky a rentability",
            yaxis_title="Hodnota (Kč)", hovermode="x unified",
            xaxis=dict(title="Rok / věk klienta", tickmode="array",
                       tickvals=tickvals, ticktext=ticktext),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- VERDIKT FÁZE 1 ---
        vyc_m = S["public_vycerpan_mesic"]
        if S["doplatek_plan_mesic"]:
            rok_p = (S["doplatek_plan_mesic"] + 11) // 12
            st.markdown(
                f'<div class="big-verdict verdict-yes">🟢 PLÁNOVANÉ DOPLACENÍ — v {rok_p}. roce '
                f'(ve věku {int(vek) + rok_p} let) jsi jednorázově doplatil zbytek hypotéky z portfolia. '
                f'Od té chvíle nemáš splátku a roste ti čistý majetek bez dluhu.</div>',
                unsafe_allow_html=True
            )
        elif S["jednorazovy_doplatek_mesic"]:
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
                f"#### 🥕 A teď ta odměna: po {int(doba)} letech (ve věku {int(vek) + int(doba)} let) "
                f"máš vybudováno **{_kc(S['pool_start_faze2'])}** a začínáš čerpat rentu."
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
        # Souhrnnou tabulku držíme přehlednou — kumulativní odkupy/rentu necháme do detailu níž
        df_fmt = df_tab.drop(columns=["Odkupy na sanaci (kumul.)", "Vyplacená renta (kumul.)"]).copy()
        df_fmt["Věk"] = df_fmt["Věk"].astype(int)
        for sl in ["Zůstatek hypotéky", "PUBLIC složka", "FKI složka", "Majetek celkem", "Majetek reálně"]:
            df_fmt[sl] = df_fmt[sl].apply(_kc)
        st.dataframe(df_fmt, use_container_width=True, hide_index=True)

        # --- SOUHRNNÉ METRIKY ---
        st.markdown("---")
        f1, f2, f3 = st.columns(3)
        f1.metric("🏆 Vybudovaný majetek (konec splácení)", _kc(S["majetek_konec_p1"]))
        f2.metric("📈 Čistý zisk z arbitráže", _kc(S["arbitraz"]),
                  help="Vybudovaný majetek minus vše vložené z vlastní kapsy (půjčená jistina se splatí).")
        if S["doplatek_plan_mesic"]:
            f3.metric("🔵 Status hypotéky", f"Plánovaně doplacena v {(S['doplatek_plan_mesic'] + 11) // 12}. roce")
        elif S["jednorazovy_doplatek_mesic"]:
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
            df_rok_fmt["Věk"] = df_rok_fmt["Věk"].astype(int)
            for sl in ["Zůstatek hypotéky", "PUBLIC složka", "FKI složka", "Majetek celkem",
                       "Majetek reálně", "Odkupy na sanaci (kumul.)", "Vyplacená renta (kumul.)"]:
                df_rok_fmt[sl] = df_rok_fmt[sl].apply(_kc)
            st.dataframe(df_rok_fmt, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Stáhnout CSV pro Excel",
                df_rok.round(2).to_csv(index=False).encode("utf-8"),
                "paka_live.csv", "text/csv", key="btn_paka_live_csv"
            )

        # --- NABÍDKA PRO KLIENTA (PDF) ---
        with st.expander("📄 Nabídka pro klienta (PDF)"):
            if not _PDF_OK:
                st.warning("Generování PDF zatím není dostupné (instaluje se balíček fpdf2). "
                           "Zkus to prosím za chvíli po nasazení.")
            else:
                st.caption("Vygeneruje klientskou nabídku s aktuálními hodnotami (zadání, klíčová "
                           "čísla, graf s věkovou osou, vyhodnocení a disclaimer). Jméno a věk se "
                           "berou z horní části. PDF odráží hodnoty v okamžiku vygenerování — "
                           "po změně posuvníků vygeneruj znovu.")
                poradce = st.text_input("Zpracoval (poradce)", value="Jiří Vrána", key="pl_poradce")
                pozn_uvod = st.text_area(
                    "✍️ Úvodní oslovení klienta (volitelné)", key="pl_pozn_uvod",
                    placeholder="Vážený pane Nováku, na základě naší konzultace jsem pro Vás připravil…",
                    help="Osobní úvod hned pod hlavičkou nabídky. Když necháš prázdné, v PDF se nezobrazí."
                )
                pozn_zaver = st.text_area(
                    "🗒️ Sdělení poradce – komentář ke strategii (volitelné)", key="pl_pozn_zaver",
                    placeholder="Toto rozložení PUBLIC/FKI volím proto, že…",
                    help="Věcný komentář na závěr (před upozorněním). Když necháš prázdné, v PDF se nezobrazí."
                )
                if klient_cele:
                    st.caption(f"📋 Nabídka pro: **{klient_cele}**, {int(vek)} let")
                if st.button("🖨️ Vygenerovat nabídku (PDF)", key="btn_paka_pdf_gen"):
                    with st.spinner("Generuji PDF…"):
                        try:
                            st.session_state["pl_pdf_bytes"] = _vytvor_pdf(
                                klient_cele, poradce, hypo, sazba, doba, public0, fki0,
                                vyn_public, vyn_fki, spoluucast, inflace, po_vycerpani,
                                renta_on, renta_castka, renta_vynos, renta_roky, df_mesic, S,
                                vek=int(vek), doplatit_on=doplatit_on, doplatit_rok=doplatit_rok,
                                pozn_uvod=pozn_uvod, pozn_zaver=pozn_zaver
                            )
                        except Exception as e:
                            st.session_state.pop("pl_pdf_bytes", None)
                            st.error(f"Nepodařilo se vygenerovat PDF: {e}")
                if st.session_state.get("pl_pdf_bytes"):
                    bezpecne_jmeno = re.sub(r"[^\w\-]+", "_", (klient_cele or "klient").strip()) or "klient"
                    st.download_button(
                        "📥 Stáhnout nabídku (PDF)",
                        st.session_state["pl_pdf_bytes"],
                        file_name=f"nabidka_paka_{bezpecne_jmeno}.pdf",
                        mime="application/pdf",
                        key="btn_paka_pdf_dl"
                    )
