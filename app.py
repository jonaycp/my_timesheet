import io
import math
import pandas as pd
import streamlit as st
from datetime import timedelta

st.set_page_config(page_title="Roster Extractor", page_icon="🗂️", layout="wide")

st.title("🗂️ Roster Extractor (last month only)")
st.caption("Upload the monthly Excel, type a name (default: Magda), and get a clean weekly view for the **latest month found in the file**.")

with st.sidebar:
    st.header("⚙️ Options")
    target_name = st.text_input("Name to search", value="Magda").strip()
    st.caption("Case-insensitive, *contains* search, e.g. it will match 'Bára +Magda' or 'Magda till 15'.")

uploaded = st.file_uploader("Drop or select the .xlsx file", type=["xlsx"])

@st.cache_data(show_spinner=False)
def list_sheets(file):
    xls = pd.ExcelFile(file)
    return xls.sheet_names

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

def _latest_month_only(df_matches):
    # Keep only rows from the latest month found in the file
    if df_matches.empty:
        return df_matches, None
    df = df_matches.copy()
    df["YearMonth"] = df["Date"].dt.to_period("M")
    latest_period = df["YearMonth"].max()
    filtered = df[df["YearMonth"] == latest_period].copy()
    filtered.drop(columns=["YearMonth"], inplace=True)
    return filtered, str(latest_period)

def _week_start(d):
    # Monday as start of week
    if pd.isna(d):
        return d
    return d - timedelta(days=d.weekday())

def _human_week_label(start_date):
    end_date = start_date + timedelta(days=6)
    return f"{start_date:%b %d} – {end_date:%b %d}"

def _weekday_sort_value(date):
    # For consistent day ordering within a week (Mon..Sun)
    return date.weekday() if pd.notna(date) else 7

def render_weekly_view(df):
    # Compute week buckets
    df = df.copy()
    df["WeekStart"] = df["Date"].apply(_week_start)
    df.sort_values(["WeekStart", "Date", "Place", "Shift"], inplace=True)

    # Summary header (top badges)
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

    # Render per week
    for wk, dfw in df.groupby("WeekStart", sort=True):
        st.markdown("---")
        st.subheader(f"Week of {_human_week_label(wk)}")

        # Group per calendar day
        for day, dfd in dfw.groupby(dfw["Date"].dt.date, sort=True):
            st.markdown(f"##### {pd.to_datetime(day):%A, %b %d}")
            # One line per entry (place — shift — text)
            for _, row in dfd.sort_values(by=["Date", "Place", "Shift"]).iterrows():
                st.markdown(f"""<div style='padding:10px;border:1px solid #e6e6e6;border-radius:12px;margin-bottom:6px;'>
  <div style='font-weight:600;'>{row['Place']}</div>
  <div style='opacity:0.9'>{row['Shift']}</div>
  <div style='font-size:0.95em;color:#444;'>“{row['CellText']}”</div>
</div>
""", unsafe_allow_html=True)

if uploaded:
    try:
        sheets = list_sheets(uploaded)
        sheet = st.selectbox("Sheet to process", options=sheets, index=0)

        if st.button("Process", type="primary"):
            with st.spinner("Parsing..."):
                raw = pd.read_excel(uploaded, sheet_name=sheet, header=None)
                wide = _fix_headers(raw)
                matches = _extract_matches(wide, target_name)
                last_month, ym = _latest_month_only(matches)
                last_month = last_month.sort_values(by=["Date", "Place", "Shift"]).reset_index(drop=True)

            if last_month.empty:
                st.warning("No matches found for the selected month (or in the file). Try another sheet or name.")
            else:
                st.success(f"Found {len(last_month)} assignments for **{target_name}** in **{ym}**.")
                render_weekly_view(last_month)

                # Export filtered results (last month only)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    last_month.to_excel(writer, index=False, sheet_name="Assignments")
                st.download_button(
                    label="⬇️ Download Excel (last month only)",
                    data=buffer.getvalue(),
                    file_name=f"{target_name.lower()}_{ym}_assignments.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.exception(e)

st.markdown("""---
### Notes
- The app assumes **row 0 = places** and **row 1 = shifts**, with **column 0 = date** and **column 1 = weekday**.
- It shows only the **latest month** detected in the file and orders entries **by day**.
- Entries are grouped into **weeks**, with compact cards for each day.
""")