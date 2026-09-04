"""Recon Studio v3.0 — High Fidelity Web Edition.

Features:
1. Working 3-Mode Theme System: Auto, Light, Dark with dynamic CSS and logo switching.
2. Top Right Corner: Ninjacart Logo (3 sizes bigger — 52px) with Theme Switcher underneath.
3. Interactive KPI Cards: Clicking Total Records, Matched, or Exceptions opens a detailed modal popup (@st.dialog) with in-modal search and export.
4. Left Sidebar: Enlarged Recon Studio logo (68px), navigation buttons (Dashboard, Reconciliation, Data Sources, Reports), status footer.
5. Reconciliation Workspace: Header with segmented controls (Sales, Collection, Both), Run button, SVG donut breakdown, input dropzone, itemized table.
"""
from __future__ import annotations

import base64
import datetime
import io
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Path Configuration
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.services.recon_engine import process_file_list
from src.export.excel_exporter import ExcelReportExporter

# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Recon Studio v3.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session State Init
# ---------------------------------------------------------------------------
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Auto"
if "active_view" not in st.session_state:
    st.session_state.active_view = "Reconciliation"
if "active_segment" not in st.session_state:
    st.session_state.active_segment = "Sales"
if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "run_history" not in st.session_state:
    st.session_state.run_history = []
if "ingested_files_log" not in st.session_state:
    st.session_state.ingested_files_log = []
if "elapsed_sec" not in st.session_state:
    st.session_state.elapsed_sec = 0.0

# ---------------------------------------------------------------------------
# Helper: Load Base64 Logos
# ---------------------------------------------------------------------------
def _load_b64_image(rel_path: str) -> str:
    full_path = _PROJECT_ROOT / rel_path
    if full_path.exists():
        with open(full_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{data}"
    return ""

# Theme-aware logo resolution
is_dark = (st.session_state.theme_mode == "Dark")

if is_dark:
    NINJACART_LOGO_B64 = _load_b64_image("assets/ninjacart_dark.png") or _load_b64_image("assets/ninjacart_light.png")
    RECON_LOGO_B64 = _load_b64_image("assets/recon_logo_dark.png") or _load_b64_image("assets/recon_studio_cropped.png")
else:
    NINJACART_LOGO_B64 = _load_b64_image("assets/ninjacart_light.png")
    RECON_LOGO_B64 = _load_b64_image("assets/recon_studio_cropped.png") or _load_b64_image("assets/recon_logo_light.png")

# ---------------------------------------------------------------------------
# Theme Color Palettes
# ---------------------------------------------------------------------------
if is_dark:
    T_BG = "#0b1220"
    T_CARD = "#111a2e"
    T_BORDER = "#1f2b45"
    T_TEXT = "#e2e8f0"
    T_MUTED = "#8fa0ba"
    T_PRIMARY = "#818cf8"
    T_PRIMARY_HOVER = "#6366f1"
    T_PRIMARY_SOFT = "#1e1b4b"
    T_GREEN = "#10b981"
    T_GREEN_SOFT = "#062a20"
    T_AMBER = "#f59e0b"
    T_AMBER_SOFT = "#2b1e05"
    T_RED = "#ef4444"
    T_RED_SOFT = "#2c0e0e"
    T_SLATE_SOFT = "#1a2438"
else:
    T_BG = "#f4f6fb"
    T_CARD = "#ffffff"
    T_BORDER = "#e2e8f0"
    T_TEXT = "#0f172a"
    T_MUTED = "#64748b"
    T_PRIMARY = "#4f46e5"
    T_PRIMARY_HOVER = "#4338ca"
    T_PRIMARY_SOFT = "#eef2ff"
    T_GREEN = "#10b981"
    T_GREEN_SOFT = "#ecfdf5"
    T_AMBER = "#f59e0b"
    T_AMBER_SOFT = "#fffbeb"
    T_RED = "#ef4444"
    T_RED_SOFT = "#fef2f2"
    T_SLATE_SOFT = "#f1f5f9"

# ---------------------------------------------------------------------------
# Dynamic CSS Injection
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"], .stApp {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: {T_BG} !important;
        color: {T_TEXT} !important;
    }}

    .block-container {{
        padding-top: 4.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 98% !important;
    }}

    /* Sidebar Clean Styling */
    section[data-testid="stSidebar"] {{
        background-color: {T_CARD} !important;
        border-right: 1px solid {T_BORDER} !important;
    }}

    /* Buttons */
    .stButton > button[kind="primary"] {{
        background-color: {T_PRIMARY} !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        padding: 0.5rem 1.2rem !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: {T_PRIMARY_HOVER} !important;
    }}
    
    .stButton > button[kind="secondary"] {{
        background-color: {T_CARD} !important;
        color: {T_TEXT} !important;
        border: 1px solid {T_BORDER} !important;
    }}

    /* Dataframe Table styling */
    .stDataFrame {{
        border: 1px solid {T_BORDER} !important;
        border-radius: 8px !important;
        background: {T_CARD} !important;
    }}

    /* Streamlit Dialog / Modal */
    div[data-testid="stDialog"] div[role="dialog"] {{
        background-color: {T_CARD} !important;
        color: {T_TEXT} !important;
        border: 1px solid {T_BORDER} !important;
        border-radius: 12px !important;
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------
def _get_ist_time_str() -> str:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    return ist.strftime("%A, %d %b %Y - %I:%M:%S %p (IST)")

def _fmt_inr(n) -> str:
    try:
        v = float(n)
        if abs(v) < 0.01:
            return "—"
        sign = "-" if v < 0 else ""
        v = abs(v)
        integer_part = int(v)
        decimal_part = f"{v - integer_part:.2f}"[1:]
        s = str(integer_part)
        if len(s) > 3:
            last3 = s[-3:]
            rest = s[:-3]
            groups = []
            while rest:
                groups.insert(0, rest[-2:])
                rest = rest[:-2]
            formatted = ",".join(groups) + "," + last3
        else:
            formatted = s
        return f"{sign}₹{formatted}{decimal_part}"
    except (TypeError, ValueError):
        return str(n)

def _generate_donut_svg(matched: int, review: int, mismatch: int) -> str:
    total = matched + review + mismatch
    bg_circle_color = T_BORDER
    if total == 0:
        return f'<svg width="110" height="110" viewBox="0 0 100 100"><circle cx="50" cy="50" r="38" fill="none" stroke="{bg_circle_color}" stroke-width="12" /></svg>'

    circ = 2 * math.pi * 38
    m_len = (matched / total) * circ
    r_len = (review / total) * circ
    mis_len = (mismatch / total) * circ
    offset2 = -m_len
    offset3 = -(m_len + r_len)

    svg = (
        f'<svg width="110" height="110" viewBox="0 0 100 100" style="transform: rotate(-90deg);">'
        f'<circle cx="50" cy="50" r="38" fill="none" stroke="{bg_circle_color}" stroke-width="12" />'
        f'<circle cx="50" cy="50" r="38" fill="none" stroke="{T_GREEN}" stroke-width="12" stroke-dasharray="{m_len:.1f} {circ:.1f}" />'
        f'<circle cx="50" cy="50" r="38" fill="none" stroke="{T_AMBER}" stroke-width="12" stroke-dasharray="{r_len:.1f} {circ:.1f}" stroke-dashoffset="{offset2:.1f}" />'
        f'<circle cx="50" cy="50" r="38" fill="none" stroke="{T_RED}" stroke-width="12" stroke-dasharray="{mis_len:.1f} {circ:.1f}" stroke-dashoffset="{offset3:.1f}" />'
        f'</svg>'
    )
    return svg

# ---------------------------------------------------------------------------
# Modal Dialog: KPI Drill-Down Popup (Matching Desktop KpiDetailsModal)
# ---------------------------------------------------------------------------
@st.dialog("📋 Reconciliation Records Viewer", width="large")
def show_kpi_modal(modal_type: str):
    results_df = st.session_state.results_df
    if results_df is None or results_df.empty:
        st.info("ℹ️ Please run a reconciliation first to view details.")
        return

    if modal_type == "Total":
        filtered_df = results_df
        title = "All Reconciliation Records"
        subtitle = "Complete dataset from the current reconciliation"
        badge_bg = T_PRIMARY
    elif modal_type == "Matched":
        filtered_df = results_df[results_df["Overall_Status"] == "Matched"]
        title = "Matched Records"
        subtitle = "Records where SAP and Book/Bank values matched within ±₹1"
        badge_bg = T_GREEN
    else:
        filtered_df = results_df[results_df["Overall_Status"] != "Matched"]
        title = "Exception & Mismatch Records"
        subtitle = "Records requiring review, missing entries, or amount variances"
        badge_bg = T_RED

    st.markdown(
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">'
        f'<div><span style="font-size:1.3rem; font-weight:800; color:{T_TEXT};">{title}</span> '
        f'<span style="background:{badge_bg}; color:#ffffff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:700;">{len(filtered_df):,} Records</span></div>'
        f'</div>'
        f'<div style="font-size:0.85rem; color:{T_MUTED}; margin-bottom:12px;">— {subtitle}</div>',
        unsafe_allow_html=True,
    )

    modal_search = st.text_input(
        "🔍 Search within template:",
        placeholder="Type reference ID, status, or any value...",
        key=f"modal_search_input_{modal_type}",
    )

    df_show = filtered_df.copy()
    if modal_search:
        mask = df_show.apply(lambda r: modal_search.lower() in " ".join(str(v) for v in r.values).lower(), axis=1)
        df_show = df_show[mask]

    st.caption(f"Showing {len(df_show):,} of {len(filtered_df):,} rows")
    st.dataframe(df_show, use_container_width=True, height=360)

    # Export Button inside modal
    csv_bytes = df_show.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇  Export Filtered View (CSV)",
        data=csv_bytes,
        file_name=f"Recon_View_{modal_type}.csv",
        mime="text/csv",
        type="primary",
    )

# ---------------------------------------------------------------------------
# Left Sidebar Navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    # Logo (68px height)
    if RECON_LOGO_B64:
        st.markdown(
            f'<div style="display:flex; align-items:center; justify-content:center; padding: 10px 0 20px 0;">'
            f'<img src="{RECON_LOGO_B64}" style="height:68px; max-width:100%; object-fit:contain;" />'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="font-size:1.6rem; font-weight:800; color:{T_PRIMARY}; padding:10px 0 20px 0; text-align:center;">'
            '📊 Recon Studio'
            '</div>',
            unsafe_allow_html=True,
        )

    # Nav buttons
    views = [
        ("Dashboard", "📊  Dashboard"),
        ("Reconciliation", "🔄  Reconciliation"),
        ("Data Sources", "📁  Data Sources"),
        ("Reports", "📈  Reports"),
    ]

    for view_key, view_label in views:
        is_active = (st.session_state.active_view == view_key)
        btn_type = "primary" if is_active else "secondary"
        if st.button(view_label, key=f"nav_{view_key}", use_container_width=True, type=btn_type):
            st.session_state.active_view = view_key
            st.rerun()

    # Footer
    st.markdown("<div style='height: 240px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.8rem; color:{T_MUTED}; padding:12px 2px; border-top:1px solid {T_BORDER}; font-weight:500;'>"
        "v3.0 · Connected to SAP ✔"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Top Bar: Breadcrumbs (Left) & Ninjacart Logo (3 sizes bigger: 52px) + Working Theme Switcher Underneath (Right)
# ---------------------------------------------------------------------------
ninja_logo_html = f'<img src="{NINJACART_LOGO_B64}" style="height:52px; max-width:100%; object-fit:contain;" />' if NINJACART_LOGO_B64 else f'<span style="font-size:1.8rem; font-weight:900; color:{T_TEXT};">ninjacart</span>'

with st.container(border=True):
    top_c1, top_c2 = st.columns([3, 1.8])
    with top_c1:
        st.markdown(
            f'<div style="font-size: 1rem; font-weight: 700; color: {T_TEXT}; padding: 14px 0 0 0;">'
            f'Recon Studio &rsaquo; <span style="color: {T_MUTED}; font-weight: 500;">{st.session_state.active_view}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with top_c2:
        # Ninjacart Logo on top (3 sizes bigger)
        st.markdown(
            f'<div style="display:flex; justify-content:flex-end; align-items:center; margin-bottom:6px;">'
            f'{ninja_logo_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Working Theme Switcher buttons underneath the logo
        theme_options = ["💻 Auto", "☀️ Light", "🌙 Dark"]
        curr_theme_idx = 0 if st.session_state.theme_mode == "Auto" else (1 if st.session_state.theme_mode == "Light" else 2)
        
        theme_sel = st.segmented_control(
            "Theme Mode",
            options=theme_options,
            default=theme_options[curr_theme_idx],
            label_visibility="collapsed",
            key="theme_mode_selector",
        )
        clean_theme = theme_sel.split(" ")[-1] if theme_sel else "Auto"
        if clean_theme != st.session_state.theme_mode:
            st.session_state.theme_mode = clean_theme
            st.rerun()

# ---------------------------------------------------------------------------
# VIEW: RECONCILIATION
# ---------------------------------------------------------------------------
if st.session_state.active_view == "Reconciliation":

    # Header Row: Title + Segment Toggle + Run Button
    h_col1, h_col2, h_col3 = st.columns([3.2, 1.8, 1.4])
    
    with h_col1:
        st.markdown(f'<h2 style="font-size:1.45rem; font-weight:800; margin:0 0 2px 0; color:{T_TEXT};">Sales & Collection Reconciliation</h2>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:0.8rem; font-weight:600; color:{T_MUTED}; margin-bottom:12px;">{_get_ist_time_str()} · Tolerance ±₹1 · Auto-match on Ref ID / UTR</div>', unsafe_allow_html=True)

    with h_col2:
        seg_options = ["Sales", "Collection", "Both"]
        curr_idx = seg_options.index(st.session_state.active_segment) if st.session_state.active_segment in seg_options else 0
        seg_val = st.segmented_control(
            "Segment",
            options=seg_options,
            default=seg_options[curr_idx],
            label_visibility="collapsed",
            key="recon_seg_control",
        )
        if seg_val:
            st.session_state.active_segment = seg_val

    with h_col3:
        run_reconcile = st.button("▶  Run Reconciliation", type="primary", use_container_width=True)

    # -----------------------------------------------------------------------
    # Row 1: 4 Interactive KPI Cards with Clickable Popup Modals
    # -----------------------------------------------------------------------
    results_df = st.session_state.results_df
    total_n = len(results_df) if results_df is not None and not results_df.empty else 0
    matched_n = int((results_df["Overall_Status"] == "Matched").sum()) if total_n else 0
    review_n = int(results_df["Overall_Status"].str.contains("review", case=False, na=False).sum()) if total_n else 0
    exceptions_n = total_n - matched_n if total_n else 0
    mismatch_n = max(0, exceptions_n - review_n)
    rate_str = f"{matched_n / total_n * 100:.1f}%" if total_n else "0%"

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div style="background:{T_CARD}; border:1px solid {T_BORDER}; border-radius:10px; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
            <div>
                <div style="font-size:0.72rem; font-weight:700; color:{T_MUTED}; letter-spacing:0.05em; text-transform:uppercase;">TOTAL RECORDS</div>
                <div style="font-size:1.75rem; font-weight:800; color:{T_TEXT}; line-height:1.2; margin:2px 0;">{total_n:,}</div>
                <div style="font-size:0.72rem; color:{T_MUTED}; font-weight:500;">▲ click below to view</div>
            </div>
            <div style="width:44px; height:44px; border-radius:8px; background:{T_PRIMARY_SOFT}; color:{T_PRIMARY}; display:flex; align-items:center; justify-content:center; font-size:1.3rem;">📄</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 View All Records", key="btn_kpi_total", use_container_width=True):
            show_kpi_modal("Total")

    with k2:
        st.markdown(f"""
        <div style="background:{T_CARD}; border:1px solid {T_BORDER}; border-radius:10px; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
            <div>
                <div style="font-size:0.72rem; font-weight:700; color:{T_MUTED}; letter-spacing:0.05em; text-transform:uppercase;">MATCHED</div>
                <div style="font-size:1.75rem; font-weight:800; color:{T_TEXT}; line-height:1.2; margin:2px 0;">{matched_n:,}</div>
                <div style="font-size:0.72rem; color:{T_MUTED}; font-weight:500;">▲ click below to view</div>
            </div>
            <div style="width:44px; height:44px; border-radius:8px; background:{T_GREEN_SOFT}; color:{T_GREEN}; display:flex; align-items:center; justify-content:center; font-size:1.3rem;">☑️</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 View Matched", key="btn_kpi_matched", use_container_width=True):
            show_kpi_modal("Matched")

    with k3:
        st.markdown(f"""
        <div style="background:{T_CARD}; border:1px solid {T_BORDER}; border-radius:10px; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
            <div>
                <div style="font-size:0.72rem; font-weight:700; color:{T_MUTED}; letter-spacing:0.05em; text-transform:uppercase;">EXCEPTIONS</div>
                <div style="font-size:1.75rem; font-weight:800; color:{T_TEXT}; line-height:1.2; margin:2px 0;">{exceptions_n:,}</div>
                <div style="font-size:0.72rem; color:{T_MUTED}; font-weight:500;">▼ click below to view</div>
            </div>
            <div style="width:44px; height:44px; border-radius:8px; background:{T_RED_SOFT}; color:{T_RED}; display:flex; align-items:center; justify-content:center; font-size:1.3rem;">⚠️</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 View Exceptions", key="btn_kpi_exceptions", use_container_width=True):
            show_kpi_modal("Exceptions")

    with k4:
        st.markdown(f"""
        <div style="background:{T_CARD}; border:1px solid {T_BORDER}; border-radius:10px; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
            <div>
                <div style="font-size:0.72rem; font-weight:700; color:{T_MUTED}; letter-spacing:0.05em; text-transform:uppercase;">MATCH RATE</div>
                <div style="font-size:1.75rem; font-weight:800; color:{T_TEXT}; line-height:1.2; margin:2px 0;">{rate_str}</div>
                <div style="font-size:0.72rem; color:{T_MUTED}; font-weight:500;">▲ vs last run</div>
            </div>
            <div style="width:44px; height:44px; border-radius:8px; background:{T_AMBER_SOFT}; color:{T_AMBER}; display:flex; align-items:center; justify-content:center; font-size:1.3rem;">🎯</div>
        </div>
        """, unsafe_allow_html=True)
        st.button("📊 Match Summary", key="btn_kpi_rate", disabled=True, use_container_width=True)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Row 2: Match Breakdown (SVG Donut) + Input Files (Dropzone)
    # -----------------------------------------------------------------------
    col_donut, col_files = st.columns([1, 2])

    with col_donut:
        with st.container(border=True):
            st.markdown(f'<div style="font-weight:700; font-size:0.95rem; color:{T_TEXT}; margin-bottom:8px;">Match Breakdown</div>', unsafe_allow_html=True)
            
            donut_svg = _generate_donut_svg(matched_n, review_n, mismatch_n)
            
            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:16px; padding: 4px 0 10px 0;">
                <div>{donut_svg}</div>
                <div style="flex:1; font-size:0.82rem; font-weight:600; color:{T_MUTED};">
                    <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                        <span><span style="color:{T_GREEN};">■</span> Matched</span>
                        <span style="font-weight:700; color:{T_TEXT};">{matched_n}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                        <span><span style="color:{T_AMBER};">■</span> Needs review</span>
                        <span style="font-weight:700; color:{T_TEXT};">{review_n}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between;">
                        <span><span style="color:{T_RED};">■</span> Mismatch / Missing</span>
                        <span style="font-weight:700; color:{T_TEXT};">{mismatch_n}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col_files:
        with st.container(border=True):
            st.markdown(f'<div style="font-weight:700; font-size:0.95rem; color:{T_TEXT}; margin-bottom:4px;">Input Files</div>', unsafe_allow_html=True)
            
            uploaded_files = st.file_uploader(
                "Drop Excel / CSV / Bank reports here",
                type=["xlsx", "xls", "csv", "tsv", "zip"],
                accept_multiple_files=True,
                key="main_uploader",
                label_visibility="collapsed",
            )

            if uploaded_files:
                st.markdown(f"<div style='font-size:0.8rem; color:{T_PRIMARY}; font-weight:700; margin-top:4px;'>📎 {len(uploaded_files)} file(s) attached:</div>", unsafe_allow_html=True)
                chips = '<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:6px;">'
                for uf in uploaded_files:
                    sz = len(uf.getvalue()) / 1024
                    chips += f'<span style="background:{T_PRIMARY_SOFT}; color:{T_PRIMARY}; border:1px solid {T_BORDER}; padding:3px 8px; border-radius:5px; font-size:0.75rem; font-weight:600;">{uf.name} ({sz:.0f} KB)</span>'
                    if not any(f["name"] == uf.name for f in st.session_state.ingested_files_log):
                        st.session_state.ingested_files_log.insert(0, {
                            "name": uf.name,
                            "size": f"{sz:.0f} KB",
                            "time": _get_ist_time_str(),
                        })
                chips += '</div>'
                st.markdown(chips, unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Execution Logic
    # -----------------------------------------------------------------------
    if run_reconcile:
        if not uploaded_files:
            st.warning("⚠️ Please drop or select files first in the Input Files box.")
        else:
            with st.spinner("🔄 Running reconciliation..."):
                t_start = time.monotonic()
                temp_dir = tempfile.mkdtemp(prefix="recon_")
                paths = []
                for uf in uploaded_files:
                    p = os.path.join(temp_dir, uf.name)
                    with open(p, "wb") as f:
                        f.write(uf.getbuffer())
                    paths.append(p)

                mapping = {
                    "Sales": "Sales Reconciliation",
                    "Collection": "Collection Reconciliation",
                    "Both": "Both (Combined)",
                }
                m_used = mapping.get(st.session_state.active_segment, "Auto")

                try:
                    res = process_file_list(
                        paths,
                        mode="Auto",
                        recon_model=m_used,
                    )
                    elapsed = time.monotonic() - t_start
                    st.session_state.results_df = res
                    st.session_state.elapsed_sec = elapsed

                    # Record run in history
                    st.session_state.run_history.insert(0, {
                        "timestamp": _get_ist_time_str(),
                        "mode": st.session_state.active_segment,
                        "files": len(uploaded_files),
                        "total": len(res),
                        "matched": int((res["Overall_Status"] == "Matched").sum()),
                        "exceptions": len(res) - int((res["Overall_Status"] == "Matched").sum()),
                        "match_rate": f"{int((res['Overall_Status'] == 'Matched').sum()) / len(res) * 100:.1f}%" if len(res) else "0%",
                        "elapsed": f"{elapsed:.1f}s",
                    })

                    st.toast(f"✅ Reconciled {len(res):,} records in {elapsed:.1f}s")
                    st.rerun()
                except Exception as err:
                    st.error(f"Processing error: {str(err)}")
                finally:
                    for p in paths:
                        try:
                            os.unlink(p)
                        except OSError:
                            pass

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Row 3: Filter Tabs + Results Table
    # -----------------------------------------------------------------------
    with st.container(border=True):
        t_c1, t_c2 = st.columns([2, 1])
        with t_c1:
            tbl_tab = st.segmented_control(
                "Filter Category",
                options=["All", "Sales", "Collection"],
                default="All",
                label_visibility="collapsed",
                key="tbl_tab_control",
            )
        with t_c2:
            search_txt = st.text_input("Filter", placeholder="🔍 Filter records...", label_visibility="collapsed", key="table_search_input")

        if results_df is not None and not results_df.empty:
            df_view = results_df.copy()

            # Tab Filter
            if tbl_tab == "Sales" and "Recon_Type" in df_view.columns:
                df_view = df_view[df_view["Recon_Type"] == "Sales"]
            elif tbl_tab == "Collection" and "Recon_Type" in df_view.columns:
                df_view = df_view[df_view["Recon_Type"] == "Collection"]

            # Search Filter
            if search_txt:
                mask = df_view.apply(lambda r: search_txt.lower() in " ".join(str(x) for x in r.values).lower(), axis=1)
                df_view = df_view[mask]

            # Table records formatting
            records = []
            for _, row in df_view.iterrows():
                rtype = row.get("Recon_Type", "Sales")
                if rtype == "Sales":
                    ref = row.get("RefId_Ref1") or row.get("Ref2_Invoice_No") or row.get("Reference") or ""
                    bu = row.get("Business_Unit", "")
                    posting = str(row.get("Posting_Date", ""))
                    sap_amt = _fmt_inr(row.get("Total_CD_LC", 0))
                    book_amt = _fmt_inr(row.get("Total_Sales_Value", 0))
                else:
                    ref = row.get("Bank_UTR", "")
                    bu = row.get("Bank_Name", "")
                    posting = str(row.get("SAP_Posting_Date", ""))
                    sap_amt = _fmt_inr(row.get("SAP_Amount", 0))
                    book_amt = _fmt_inr(row.get("Bank_Amount", 0))

                var_val = row.get("Amount_Variance", 0)
                status = str(row.get("Overall_Status", ""))
                remarks = str(row.get("Reconciliation_Remarks", ""))

                records.append({
                    "Source": rtype,
                    "Reference": str(ref),
                    "Business Unit": str(bu),
                    "SAP Posting": posting,
                    "SAP Amount": sap_amt,
                    "Book Amount": book_amt,
                    "Variance": _fmt_inr(var_val) if var_val else "—",
                    "Status": status,
                    "Remarks": remarks,
                })

            df_final = pd.DataFrame(records)

            def style_status(val):
                s = str(val).lower()
                if "matched" in s and "not" not in s and "mis" not in s:
                    return f"color: {T_GREEN}; font-weight: 700;"
                elif "missing" in s or "mismatch" in s:
                    return f"color: {T_RED}; font-weight: 700;"
                elif "review" in s:
                    return f"color: {T_AMBER}; font-weight: 700;"
                return ""

            styled_t = df_final.style.map(style_status, subset=["Status"])
            st.dataframe(styled_t, use_container_width=True, height=440)

            # Download Buttons
            d_c1, d_c2, _ = st.columns([1.5, 1.5, 3])
            with d_c1:
                exporter = ExcelReportExporter()
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    exporter.export(tmp.name, results_df)
                    with open(tmp.name, "rb") as f:
                        xl_bytes = f.read()
                st.download_button(
                    "📊  Export Excel Report",
                    data=xl_bytes,
                    file_name="Reconciliation_Summary_Report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )
            with d_c2:
                st.download_button(
                    "📄  Export CSV",
                    data=results_df.to_csv(index=False).encode("utf-8"),
                    file_name="Reconciliation_Results.csv",
                    mime="text/csv",
                )
        else:
            empty_cols = ["Source", "Reference", "Business Unit", "SAP Posting", "SAP Amount", "Book Amount", "Variance", "Status"]
            st.dataframe(pd.DataFrame(columns=empty_cols), use_container_width=True, height=280)
            st.caption("No records to display. Drop files above and click 'Run Reconciliation'.")


# ---------------------------------------------------------------------------
# VIEW: DASHBOARD
# ---------------------------------------------------------------------------
elif st.session_state.active_view == "Dashboard":
    st.markdown(f'<h2 style="font-size:1.45rem; font-weight:800; color:{T_TEXT};">Dashboard & Audit History</h2>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:0.8rem; font-weight:600; color:{T_MUTED}; margin-bottom:14px;">Audit trail of the last 30 reconciliation runs</div>', unsafe_allow_html=True)

    history = st.session_state.run_history
    if history:
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.metric("Total Runs", len(history))
        with d2:
            st.metric("Total Reconciled", sum(h["total"] for h in history))
        with d3:
            st.metric("Total Matched", sum(h["matched"] for h in history))
        with d4:
            st.metric("Total Exceptions", sum(h["exceptions"] for h in history))

        st.markdown("### 📋 Run Records Log")
        st.dataframe(pd.DataFrame(history), use_container_width=True)
    else:
        st.info("No runs recorded in this session yet. Reconcile files to view audit history.")


# ---------------------------------------------------------------------------
# VIEW: DATA SOURCES
# ---------------------------------------------------------------------------
elif st.session_state.active_view == "Data Sources":
    st.markdown(f'<h2 style="font-size:1.45rem; font-weight:800; color:{T_TEXT};">Ingested Data Sources</h2>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:0.8rem; font-weight:600; color:{T_MUTED}; margin-bottom:14px;">Audit trail of files ingested in this session</div>', unsafe_allow_html=True)

    files_log = st.session_state.ingested_files_log
    if files_log:
        st.dataframe(pd.DataFrame(files_log), use_container_width=True)
    else:
        st.info("No files uploaded in this session yet.")


# ---------------------------------------------------------------------------
# VIEW: REPORTS
# ---------------------------------------------------------------------------
elif st.session_state.active_view == "Reports":
    st.markdown(f'<h2 style="font-size:1.45rem; font-weight:800; color:{T_TEXT};">Executive Reconciliation Reports</h2>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:0.8rem; font-weight:600; color:{T_MUTED}; margin-bottom:14px;">Detailed breakdown tables and styled workbook exports</div>', unsafe_allow_html=True)

    results_df = st.session_state.results_df
    if results_df is not None and not results_df.empty:
        exporter = ExcelReportExporter()
        sales_summary = exporter._build_sales_summary_table(results_df[results_df.get("Recon_Type") == "Sales"]) if "Recon_Type" in results_df.columns else pd.DataFrame()
        coll_summary = exporter._build_collection_summary_table(results_df[results_df.get("Recon_Type") == "Collection"]) if "Recon_Type" in results_df.columns else pd.DataFrame()

        if not sales_summary.empty:
            st.markdown("### 📊 Sales Breakdown by Business Unit")
            st.dataframe(sales_summary, use_container_width=True)

        if not coll_summary.empty:
            st.markdown("### 🏦 Collection Breakdown by Bank")
            st.dataframe(coll_summary, use_container_width=True)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            exporter.export(tmp.name, results_df)
            with open(tmp.name, "rb") as f:
                xl_bytes = f.read()
        st.download_button(
            "📥  Download Executive Report Workbook (.xlsx)",
            data=xl_bytes,
            file_name="Executive_Reconciliation_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
    else:
        st.info("Perform a reconciliation to view and download executive summary reports.")
