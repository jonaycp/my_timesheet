import io
import re
import requests
import gdown
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, date

st.set_page_config(page_title="Roster Extractor", page_icon="🗂️", layout="wide")

st.title("🗂️ Majda workdays")
st.caption("Upload the Excel **or paste a Google Drive link**, type a name (default: Magda). The app will read the **Směny** sheet automatically. Pick a month (defaults to **current month** if available), view the whole month by default, or jump to **This week** / **Next week**.")

# ----------------------------- Sidebar -----------------------------
with st.sidebar:
    st.header("⚙️ Options")
    target_name = st.text_input("Name to search", value="Magda").strip()
    st.caption("Case-insensitive, *contains* search (e.g., it matches 'Bára +Magda' or 'Magda till 15').")

uploaded = st.file_uploader("Drop or select the .xlsx file", type=["xlsx"])
drive_url = st.text_input("…or paste a Google Drive URL (optional)", placeholder="https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing")

# ----------------------------- Helpers -----------------------------
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

def _week_start(d: date):
    # Monday as start of week
    if pd.isna(d):
        return d
    return d - timedelta(days=d.weekday())

def _human_week_label(start_date: date):
    end_date = start_date + timedelta(days=6)
    return f"{start_date:%b %d} – {end_date:%b %d}"

def _filter_by_week(df, week_start: date):
    week_end = week_start + timedelta(days=6)
    m = (df["Date"].dt.date >= week_start) & (df["Date"].dt.date <= week_end)
    return df[m].copy()

# ---- Drive helpers ----
_DRIVE_ID_PATTERNS = [
    r'drive\\.google\\.com/file/d/([^/]+)/',       # /file/d/<id>/view
    r'drive\\.google\\.com/open\\?id=([^&]+)',     # open?id=<id>
    r'drive\\.google\\.com/uc\\?id=([^&]+)',       # uc?id=<id>
    r'docs\\.google\\.com/spreadsheets/d/([^/]+)/' # spreadsheets (in case someone shares one)
]

def _extract_drive_id(url: str):
    for pat in _DRIVE_ID_PATTERNS:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

def _download_from_drive(url: str) -> io.BytesIO:
    fileobj = io.BytesIO()
    file_id = _extract_drive_id(url)
    if file_id:
        # Use gdown to handle large-file confirmation tokens if needed
        direct_url = f"https://drive.google.com/uc?id={file_id}"
        out_path = gdown.download(url=direct_url, quiet=True)
        if out_path is None:
            raise RuntimeError("Failed to download from Google Drive (check permissions or link).")
        with open(out_path, "rb") as f:
            fileobj.write(f.read())
    else:
        # Fallback: plain GET (works for direct file links)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        fileobj.write(r.content)
    fileobj.seek(0)
    return fileobj

def render_weekly_view(df, focus_week: date | None = None):
    # Prepare week buckets
    df = df.copy()
    df["WeekStart"] = df["Date"].dt.date.apply(_week_start)
    # Ascending: weeks from earliest to latest; days from earliest to latest
    df.sort_values(["WeekStart", "Date", "Place", "Shift"], ascending=[True, True, True, True], inplace=True)

    # Overview
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

    # If focusing on a single week, filter here (keeps ordering)
    if focus_week is not None:
        df = _filter_by_week(df, focus_week)
        df["WeekStart"] = df["Date"].dt.date.apply(_week_start)

    # Render per week (ascending)
    for wk, dfw in df.groupby("WeekStart", sort=False):
        st.markdown("---")
        st.subheader(f"Week of {_human_week_label(wk)}")

        # Group per calendar day (ascending)
        for day, dfd in dfw.groupby(dfw["Date"].dt.date, sort=True):
            st.markdown(f"##### {pd.to_datetime(day):%A, %b %d}")
            for _, row in dfd.iterrows():
                st.markdown(f"""
<div style='padding:10px;border:1px solid #e6e6e6;border-radius:12px;margin-bottom:6px;'>
  <div style='font-weight:600;'>{row['Place']}</div>
  <div style='opacity:0.9'>{row['Shift']}</div>
  <div style='font-size:0.95em;color:#444;'>“{row['CellText']}”</div>
</div>
""", unsafe_allow_html=True)

# ----------------------------- Main Flow -----------------------------
source_buffer = None

if uploaded is not None:
    source_buffer = uploaded
elif drive_url.strip():
    try:
        with st.spinner("Downloading file from Drive..."):
            source_buffer = _download_from_drive(drive_url.strip())
    except Exception as e:
        st.error(f"Could not download from the provided URL: {e}")

if source_buffer is not None:
    try:
        # Always load the 'Směny' sheet. If it doesn't exist, fallback to the first sheet.
        xls = pd.ExcelFile(source_buffer)
        sheet_name = "Směny" if "Směny" in xls.sheet_names else xls.sheet_names[0]
        raw = pd.read_excel(source_buffer, sheet_name=sheet_name, header=None)

        wide = _fix_headers(raw)
        matches = _extract_matches(wide, target_name)

        if matches.empty:
            st.warning("No matches found in the selected file for that name.")
        else:
            # Build available months (descending) and default to CURRENT month if present
            matches["YearMonth"] = matches["Date"].dt.to_period("M").astype(str)
            months = sorted(matches["YearMonth"].dropna().unique(), reverse=True)
            current_ym = str(pd.Timestamp.today().to_period("M"))
            default_index = months.index(current_ym) if current_ym in months else 0
            chosen = st.selectbox("Month", options=months, index=default_index, help="Newest first (defaults to current month if available)")

            # Filter to chosen month and sort ASCENDING by date (day 1 → 31)
            view = matches[matches["YearMonth"] == chosen].copy()
            view.drop(columns=["YearMonth"], inplace=True)
            view.sort_values(["Date", "Place", "Shift"], ascending=[True, True, True], inplace=True)

            if view.empty:
                st.info("No entries for the selected month.")
            else:
                # Week jump controls
                st.markdown("### Quick jump")
                colA, colB, colC = st.columns(3)
                today = date.today()
                this_week_start = today - timedelta(days=today.weekday())
                next_week_start = this_week_start + timedelta(days=7)

                # Session state for focus
                if "focus_mode" not in st.session_state:
                    st.session_state["focus_mode"] = "all"  # 'all' | 'this' | 'next'

                def set_focus(mode):
                    st.session_state["focus_mode"] = mode

                with colA:
                    if st.button("📅 This week"):
                        set_focus("this")
                with colB:
                    if st.button("➡️ Next week"):
                        set_focus("next")
                with colC:
                    if st.button("📆 All month"):
                        set_focus("all")

                # Determine focus_week based on current selection
                focus_week = None
                if st.session_state["focus_mode"] == "this":
                    focus_week = this_week_start
                elif st.session_state["focus_mode"] == "next":
                    focus_week = next_week_start

                # Render
                render_weekly_view(view, focus_week=focus_week)

                # Download of this month's assignments (ascending)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    view.to_excel(writer, index=False, sheet_name="Assignments")
                st.download_button(
                    label=f"⬇️ Download Excel ({chosen})",
                    data=buffer.getvalue(),
                    file_name=f"{target_name.lower()}_{chosen}_assignments.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.exception(e)
else:
    st.info("Upload an .xlsx file or paste a Google Drive link to begin.")

st.markdown("""
---
### Notes
- You can upload a file **or** paste a **Google Drive link** (make sure the file is shared with 'Anyone with the link').
- The app automatically reads the **Směny** sheet (fallback to the first sheet if missing).
- Month list is newest → oldest and **defaults to current month** when available.
- Default view shows **all month** (ascending by day). Use **This week** or **Next week** to focus on a single week.
""")