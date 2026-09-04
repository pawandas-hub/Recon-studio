"""Recon Studio v3.0 — Web Edition (Exact Desktop UI Replica).

Recreates the exact UI, layout, components, and workflows of Recon Studio v3.0:
- Left Sidebar with Recon Studio logo, Navigation (Dashboard, Reconciliation, Data Sources, Reports), status footer
- Top Bar with breadcrumbs, theme selector, Export Excel button, Ninjacart logo
- Reconciliation Workspace:
  - Header with title, segment mode buttons (Sales / Collection / Both), Run button
  - Live IST time subtitle with tolerance and matching info
  - 4 Clickable KPI cards (Total Records, Matched, Exceptions, Match Rate) with icons
  - Row 2: Match Breakdown donut chart & Input Files drag-and-drop zone
  - Row 3: Filter tabs (All / Sales / Collection), search filter, itemized ledger table
- Dashboard view: 30-run audit history
- Data Sources view: Ingested file audit logs
- Reports view: Executive summaries and multi-sheet exports
"""
from __future__ import annotations

import base64
import datetime
import io
import json
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
# Path setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.services.recon_engine import process_file_list
from src.export.excel_exporter import ExcelReportExporter

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Recon Studio v3.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helper: Base64 Images for Logos
# ---------------------------------------------------------------------------
def _load_b64_image(rel_path: str) -> str:
    full_path = _PROJECT_ROOT / rel_path
    if full_path.exists():
        with open(full_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{data}"
    return ""

NINJACART_LOGO_B64 = _load_b64_image("assets/ninjacart_light.png")
RECON_LOGO_B64 = _load_b64_image("assets/recon_studio_cropped.png")

# ---------------------------------------------------------------------------
# Helper: IST Time String
# ---------------------------------------------------------------------------
def _get_ist_time_str() -> str:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    return ist.strftime("%A, %d %b %Y - %I:%M:%S %p (IST)")

# ---------------------------------------------------------------------------
# Number Formatting
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Custom CSS — Exact Recon Studio v3.0 Desktop Theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Global Reset & Typography */
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        background-color: #f4f6fb !important;
        color: #0f172a;
    }
    
    .stApp {
        background-color: #f4f6fb !important;
    }

    /* Top Navigation Bar */
    .topbar-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background-color: #ffffff;
        border-bottom: 1px solid #e6eaf2;
        padding: 10px 24px;
        margin: -4rem -4rem 1.5rem -4rem;
    }
    .topbar-breadcrumb {
        font-size: 0.95rem;
        font-weight: 600;
        color: #0f172a;
    }
    .topbar-breadcrumb span {
        color: #64748b;
        font-weight: 400;
    }
    .topbar-right {
        display: flex;
        align-items: center;
        gap: 14px;
    }
    .theme-seg {
        display: flex;
        background: #f1f5f9;
        border-radius: 6px;
        padding: 2px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #64748b;
    }
    .theme-seg-item {
        padding: 4px 10px;
        border-radius: 4px;
        cursor: pointer;
    }
    .theme-seg-active {
        background: #ffffff;
        color: #4f46e5;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    
    /* Header & Action Controls */
    .view-title-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }
    .view-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
    }
    .view-subtitle {
        font-size: 0.82rem;
        font-weight: 600;
        color: #64748b;
        margin-bottom: 1rem;
    }

    /* Cards */
    .rs-card {
        background: #ffffff;
        border: 1px solid #e6eaf2;
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        margin-bottom: 14px;
    }
    
    /* KPI Cards */
    .kpi-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin-bottom: 14px;
    }
    .kpi-card-inner {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .kpi-meta-title {
        font-size: 0.72rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .kpi-meta-val {
        font-size: 1.85rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.2;
        margin: 4px 0 2px 0;
    }
    .kpi-meta-sub {
        font-size: 0.72rem;
        color: #64748b;
        font-weight: 500;
    }
    .kpi-icon-box {
        width: 44px;
        height: 44px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
    }

    /* Input Files Box */
    .dropzone-box {
        border: 2px dashed #cbd5e1;
        border-radius: 8px;
        padding: 24px;
        text-align: center;
        background: #f8fafc;
        color: #64748b;
        cursor: pointer;
        transition: border 0.2s ease;
    }
    .dropzone-box:hover {
        border-color: #4f46e5;
    }

    /* Status Tags in Table */
    .tag-matched {
        color: #10b981;
        font-weight: 700;
    }
    .tag-mismatch {
        color: #ef4444;
        font-weight: 700;
    }
    .tag-review {
        color: #f59e0b;
        font-weight: 700;
    }

    /* Sidebar Clean styling */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e6eaf2 !important;
        width: 230px !important;
    }
    
    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session State Init
# ---------------------------------------------------------------------------
if "current_view" not in st.session_state:
    st.session_state.current_view = "Reconciliation"
if "recon_mode" not in st.session_state:
    st.session_state.recon_mode = "Sales"
if "active_table_tab" not in st.session_state:
    st.session_state.active_table_tab = "All"
if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "run_history" not in st.session_state:
    st.session_state.run_history = []
if "ingested_files_log" not in st.session_state:
    st.session_state.ingested_files_log = []
if "elapsed_time" not in st.session_state:
    st.session_state.elapsed_time = 0.0

# ---------------------------------------------------------------------------
# Sidebar Navigation & Branding
# ---------------------------------------------------------------------------
with st.sidebar:
    # Logo
    if RECON_LOGO_B64:
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:10px; padding: 10px 4px 18px 4px;">'
            f'<img src="{RECON_LOGO_B64}" style="height:36px;" />'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="font-size:1.25rem; font-weight:700; color:#4f46e5; padding:10px 0 16px 0;">'
            '📊 Recon Studio'
            '</div>',
            unsafe_allow_html=True,
        )

    # Navigation Menu
    nav_options = ["📊  Dashboard", "🔄  Reconciliation", "📁  Data Sources", "📈  Reports"]
    current_idx = 1
    if st.session_state.current_view == "Dashboard":
        current_idx = 0
    elif st.session_state.current_view == "Data Sources":
        current_idx = 2
    elif st.session_state.current_view == "Reports":
        current_idx = 3

    selected_nav = st.radio(
        "Navigation",
        options=nav_options,
        index=current_idx,
        label_visibility="collapsed",
    )

    clean_nav = selected_nav.split("  ")[-1].strip()
    if clean_nav != st.session_state.current_view:
        st.session_state.current_view = clean_nav
        st.rerun()

    # Footer
    st.markdown("<div style='height: 280px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.8rem; color:#64748b; padding:12px 4px; border-top:1px solid #e6eaf2;'>"
        "v3.0 · Connected to SAP ✔"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Top Bar Header (Breadcrumb, Theme, Export Excel, Ninjacart Logo)
# ---------------------------------------------------------------------------
ninja_img_html = f'<img src="{NINJACART_LOGO_B64}" style="height:26px;" />' if NINJACART_LOGO_B64 else '<span style="font-weight:800; color:#0f172a;">ninjacart</span>'

st.markdown(f"""
<div class="topbar-container">
    <div class="topbar-breadcrumb">
        Recon Studio &rsaquo; <span>{st.session_state.current_view}</span>
    </div>
    <div class="topbar-right">
        <div class="theme-seg">
            <span class="theme-seg-item theme-seg-active">💻 Auto</span>
            <span class="theme-seg-item">☀️ Light</span>
            <span class="theme-seg-item">🌙 Dark</span>
        </div>
        <div>
            {ninja_img_html}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# VIEW: RECONCILIATION
# ---------------------------------------------------------------------------
if st.session_state.current_view == "Reconciliation":

    # Header Row with Title, Segment, and Run Button
    head_col1, head_col2, head_col3 = st.columns([3, 2, 1.5])
    
    with head_col1:
        st.markdown('<h2 class="view-title">Sales & Collection Reconciliation</h2>', unsafe_allow_html=True)
        st.markdown(f'<div class="view-subtitle">{_get_ist_time_str()} · Tolerance ±₹1 · Auto-match on Ref ID / UTR</div>', unsafe_allow_html=True)
    
    with head_col2:
        seg_options = ["Sales", "Collection", "Both"]
        seg_idx = 0 if st.session_state.recon_mode == "Sales" else (1 if st.session_state.recon_mode == "Collection" else 2)
        selected_seg = st.radio(
            "Recon Segment",
            options=seg_options,
            index=seg_idx,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.recon_mode = selected_seg

    with head_col3:
        run_btn = st.button("▶  Run Reconciliation", type="primary", use_container_width=True)

    # -----------------------------------------------------------------------
    # KPI Cards (Row 1)
    # -----------------------------------------------------------------------
    results_df = st.session_state.results_df
    total_n = len(results_df) if results_df is not None and not results_df.empty else 0
    matched_n = int((results_df["Overall_Status"] == "Matched").sum()) if total_n else 0
    review_n = int(results_df["Overall_Status"].str.contains("review", case=False, na=False).sum()) if total_n else 0
    exceptions_n = total_n - matched_n if total_n else 0
    mismatch_n = max(0, exceptions_n - review_n)
    rate_str = f"{matched_n / total_n * 100:.1f}%" if total_n else "0%"

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f"""
        <div class="rs-card">
            <div class="kpi-card-inner">
                <div>
                    <div class="kpi-meta-title">TOTAL RECORDS</div>
                    <div class="kpi-meta-val">{total_n:,}</div>
                    <div class="kpi-meta-sub">▲ click to view all records</div>
                </div>
                <div class="kpi-icon-box" style="background:#eef2ff; color:#4f46e5;">📄</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with kpi2:
        st.markdown(f"""
        <div class="rs-card">
            <div class="kpi-card-inner">
                <div>
                    <div class="kpi-meta-title">MATCHED</div>
                    <div class="kpi-meta-val">{matched_n:,}</div>
                    <div class="kpi-meta-sub">▲ click to view matched</div>
                </div>
                <div class="kpi-icon-box" style="background:#ecfdf5; color:#10b981;">☑️</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with kpi3:
        st.markdown(f"""
        <div class="rs-card">
            <div class="kpi-card-inner">
                <div>
                    <div class="kpi-meta-title">EXCEPTIONS</div>
                    <div class="kpi-meta-val">{exceptions_n:,}</div>
                    <div class="kpi-meta-sub">▼ click to view exceptions</div>
                </div>
                <div class="kpi-icon-box" style="background:#fef2f2; color:#ef4444;">⚠️</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with kpi4:
        st.markdown(f"""
        <div class="rs-card">
            <div class="kpi-card-inner">
                <div>
                    <div class="kpi-meta-title">MATCH RATE</div>
                    <div class="kpi-meta-val">{rate_str}</div>
                    <div class="kpi-meta-sub">▲ vs last run</div>
                </div>
                <div class="kpi-icon-box" style="background:#fffbeb; color:#f59e0b;">🎯</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Row 2: Match Breakdown Donut & Input Files Box
    # -----------------------------------------------------------------------
    col_breakdown, col_input = st.columns([1, 2])

    with col_breakdown:
        st.markdown('<div class="rs-card" style="min-height:220px;">'
                    '<div style="font-weight:700; font-size:0.95rem; margin-bottom:8px;">Match Breakdown</div>',
                    unsafe_allow_html=True)
        
        # Donut Chart & Legend
        try:
            import plotly.graph_objects as go
            labels = ["Matched", "Needs review", "Mismatch / Missing"]
            values = [matched_n if total_n else 1, review_n if total_n else 0, mismatch_n if total_n else 0]
            colors = ["#10b981", "#f59e0b", "#ef4444"]
            
            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.7,
                marker=dict(colors=colors),
                textinfo="none",
                hoverinfo="label+value+percent" if total_n else "none",
                showlegend=False,
            )])
            fig.update_layout(
                height=120,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass

        st.markdown(f"""
        <div style="font-size:0.82rem; font-weight:600; margin-top:6px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span><span style="color:#10b981;">■</span> Matched</span>
                <span style="font-weight:700;">{matched_n}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span><span style="color:#f59e0b;">■</span> Needs review</span>
                <span style="font-weight:700;">{review_n}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span><span style="color:#ef4444;">■</span> Mismatch / Missing</span>
                <span style="font-weight:700;">{mismatch_n}</span>
            </div>
        </div>
        </div>
        """, unsafe_allow_html=True)

    with col_input:
        st.markdown('<div class="rs-card" style="min-height:220px;">'
                    '<div style="font-weight:700; font-size:0.95rem; margin-bottom:8px;">Input Files</div>',
                    unsafe_allow_html=True)
        
        uploaded_files = st.file_uploader(
            "Upload files",
            type=["xlsx", "xls", "csv", "tsv", "zip"],
            accept_multiple_files=True,
            key="recon_file_uploader",
            label_visibility="collapsed",
        )

        if uploaded_files:
            st.markdown(f"<div style='font-size:0.82rem; color:#4f46e5; font-weight:600;'>📎 {len(uploaded_files)} file(s) attached:</div>", unsafe_allow_html=True)
            chips_html = '<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:6px;">'
            for uf in uploaded_files:
                size_kb = len(uf.getvalue()) / 1024
                chips_html += f'<span style="background:#eef2ff; color:#4f46e5; padding:3px 8px; border-radius:4px; font-size:0.75rem; font-weight:600;">{uf.name} ({size_kb:.0f} KB)</span>'
                # Track in ingested log
                if not any(f["name"] == uf.name for f in st.session_state.ingested_files_log):
                    st.session_state.ingested_files_log.insert(0, {
                        "name": uf.name,
                        "size": f"{size_kb:.0f} KB",
                        "time": _get_ist_time_str(),
                    })
            chips_html += '</div>'
            st.markdown(chips_html, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="dropzone-box">
                <div style="font-size:1.2rem; margin-bottom:4px;">↑ Drag & drop Excel / CSV here — or click to browse</div>
                <div style="font-size:0.75rem; color:#94a3b8;">SAP export · Sales register · Bank statement</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Run Reconciliation Logic
    # -----------------------------------------------------------------------
    if run_btn:
        if not uploaded_files:
            st.info("ℹ️ Please add files first using the Input Files box above.")
        else:
            with st.spinner("🔄 Reconciling records..."):
                start_t = time.monotonic()
                temp_dir = tempfile.mkdtemp(prefix="recon_studio_")
                file_paths = []
                for uf in uploaded_files:
                    fp = os.path.join(temp_dir, uf.name)
                    with open(fp, "wb") as f:
                        f.write(uf.getbuffer())
                    file_paths.append(fp)

                model_mapping = {
                    "Sales": "Sales Reconciliation",
                    "Collection": "Collection Reconciliation",
                    "Both": "Both (Combined)",
                }
                recon_model_used = model_mapping.get(st.session_state.recon_mode, "Auto")

                try:
                    res = process_file_list(
                        file_paths,
                        mode="Auto",
                        recon_model=recon_model_used,
                    )
                    elapsed = time.monotonic() - start_t
                    st.session_state.results_df = res
                    st.session_state.elapsed_time = elapsed

                    # Record history
                    total_r = len(res)
                    matched_r = int((res["Overall_Status"] == "Matched").sum())
                    st.session_state.run_history.insert(0, {
                        "timestamp": _get_ist_time_str(),
                        "mode": st.session_state.recon_mode,
                        "files_count": len(uploaded_files),
                        "total": total_r,
                        "matched": matched_r,
                        "exceptions": total_r - matched_r,
                        "match_rate": f"{matched_r / total_r * 100:.1f}%" if total_r else "0%",
                        "elapsed": f"{elapsed:.1f}s",
                    })

                    st.toast(f"Reconciliation complete — {total_r:,} records in {elapsed:.1f}s ✔")
                    st.rerun()
                except Exception as err:
                    st.error(f"Error during reconciliation: {err}")
                finally:
                    for p in file_paths:
                        try:
                            os.unlink(p)
                        except OSError:
                            pass

    # -----------------------------------------------------------------------
    # Row 3: Filter Tabs & Table
    # -----------------------------------------------------------------------
    st.markdown('<div class="rs-card">', unsafe_allow_html=True)
    
    t_col1, t_col2 = st.columns([2, 1])
    with t_col1:
        tab_choice = st.radio(
            "Table Tab",
            options=["All", "Sales", "Collection"],
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.active_table_tab = tab_choice

    with t_col2:
        search_query = st.text_input("Filter:", placeholder="🔍 Filter records...", label_visibility="collapsed")

    # Render Table Data
    if results_df is not None and not results_df.empty:
        df_filtered = results_df.copy()
        
        # Filter by tab
        if tab_choice == "Sales" and "Recon_Type" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Recon_Type"] == "Sales"]
        elif tab_choice == "Collection" and "Recon_Type" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Recon_Type"] == "Collection"]

        # Filter by search query
        if search_query:
            mask = df_filtered.apply(
                lambda r: search_query.lower() in " ".join(str(v) for v in r.values).lower(),
                axis=1,
            )
            df_filtered = df_filtered[mask]

        # Format Columns to match desktop view
        table_rows = []
        for _, row in df_filtered.iterrows():
            recon_t = row.get("Recon_Type", "Sales")
            if recon_t == "Sales":
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

            table_rows.append({
                "Source": recon_t,
                "Reference": str(ref),
                "Business Unit": str(bu),
                "SAP Posting": posting,
                "SAP Amount": sap_amt,
                "Book Amount": book_amt,
                "Variance": _fmt_inr(var_val) if var_val else "—",
                "Status": status,
                "Remarks": remarks,
            })

        df_display = pd.DataFrame(table_rows)

        # Style function for Status
        def highlight_status(val):
            s = str(val).lower()
            if "matched" in s and "not" not in s and "mis" not in s:
                return "color: #10b981; font-weight: bold;"
            elif "missing" in s or "mismatch" in s:
                return "color: #ef4444; font-weight: bold;"
            elif "review" in s:
                return "color: #f59e0b; font-weight: bold;"
            return ""

        styled_df = df_display.style.map(highlight_status, subset=["Status"])
        st.dataframe(styled_df, use_container_width=True, height=450)

        # Bottom actions
        exp_c1, exp_c2, _ = st.columns([1.5, 1.5, 3])
        with exp_c1:
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
        with exp_c2:
            st.download_button(
                "📄  Export CSV",
                data=results_df.to_csv(index=False).encode("utf-8"),
                file_name="Reconciliation_Results.csv",
                mime="text/csv",
            )
    else:
        # Empty placeholder table matching desktop UI
        empty_cols = ["Source", "Reference", "Business Unit", "SAP Posting", "SAP Amount", "Book Amount", "Variance", "Status"]
        empty_df = pd.DataFrame(columns=empty_cols)
        st.dataframe(empty_df, use_container_width=True, height=300)
        st.caption("No reconciliation results yet. Upload files above and click 'Run Reconciliation'.")

    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# VIEW: DASHBOARD (Audit History)
# ---------------------------------------------------------------------------
elif st.session_state.current_view == "Dashboard":
    st.markdown('<h2 class="view-title">Dashboard & Run History</h2>', unsafe_allow_html=True)
    st.markdown('<div class="view-subtitle">Audit trail of the last 30 reconciliation runs</div>', unsafe_allow_html=True)

    history = st.session_state.run_history
    if history:
        d_col1, d_col2, d_col3, d_col4 = st.columns(4)
        with d_col1:
            st.metric("Total Runs", len(history))
        with d_col2:
            st.metric("Total Records Reconciled", sum(h["total"] for h in history))
        with d_col3:
            st.metric("Total Matched", sum(h["matched"] for h in history))
        with d_col4:
            st.metric("Total Exceptions", sum(h["exceptions"] for h in history))

        st.markdown("### 📋 Recent Runs Audit Log")
        st.dataframe(pd.DataFrame(history), use_container_width=True)
    else:
        st.info("No runs recorded in this session yet. Perform a reconciliation to see history.")


# ---------------------------------------------------------------------------
# VIEW: DATA SOURCES
# ---------------------------------------------------------------------------
elif st.session_state.current_view == "Data Sources":
    st.markdown('<h2 class="view-title">Ingested Data Sources</h2>', unsafe_allow_html=True)
    st.markdown('<div class="view-subtitle">Audit log of files uploaded in this session</div>', unsafe_allow_html=True)

    files_log = st.session_state.ingested_files_log
    if files_log:
        st.dataframe(pd.DataFrame(files_log), use_container_width=True)
    else:
        st.info("No files uploaded in this session yet.")


# ---------------------------------------------------------------------------
# VIEW: REPORTS
# ---------------------------------------------------------------------------
elif st.session_state.current_view == "Reports":
    st.markdown('<h2 class="view-title">Executive Reconciliation Reports</h2>', unsafe_allow_html=True)
    st.markdown('<div class="view-subtitle">Detailed business unit and bank breakdown summaries</div>', unsafe_allow_html=True)

    results_df = st.session_state.results_df
    if results_df is not None and not results_df.empty:
        exporter = ExcelReportExporter()
        sales_summary = exporter._build_sales_summary_table(results_df[results_df.get("Recon_Type") == "Sales"]) if "Recon_Type" in results_df.columns else pd.DataFrame()
        coll_summary = exporter._build_collection_summary_table(results_df[results_df.get("Recon_Type") == "Collection"]) if "Recon_Type" in results_df.columns else pd.DataFrame()

        if not sales_summary.empty:
            st.markdown("### 📊 Sales Reconciliation Summary by BU")
            st.dataframe(sales_summary, use_container_width=True)

        if not coll_summary.empty:
            st.markdown("### 🏦 Collection Reconciliation Summary by Bank")
            st.dataframe(coll_summary, use_container_width=True)

        # Export button
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            exporter.export(tmp.name, results_df)
            with open(tmp.name, "rb") as f:
                xl_bytes = f.read()
        st.download_button(
            "📥  Download Full Styled Executive Workbook (.xlsx)",
            data=xl_bytes,
            file_name="Executive_Reconciliation_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
    else:
        st.info("Run a reconciliation first to view and download executive reports.")
