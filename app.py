import io
import os
import re
from urllib.parse import urlparse, parse_qs
import requests
import gdown
import pandas as pd
import streamlit as st
from datetime import timedelta, date
import hashlib

st.set_page_config(page_title="Roster Extractor", page_icon="🗂️", layout="wide")

# ----------------------------- Simple password gate -----------------------------
# Password is hashed (SHA-256 of "2101") so plaintext isn't in the repo
PASSWORD_HASH = "6cf713e83ca48f8a190b07af39303ea10884872d491f8d0c2056907fc2a26bad"

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]:
        return True

    st.markdown("### 🔐 Please enter the access password")
    pwd = st.text_input("Password", type="password")
    if pwd is not None and pwd != "":
        h = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
        if h == PASSWORD_HASH:
            st.session_state["authenticated"] = True
            st.success("Access granted ✅")
            return True
        else:
            st.error("Incorrect password — try again.")
            return False
    return False

if not check_password():
    st.stop()

# ----------------------------- App UI -----------------------------
st.title("🗂️ Majda workdays")
st.caption("Upload the Excel **or paste a Google Drive/Google Sheets link**, type a name (default: Magda). The app reads the **Směny** sheet automatically. Pick a month (defaults to **current month** if available), view the whole month by default, or jump to **This week** / **Next week**.")

LAST_LINK_FILE = "last_link.txt"

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
    places = df.iloc[0].ffill(axis=0)
    shifts = df.iloc[1].ffill(axis=0)
    headers = [f"{str(p)} | {str(s)}" for p, s in zip(places, shifts)]
    out = df.copy()
    out.columns = headers
    out = out.drop([0, 1]).reset_index(drop=True)
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

def _load_last_link():
    try:
        if os.path.exists(LAST_LINK_FILE):
            with open(LAST_LINK_FILE, "r", encoding="utf-8") as f:
                url = f.read().strip()
                return url if url else None
    except Exception:
        pass
    return None

def _save_last_link(url: str):
    try:
        with open(LAST_LINK_FILE, "w", encoding="utf-8") as f:
            f.write(url.strip())
    except Exception as e:
        st.warning(f"Could not save last link: {e}")

def _clear_last_link():
    try:
        if os.path.exists(LAST_LINK_FILE):
            os.remove(LAST_LINK_FILE)
    except Exception:
        pass

from urllib.parse import urlparse, parse_qs
import re

def _parse_drive_or_sheets_id(url: str):
    try:
        u = urlparse(url)
    except Exception:
        return None, None
    host = u.netloc.lower()
    path = u.path

    if "docs.google.com" in host and "/spreadsheets/" in path:
        parts = [p for p in path.split("/") if p]
        if "spreadsheets" in parts and "d" in parts:
            try:
                idx = parts.index("d")
                fid = parts[idx+1]
                return "sheets", fid
            except Exception:
                pass
        m = re.search(r"/spreadsheets/d/([^/]+)/?", path)
        if m:
            return "sheets", m.group(1)

    if "drive.google.com" in host:
        m = re.search(r"/file/d/([^/]+)/?", path)
        if m:
            return "drive", m.group(1)
        q = parse_qs(u.query)
        if "id" in q and q["id"]:
            return "drive", q["id"][0]

    return None, None

import requests, gdown

def _download_from_link(url: str) -> io.BytesIO:
    kind, file_id = _parse_drive_or_sheets_id(url)
    buf = io.BytesIO()

    if kind == "sheets":
        export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
        r = requests.get(export_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        buf.write(r.content)
    elif kind == "drive":
        direct_url = f"https://drive.google.com/uc?id={file_id}"
        out_path = gdown.download(url=direct_url, quiet=True)
        if out_path is None:
            raise RuntimeError("Download failed. Check that the file is shared with 'Anyone with the link'.")
        with open(out_path, "rb") as f:
            buf.write(f.read())
    else:
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

# ----------------------------- Last link prompt -----------------------------
if "last_prompt_decided" not in st.session_state:
    st.session_state["last_prompt_decided"] = False
if "use_last_link" not in st.session_state:
    st.session_state["use_last_link"] = False

last_link = None
try:
    with open("last_link.txt","r",encoding="utf-8") as _f:
        last_link = _f.read().strip() or None
except Exception:
    pass

if last_link and not st.session_state["last_prompt_decided"]:
    with st.container():
        st.info("Use the last successful link?")
        st.code(last_link, language=None)
        col_ok, col_no = st.columns(2)
        if col_ok.button("✅ Yes, use it"):
            st.session_state["use_last_link"] = True
            st.session_state["last_prompt_decided"] = True
        if col_no.button("❌ No, I'll paste/upload a new one"):
            st.session_state["use_last_link"] = False
            st.session_state["last_prompt_decided"] = True

# ----------------------------- Main Flow -----------------------------
uploaded = st.file_uploader("Drop or select the .xlsx file", type=["xlsx"])
drive_url = st.text_input("…or paste a Google Drive/Sheets URL (optional)", placeholder="https://docs.google.com/spreadsheets/d/<ID>/edit or https://drive.google.com/file/d/<ID>/view")

source_buffer = None
source_used_link = None

from datetime import date, timedelta

try:
    if st.session_state["use_last_link"] and last_link:
        with st.spinner("Downloading last link..."):
            source_buffer = _download_from_link(last_link)
        source_used_link = last_link
    elif uploaded is not None:
        source_buffer = uploaded
    elif drive_url.strip():
        with st.spinner("Downloading provided link..."):
            source_buffer = _download_from_link(drive_url.strip())
        source_used_link = drive_url.strip()
except Exception as e:
    st.error(f"Could not download from the provided URL: {e}")
    if st.session_state["use_last_link"] and last_link:
        try:
            os.remove("last_link.txt")
        except Exception:
            pass
    source_buffer = None
    source_used_link = None

if source_buffer is not None:
    try:
        xls = pd.ExcelFile(source_buffer)
        sheet_name = "Směny" if "Směny" in xls.sheet_names else xls.sheet_names[0]
        raw = pd.read_excel(source_buffer, sheet_name=sheet_name, header=None)

        wide = _fix_headers(raw)
        matches = _extract_matches(wide, target_name)

        if source_used_link:
            with open("last_link.txt","w",encoding="utf-8") as _fw:
                _fw.write(source_used_link)

        if matches.empty:
            st.warning("No matches found in the selected file for that name.")
        else:
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

                if colA.button("📅 This week"):
                    st.session_state["focus_mode"] = "this"
                if colB.button("➡️ Next week"):
                    st.session_state["focus_mode"] = "next"
                if colC.button("📆 All month"):
                    st.session_state["focus_mode"] = "all"

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