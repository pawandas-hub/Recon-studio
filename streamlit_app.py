"""Recon Studio v3.0 — High Fidelity Web Edition.

Exact replica of Recon Studio v3.0 Desktop UI:
- Crisp Light Theme matching desktop palette (#f4f6fb background, #ffffff cards, #4f46e5 primary)
- Left Sidebar with Recon Studio branding, styled navigation buttons, and status footer
- Top Bar with breadcrumbs, theme switcher pills, Ninjacart branding
- Main Workspace:
  - Header: Title, Segmented mode selector (Sales | Collection | Both), Run Reconciliation button
  - Subtitle: Live IST timestamp, tolerance (±₹1), auto-match info
  - KPI Cards: Total Records, Matched, Exceptions, Match Rate with icons and contrast text
  - Middle Row: Match Breakdown Donut chart + Input Files upload container
  - Results Card: Tabs (All / Sales / Collection), search filter, styled records table
  - Reports / Dashboard / Data Sources views
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
# Path configuration
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.services.recon_engine import process_file_list
from src.export.excel_exporter import ExcelReportExporter

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Recon Studio v3.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helper: Load Logos
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
# Time & Formatting Helpers
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

# ---------------------------------------------------------------------------
# Global Theme CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Global Styles */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #f4f6fb !important;
        color: #0f172a !important;
    }

    /* Main Container Padding */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
        max-width: 98% !important;
    }

    /* Top Bar Header */
    .recon-topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 18px;
        margin-bottom: 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .recon-breadcrumb {
        font-size: 0.95rem;
        font-weight: 700;
        color: #0f172a;
    }
    .recon-breadcrumb span {
        color: #64748b;
        font-weight: 500;
    }
    .recon-topbar-right {
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .theme-pill {
        display: inline-flex;
        background: #f1f5f9;
        border-radius: 6px;
        padding: 3px 6px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #475569;
        gap: 8px;
    }
    .theme-pill-active {
        background: #ffffff;
        color: #4f46e5;
        padding: 2px 8px;
        border-radius: 4px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.06);
    }

    /* Cards */
    .recon-card {
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 16px 18px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
        margin-bottom: 14px !important;
    }

    /* KPI Cards */
    .kpi-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .kpi-title {
        font-size: 0.72rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-bottom: 2px;
    }
    .kpi-val {
        font-size: 1.75rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .kpi-sub {
        font-size: 0.72rem;
        color: #64748b;
        font-weight: 500;
        margin-top: 3px;
    }
    .kpi-badge {
        width: 42px;
        height: 42px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 600 !important;
        transition: all 0.15s ease !important;
    }
    
    /* Primary Action Button (Indigo) */
    .stButton > button[kind="primary"] {
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        border: none !important;
        padding: 0.5rem 1.2rem !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #4338ca !important;
    }

    /* Sidebar Navigation Item */
    .nav-btn {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 6px;
        font-size: 0.9rem;
        font-weight: 600;
        color: #475569;
        text-decoration: none;
        cursor: pointer;
        margin-bottom: 4px;
    }
    .nav-btn-active {
        background: #eef2ff !important;
        color: #4f46e5 !important;
        font-weight: 700 !important;
    }
    
    /* Clean Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
    }
    
    /* Dataframe Table styling */
    .stDataFrame {
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        background: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------
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
# Left Sidebar Navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    # Logo
    if RECON_LOGO_B64:
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:10px; padding: 6px 0 16px 0;">'
            f'<img src="{RECON_LOGO_B64}" style="height:38px;" />'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="font-size:1.3rem; font-weight:800; color:#4f46e5; padding:6px 0 16px 0;">'
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
    st.markdown("<div style='height: 280px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.8rem; color:#64748b; padding:12px 2px; border-top:1px solid #e2e8f0; font-weight:500;'>"
        "v3.0 · Connected to SAP ✔"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Top Bar
# ---------------------------------------------------------------------------
ninja_logo_html = f'<img src="{NINJACART_LOGO_B64}" style="height:24px;" />' if NINJACART_LOGO_B64 else '<span style="font-weight:800; color:#0f172a;">ninjacart</span>'

st.markdown(f"""
<div class="recon-topbar">
    <div class="recon-breadcrumb">
        Recon Studio &rsaquo; <span>{st.session_state.active_view}</span>
    </div>
    <div class="recon-topbar-right">
        <div class="theme-pill">
            <span class="theme-pill-active">💻 Auto</span>
            <span>☀️ Light</span>
            <span>🌙 Dark</span>
        </div>
        <div>
            {ninja_logo_html}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# VIEW: RECONCILIATION
# ---------------------------------------------------------------------------
if st.session_state.active_view == "Reconciliation":

    # Header Row: Title + Segment Toggle + Run Button
    h_col1, h_col2, h_col3 = st.columns([3, 2, 1.3])
    
    with h_col1:
        st.markdown('<h2 style="font-size:1.45rem; font-weight:800; margin:0 0 2px 0; color:#0f172a;">Sales & Collection Reconciliation</h2>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:0.8rem; font-weight:600; color:#64748b; margin-bottom:12px;">{_get_ist_time_str()} · Tolerance ±₹1 · Auto-match on Ref ID / UTR</div>', unsafe_allow_html=True)

    with h_col2:
        seg_options = ["Sales", "Collection", "Both"]
        curr_idx = seg_options.index(st.session_state.active_segment) if st.session_state.active_segment in seg_options else 0
        seg_val = st.segmented_control(
            "Segment",
            options=seg_options,
            default=seg_options[curr_idx],
            label_visibility="collapsed",
        )
        if seg_val:
            st.session_state.active_segment = seg_val

    with h_col3:
        run_reconcile = st.button("▶  Run Reconciliation", type="primary", use_container_width=True)

    # -----------------------------------------------------------------------
    # Row 1: KPI Cards
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
        <div class="kpi-box">
            <div>
                <div class="kpi-title">TOTAL RECORDS</div>
                <div class="kpi-val">{total_n:,}</div>
                <div class="kpi-sub">▲ click to view all records</div>
            </div>
            <div class="kpi-badge" style="background:#eef2ff; color:#4f46e5;">📄</div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        st.markdown(f"""
        <div class="kpi-box">
            <div>
                <div class="kpi-title">MATCHED</div>
                <div class="kpi-val">{matched_n:,}</div>
                <div class="kpi-sub">▲ click to view matched</div>
            </div>
            <div class="kpi-badge" style="background:#ecfdf5; color:#10b981;">☑️</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        st.markdown(f"""
        <div class="kpi-box">
            <div>
                <div class="kpi-title">EXCEPTIONS</div>
                <div class="kpi-val">{exceptions_n:,}</div>
                <div class="kpi-sub">▼ click to view exceptions</div>
            </div>
            <div class="kpi-badge" style="background:#fef2f2; color:#ef4444;">⚠️</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class="kpi-box">
            <div>
                <div class="kpi-title">MATCH RATE</div>
                <div class="kpi-val">{rate_str}</div>
                <div class="kpi-sub">▲ vs last run</div>
            </div>
            <div class="kpi-badge" style="background:#fffbeb; color:#f59e0b;">🎯</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Row 2: Match Breakdown + Input Files
    # -----------------------------------------------------------------------
    col_donut, col_files = st.columns([1, 2])

    with col_donut:
        st.markdown("""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:16px 18px; min-height:240px;">
            <div style="font-weight:700; font-size:0.95rem; color:#0f172a; margin-bottom:8px;">Match Breakdown</div>
        """, unsafe_allow_html=True)

        try:
            import plotly.graph_objects as go
            labels = ["Matched", "Needs review", "Mismatch / Missing"]
            values = [matched_n if total_n else 1, review_n if total_n else 0, mismatch_n if total_n else 0]
            colors = ["#10b981", "#f59e0b", "#ef4444"]
            
            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.68,
                marker=dict(colors=colors),
                textinfo="none",
                hoverinfo="label+value+percent" if total_n else "none",
                showlegend=False,
            )])
            fig.update_layout(
                height=110,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass

        st.markdown(f"""
            <div style="font-size:0.8rem; font-weight:600; color:#334155; margin-top:8px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span><span style="color:#10b981;">■</span> Matched</span>
                    <span style="font-weight:700; color:#0f172a;">{matched_n}</span>
                </div>
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span><span style="color:#f59e0b;">■</span> Needs review</span>
                    <span style="font-weight:700; color:#0f172a;">{review_n}</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span><span style="color:#ef4444;">■</span> Mismatch / Missing</span>
                    <span style="font-weight:700; color:#0f172a;">{mismatch_n}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_files:
        st.markdown("""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:16px 18px; min-height:240px;">
            <div style="font-weight:700; font-size:0.95rem; color:#0f172a; margin-bottom:6px;">Input Files</div>
        """, unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            "Drop Excel / CSV / Bank reports here",
            type=["xlsx", "xls", "csv", "tsv", "zip"],
            accept_multiple_files=True,
            key="main_uploader",
            label_visibility="collapsed",
        )

        if uploaded_files:
            st.markdown(f"<div style='font-size:0.8rem; color:#4f46e5; font-weight:700; margin-top:4px;'>📎 {len(uploaded_files)} file(s) attached:</div>", unsafe_allow_html=True)
            chips = '<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:6px;">'
            for uf in uploaded_files:
                sz = len(uf.getvalue()) / 1024
                chips += f'<span style="background:#eef2ff; color:#4f46e5; border:1px solid #c7d2fe; padding:3px 8px; border-radius:5px; font-size:0.75rem; font-weight:600;">{uf.name} ({sz:.0f} KB)</span>'
                if not any(f["name"] == uf.name for f in st.session_state.ingested_files_log):
                    st.session_state.ingested_files_log.insert(0, {
                        "name": uf.name,
                        "size": f"{sz:.0f} KB",
                        "time": _get_ist_time_str(),
                    })
            chips += '</div>'
            st.markdown(chips, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

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
    st.markdown("""
    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:16px 18px;">
    """, unsafe_allow_html=True)

    t_c1, t_c2 = st.columns([2, 1])
    with t_c1:
        tbl_tab = st.segmented_control(
            "Filter Category",
            options=["All", "Sales", "Collection"],
            default="All",
            label_visibility="collapsed",
        )
    with t_c2:
        search_txt = st.text_input("Filter", placeholder="🔍 Filter records...", label_visibility="collapsed")

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
                return "color: #10b981; font-weight: 700;"
            elif "missing" in s or "mismatch" in s:
                return "color: #ef4444; font-weight: 700;"
            elif "review" in s:
                return "color: #f59e0b; font-weight: 700;"
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

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# VIEW: DASHBOARD
# ---------------------------------------------------------------------------
elif st.session_state.active_view == "Dashboard":
    st.markdown('<h2 style="font-size:1.45rem; font-weight:800; color:#0f172a;">Dashboard & Audit History</h2>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.8rem; font-weight:600; color:#64748b; margin-bottom:14px;">Audit trail of the last 30 reconciliation runs</div>', unsafe_allow_html=True)

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
    st.markdown('<h2 style="font-size:1.45rem; font-weight:800; color:#0f172a;">Ingested Data Sources</h2>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.8rem; font-weight:600; color:#64748b; margin-bottom:14px;">Audit trail of files ingested in this session</div>', unsafe_allow_html=True)

    files_log = st.session_state.ingested_files_log
    if files_log:
        st.dataframe(pd.DataFrame(files_log), use_container_width=True)
    else:
        st.info("No files uploaded in this session yet.")


# ---------------------------------------------------------------------------
# VIEW: REPORTS
# ---------------------------------------------------------------------------
elif st.session_state.active_view == "Reports":
    st.markdown('<h2 style="font-size:1.45rem; font-weight:800; color:#0f172a;">Executive Reconciliation Reports</h2>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.8rem; font-weight:600; color:#64748b; margin-bottom:14px;">Detailed breakdown tables and styled workbook exports</div>', unsafe_allow_html=True)

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
