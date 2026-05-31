import streamlit as st


def zobraz_tabulku_s_prepinacem(df, filename="data.csv"):
    zobrazit = st.radio(
        "Zobrazit data v tabulce po:",
        ["Rocích (Přehledně)", "Měsících (Detail)"],
        horizontal=True,
        key=filename
    )
    if zobrazit == "Rocích (Přehledně)":
        df_display = df[df['Měsíc'] % 12 == 0].copy()
    else:
        df_display = df.copy()

    df_formatted = df_display.style.format(
        lambda x: f"{x:,.2f}".replace(",", " ") if isinstance(x, (int, float)) else x
    )
    st.dataframe(df_formatted, use_container_width=True)
    df_export = df.round(2)
    st.download_button(
        "📥 Stáhnout CSV pro Excel",
        df_export.to_csv(index=False).encode('utf-8'),
        filename,
        "text/csv",
        key="btn_" + filename
    )
