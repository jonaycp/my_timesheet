# Roster Extractor (last month only)

Mobile-friendly Streamlit app. Upload a monthly Excel and extract all cells containing a given name (default: Magda). It shows **only the latest month in the file**, ordered by day, grouped by **weeks**, and provides a clean, friendly view. No month/place pivot is generated.

## Deploy (no VPS required)

### Streamlit Community Cloud
1. Create a GitHub repo with `app.py` and `requirements.txt`.
2. In Streamlit Cloud, create an app pointing to `app.py`.
3. Share the public URL (it works nicely on mobile).

### Hugging Face Spaces (Streamlit)
1. Create a new Space (type Streamlit).
2. Upload `app.py` and `requirements.txt`.
