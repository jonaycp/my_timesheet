import io
import pandas as pd
import streamlit as st
from datetime import timedelta

st.set_page_config(page_title="Roster Extractor", page_icon="🗂️", layout="wide")

st.title("🗂️ Roster Extractor (choose month)")
st.caption("Upload the Excel, type a name (default: Magda). The app will read the **Směny** sheet automatically and let you pick the month to display, newest first.")

with st.sidebar:
    st.header("⚙️ Options")
    target_name = st.text_input("Name to search", value="Magda").strip()
    st.caption("Case-insensitive, *contains* search (e.g., it matches 'Bára +Magda' or 'Magda till 15').")

uploaded = st.file_uploader("Drop or select the .xlsx file", type=["xlsx"])

def _safe_to_datetime(s):
    return pd.to_datetime(s, errors="coerce")

def _fix_headers(df):
    # Row 0 = places, Row 1 = shifts
    places = df.iloc[0].ffill(axis=0)
    shifts = df.iloc[1].ffill(axis=0)
    headers = [f"{str(p)} | {str(s)}" for p, s in zip(places, shifts)]
    out = df.copy()
    out.columns = headers
    out = out.drop([0, 1]).reset_index(drop=True)
    # First two columns are Date and Weekday labels
    out.rename(columns={out.columns[0]: "Date", out.columns[1]: "Weekday"}, inplace=True)
    out["Date"] = _safe_to_datetime(out["Date"])
    return out

def _extract_matches(df, name):
    results = []
    name_l = name.lower()
    for col in df.columns[2:]:
        if "|" not in col:
            continue
        place, shift = [x.strip() for x in col.split("|", 1)]
        series = df[col]
        for i, val in enumerate(series):
            if isinstance(val, str) and name_l in val.lower():
                results.append({
                    "Date": df.loc[i, "Date"],
                    "Weekday": df.loc[i, "Weekday"],
                    "Place": place,
                    "Shift": shift,
                    "CellText": val.strip(),
                })
    return pd.DataFrame(results) if results else pd.DataFrame(columns=["Date","Weekday","Place","Shift","CellText"])

def _week_start(d):
    # Monday as start of week
    if pd.isna(d):
        return d
    return d - timedelta(days=d.weekday())

def _human_week_label(start_date):
    end_date = start_date + timedelta(days=6)
    return f"{start_date:%b %d} – {end_date:%b %d}"

def render_weekly_view(df):
    # Descending order by week then date (newest first)
    df = df.copy()
    df["WeekStart"] = df["Date"].apply(_week_start)
    df.sort_values(["WeekStart", "Date", "Place", "Shift"], ascending=[False, False, True, True], inplace=True)

    # Summary header
    total_days = df["Date"].dt.normalize().nunique()
    total_entries = len(df)
    unique_places = df["Place"].nunique()

    st.markdown("### Overview")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Distinct work days", int(total_days))
    with c2:
        st.metric("Total assignments", int(total_entries))
    with c3:
        st.metric("Places this month", int(unique_places))

    # Render per week (newest first)
    for wk, dfw in df.groupby("WeekStart", sort=False):
        st.markdown("---")
        st.subheader(f"Week of {_human_week_label(wk)}")

        # Group per calendar day (newest first within the week)
        for day, dfd in dfw.groupby(dfw["Date"].dt.date, sort=False):
            st.markdown(f"##### {pd.to_datetime(day):%A, %b %d}")
            for _, row in dfd.iterrows():
                st.markdown(f"""
<div style='padding:10px;border:1px solid #e6e6e6;border-radius:12px;margin-bottom:6px;'>
  <div style='font-weight:600;'>{row['Place']}</div>
  <div style='opacity:0.9'>{row['Shift']}</div>
  <div style='font-size:0.95em;color:#444;'>“{row['CellText']}”</div>
</div>
""", unsafe_allow_html=True)

if uploaded:
    try:
        # Always load the 'Směny' sheet. If it doesn't exist, fallback to the first sheet.
        xls = pd.ExcelFile(uploaded)
        sheet_name = "Směny" if "Směny" in xls.sheet_names else xls.sheet_names[0]
        raw = pd.read_excel(uploaded, sheet_name=sheet_name, header=None)

        wide = _fix_headers(raw)
        matches = _extract_matches(wide, target_name)

        if matches.empty:
            st.warning("No matches found in the selected file for that name.")
        else:
            # Build available months from data and let the user pick (descending)
            matches["YearMonth"] = matches["Date"].dt.to_period("M").astype(str)
            months = sorted(matches["YearMonth"].dropna().unique(), reverse=True)
            default_index = 0  # newest first
            chosen = st.selectbox("Month to display", options=months, index=default_index)

            # Filter to chosen month and sort descending by date for rendering
            view = matches[matches["YearMonth"] == chosen].copy()
            view.drop(columns=["YearMonth"], inplace=True)
            if view.empty:
                st.info("No entries for the selected month.")
            else:
                # Render weekly cards (descending)
                render_weekly_view(view)

                # Download of this month's assignments only
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    view.sort_values(["Date","Place","Shift"], ascending=[False, True, True]).to_excel(writer, index=False, sheet_name="Assignments")
                st.download_button(
                    label=f"⬇️ Download Excel ({chosen})",
                    data=buffer.getvalue(),
                    file_name=f"{target_name.lower()}_{chosen}_assignments.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.exception(e)

st.markdown("""
---
### Notes
- The app automatically reads the **Směny** sheet (fallback to the first sheet if missing).
- Pick the **month** you want (months are listed from newest to oldest).
- The view is sorted **newest to oldest**, grouped into **weeks** for clarity.
""")