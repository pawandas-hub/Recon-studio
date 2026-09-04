"""Recon Studio Web — Streamlit Cloud Edition.

A shareable web version of Recon Studio that reuses all existing
reconciliation logic from `src/services/`, `src/core/`, `src/readers/`,
and `src/export/`. Designed for deployment on Streamlit Community Cloud.

Shareable link: Anyone with the URL can open in any browser, upload files,
run reconciliation, and download results — without your laptop being on.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so `src.*` imports resolve
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.services.recon_engine import process_file_list
from src.export.excel_exporter import ExcelReportExporter

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Recon Studio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — Clean modern styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #4f46e5;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #64748b;
        margin-bottom: 1.5rem;
    }
    .kpi-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .kpi-value {
        font-size: 2rem;
        font-weight: 800;
        margin: 0.3rem 0;
    }
    .kpi-label {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748b;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _fmt_inr(n) -> str:
    """Format number in Indian style with commas."""
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


def _save_uploaded_to_temp(uploaded_files) -> List[str]:
    """Save Streamlit UploadedFile objects to temp directory and return paths."""
    temp_dir = tempfile.mkdtemp(prefix="recon_studio_")
    paths = []
    for uf in uploaded_files:
        file_path = os.path.join(temp_dir, uf.name)
        with open(file_path, "wb") as f:
            f.write(uf.getbuffer())
        paths.append(file_path)
    return paths


def _generate_excel_download(results_df: pd.DataFrame) -> bytes:
    """Generate styled Excel report in memory and return bytes."""
    exporter = ExcelReportExporter()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        exporter.export(tmp_path, results_df)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Sidebar — Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<p class="main-header">📊 Recon Studio</p>'
        '<p class="sub-header">Sales & Collection Reconciliation</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("### 📁 Upload Files")
    st.caption("Upload SAP ledgers, sales/DB exports, bank statements, or customer mapping files.")

    uploaded_files = st.file_uploader(
        "Drop files here",
        type=["xlsx", "xls", "csv", "tsv", "zip"],
        accept_multiple_files=True,
        key="file_uploader",
        label_visibility="collapsed",
    )

    st.divider()

    st.markdown("### ⚙️ Settings")
    recon_model = st.selectbox(
        "Recon Model",
        options=["Auto", "Sales Reconciliation", "Collection Reconciliation", "Both (Combined)"],
        index=0,
        help="Auto-detect or manually select the reconciliation type.",
    )

    format_mode = st.selectbox(
        "Format Mode",
        options=["Auto", "Format 1 (Ref.1 / Standard)", "Format 2 (Ref.2 / Retailer FnV)"],
        index=0,
        help="Auto-detect or manually select the SAP ledger format.",
    )

    st.divider()

    run_clicked = st.button(
        "🚀 Run Reconciliation",
        use_container_width=True,
        type="primary",
        disabled=not uploaded_files,
    )

    if uploaded_files:
        st.caption(f"📎 {len(uploaded_files)} file(s) selected:")
        for uf in uploaded_files:
            size_kb = len(uf.getvalue()) / 1024
            st.caption(f"  • {uf.name} ({size_kb:.0f} KB)")


# ---------------------------------------------------------------------------
# Main Page Header
# ---------------------------------------------------------------------------

st.markdown(
    '<p class="main-header">📊 Recon Studio</p>'
    '<p class="sub-header">Sales & Collection Reconciliation — Cloud Edition</p>',
    unsafe_allow_html=True,
)

# Session state initialization
if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "run_elapsed" not in st.session_state:
    st.session_state.run_elapsed = 0.0


# ---------------------------------------------------------------------------
# Run Processing
# ---------------------------------------------------------------------------

if run_clicked and uploaded_files:
    with st.spinner("🔄 Running reconciliation... Please wait."):
        start_time = time.monotonic()
        file_paths = _save_uploaded_to_temp(uploaded_files)
        progress_bar = st.progress(0, text="Preparing files...")

        def _progress_cb(stage: str, cur: int, tot: int):
            if tot > 0:
                pct = min(100, int(cur / tot * 100))
                try:
                    progress_bar.progress(pct / 100, text=stage)
                except Exception:
                    pass

        try:
            results = process_file_list(
                file_paths,
                mode=format_mode if format_mode != "Auto" else "Auto",
                recon_model=recon_model,
                progress_callback=_progress_cb,
            )
            elapsed = time.monotonic() - start_time
            st.session_state.results_df = results
            st.session_state.run_elapsed = elapsed
            progress_bar.progress(1.0, text="✅ Complete!")
            time.sleep(0.5)
            progress_bar.empty()
        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ Reconciliation failed: {str(e)}")
            st.session_state.results_df = None

        for fp in file_paths:
            try:
                os.unlink(fp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Results Display
# ---------------------------------------------------------------------------

results_df = st.session_state.results_df

if results_df is not None and not results_df.empty:
    total = len(results_df)
    matched = int((results_df["Overall_Status"] == "Matched").sum())
    review = int(results_df["Overall_Status"].str.contains("review", case=False, na=False).sum())
    exceptions = total - matched
    mismatch = exceptions - review
    rate_str = f"{matched / total * 100:.1f}%" if total else "0%"
    elapsed = st.session_state.run_elapsed

    st.success(f"✅ Reconciliation complete — **{total:,}** records processed in **{elapsed:.1f}s**")

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Total Records</div><div class="kpi-value" style="color:#4f46e5;">{total:,}</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Matched</div><div class="kpi-value" style="color:#10b981;">{matched:,}</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Exceptions</div><div class="kpi-value" style="color:#ef4444;">{exceptions:,}</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Match Rate</div><div class="kpi-value" style="color:#f59e0b;">{rate_str}</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # Chart & Export Section
    chart_col, export_col = st.columns([2, 1])

    with chart_col:
        st.markdown("### 📊 Match Breakdown")
        try:
            import plotly.graph_objects as go
            labels = ["Matched", "Needs Review", "Mismatched / Missing"]
            values = [matched, review, max(0, mismatch)]
            colors = ["#10b981", "#f59e0b", "#ef4444"]
            filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
            if filtered:
                f_l, f_v, f_c = zip(*filtered)
                fig = go.Figure(data=[go.Pie(labels=list(f_l), values=list(f_v), hole=0.55, marker=dict(colors=list(f_c)), textinfo="label+percent")])
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No chart data available.")
        except Exception:
            st.bar_chart({"Count": [matched, review, max(0, mismatch)]})

    with export_col:
        st.markdown("### 📥 Export Report")
        try:
            excel_bytes = _generate_excel_download(results_df)
            st.download_button(
                label="📥 Download Styled Excel",
                data=excel_bytes,
                file_name="Reconciliation_Summary_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.error(f"Excel error: {e}")

        csv_bytes = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📄 Download CSV",
            data=csv_bytes,
            file_name="Reconciliation_Results.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Detailed Table
    st.markdown("### 📋 Detailed Records")
    tabs = ["All"]
    if "Recon_Type" in results_df.columns:
        tabs.extend(results_df["Recon_Type"].dropna().unique().tolist())

    sel_tab = st.radio("Filter type:", tabs, horizontal=True, label_visibility="collapsed")
    df_show = results_df.copy()
    if sel_tab != "All" and "Recon_Type" in df_show.columns:
        df_show = df_show[df_show["Recon_Type"] == sel_tab]

    search_term = st.text_input("🔍 Search records...", placeholder="Search reference, customer, remarks...")
    if search_term:
        mask = df_show.apply(lambda row: search_term.lower() in " ".join(str(v) for v in row.values).lower(), axis=1)
        df_show = df_show[mask]

    st.caption(f"Showing {len(df_show):,} of {len(results_df):,} records")
    st.dataframe(df_show, use_container_width=True, height=500)

elif results_df is not None and results_df.empty:
    st.warning("⚠️ No records matched. Please verify the uploaded files.")
else:
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 📁 1. Upload Files\nDrag & drop SAP ledgers, Sales registers, or Bank statements into the sidebar.")
    with col2:
        st.markdown("### ⚙️ 2. Configure\nSelect your Recon Model or keep 'Auto' for intelligent file detection.")
    with col3:
        st.markdown("### 🚀 3. Run & Export\nClick **Run Reconciliation** to view KPIs, visualizations, and download reports.")
    st.markdown("---")
    st.info("💡 **Tip:** You can upload multiple files together. The engine auto-detects SAP, Bank, and Sales exports.")
