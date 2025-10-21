# Extractor de turnos por persona (Streamlit)

App web móvil: sube un Excel mensual y extrae todas las celdas que contienen un nombre (por defecto, Magda), generando una tabla detallada y un resumen por mes/lugar.

## Despliegue sin VPS

### Opción 1: Streamlit Community Cloud
1. Crea un repositorio en GitHub con `app.py` y `requirements.txt`.
2. En Streamlit Community Cloud, crea una app apuntando a `app.py`.
3. Obtendrás una URL pública para compartir (funciona en móvil).

### Opción 2: Hugging Face Spaces
1. Crea un Space (tipo Streamlit).
2. Sube `app.py` y `requirements.txt`.
3. Obtendrás una URL pública (funciona en móvil).

## Ejecutar en local (opcional)
```
python -m venv .venv
source .venv/bin/activate   # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

