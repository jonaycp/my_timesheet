import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Extractor de turnos", page_icon="🗂️", layout="wide")
st.title("🗂️ Extractor de turnos por persona")
st.markdown(
    "Sube el Excel mensual y te devolveré todas las filas donde aparece el nombre indicado, "
    "con **Fecha**, **Día**, **Lugar**, **Horario** y el **texto original** — además de un "
    "resumen por **mes y lugar**."
)

with st.sidebar:
    st.header("⚙️ Opciones")
    nombre_objetivo = st.text_input("Nombre a buscar", value="Magda").strip()
    st.caption("Búsqueda que contiene (no exacta), sin distinguir mayúsculas/minúsculas.")

archivo = st.file_uploader("Arrastra o selecciona el archivo .xlsx", type=["xlsx"]) 

@st.cache_data(show_spinner=False)
def leer_excel(archivo):
    xls = pd.ExcelFile(archivo)
    hojas = xls.sheet_names
    return hojas

@st.cache_data(show_spinner=False)
def procesar_hoja(archivo, nombre_hoja, nombre_objetivo):
    df = pd.read_excel(archivo, sheet_name=nombre_hoja, header=None)

    if df.shape[0] < 3 or df.shape[1] < 4:
        raise ValueError("La hoja no parece tener el formato esperado (mínimo 3 filas y 4 columnas).")

    places = df.iloc[0].ffill(axis=0)
    shifts = df.iloc[1].ffill(axis=0)

    headers = [f"{str(p)} | {str(s)}" for p, s in zip(places, shifts)]
    tmp = df.copy()
    tmp.columns = headers
    tmp = tmp.drop([0, 1]).reset_index(drop=True)

    tmp.rename(columns={tmp.columns[0]: "Fecha", tmp.columns[1]: "Día"}, inplace=True)
    tmp["Fecha"] = pd.to_datetime(tmp["Fecha"], errors="coerce")

    resultados = []
    nombre_lower = nombre_objetivo.lower()
    for col in tmp.columns[2:]:
        if "|" not in col:
            continue
        lugar, horario = [x.strip() for x in col.split("|", 1)]
        for i, valor in enumerate(tmp[col]):
            if isinstance(valor, str) and nombre_lower in valor.lower():
                resultados.append({
                    "Fecha": tmp.loc[i, "Fecha"],
                    "Día": tmp.loc[i, "Día"],
                    "Lugar": lugar,
                    "Horario": horario,
                    "Texto": valor.strip()
                })

    if not resultados:
        registros = pd.DataFrame(columns=["Fecha", "Día", "Lugar", "Horario", "Texto"]) 
        pivot = pd.DataFrame(columns=["Mes", "Lugar", f"Días con {nombre_objetivo}"])
    else:
        registros = pd.DataFrame(resultados)
        registros["Mes"] = registros["Fecha"].dt.to_period("M").astype(str)
        pivot = (
            pd.pivot_table(registros, values="Texto", index=["Mes", "Lugar"], aggfunc="count")
            .reset_index().rename(columns={"Texto": f"Días con {nombre_objetivo}"})
        )

    return registros, pivot

if archivo:
    try:
        hojas = leer_excel(archivo)
        hoja_sel = st.selectbox("Hoja a procesar", options=hojas, index=0)

        if st.button("Procesar", type="primary"):
            with st.spinner("Procesando..."):
                registros, pivot = procesar_hoja(archivo, hoja_sel, nombre_objetivo)

            st.success("¡Listo!")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📜 Registros encontrados")
                st.dataframe(registros, use_container_width=True)
            with col2:
                st.subheader("📊 Resumen por mes y lugar")
                st.dataframe(pivot, use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                registros.to_excel(writer, index=False, sheet_name="Registros")
                pivot.to_excel(writer, index=False, sheet_name="Resumen")
            st.download_button(
                label="⬇️ Descargar Excel (Registros + Resumen)",
                data=buffer.getvalue(),
                file_name=f"resultado_{nombre_objetivo.lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"Ocurrió un problema: {e}")
        st.exception(e)

st.markdown("""
---
### 📝 Notas de uso
- La app asume que **fila 0 = lugares** y **fila 1 = horarios**, y que la **columna 0** es **Fecha** y la **columna 1** es **Día**.
- Busca coincidencias **que contengan** el nombre (p. ej., "Bára +Magda", "Magda do 15").
- Exporta un Excel con dos hojas: **Registros** y **Resumen**.
""")