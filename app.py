import io
import re
from urllib.parse import urlparse, parse_qs
import requests
import gdown
import pandas as pd
import streamlit as st
from datetime import timedelta, date

st.set_page_config(page_title="Roster Extractor", page_icon="🗂️", layout="wide")

st.title("🗂️ Majda workdays")
st.caption("Upload the Excel **or paste a Google Drive/Google Sheets link**, type a name (default: Magda). The app will read the **Směny** sheet automatically. Pick a month (defaults to **current month** if available), view the whole month by default, or jump to **This week** / **Next week**.")

# ----------------------------- Sidebar -----------------------------
with st.sidebar:
    st.header("⚙️ Options")
    target_name = st.text_input("Name to search", value="Magda").strip()
    st.caption("Case-insensitive, *contains* search (e.g., it matches 'Bára +Magda' or 'Magda till 15').")

uploaded = st.file_uploader("Drop or select the .xlsx file", type=["xlsx"])
drive_url = st.text_input("…or paste a Google Drive/Sheets URL (optional)", placeholder="https://docs.google.com/spreadsheets/d/<ID>/edit or https://drive.google.com/file/d/<ID>/view")

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
        for i, val in enumerate(df[col]):
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

# ---- Robust Drive/Sheets ID parsing ----
def _parse_drive_or_sheets_id(url: str):
    """Return tuple(kind, file_id) where kind in {'drive','sheets'} or (None, None)."""
    try:
        u = urlparse(url)
    except Exception:
        return None, None
    host = u.netloc.lower()
    path = u.path

    # Google Sheets: docs.google.com/spreadsheets/d/<ID>/...
    if "docs.google.com" in host and "/spreadsheets/" in path:
        parts = [p for p in path.split("/") if p]
        # expect ['spreadsheets','d','<id>', ...]
        if "spreadsheets" in parts and "d" in parts:
            try:
                idx = parts.index("d")
                fid = parts[idx+1]
                return "sheets", fid
            except Exception:
                pass
        # fallback with regex
        m = re.search(r"/spreadsheets/d/([^/]+)/?", path)
        if m:
            return "sheets", m.group(1)

    # Drive file: drive.google.com/file/d/<ID>/...
    if "drive.google.com" in host:
        m = re.search(r"/file/d/([^/]+)/?", path)
        if m:
            return "drive", m.group(1)
        # open?id=<ID> or uc?id=<ID>
        q = parse_qs(u.query)
        for k in ("id",):
            if k in q and q[k]:
                return "drive", q[k][0]

    return None, None

def _download_from_link(url: str) -> io.BytesIO:
    kind, file_id = _parse_drive_or_sheets_id(url)
    buf = io.BytesIO()

    if kind == "sheets":
        # Export Google Sheets to XLSX
        export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
        r = requests.get(export_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        buf.write(r.content)
    elif kind == "drive":
        # Use gdown for Drive files (handles confirmation tokens)
        direct_url = f"https://drive.google.com/uc?id={file_id}"
        out_path = gdown.download(url=direct_url, quiet=True)
        if out_path is None:
            raise RuntimeError("Download failed. Check that the file is shared with 'Anyone with the link'.")
        with open(out_path, "rb") as f:
            buf.write(f.read())
    else:
        # As a last resort, try a direct GET
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        buf.write(r.content)

    buf.seek(0)
    return buf

def render_weekly_view(df, focus_week: date | None = None):
    df = df.copy()
    df["WeekStart"] = df["Date"].dt.date.apply(_week_start)
    df.sort_values(["WeekStart", "Date", "Place", "Shift"], ascending=[True, True, True, True], inplace=True)

    total_days = df["Date"].dt.normalize().nunique()
    total_entries = len(df)
    unique_places = df["Place"].nunique()

    st.markdown("### Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Distinct work days", int(total_days))
    c2.metric("Total assignments", int(total_entries))
    c3.metric("Places this month", int(unique_places))

    if focus_week is not None:
        df = _filter_by_week(df, focus_week)
        df["WeekStart"] = df["Date"].dt.date.apply(_week_start)

    for wk, dfw in df.groupby("WeekStart", sort=False):
        st.markdown("---")
        st.subheader(f"Week of {_human_week_label(wk)}")
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
        with st.spinner("Downloading file..."):
            source_buffer = _download_from_link(drive_url.strip())
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
            # Months descending; default current month if present
            matches["YearMonth"] = matches["Date"].dt.to_period("M").astype(str)
            months = sorted(matches["YearMonth"].dropna().unique(), reverse=True)
            current_ym = str(pd.Timestamp.today().to_period("M"))
            default_index = months.index(current_ym) if current_ym in months else 0
            chosen = st.selectbox("Month", options=months, index=default_index, help="Newest first (defaults to current month if available)")

            view = matches[matches["YearMonth"] == chosen].copy()
            view.drop(columns=["YearMonth"], inplace=True)
            view.sort_values(["Date", "Place", "Shift"], ascending=[True, True, True], inplace=True)

            if view.empty:
                st.info("No entries for the selected month.")
            else:
                st.markdown("### Quick jump")
                colA, colB, colC = st.columns(3)
                today = date.today()
                this_week_start = today - timedelta(days=today.weekday())
                next_week_start = this_week_start + timedelta(days=7)

                if "focus_mode" not in st.session_state:
                    st.session_state["focus_mode"] = "all"

                def set_focus(mode):
                    st.session_state["focus_mode"] = mode

                if colA.button("📅 This week"):
                    set_focus("this")
                if colB.button("➡️ Next week"):
                    set_focus("next")
                if colC.button("📆 All month"):
                    set_focus("all")

                focus_week = None
                if st.session_state["focus_mode"] == "this":
                    focus_week = this_week_start
                elif st.session_state["focus_mode"] == "next":
                    focus_week = next_week_start

                render_weekly_view(view, focus_week=focus_week)

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
    st.info("Upload an .xlsx file or paste a Google Drive/Sheets link to begin.")

st.markdown("""
---
### Notes
- Paste **Google Sheets** links like `https://docs.google.com/spreadsheets/d/<ID>/edit` — we will export to **XLSX** automatically.
- Paste **Google Drive** links like `https://drive.google.com/file/d/<ID>/view` — direct download is handled.
- Make sure sharing is set to **Anyone with the link**.
""")