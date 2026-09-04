"""Recon Studio v3.0 — Production Desktop Workspace for Sales & Collection Reconciliation.

Features:
- Multi-view navigation: Dashboard (Last 30 runs history), Reconciliation, Data Sources (Last 10 files), Reports.
- 3-Mode Theme System: System Default (Auto-detects Windows Dark/Light mode), Light, Dark.
- 100% Complete Dark Mode with clam engine (zero white boxes).
- Dynamic transparent Ninjacart logo (adapts to Light & Dark themes).
- Live 12-hour IST Clock (Kolkata/Mumbai/Chennai).
- Tolerance updated to ±₹1.
- Interactive KPI popup templates on Total Records, Matched, and Exceptions cards.
- Universal Copy menu (Right-click & Ctrl+C) on all tables and dialogs.
- Persistent run and data source history in recon_history.json.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import math
import os
import sys
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from ..export.excel_exporter import ExcelReportExporter
from ..services.recon_engine import process_file_list

# ─────────────────────────────────────────────────────────────────────────────
# OS Theme Detection
# ─────────────────────────────────────────────────────────────────────────────

def is_windows_dark_mode() -> bool:
    """Detects whether Windows 10/11 is currently set to Dark Mode."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return False
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Theme System
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ThemeVars:
    bg: str
    card: str
    border: str
    text: str
    muted: str
    primary: str
    primary_soft: str
    green: str
    green_soft: str
    amber: str
    amber_soft: str
    red: str
    red_soft: str
    slate_soft: str


LIGHT = ThemeVars(
    bg="#f4f6fb", card="#ffffff", border="#e6eaf2",
    text="#0f172a", muted="#64748b",
    primary="#4f46e5", primary_soft="#eef2ff",
    green="#10b981", green_soft="#ecfdf5",
    amber="#f59e0b", amber_soft="#fffbeb",
    red="#ef4444", red_soft="#fef2f2",
    slate_soft="#f1f5f9",
)

DARK = ThemeVars(
    bg="#0b1220", card="#111a2e", border="#1f2b45",
    text="#e2e8f0", muted="#8fa0ba",
    primary="#818cf8", primary_soft="#1e1b4b",
    green="#10b981", green_soft="#062a20",
    amber="#f59e0b", amber_soft="#2b1e05",
    red="#ef4444", red_soft="#2c0e0e",
    slate_soft="#1a2438",
)


# ─────────────────────────────────────────────────────────────────────────────
# Persistent History Manager
# ─────────────────────────────────────────────────────────────────────────────

HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "recon_history.json")

class ReconHistoryManager:
    """Manages persistent history for reconciliation runs and uploaded data sources."""

    def __init__(self, filepath: str = HISTORY_FILE):
        self.filepath = filepath
        self._lock = threading.Lock()
        self.data: dict = {"runs": [], "files": []}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    if not isinstance(self.data, dict):
                        self.data = {"runs": [], "files": []}
                    self.data.setdefault("runs", [])
                    self.data.setdefault("files", [])
            except Exception:
                self.data = {"runs": [], "files": []}
        else:
            self.data = {"runs": [], "files": []}

    def _save(self) -> None:
        try:
            tmp_path = self.filepath + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.filepath)
        except Exception:
            pass

    def add_run(self, run_info: dict) -> None:
        with self._lock:
            self.data["runs"].insert(0, run_info)
            self.data["runs"] = self.data["runs"][:30]
            self._save()

    def get_runs(self) -> List[dict]:
        with self._lock:
            return list(self.data.get("runs", []))

    def add_file(self, file_info: dict) -> None:
        with self._lock:
            self.data["files"].insert(0, file_info)
            self.data["files"] = self.data["files"][:10]
            self._save()

    def get_files(self) -> List[dict]:
        with self._lock:
            return list(self.data.get("files", []))

    def clear_runs(self) -> None:
        with self._lock:
            self.data["runs"] = []
            self._save()

    def clear_files(self) -> None:
        with self._lock:
            self.data["files"] = []
            self._save()


# ─────────────────────────────────────────────────────────────────────────────
# Universal Copy Context Menu & Clipboard Helpers
# ─────────────────────────────────────────────────────────────────────────────

def attach_copy_menu(tree: ttk.Treeview, root_app: tk.Tk) -> None:
    """Attach a comprehensive right-click context menu and Ctrl+C handler to any Treeview."""
    menu = tk.Menu(tree, tearoff=0, font=("Segoe UI", 9))

    def _copy_selected_cell():
        sel = tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = tree.item(item, "values")
        if vals:
            text = " | ".join(str(v) for v in vals)
            root_app.clipboard_clear()
            root_app.clipboard_append(text)

    def _copy_selected_rows():
        sel = tree.selection()
        if not sel:
            return
        lines = []
        for item in sel:
            vals = tree.item(item, "values")
            lines.append("\t".join(str(v) for v in vals))
        text = "\n".join(lines)
        root_app.clipboard_clear()
        root_app.clipboard_append(text)

    def _copy_entire_table():
        cols = [tree.heading(c)["text"] for c in tree["columns"]]
        lines = ["\t".join(cols)]
        for item in tree.get_children(""):
            vals = tree.item(item, "values")
            lines.append("\t".join(str(v) for v in vals))
        text = "\n".join(lines)
        root_app.clipboard_clear()
        root_app.clipboard_append(text)

    menu.add_command(label="📋  Copy Selected Row(s)", command=_copy_selected_rows)
    menu.add_command(label="📑  Copy Row Text", command=_copy_selected_cell)
    menu.add_separator()
    menu.add_command(label="📊  Copy Entire Table (TSV)", command=_copy_entire_table)

    def _popup(event):
        item = tree.identify_row(event.y)
        if item:
            if item not in tree.selection():
                tree.selection_set(item)
            menu.tk_popup(event.x_root, event.y_root)

    tree.bind("<Button-3>", _popup)
    tree.bind("<Button-2>", _popup)
    tree.bind("<Control-c>", lambda _e: _copy_selected_rows())
    tree.bind("<Control-C>", lambda _e: _copy_selected_rows())


# ─────────────────────────────────────────────────────────────────────────────
# Format Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sales_reference(row) -> str:
    for col in ("Ref2_Invoice_No", "RefId_Ref1", "Reference"):
        val = row.get(col, "")
        if not pd.isna(val) and str(val).strip():
            return str(val)
    return ""

def _fmt_inr(n) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    return f"₹{abs(v):,.2f}"

def _get_ist_time_str() -> str:
    now = datetime.datetime.now()
    return now.strftime("%A, %d %b %Y · %I:%M:%S %p (IST)")


# ─────────────────────────────────────────────────────────────────────────────
# Donut Chart & Progress Ring (Canvas-based)
# ─────────────────────────────────────────────────────────────────────────────

class DonutChart(tk.Canvas):
    def __init__(self, parent, size=130, **kw):
        super().__init__(parent, width=size, height=size, highlightthickness=0, **kw)
        self._size = size
        self._cx = size / 2
        self._cy = size / 2
        self._r = size * 0.415
        self._stroke_w = size * 0.108

    def update_segments(self, matched: int, review: int, mismatch: int, t: ThemeVars):
        self.delete("all")
        self._draw_arc(t.slate_soft, 0, 360, t)
        total = matched + review + mismatch
        if total == 0:
            return
        start = -90.0
        for count, color in ((matched, t.green), (review, t.amber), (mismatch, t.red)):
            if count:
                extent = count / total * 360.0
                self._draw_arc(color, start, extent, t, filled=True)
                start += extent

    def _draw_arc(self, color: str, start: float, extent: float, t: ThemeVars, filled: bool = False):
        cx, cy, r, sw = self._cx, self._cy, self._r, self._stroke_w
        x0, y0 = cx - r, cy - r
        x1, y1 = cx + r, cy + r
        if filled:
            self.create_arc(x0, y0, x1, y1, start=start, extent=extent,
                            style=tk.ARC, outline=color, width=sw)
        else:
            self.create_arc(x0, y0, x1, y1, start=0, extent=359.9,
                            style=tk.ARC, outline=color, width=sw)

    def clear(self, t: ThemeVars):
        self.delete("all")
        self._draw_arc(t.slate_soft, 0, 360, t)


class ProgressRing(tk.Canvas):
    def __init__(self, parent, size=52, **kw):
        super().__init__(parent, width=size, height=size, highlightthickness=0, **kw)
        self._size = size
        self._cx = size / 2
        self._cy = size / 2
        self._r = 18.0 * (size / 52)
        self._stroke_w = 4.5 * (size / 52)
        self._pct_text = None
        self._track_id = None
        self._fill_id = None

    def setup(self, t: ThemeVars):
        self.delete("all")
        cx, cy, r, sw = self._cx, self._cy, self._r, self._stroke_w
        self._track_id = self.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=0, extent=359.9, style=tk.ARC,
            outline=t.slate_soft, width=sw,
        )
        self._fill_id = self.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=0, style=tk.ARC,
            outline=t.primary, width=sw,
        )
        self._pct_text = self.create_text(
            cx, cy, text="0%", font=("Segoe UI", 8, "bold"), fill=t.text,
        )

    def set_pct(self, pct: float, t: ThemeVars, done=False, cancelled=False, errored=False):
        if self._fill_id is None:
            return
        extent = -pct / 100 * 359.9
        color = t.green if done else (t.amber if errored else (t.red if cancelled else t.primary))
        self.itemconfig(self._fill_id, extent=extent, outline=color)
        label = "✓" if done else ("⚠" if errored else ("✕" if cancelled else f"{int(pct)}%"))
        self.itemconfig(self._pct_text, text=label,
                        fill=color if (done or cancelled or errored) else t.text)


# ─────────────────────────────────────────────────────────────────────────────
# Scrollable Frame Helper
# ─────────────────────────────────────────────────────────────────────────────

class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._vsb = tk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self._canvas)
        self._win = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", self._bind_mouse)
        self._canvas.bind("<Leave>", self._unbind_mouse)

    def _on_inner_configure(self, _e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _bind_mouse(self, _e):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mouse(self, _e):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def set_bg(self, color: str):
        self._canvas.config(bg=color)
        self.inner.config(bg=color)
        self.config(bg=color)


# ─────────────────────────────────────────────────────────────────────────────
# KPI Popup Modal Template Window
# ─────────────────────────────────────────────────────────────────────────────

class KpiDetailsModal(tk.Toplevel):
    def __init__(self, parent: ReconApp, title: str, subtitle: str, rows_data: List[dict],
                 badge_color: str, t: ThemeVars):
        super().__init__(parent)
        self.title(title)
        self.geometry("1100x650")
        self.minsize(800, 480)
        self.configure(bg=t.bg)
        self.transient(parent)

        self._parent_app = parent
        self._all_rows = rows_data
        self._theme = t
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        head = tk.Frame(self, bg=t.card, padx=20, pady=14,
                        highlightthickness=1, highlightbackground=t.border)
        head.pack(fill=tk.X)

        title_lbl = tk.Label(head, text=title, font=("Segoe UI", 14, "bold"),
                             bg=t.card, fg=t.text)
        title_lbl.pack(side=tk.LEFT)

        count_badge = tk.Label(head, text=f"{len(rows_data):,} Records",
                               font=("Segoe UI", 9, "bold"),
                               bg=badge_color, fg="#ffffff", padx=10, pady=3)
        count_badge.pack(side=tk.LEFT, padx=(12, 0))

        sub_lbl = tk.Label(head, text=f"— {subtitle}", font=("Segoe UI", 9),
                           bg=t.card, fg=t.muted)
        sub_lbl.pack(side=tk.LEFT, padx=(8, 0))

        close_btn = tk.Label(head, text="✕ Close", font=("Segoe UI", 9, "bold"),
                             bg=t.slate_soft, fg=t.text, padx=12, pady=6, cursor="hand2")
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda _e: self.destroy())

        export_btn = tk.Label(head, text="⬇ Export View", font=("Segoe UI", 9, "bold"),
                              bg=t.primary, fg="#ffffff", padx=14, pady=6, cursor="hand2")
        export_btn.pack(side=tk.RIGHT, padx=(0, 10))
        export_btn.bind("<Button-1>", lambda _e: self._export_modal_data())

        search_f = tk.Frame(self, bg=t.card, padx=20, pady=10,
                            highlightthickness=1, highlightbackground=t.border)
        search_f.pack(fill=tk.X, pady=(1, 0))

        tk.Label(search_f, text="🔍 Search within template:", font=("Segoe UI", 9, "bold"),
                 bg=t.card, fg=t.text).pack(side=tk.LEFT, padx=(0, 8))
        search_entry = tk.Entry(search_f, textvariable=self._search_var,
                                font=("Segoe UI", 10), bg=t.bg, fg=t.text,
                                insertbackground=t.text, width=36,
                                relief="flat", highlightthickness=1, highlightbackground=t.border)
        search_entry.pack(side=tk.LEFT, ipady=4)

        self._count_lbl = tk.Label(search_f, text=f"{len(rows_data)} rows",
                                   font=("Segoe UI", 9), bg=t.card, fg=t.muted)
        self._count_lbl.pack(side=tk.RIGHT)

        table_f = tk.Frame(self, bg=t.card, padx=16, pady=12)
        table_f.pack(fill=tk.BOTH, expand=True)

        cols = ("Source", "Reference", "Business Unit", "SAP Posting",
                "SAP Amount", "Book Amount", "Variance", "Status", "Remarks")
        self._tree = ttk.Treeview(table_f, columns=cols, show="headings",
                                  selectmode="extended", style="V3.Treeview")

        widths = {
            "Source": 75, "Reference": 150, "Business Unit": 110,
            "SAP Posting": 105, "SAP Amount": 105, "Book Amount": 105,
            "Variance": 95, "Status": 100, "Remarks": 250,
        }
        for col in cols:
            anchor = "e" if col in ("SAP Amount", "Book Amount", "Variance") else "w"
            self._tree.heading(col, text=col, command=lambda c=col: self._sort_tree(c))
            self._tree.column(col, width=widths.get(col, 100), anchor=anchor, stretch=(col in ("Reference", "Remarks")))

        vsb = ttk.Scrollbar(table_f, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(table_f, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        self._tree.tag_configure("matched", foreground=t.green)
        self._tree.tag_configure("review", foreground=t.amber)
        self._tree.tag_configure("mismatch", foreground=t.red)
        self._tree.tag_configure("missing", foreground=t.muted)

        attach_copy_menu(self._tree, self)
        self._render_rows(self._all_rows)

    def _render_rows(self, rows: List[dict]):
        for item in self._tree.get_children(""):
            self._tree.delete(item)
        for r in rows:
            self._tree.insert("", tk.END,
                              values=(r.get("src", ""), r.get("ref", ""), r.get("bu", ""),
                                      r.get("posting", ""), r.get("sap_amt", ""),
                                      r.get("book_amt", ""), r.get("variance", ""),
                                      r.get("status", ""), r.get("remarks", "")),
                              tags=(r.get("tag", ""),))
        self._count_lbl.config(text=f"{len(rows):,} of {len(self._all_rows):,} rows")

    def _apply_filter(self):
        q = self._search_var.get().strip().lower()
        if not q:
            self._render_rows(self._all_rows)
            return
        filtered = [r for r in self._all_rows if q in r.get("search_str", "").lower()]
        self._render_rows(filtered)

    def _sort_tree(self, col: str):
        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        try:
            items.sort(key=lambda t: float(str(t[0]).replace("₹", "").replace(",", "").replace("—", "0") or 0))
        except ValueError:
            items.sort(key=lambda t: t[0].lower())
        if items and self._tree.set(items[0][1], col) == self._tree.set(self._tree.get_children("")[0], col):
            items.reverse()
        for idx, (_, k) in enumerate(items):
            self._tree.move(k, "", idx)

    def _export_modal_data(self):
        if not self._all_rows:
            messagebox.showinfo("No Data", "No rows to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel File", "*.xlsx"), ("CSV File", "*.csv")],
            initialfile=f"Recon_View_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        if not path:
            return
        try:
            df = pd.DataFrame(self._all_rows)
            if "search_str" in df.columns:
                df = df.drop(columns=["search_str", "tag"], errors="ignore")
            if path.endswith(".csv"):
                df.to_csv(path, index=False)
            else:
                df.to_excel(path, index=False)
            messagebox.showinfo("Export Successful", f"Saved records to:\n{path}")
        except Exception as err:
            messagebox.showerror("Export Error", str(err))


# ─────────────────────────────────────────────────────────────────────────────
# Main Application Class
# ─────────────────────────────────────────────────────────────────────────────

class ReconApp(tk.Tk):
    """Recon Studio v3.0 — Complete Desktop Application."""

    def __init__(self):
        super().__init__()
        self.title("Recon Studio v3.0")
        self.geometry("1440x900")
        self.minsize(1100, 700)

        # 3-mode theme system: "system", "light", "dark"
        self._theme_preference = "system"
        self._dark = is_windows_dark_mode()
        self._theme: ThemeVars = DARK if self._dark else LIGHT

        self.selected_files: List[str] = []
        self.results_df: Optional[pd.DataFrame] = None
        self.exporter = ExcelReportExporter()
        self.history = ReconHistoryManager()
        self._busy = False
        self._cancel_event = threading.Event()
        self._started_at: Optional[float] = None
        self._recon_model_used = "Auto"

        self._recon_mode = tk.StringVar(value="Sales")
        self._active_tab = "All"
        self._all_rows: list = []
        self._current_view_name = "Reconciliation"

        # Progress bar state
        self._prog_visible = False
        self._prog_minimized = False
        self._prog_pct = 0.0
        self._prog_phase_idx = 0
        self._prog_phases: list = []
        self._prog_paused = False
        self._prog_cancelled = False

        self._build_app()
        self._start_clock()
        self._start_system_theme_listener()

    # ─────────────────────────────────────────────────────────────────
    # Core Layout
    # ─────────────────────────────────────────────────────────────────
    def _build_app(self):
        t = self._theme
        self.configure(bg=t.bg)

        # Style Treeviews with clam for 100% dark mode support
        self._apply_treeview_style()

        self._root_frame = tk.Frame(self, bg=t.bg)
        self._root_frame.pack(fill=tk.BOTH, expand=True)

        self._sidebar_frame = tk.Frame(self._root_frame, width=212, bg=t.card)
        self._sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar_frame.pack_propagate(False)

        self._main_frame = tk.Frame(self._root_frame, bg=t.bg)
        self._main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_sidebar()
        self._build_topbar()

        self._views_container = tk.Frame(self._main_frame, bg=t.bg)
        self._views_container.pack(fill=tk.BOTH, expand=True)

        self._rebuild_views()
        self._show_view("Reconciliation")

        self._build_statusbar()
        self._build_progress_overlay()

    def _apply_treeview_style(self):
        t = self._theme
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("V3.Treeview",
                        background=t.card,
                        fieldbackground=t.card,
                        foreground=t.text,
                        rowheight=28,
                        font=("Segoe UI", 9),
                        borderwidth=0)
        style.configure("V3.Treeview.Heading",
                        background=t.slate_soft,
                        foreground=t.muted,
                        font=("Segoe UI", 8, "bold"),
                        relief="flat")
        style.map("V3.Treeview",
                  background=[("selected", t.primary_soft)],
                  foreground=[("selected", t.primary)])

    def _rebuild_views(self):
        """Rebuilds all view containers cleanly to ensure 100% theme consistency."""
        t = self._theme
        for w in self._views_container.winfo_children():
            w.destroy()

        self._view_reconciliation = self._build_reconciliation_view(self._views_container)
        self._view_dashboard = self._build_dashboard_view(self._views_container)
        self._view_data_sources = self._build_data_sources_view(self._views_container)
        self._view_reports = self._build_reports_view(self._views_container)

        # Restore results if already computed
        if self.results_df is not None and not self.results_df.empty:
            self._update_kpis()
            self._build_result_rows()
            self._filter_table()

        if self.selected_files:
            self._refresh_chips()

    # ─────────────────────────────────────────────────────────────────
    # SIDEBAR
    # ─────────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        t = self._theme
        sb = self._sidebar_frame

        logo_f = tk.Frame(sb, bg=t.card, pady=6)
        logo_f.pack(fill=tk.X, padx=12, pady=(18, 14))
        self._logo_f = logo_f

        self._recon_logo_img = None
        self._recon_logo_lbl = tk.Label(logo_f, bg=t.card, cursor="hand2")
        self._recon_logo_lbl.pack(side=tk.LEFT)
        self._recon_logo_lbl.bind("<Button-1>", lambda _e: self._show_view("Reconciliation"))
        self._update_recon_studio_logo()

        nav_items = [
            ("📊", "Dashboard", "Dashboard"),
            ("🔄", "Reconciliation", "Reconciliation"),
            ("📁", "Data Sources", "Data Sources"),
            ("📈", "Reports", "Reports"),
        ]
        self._nav_widgets: dict = {}
        self._nav_frame = tk.Frame(sb, bg=t.card)
        self._nav_frame.pack(fill=tk.X, padx=8)

        for icon, label, view_key in nav_items:
            is_active = (view_key == self._current_view_name)
            f = tk.Frame(self._nav_frame, bg=t.primary_soft if is_active else t.card, cursor="hand2")
            f.pack(fill=tk.X, pady=2)

            lbl = tk.Label(f, text=f"  {icon}  {label}",
                           font=("Segoe UI", 10, "bold" if is_active else "normal"),
                           bg=t.primary_soft if is_active else t.card,
                           fg=t.primary if is_active else t.muted,
                           anchor="w", padx=4, pady=10)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            self._nav_widgets[view_key] = (f, lbl, icon, label)

            def _click(vk=view_key):
                self._show_view(vk)

            for widget in (f, lbl):
                widget.bind("<Button-1>", lambda e, fn=_click: fn())
                widget.bind("<Enter>", lambda e, f=f, lbl=lbl, vk=view_key: self._on_nav_hover(f, lbl, vk, True))
                widget.bind("<Leave>", lambda e, f=f, lbl=lbl, vk=view_key: self._on_nav_hover(f, lbl, vk, False))

        self._sidebar_footer = tk.Label(
            sb, text="v3.0 · Connected to SAP ✔",
            font=("Segoe UI", 9), bg=t.card, fg=t.muted,
            anchor="w", padx=12, pady=10,
        )
        self._sidebar_footer.pack(side=tk.BOTTOM, fill=tk.X)

    def _on_nav_hover(self, f, lbl, view_key: str, enter: bool):
        if view_key == self._current_view_name:
            return
        t = self._theme
        bg_col = t.slate_soft if enter else t.card
        f.config(bg=bg_col)
        lbl.config(bg=bg_col)

    def _show_view(self, view_name: str):
        self._current_view_name = view_name
        t = self._theme

        for vk, (f, lbl, icon, label) in self._nav_widgets.items():
            if vk == view_name:
                f.config(bg=t.primary_soft)
                lbl.config(bg=t.primary_soft, fg=t.primary, font=("Segoe UI", 10, "bold"))
            else:
                f.config(bg=t.card)
                lbl.config(bg=t.card, fg=t.muted, font=("Segoe UI", 10, "normal"))

        self._view_reconciliation.pack_forget()
        self._view_dashboard.pack_forget()
        self._view_data_sources.pack_forget()
        self._view_reports.pack_forget()

        if view_name == "Reconciliation":
            self._view_reconciliation.pack(fill=tk.BOTH, expand=True)
        elif view_name == "Dashboard":
            self._refresh_dashboard_data()
            self._view_dashboard.pack(fill=tk.BOTH, expand=True)
        elif view_name == "Data Sources":
            self._refresh_data_sources_data()
            self._view_data_sources.pack(fill=tk.BOTH, expand=True)
        elif view_name == "Reports":
            self._refresh_reports_data()
            self._view_reports.pack(fill=tk.BOTH, expand=True)

        self._topbar_title.config(text=f"Recon Studio  ›  {view_name}")

    # ─────────────────────────────────────────────────────────────────
    # TOPBAR (With 3-Way Theme Segment + Ninjacart Logo)
    # ─────────────────────────────────────────────────────────────────
    def _build_topbar(self):
        t = self._theme
        bar = tk.Frame(self._main_frame, bg=t.card, height=56)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        self._topbar = bar

        sep = tk.Frame(self._main_frame, bg=t.border, height=1)
        sep.pack(fill=tk.X)
        self._topbar_sep = sep

        self._topbar_title = tk.Label(
            bar, text="Recon Studio  ›  Reconciliation",
            font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text, padx=20
        )
        self._topbar_title.pack(side=tk.LEFT)

        right = tk.Frame(bar, bg=t.card)
        right.pack(side=tk.RIGHT, padx=20)
        self._topbar_right = right

        # Ninjacart Logo in right-side upper corner (Dynamic Light/Dark)
        self._logo_img = None
        self._avatar = tk.Label(right, bg=t.card, padx=4, pady=2)
        self._avatar.pack(side=tk.RIGHT, padx=(12, 0))
        self._update_ninjacart_logo()

        # Quick Export button
        self._btn_export = self._ghost_button(right, "⬇  Export Excel", command=self._do_export)
        self._btn_export.pack(side=tk.RIGHT, padx=(0, 12))

        # 3-Mode Theme Selector Segment: 💻 System / ☀️ Light / 🌙 Dark
        theme_f = tk.Frame(right, bg=t.slate_soft, padx=2, pady=2)
        theme_f.pack(side=tk.RIGHT, padx=(0, 6))
        self._theme_seg_frame = theme_f
        self._theme_mode_btns: dict = {}

        for mode_key, mode_label in (("system", "💻 Auto"), ("light", "☀️ Light"), ("dark", "🌙 Dark")):
            b = tk.Label(theme_f, text=mode_label, font=("Segoe UI", 8, "bold"),
                         padx=8, pady=4, cursor="hand2")
            b.pack(side=tk.LEFT)
            b.bind("<Button-1>", lambda e, m=mode_key: self._set_theme_preference(m))
            self._theme_mode_btns[mode_key] = b

        self._refresh_theme_seg_ui()

    def _update_ninjacart_logo(self):
        """Loads transparent Ninjacart logo tailored for current Light or Dark theme."""
        t = self._theme
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        logo_filename = "ninjacart_dark.png" if self._dark else "ninjacart_light.png"
        logo_path = os.path.join(base_dir, "assets", logo_filename)

        if not os.path.exists(logo_path):
            logo_path = os.path.join(base_dir, "assets", "ninjacart_logo_32.png")

        if os.path.exists(logo_path):
            try:
                self._logo_img = tk.PhotoImage(file=logo_path)
                self._avatar.config(image=self._logo_img, text="", bg=t.card)
            except Exception:
                self._avatar.config(image="", text="ninjacart", font=("Segoe UI", 10, "bold"),
                                    bg=t.card, fg=t.text)
        else:
            self._avatar.config(image="", text="ninjacart", font=("Segoe UI", 10, "bold"),
                                bg=t.card, fg=t.text)

    def _update_recon_studio_logo(self):
        """Loads transparent Recon Studio logo tailored for current Light or Dark theme."""
        t = self._theme
        if not hasattr(self, "_recon_logo_lbl") or not self._recon_logo_lbl.winfo_exists():
            return
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        logo_filename = "recon_logo_dark.png" if self._dark else "recon_logo_light.png"
        logo_path = os.path.join(base_dir, "assets", logo_filename)

        if os.path.exists(logo_path):
            try:
                self._recon_logo_img = tk.PhotoImage(file=logo_path)
                self._recon_logo_lbl.config(image=self._recon_logo_img, text="", bg=t.card)
            except Exception:
                self._recon_logo_lbl.config(image="", text="Recon Studio", font=("Segoe UI", 12, "bold"),
                                            bg=t.card, fg=t.text)
        else:
            self._recon_logo_lbl.config(image="", text="Recon Studio", font=("Segoe UI", 12, "bold"),
                                        bg=t.card, fg=t.text)

    def _refresh_theme_seg_ui(self):
        t = self._theme
        if not hasattr(self, "_theme_seg_frame") or not self._theme_seg_frame.winfo_exists():
            return
        self._theme_seg_frame.config(bg=t.slate_soft)
        for k, b in self._theme_mode_btns.items():
            if k == self._theme_preference:
                b.config(bg=t.card, fg=t.primary)
            else:
                b.config(bg=t.slate_soft, fg=t.muted)

    def _set_theme_preference(self, pref: str):
        self._theme_preference = pref
        self._resolve_and_apply_theme()

    def _resolve_and_apply_theme(self):
        if self._theme_preference == "system":
            is_dark = is_windows_dark_mode()
        elif self._theme_preference == "dark":
            is_dark = True
        else:
            is_dark = False

        self._dark = is_dark
        self._theme = DARK if is_dark else LIGHT
        self._apply_full_theme()

    def _start_system_theme_listener(self):
        """Polls Windows system theme every 3 seconds if System Default is selected."""
        if self._theme_preference == "system":
            current_is_dark = is_windows_dark_mode()
            if current_is_dark != self._dark:
                self._resolve_and_apply_theme()
        self.after(3000, self._start_system_theme_listener)

    def _apply_full_theme(self):
        t = self._theme
        self.configure(bg=t.bg)
        self._root_frame.config(bg=t.bg)
        self._sidebar_frame.config(bg=t.card)
        if hasattr(self, "_logo_f") and self._logo_f.winfo_exists():
            self._logo_f.config(bg=t.card)
        self._sidebar_footer.config(bg=t.card, fg=t.muted)
        self._update_recon_studio_logo()
        self._nav_frame.config(bg=t.card)

        self._topbar.config(bg=t.card)
        self._topbar_sep.config(bg=t.border)
        self._topbar_title.config(bg=t.card, fg=t.text)
        if hasattr(self, "_topbar_right") and self._topbar_right.winfo_exists():
            self._topbar_right.config(bg=t.card)
            self._btn_export.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        self._update_ninjacart_logo()
        self._refresh_theme_seg_ui()

        self._apply_treeview_style()
        self._statusbar.config(bg=t.card)
        self._live_dot.config(bg=t.card, fg=t.green)
        self._status_lbl.config(bg=t.card, fg=t.muted)
        if hasattr(self, "_status_version_lbl") and self._status_version_lbl.winfo_exists():
            self._status_version_lbl.config(bg=t.card, fg=t.muted)

        # Rebuild view frames with new theme colors
        self._rebuild_views()
        self._show_view(self._current_view_name)

        # Update floating progress bar colors
        if hasattr(self, "_prog_bar") and self._prog_bar.winfo_exists():
            self._prog_bar.config(bg=t.card, highlightbackground=t.border)
        if hasattr(self, "_prog_inner") and self._prog_inner.winfo_exists():
            self._prog_inner.config(bg=t.card)
        if hasattr(self, "_prog_info") and self._prog_info.winfo_exists():
            self._prog_info.config(bg=t.card)
        if hasattr(self, "_prog_title_row") and self._prog_title_row.winfo_exists():
            self._prog_title_row.config(bg=t.card)
        if hasattr(self, "_phases_frame") and self._phases_frame.winfo_exists():
            self._phases_frame.config(bg=t.card)
        if hasattr(self, "_prog_actions") and self._prog_actions.winfo_exists():
            self._prog_actions.config(bg=t.card)
        if hasattr(self, "_prog_ring") and self._prog_ring.winfo_exists():
            self._prog_ring.config(bg=t.card)
            self._prog_ring.setup(t)
        if hasattr(self, "_prog_title") and self._prog_title.winfo_exists():
            self._prog_title.config(bg=t.card, fg=t.text)
        if hasattr(self, "_prog_sub") and self._prog_sub.winfo_exists():
            self._prog_sub.config(bg=t.card, fg=t.muted)
        if hasattr(self, "_prog_track_ref") and self._prog_track_ref.winfo_exists():
            self._prog_track_ref.config(bg=t.slate_soft)
        if hasattr(self, "_prog_fill") and self._prog_fill.winfo_exists():
            self._prog_fill.config(bg=t.primary)
        if hasattr(self, "_btn_pause") and self._btn_pause.winfo_exists():
            self._btn_pause.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        if hasattr(self, "_btn_prog_cancel") and self._btn_prog_cancel.winfo_exists():
            self._btn_prog_cancel.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        if hasattr(self, "_btn_minimize") and self._btn_minimize.winfo_exists():
            self._btn_minimize.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        if hasattr(self, "_btn_prog_hide") and self._btn_prog_hide.winfo_exists():
            self._btn_prog_hide.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        if hasattr(self, "_pill") and self._pill.winfo_exists():
            self._pill.config(bg=t.card, highlightbackground=t.border)
        if hasattr(self, "_pill_pct") and self._pill_pct.winfo_exists():
            self._pill_pct.config(bg=t.card, fg=t.text)
        if hasattr(self, "_toast_frame") and self._toast_frame.winfo_exists():
            self._toast_frame.config(bg=t.card)
        if hasattr(self, "_toast_lbl") and self._toast_lbl.winfo_exists():
            self._toast_lbl.config(bg=t.card, fg=t.text)

    # ─────────────────────────────────────────────────────────────────
    # VIEW 1: RECONCILIATION
    # ─────────────────────────────────────────────────────────────────
    def _build_reconciliation_view(self, parent) -> tk.Frame:
        t = self._theme
        scroll = ScrollableFrame(parent, bg=t.bg)
        c = scroll.inner
        c.config(bg=t.bg)
        self._recon_scroll = scroll

        pad_x = 24

        head = tk.Frame(c, bg=t.bg)
        head.pack(fill=tk.X, padx=pad_x, pady=(18, 0))

        top_row = tk.Frame(head, bg=t.bg)
        top_row.pack(fill=tk.X)

        self._page_title = tk.Label(top_row, text="Sales & Collection Reconciliation",
                                    font=("Segoe UI", 16, "bold"), bg=t.bg, fg=t.text)
        self._page_title.pack(side=tk.LEFT)

        seg_f = tk.Frame(top_row, bg=t.slate_soft, padx=3, pady=3)
        seg_f.pack(side=tk.LEFT, padx=14)
        self._seg_frame = seg_f
        self._seg_btns: dict = {}
        for mode_key, mode_label in (("Sales", "Sales"), ("Coll", "Collection"), ("All", "Both")):
            b = tk.Label(seg_f, text=mode_label, font=("Segoe UI", 10, "bold"),
                         padx=16, pady=6, cursor="hand2")
            b.pack(side=tk.LEFT)
            b.bind("<Button-1>", lambda e, k=mode_key: self._set_recon_mode(k))
            self._seg_btns[mode_key] = b
        self._refresh_seg()

        self._btn_run = tk.Label(top_row, text="▶  Run Reconciliation",
                                 font=("Segoe UI", 10, "bold"),
                                 bg=t.primary, fg="#ffffff",
                                 padx=18, pady=9, cursor="hand2")
        self._btn_run.pack(side=tk.RIGHT)
        self._btn_run.bind("<Button-1>", lambda e: self._run_reconciliation())

        self._live_clock_lbl = tk.Label(
            head,
            text=f"{_get_ist_time_str()}  ·  Tolerance ±₹1  ·  Auto-match on Ref ID / UTR",
            font=("Segoe UI", 9, "bold"), bg=t.bg, fg=t.muted, anchor="w"
        )
        self._live_clock_lbl.pack(fill=tk.X, pady=(6, 0))

        kpi_row = tk.Frame(c, bg=t.bg)
        kpi_row.pack(fill=tk.X, padx=pad_x, pady=(14, 0))
        self._build_clickable_kpis(kpi_row)

        row2 = tk.Frame(c, bg=t.bg)
        row2.pack(fill=tk.X, padx=pad_x, pady=(14, 0))
        self._build_row2(row2)

        results_f = tk.Frame(c, bg=t.bg)
        results_f.pack(fill=tk.BOTH, padx=pad_x, pady=(14, 40))
        self._build_results_card(results_f)

        return scroll

    def _start_clock(self):
        if hasattr(self, "_live_clock_lbl") and self._live_clock_lbl.winfo_exists():
            time_str = _get_ist_time_str()
            self._live_clock_lbl.config(
                text=f"{time_str}  ·  Tolerance ±₹1  ·  Auto-match on Ref ID / UTR"
            )
        self.after(1000, self._start_clock)

    def _build_clickable_kpis(self, parent):
        t = self._theme
        self._kpi_labels: dict = {}
        specs = [
            ("kTotal", "TOTAL RECORDS", "0", "▲ click to view all records", "🧾", t.primary_soft, lambda: self._open_kpi_modal("Total")),
            ("kMatched", "MATCHED", "0", "▲ click to view matched", "✅", t.green_soft, lambda: self._open_kpi_modal("Matched")),
            ("kEx", "EXCEPTIONS", "0", "▼ click to view exceptions", "⚠️", t.red_soft, lambda: self._open_kpi_modal("Exceptions")),
            ("kRate", "MATCH RATE", "0%", "▲ vs last run", "🎯", t.amber_soft, None),
        ]
        for i, (key, lbl, val, delta, icon, icon_bg, click_fn) in enumerate(specs):
            card = self._card(parent)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14 if i < 3 else 0))

            inner = tk.Frame(card, bg=t.card, cursor="hand2" if click_fn else "arrow")
            inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

            left = tk.Frame(inner, bg=t.card)
            left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            tk.Label(left, text=lbl, font=("Segoe UI", 8, "bold"), bg=t.card, fg=t.muted).pack(anchor="w")
            v_lbl = tk.Label(left, text=val, font=("Segoe UI", 22, "bold"), bg=t.card, fg=t.text)
            v_lbl.pack(anchor="w", pady=(3, 0))
            tk.Label(left, text=delta, font=("Segoe UI", 8), bg=t.card, fg=t.muted).pack(anchor="w", pady=(2, 0))
            self._kpi_labels[key] = v_lbl

            ico_f = tk.Frame(inner, bg=icon_bg, width=44, height=44)
            ico_f.pack(side=tk.RIGHT, anchor="center")
            ico_f.pack_propagate(False)
            ico_lbl = tk.Label(ico_f, text=icon, font=("Segoe UI", 18), bg=icon_bg)
            ico_lbl.place(relx=0.5, rely=0.5, anchor="center")

            if click_fn:
                for w in (card, inner, left, v_lbl, ico_f, ico_lbl):
                    w.bind("<Button-1>", lambda e, fn=click_fn: fn())

    def _open_kpi_modal(self, modal_type: str):
        t = self._theme
        if not self._all_rows:
            messagebox.showinfo("No Reconciliation Results", "Please run a reconciliation first to view details.")
            return

        if modal_type == "Total":
            filtered = list(self._all_rows)
            title = "All Reconciliation Records"
            subtitle = "Complete dataset from the current reconciliation"
            color = t.primary
        elif modal_type == "Matched":
            filtered = [r for r in self._all_rows if r.get("tag") == "matched"]
            title = "Matched Records"
            subtitle = "Records where SAP and Book/Bank values matched within ±₹1"
            color = t.green
        else:
            filtered = [r for r in self._all_rows if r.get("tag") != "matched"]
            title = "Exception & Mismatch Records"
            subtitle = "Records requiring review, missing entries, or amount variances"
            color = t.red

        KpiDetailsModal(self, title, subtitle, filtered, color, t)

    def _build_row2(self, parent):
        t = self._theme

        donut_card = self._card(parent)
        donut_card.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 14))

        tk.Label(donut_card, text="Match Breakdown",
                 font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text,
                 anchor="w").pack(fill=tk.X, padx=16, pady=(14, 8))

        donut_inner = tk.Frame(donut_card, bg=t.card)
        donut_inner.pack(fill=tk.BOTH, padx=16, pady=(0, 14))

        self._donut = DonutChart(donut_inner, size=130, bg=t.card)
        self._donut.pack(side=tk.LEFT)
        self._donut.clear(t)

        legend_f = tk.Frame(donut_inner, bg=t.card)
        legend_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        self._legend_labels: dict = {}
        for key, color, label in (
            ("matched", t.green, "Matched"),
            ("review", t.amber, "Needs review"),
            ("mismatch", t.red, "Mismatch / Missing"),
        ):
            row = tk.Frame(legend_f, bg=t.card)
            row.pack(fill=tk.X, pady=5)
            dot = tk.Label(row, bg=color, width=2, relief="flat")
            dot.pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(row, text=label, font=("Segoe UI", 9), bg=t.card, fg=t.muted).pack(side=tk.LEFT)
            count_lbl = tk.Label(row, text="0", font=("Segoe UI", 9, "bold"), bg=t.card, fg=t.text)
            count_lbl.pack(side=tk.RIGHT)
            self._legend_labels[key] = count_lbl

        files_card = self._card(parent)
        files_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(files_card, text="Input Files",
                 font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text,
                 anchor="w").pack(fill=tk.X, padx=16, pady=(14, 8))

        drop_f = tk.Frame(files_card, bg=t.card, padx=16, pady=4)
        drop_f.pack(fill=tk.X)

        self._drop_zone = tk.Label(
            drop_f,
            text="⬆  Drag & drop Excel / CSV here — or click to browse\n"
                 "SAP export · Sales register · Bank statement",
            font=("Segoe UI", 10), bg=t.card, fg=t.muted,
            relief="flat", cursor="hand2", padx=20, pady=14, justify="center",
            highlightthickness=2, highlightbackground=t.border
        )
        self._drop_zone.pack(fill=tk.X)
        self._drop_zone.bind("<Button-1>", lambda _e: self._browse_files())

        self._chips_frame = tk.Frame(files_card, bg=t.card)
        self._chips_frame.pack(fill=tk.X, padx=16, pady=(6, 8))

        btn_row = tk.Frame(files_card, bg=t.card)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._ghost_button(btn_row, "Remove", command=self._remove_file).pack(side=tk.LEFT, padx=(0, 8))
        self._ghost_button(btn_row, "Clear all", command=self._clear_files).pack(side=tk.LEFT)

    def _build_results_card(self, parent):
        t = self._theme
        card = self._card(parent)
        card.pack(fill=tk.BOTH, expand=True)

        top_row = tk.Frame(card, bg=t.card, padx=6, pady=4)
        top_row.pack(fill=tk.X)

        tabs_f = tk.Frame(top_row, bg=t.card)
        tabs_f.pack(side=tk.LEFT)
        self._tab_btns: dict = {}
        for key, label in (("All", "All"), ("Sales", "Sales"), ("Coll", "Collection")):
            b = tk.Label(tabs_f, text=label, font=("Segoe UI", 10, "bold"),
                         bg=t.card, cursor="hand2", padx=14, pady=8)
            b.pack(side=tk.LEFT)
            b.bind("<Button-1>", lambda e, k=key: self._set_active_tab(k))
            self._tab_btns[key] = b

        search_f = tk.Frame(top_row, bg=t.card)
        search_f.pack(side=tk.RIGHT, padx=10)
        tk.Label(search_f, text="🔍 Filter:", font=("Segoe UI", 9, "bold"), bg=t.card, fg=t.muted).pack(side=tk.LEFT, padx=(0, 6))
        self._table_search_var = tk.StringVar()
        self._table_search_var.trace_add("write", lambda *_: self._filter_table())
        search_entry = tk.Entry(search_f, textvariable=self._table_search_var,
                                font=("Segoe UI", 9), bg=t.bg, fg=t.text,
                                insertbackground=t.text, width=28,
                                relief="flat", highlightthickness=1, highlightbackground=t.border)
        search_entry.pack(side=tk.LEFT, ipady=3)

        sep = tk.Frame(card, bg=t.border, height=1)
        sep.pack(fill=tk.X)

        self._refresh_tab_buttons()

        tree_frame = tk.Frame(card, bg=t.card)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(4, 0))

        cols = ("Source", "Reference", "Business Unit", "SAP Posting",
                "SAP Amount", "Book Amount", "Variance", "Status")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", selectmode="extended",
                                  style="V3.Treeview")

        widths = {
            "Source": 80, "Reference": 160, "Business Unit": 110,
            "SAP Posting": 110, "SAP Amount": 110, "Book Amount": 110,
            "Variance": 95, "Status": 100,
        }
        for col in cols:
            anchor = "e" if col in ("SAP Amount", "Book Amount", "Variance") else "w"
            self._tree.heading(col, text=col, command=lambda c=col: self._sort_tree(c))
            self._tree.column(col, width=widths.get(col, 100), anchor=anchor, stretch=(col == "Reference"))

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        self._tree.tag_configure("matched", foreground=t.green)
        self._tree.tag_configure("review", foreground=t.amber)
        self._tree.tag_configure("mismatch", foreground=t.red)
        self._tree.tag_configure("missing", foreground=t.muted)

        attach_copy_menu(self._tree, self)

        foot = tk.Frame(card, bg=t.card)
        foot.pack(fill=tk.X, padx=16, pady=(8, 14))
        self._row_count_lbl = tk.Label(foot, text="0 rows", font=("Segoe UI", 9), bg=t.card, fg=t.muted)
        self._row_count_lbl.pack(side=tk.LEFT)
        tk.Label(foot, text="Auto-refresh on · Right-click row to Copy", font=("Segoe UI", 9), bg=t.card, fg=t.muted).pack(side=tk.RIGHT)

    # ─────────────────────────────────────────────────────────────────
    # VIEW 2: DASHBOARD
    # ─────────────────────────────────────────────────────────────────
    def _build_dashboard_view(self, parent) -> tk.Frame:
        t = self._theme
        scroll = ScrollableFrame(parent, bg=t.bg)
        c = scroll.inner
        c.config(bg=t.bg)
        self._dash_scroll = scroll

        pad_x = 24

        head = tk.Frame(c, bg=t.bg)
        head.pack(fill=tk.X, padx=pad_x, pady=(18, 0))

        top_row = tk.Frame(head, bg=t.bg)
        top_row.pack(fill=tk.X)

        tk.Label(top_row, text="📊 Reconciliation Dashboard & Run History",
                 font=("Segoe UI", 16, "bold"), bg=t.bg, fg=t.text).pack(side=tk.LEFT)

        clear_btn = tk.Label(top_row, text="🗑 Clear History", font=("Segoe UI", 9, "bold"),
                             bg=t.slate_soft, fg=t.muted, padx=12, pady=6, cursor="hand2")
        clear_btn.pack(side=tk.RIGHT)
        clear_btn.bind("<Button-1>", lambda _e: self._clear_dashboard_history())

        tk.Label(head, text="Audit trail of the last 30 reconciliation runs with matching metrics and timelines",
                 font=("Segoe UI", 9), bg=t.bg, fg=t.muted).pack(anchor="w", pady=(4, 0))

        kpi_row = tk.Frame(c, bg=t.bg)
        kpi_row.pack(fill=tk.X, padx=pad_x, pady=(14, 0))
        self._dash_kpi_labels: dict = {}
        dash_specs = [
            ("dRuns", "TOTAL RUNS", "0", "📈 historical executions", "🔁", t.primary_soft),
            ("dTotal", "TOTAL RECORDS", "0", "🧾 total items reconciled", "📄", t.slate_soft),
            ("dMatched", "TOTAL MATCHED", "0", "✅ auto-matched entries", "🎯", t.green_soft),
            ("dExceptions", "TOTAL EXCEPTIONS", "0", "⚠️ flagged discrepancies", "🚨", t.red_soft),
        ]
        for i, (key, lbl, val, sub, ico, ico_bg) in enumerate(dash_specs):
            card = self._card(kpi_row)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14 if i < 3 else 0))

            inner = tk.Frame(card, bg=t.card, padx=16, pady=14)
            inner.pack(fill=tk.BOTH, expand=True)

            left = tk.Frame(inner, bg=t.card)
            left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            tk.Label(left, text=lbl, font=("Segoe UI", 8, "bold"), bg=t.card, fg=t.muted).pack(anchor="w")
            v_lbl = tk.Label(left, text=val, font=("Segoe UI", 20, "bold"), bg=t.card, fg=t.text)
            v_lbl.pack(anchor="w", pady=(3, 0))
            tk.Label(left, text=sub, font=("Segoe UI", 8), bg=t.card, fg=t.muted).pack(anchor="w", pady=(2, 0))
            self._dash_kpi_labels[key] = v_lbl

            ico_f = tk.Frame(inner, bg=ico_bg, width=40, height=40)
            ico_f.pack(side=tk.RIGHT, anchor="center")
            ico_f.pack_propagate(False)
            tk.Label(ico_f, text=ico, font=("Segoe UI", 16), bg=ico_bg).place(relx=0.5, rely=0.5, anchor="center")

        card = self._card(c)
        card.pack(fill=tk.BOTH, expand=True, padx=pad_x, pady=(14, 40))

        head_tbl = tk.Frame(card, bg=t.card, padx=16, pady=12)
        head_tbl.pack(fill=tk.X)
        tk.Label(head_tbl, text="Recent Reconciliation Runs (Last 30 Records)",
                 font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text).pack(side=tk.LEFT)

        sep = tk.Frame(card, bg=t.border, height=1)
        sep.pack(fill=tk.X)

        tree_f = tk.Frame(card, bg=t.card, padx=8, pady=8)
        tree_f.pack(fill=tk.BOTH, expand=True)

        cols = ("Run_ID", "Timestamp", "Mode", "Files_Count", "Total_Records", "Matched", "Exceptions", "Match_Rate", "Elapsed")
        self._dash_tree = ttk.Treeview(tree_f, columns=cols, show="headings",
                                       selectmode="extended", style="V3.Treeview", height=14)

        labels = {
            "Run_ID": "#", "Timestamp": "Date & Time (IST)", "Mode": "Recon Mode",
            "Files_Count": "Files", "Total_Records": "Total Records",
            "Matched": "Matched", "Exceptions": "Exceptions",
            "Match_Rate": "Match Rate", "Elapsed": "Duration"
        }
        widths = {
            "Run_ID": 40, "Timestamp": 180, "Mode": 140, "Files_Count": 70,
            "Total_Records": 100, "Matched": 90, "Exceptions": 90,
            "Match_Rate": 90, "Elapsed": 80
        }
        for col in cols:
            anchor = "e" if col in ("Total_Records", "Matched", "Exceptions", "Match_Rate", "Files_Count") else "w"
            self._dash_tree.heading(col, text=labels.get(col, col))
            self._dash_tree.column(col, width=widths.get(col, 100), anchor=anchor)

        vsb = ttk.Scrollbar(tree_f, orient=tk.VERTICAL, command=self._dash_tree.yview)
        hsb = ttk.Scrollbar(tree_f, orient=tk.HORIZONTAL, command=self._dash_tree.xview)
        self._dash_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._dash_tree.pack(fill=tk.BOTH, expand=True)

        self._dash_tree.tag_configure("high_rate", foreground=t.green)
        self._dash_tree.tag_configure("low_rate", foreground=t.amber)

        attach_copy_menu(self._dash_tree, self)
        return scroll

    def _refresh_dashboard_data(self):
        runs = self.history.get_runs()
        for item in self._dash_tree.get_children(""):
            self._dash_tree.delete(item)

        total_runs = len(runs)
        total_records = sum(r.get("total", 0) for r in runs)
        total_matched = sum(r.get("matched", 0) for r in runs)
        total_exceptions = sum(r.get("exceptions", 0) for r in runs)

        self._dash_kpi_labels["dRuns"].config(text=f"{total_runs:,}")
        self._dash_kpi_labels["dTotal"].config(text=f"{total_records:,}")
        self._dash_kpi_labels["dMatched"].config(text=f"{total_matched:,}")
        self._dash_kpi_labels["dExceptions"].config(text=f"{total_exceptions:,}")

        for i, r in enumerate(runs, 1):
            rate_val = r.get("match_rate", "0%")
            try:
                num_rate = float(rate_val.replace("%", ""))
                tag = "high_rate" if num_rate >= 90.0 else "low_rate"
            except ValueError:
                tag = ""
            self._dash_tree.insert("", tk.END,
                                   values=(f"#{i}", r.get("timestamp", ""), r.get("mode", ""),
                                           f"{r.get('files_count', 0)} files",
                                           f"{r.get('total', 0):,}", f"{r.get('matched', 0):,}",
                                           f"{r.get('exceptions', 0):,}", rate_val,
                                           f"{r.get('elapsed', 0):.1f}s"),
                                   tags=(tag,))

    def _clear_dashboard_history(self):
        if messagebox.askyesno("Clear Run History", "Are you sure you want to clear all 30 reconciliation history records?"):
            self.history.clear_runs()
            self._refresh_dashboard_data()

    # ─────────────────────────────────────────────────────────────────
    # VIEW 3: DATA SOURCES
    # ─────────────────────────────────────────────────────────────────
    def _build_data_sources_view(self, parent) -> tk.Frame:
        t = self._theme
        scroll = ScrollableFrame(parent, bg=t.bg)
        c = scroll.inner
        c.config(bg=t.bg)
        self._data_sources_scroll = scroll

        pad_x = 24

        head = tk.Frame(c, bg=t.bg)
        head.pack(fill=tk.X, padx=pad_x, pady=(18, 0))

        top_row = tk.Frame(head, bg=t.bg)
        top_row.pack(fill=tk.X)

        tk.Label(top_row, text="📁 Data Sources & Ingestion History",
                 font=("Segoe UI", 16, "bold"), bg=t.bg, fg=t.text).pack(side=tk.LEFT)

        add_btn = tk.Label(top_row, text="＋ Upload More Files", font=("Segoe UI", 9, "bold"),
                           bg=t.primary, fg="#ffffff", padx=14, pady=6, cursor="hand2")
        add_btn.pack(side=tk.RIGHT)
        add_btn.bind("<Button-1>", lambda _e: self._browse_files())

        clear_btn = tk.Label(top_row, text="🗑 Clear List", font=("Segoe UI", 9, "bold"),
                             bg=t.slate_soft, fg=t.muted, padx=12, pady=6, cursor="hand2")
        clear_btn.pack(side=tk.RIGHT, padx=(0, 8))
        clear_btn.bind("<Button-1>", lambda _e: self._clear_data_sources_history())

        tk.Label(head, text="Audit record of the last 10 data source files ingested into the system",
                 font=("Segoe UI", 9), bg=t.bg, fg=t.muted).pack(anchor="w", pady=(4, 0))

        card = self._card(c)
        card.pack(fill=tk.BOTH, expand=True, padx=pad_x, pady=(14, 40))

        head_tbl = tk.Frame(card, bg=t.card, padx=16, pady=12)
        head_tbl.pack(fill=tk.X)
        self._ds_count_lbl = tk.Label(head_tbl, text="Recent File Uploads (Last 10 Items)",
                                     font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text)
        self._ds_count_lbl.pack(side=tk.LEFT)

        sep = tk.Frame(card, bg=t.border, height=1)
        sep.pack(fill=tk.X)

        tree_f = tk.Frame(card, bg=t.card, padx=8, pady=8)
        tree_f.pack(fill=tk.BOTH, expand=True)

        cols = ("Index", "Timestamp", "File_Name", "Detected_Type", "File_Size", "File_Path", "Status")
        self._ds_tree = ttk.Treeview(tree_f, columns=cols, show="headings",
                                     selectmode="extended", style="V3.Treeview", height=12)

        labels = {
            "Index": "#", "Timestamp": "Upload Date & Time (IST)", "File_Name": "File Name",
            "Detected_Type": "Detected Type", "File_Size": "Size",
            "File_Path": "Full File Path", "Status": "Status"
        }
        widths = {
            "Index": 40, "Timestamp": 180, "File_Name": 240, "Detected_Type": 160,
            "File_Size": 90, "File_Path": 300, "Status": 100
        }
        for col in cols:
            anchor = "e" if col in ("Index", "File_Size") else "w"
            self._ds_tree.heading(col, text=labels.get(col, col))
            self._ds_tree.column(col, width=widths.get(col, 100), anchor=anchor, stretch=(col in ("File_Name", "File_Path")))

        vsb = ttk.Scrollbar(tree_f, orient=tk.VERTICAL, command=self._ds_tree.yview)
        hsb = ttk.Scrollbar(tree_f, orient=tk.HORIZONTAL, command=self._ds_tree.xview)
        self._ds_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._ds_tree.pack(fill=tk.BOTH, expand=True)

        attach_copy_menu(self._ds_tree, self)
        return scroll

    def _refresh_data_sources_data(self):
        files = self.history.get_files()
        for item in self._ds_tree.get_children(""):
            self._ds_tree.delete(item)

        self._ds_count_lbl.config(text=f"Recent File Uploads (Last {len(files)} of 10 Items)")
        for i, f in enumerate(files, 1):
            self._ds_tree.insert("", tk.END,
                                 values=(f"#{i}", f.get("timestamp", ""), f.get("filename", ""),
                                         f.get("type", "Data File"), f.get("size", "0 KB"),
                                         f.get("path", ""), f.get("status", "Loaded ✔")))

    def _clear_data_sources_history(self):
        if messagebox.askyesno("Clear Ingestion History", "Clear the recent 10 file upload records?"):
            self.history.clear_files()
            self._refresh_data_sources_data()

    # ─────────────────────────────────────────────────────────────────
    # VIEW 4: REPORTS
    # ─────────────────────────────────────────────────────────────────
    def _build_reports_view(self, parent) -> tk.Frame:
        t = self._theme
        scroll = ScrollableFrame(parent, bg=t.bg)
        c = scroll.inner
        c.config(bg=t.bg)
        self._reports_scroll = scroll

        pad_x = 24

        head = tk.Frame(c, bg=t.bg)
        head.pack(fill=tk.X, padx=pad_x, pady=(18, 0))

        top_row = tk.Frame(head, bg=t.bg)
        top_row.pack(fill=tk.X)

        tk.Label(top_row, text="📈 Current Reconciliation Reports & Summary",
                 font=("Segoe UI", 16, "bold"), bg=t.bg, fg=t.text).pack(side=tk.LEFT)

        export_xlsx_btn = tk.Label(top_row, text="⬇ Export Excel (.xlsx)", font=("Segoe UI", 9, "bold"),
                                   bg=t.green, fg="#ffffff", padx=14, pady=6, cursor="hand2")
        export_xlsx_btn.pack(side=tk.RIGHT)
        export_xlsx_btn.bind("<Button-1>", lambda _e: self._do_export())

        export_csv_btn = tk.Label(top_row, text="⬇ Export CSV", font=("Segoe UI", 9, "bold"),
                                  bg=t.primary, fg="#ffffff", padx=14, pady=6, cursor="hand2")
        export_csv_btn.pack(side=tk.RIGHT, padx=(0, 8))
        export_csv_btn.bind("<Button-1>", lambda _e: self._do_export_csv())

        self._rep_subtitle = tk.Label(head, text="Executive breakdown and itemized reconciliation ledger",
                                      font=("Segoe UI", 9), bg=t.bg, fg=t.muted)
        self._rep_subtitle.pack(anchor="w", pady=(4, 0))

        card = self._card(c)
        card.pack(fill=tk.BOTH, expand=True, padx=pad_x, pady=(14, 40))

        head_tbl = tk.Frame(card, bg=t.card, padx=16, pady=12)
        head_tbl.pack(fill=tk.X)
        self._rep_count_lbl = tk.Label(head_tbl, text="Active Reconciliation Details (0 records)",
                                       font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text)
        self._rep_count_lbl.pack(side=tk.LEFT)

        sep = tk.Frame(card, bg=t.border, height=1)
        sep.pack(fill=tk.X)

        tree_f = tk.Frame(card, bg=t.card, padx=8, pady=8)
        tree_f.pack(fill=tk.BOTH, expand=True)

        cols = ("Source", "Reference", "Business Unit", "SAP Posting",
                "SAP Amount", "Book Amount", "Variance", "Status", "Remarks")
        self._rep_tree = ttk.Treeview(tree_f, columns=cols, show="headings",
                                      selectmode="extended", style="V3.Treeview", height=15)

        widths = {
            "Source": 75, "Reference": 150, "Business Unit": 110,
            "SAP Posting": 105, "SAP Amount": 105, "Book Amount": 105,
            "Variance": 95, "Status": 100, "Remarks": 250,
        }
        for col in cols:
            anchor = "e" if col in ("SAP Amount", "Book Amount", "Variance") else "w"
            self._rep_tree.heading(col, text=col)
            self._rep_tree.column(col, width=widths.get(col, 100), anchor=anchor, stretch=(col in ("Reference", "Remarks")))

        vsb = ttk.Scrollbar(tree_f, orient=tk.VERTICAL, command=self._rep_tree.yview)
        hsb = ttk.Scrollbar(tree_f, orient=tk.HORIZONTAL, command=self._rep_tree.xview)
        self._rep_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._rep_tree.pack(fill=tk.BOTH, expand=True)

        self._rep_tree.tag_configure("matched", foreground=t.green)
        self._rep_tree.tag_configure("review", foreground=t.amber)
        self._rep_tree.tag_configure("mismatch", foreground=t.red)

        attach_copy_menu(self._rep_tree, self)
        return scroll

    def _refresh_reports_data(self):
        for item in self._rep_tree.get_children(""):
            self._rep_tree.delete(item)

        total = len(self._all_rows)
        self._rep_count_lbl.config(text=f"Active Reconciliation Details ({total:,} records)")
        if self._all_rows:
            matched_n = sum(1 for r in self._all_rows if r.get("tag") == "matched")
            self._rep_subtitle.config(
                text=f"Current Run: {total:,} total records  ·  {matched_n:,} matched ({matched_n/total*100:.1f}%)  ·  {total - matched_n:,} exceptions"
            )
            for r in self._all_rows:
                self._rep_tree.insert("", tk.END,
                                      values=(r.get("src", ""), r.get("ref", ""), r.get("bu", ""),
                                              r.get("posting", ""), r.get("sap_amt", ""),
                                              r.get("book_amt", ""), r.get("variance", ""),
                                              r.get("status", ""), r.get("remarks", "")),
                                      tags=(r.get("tag", ""),))

    def _do_export_csv(self):
        if not self._all_rows:
            messagebox.showinfo("No Data", "Run a reconciliation first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv")],
            initialfile=f"Reconciliation_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        try:
            df = pd.DataFrame(self._all_rows)
            if "search_str" in df.columns:
                df = df.drop(columns=["search_str", "tag"], errors="ignore")
            df.to_csv(path, index=False)
            messagebox.showinfo("Export Successful", f"Saved CSV report to:\n{path}")
        except Exception as err:
            messagebox.showerror("Export Error", str(err))

    # ─────────────────────────────────────────────────────────────────
    # Status Bar
    # ─────────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        t = self._theme
        bar = tk.Frame(self._main_frame, bg=t.card, height=34)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)

        sep = tk.Frame(self._main_frame, bg=t.border, height=1)
        sep.pack(side=tk.BOTTOM, fill=tk.X)

        self._live_dot = tk.Label(bar, text="●", font=("Segoe UI", 9), bg=t.card, fg=t.green, padx=8)
        self._live_dot.pack(side=tk.LEFT)
        self._status_lbl = tk.Label(bar, text="Ready", font=("Segoe UI", 9), bg=t.card, fg=t.muted)
        self._status_lbl.pack(side=tk.LEFT)

        self._status_version_lbl = tk.Label(bar, text="Recon Studio v3.0", font=("Segoe UI", 9), bg=t.card, fg=t.muted)
        self._status_version_lbl.pack(side=tk.RIGHT, padx=16)
        self._statusbar = bar

    # ─────────────────────────────────────────────────────────────────
    # Progress Overlay
    # ─────────────────────────────────────────────────────────────────
    def _build_progress_overlay(self):
        t = self._theme
        self._prog_bar = tk.Frame(self._main_frame, bg=t.card, relief="flat", bd=0,
                                  highlightthickness=1, highlightbackground=t.border)
        self._prog_bar_visible = False

        inner = tk.Frame(self._prog_bar, bg=t.card, padx=14, pady=12)
        inner.pack(fill=tk.BOTH, expand=True)
        self._prog_inner = inner

        self._prog_ring = ProgressRing(inner, size=52, bg=t.card)
        self._prog_ring.pack(side=tk.LEFT, padx=(0, 14))
        self._prog_ring.setup(t)

        info = tk.Frame(inner, bg=t.card)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._prog_info = info

        title_row = tk.Frame(info, bg=t.card)
        title_row.pack(fill=tk.X)
        self._prog_title_row = title_row
        self._prog_title = tk.Label(title_row, text="—", font=("Segoe UI", 11, "bold"), bg=t.card, fg=t.text)
        self._prog_title.pack(side=tk.LEFT)

        self._prog_sub = tk.Label(info, text="—", font=("Segoe UI", 9), bg=t.card, fg=t.muted, anchor="w")
        self._prog_sub.pack(fill=tk.X, pady=(2, 0))

        prog_track = tk.Frame(info, bg=t.slate_soft, height=4)
        prog_track.pack(fill=tk.X, pady=(6, 0))
        prog_track.pack_propagate(False)
        self._prog_track_ref = prog_track
        self._prog_fill = tk.Frame(prog_track, bg=t.primary, height=4, width=0)
        self._prog_fill.place(x=0, y=0, relheight=1)

        self._phases_frame = tk.Frame(info, bg=t.card)
        self._phases_frame.pack(fill=tk.X, pady=(6, 0))

        actions = tk.Frame(inner, bg=t.card)
        actions.pack(side=tk.RIGHT, padx=(14, 0))
        self._prog_actions = actions

        self._btn_pause = self._icon_button(actions, "⏸", command=self._toggle_pause)
        self._btn_pause.pack(pady=2)
        self._btn_prog_cancel = self._icon_button(actions, "✕", command=self._cancel_prog)
        self._btn_prog_cancel.pack(pady=2)
        self._btn_minimize = self._icon_button(actions, "–", command=self._minimize_prog)
        self._btn_minimize.pack(pady=2)
        self._btn_open_report = tk.Label(actions, text="⬇ Open report", font=("Segoe UI", 9, "bold"),
                                         bg=t.green, fg="#ffffff", padx=10, pady=5, cursor="hand2")
        self._btn_open_report.pack(pady=2)
        self._btn_open_report.bind("<Button-1>", lambda e: self._toast("Opening Excel report…"))
        self._btn_open_report.pack_forget()

        self._btn_prog_hide = self._ghost_button(actions, "Hide", command=self._hide_prog)
        self._btn_prog_hide.pack_forget()

        self._pill = tk.Frame(self._main_frame, bg=t.card, highlightthickness=1,
                              highlightbackground=t.border, cursor="hand2")
        self._pill_pct = tk.Label(self._pill, text="0%", font=("Segoe UI", 9, "bold"),
                                  bg=t.card, fg=t.text, padx=8)
        self._pill_pct.pack(side=tk.LEFT)
        self._pill.bind("<Button-1>", lambda e: self._restore_prog())
        self._pill_pct.bind("<Button-1>", lambda e: self._restore_prog())

        self._toast_frame = tk.Frame(self._main_frame, bg=t.card, highlightthickness=1,
                                     highlightbackground=t.green, relief="flat")
        self._toast_lbl = tk.Label(self._toast_frame, text="", font=("Segoe UI", 10, "bold"),
                                   bg=t.card, fg=t.text, padx=16, pady=10)
        self._toast_lbl.pack()
        self._toast_after = None

    # ─────────────────────────────────────────────────────────────────
    # File Management & Ingestion History
    # ─────────────────────────────────────────────────────────────────
    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Select reconciliation files",
            filetypes=[("Excel and data files", "*.xlsx *.xls *.tsv *.csv"), ("All files", "*.*")],
        )
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    sz = os.path.getsize(f) / 1024 if os.path.exists(f) else 0
                    sz_str = f"{sz/1024:.1f} MB" if sz >= 1024 else f"{sz:.0f} KB"
                    fname = os.path.basename(f)
                    ftype = "SAP Ledger" if "101" in fname or "402" in fname or "account" in fname.lower() else (
                        "Bank Statement" if "statement" in fname.lower() or "scb" in fname.lower() or "icici" in fname.lower() else "Sales Register"
                    )
                    self.history.add_file({
                        "timestamp": _get_ist_time_str(),
                        "filename": fname,
                        "type": ftype,
                        "size": sz_str,
                        "path": f,
                        "status": "Loaded ✔"
                    })
            self._refresh_chips()

    def _refresh_chips(self):
        t = self._theme
        if not hasattr(self, "_chips_frame") or not self._chips_frame.winfo_exists():
            return
        for w in self._chips_frame.winfo_children():
            w.destroy()
        for i, fp in enumerate(self.selected_files):
            chip = tk.Frame(self._chips_frame, bg=t.primary_soft, padx=10, pady=5)
            chip.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="w")
            tk.Label(chip, text=f"📄 {os.path.basename(fp)}", font=("Segoe UI", 9, "bold"),
                     bg=t.primary_soft, fg=t.primary).pack(side=tk.LEFT)
            x_btn = tk.Label(chip, text=" ×", font=("Segoe UI", 10, "bold"),
                             bg=t.primary_soft, fg=t.primary, cursor="hand2")
            x_btn.pack(side=tk.LEFT)
            x_btn.bind("<Button-1>", lambda e, idx=i: self._remove_chip(idx))

        n = len(self.selected_files)
        self._status_lbl.config(text=f"{n} file(s) loaded" if n else "Ready")

    def _remove_chip(self, idx: int):
        if 0 <= idx < len(self.selected_files):
            self.selected_files.pop(idx)
            self._refresh_chips()

    def _remove_file(self):
        if self.selected_files:
            self.selected_files.pop()
            self._refresh_chips()

    def _clear_files(self):
        self.selected_files.clear()
        self._refresh_chips()

    # ─────────────────────────────────────────────────────────────────
    # Reconciliation Execution
    # ─────────────────────────────────────────────────────────────────
    def _run_reconciliation(self):
        if not self.selected_files:
            messagebox.showinfo("No Files", "Please add files first using the Input Files panel.")
            return
        if self._busy:
            return
        self._busy = True
        self._cancel_event.clear()
        self._started_at = time.monotonic()
        self._status_lbl.config(text="Reconciling…")
        self._btn_run.config(bg="#9ca3af", cursor="arrow")

        mode_map = {
            "Sales": "Sales Reconciliation",
            "Coll": "Collection Reconciliation",
            "All": "Auto",
        }
        self._recon_model_used = mode_map.get(self._recon_mode.get(), "Auto")

        self._show_progress_bar(
            title="Reconciling records…",
            phases=["Read files", "Extract", "Validate", "Match", "Report"],
        )
        threading.Thread(target=self._run_worker, args=(self._recon_model_used,), daemon=True).start()

    def _run_worker(self, recon_model: str):
        self._last_error: Optional[str] = None
        try:
            self.results_df = process_file_list(
                self.selected_files,
                mode="Auto",
                recon_model=recon_model,
                progress_callback=lambda stage, cur, tot: self.after(0, self._on_engine_progress, stage, cur, tot),
                cancel_event=self._cancel_event,
            )
        except RuntimeError as err:
            if self._prog_cancelled or "cancelled" in str(err).lower():
                pass
            else:
                self._last_error = str(err)
        except Exception as err:
            self._last_error = str(err)
        finally:
            self.after(0, self._finish_recon)

    def _on_engine_progress(self, stage: str, cur: int, tot: int):
        self._status_lbl.config(text=stage)
        if tot:
            pct = min(100.0, cur / tot * 100.0)
            self._update_progress_bar(pct, stage)

    def _finish_recon(self):
        self._busy = False
        elapsed = time.monotonic() - self._started_at if self._started_at else 0
        self._btn_run.config(bg=self._theme.primary, cursor="hand2")

        if self._prog_cancelled:
            self._status_lbl.config(text="Cancelled by user")
            return

        last_err = getattr(self, "_last_error", None)
        if last_err:
            self._complete_progress_bar(errored=True, msg=f"Error: {last_err[:80]}")
            self._status_lbl.config(text="Processing error")
            messagebox.showerror("Processing Error", last_err)
            return

        if self.results_df is None or self.results_df.empty:
            used_mode = getattr(self, "_recon_model_used", "Auto")
            if used_mode != "Auto":
                self._status_lbl.config(text="Retrying with Auto-detect mode…")
                self._busy = True
                self._cancel_event.clear()
                self._recon_model_used = "Auto"
                self._show_progress_bar(
                    title="Reconciling (Auto mode)…",
                    phases=["Read files", "Extract", "Validate", "Match", "Report"],
                )
                threading.Thread(target=self._run_worker, args=("Auto",), daemon=True).start()
                return

            self._complete_progress_bar(errored=True, msg="No records matched — check file formats / mode")
            self._status_lbl.config(text="No results — check files")
            return

        self._complete_progress_bar(done=True)
        self._update_kpis()
        self._build_result_rows()

        total_n = len(self.results_df)
        matched_n = int((self.results_df["Overall_Status"] == "Matched").sum())
        exceptions_n = total_n - matched_n
        rate_str = f"{matched_n / total_n * 100:.1f}%" if total_n else "0%"

        self.history.add_run({
            "timestamp": _get_ist_time_str(),
            "mode": self._recon_mode.get(),
            "files_count": len(self.selected_files),
            "total": total_n,
            "matched": matched_n,
            "exceptions": exceptions_n,
            "match_rate": rate_str,
            "elapsed": round(elapsed, 1),
        })

        sales_count = sum(1 for r in self._all_rows if r["src"] == "Sales")
        coll_count = sum(1 for r in self._all_rows if r["src"] == "Collection")
        if self._active_tab == "Sales" and sales_count == 0 and coll_count > 0:
            self._active_tab = "Coll"
            self._recon_mode.set("Coll")
            self._refresh_seg()
            self._refresh_tab_buttons()
        elif self._active_tab == "Coll" and coll_count == 0 and sales_count > 0:
            self._active_tab = "Sales"
            self._recon_mode.set("Sales")
            self._refresh_seg()
            self._refresh_tab_buttons()
        elif sales_count > 0 and coll_count > 0 and self._recon_mode.get() == "All":
            self._active_tab = "All"
            self._refresh_tab_buttons()

        self._filter_table()
        self._status_lbl.config(text=f"Complete — {total_n:,} records in {elapsed:.1f}s")
        self._toast(f"Reconciliation complete — {total_n:,} records in {elapsed:.1f}s")

    def _update_kpis(self):
        if not hasattr(self, "_kpi_labels") or not self._kpi_labels:
            return
        df = self.results_df
        if df is None or df.empty:
            return
        total = len(df)
        matched = int((df["Overall_Status"] == "Matched").sum())
        review = int(df["Overall_Status"].str.contains("review", case=False, na=False).sum())
        exceptions = total - matched
        rate = f"{matched / total * 100:.1f}%" if total else "0%"

        self._kpi_labels["kTotal"].config(text=f"{total:,}")
        self._kpi_labels["kMatched"].config(text=f"{matched:,}")
        self._kpi_labels["kEx"].config(text=f"{exceptions:,}")
        self._kpi_labels["kRate"].config(text=rate)

        mismatch = exceptions - review
        self._donut.update_segments(matched, review, max(0, mismatch), self._theme)
        self._legend_labels["matched"].config(text=str(matched))
        self._legend_labels["review"].config(text=str(review))
        self._legend_labels["mismatch"].config(text=str(max(0, mismatch)))

    def _build_result_rows(self):
        df = self.results_df
        if df is None:
            self._all_rows = []
            return
        self._all_rows = []

        for _, row in df.iterrows():
            recon_type = row.get("Recon_Type", "Sales")

            if recon_type == "Sales":
                ref = _sales_reference(row)
                sap_amt = row.get("Total_CD_LC", 0) or 0
                book_amt = row.get("Total_Sales_Value", 0) or 0
                variance = row.get("Amount_Variance", 0) or 0
                posting = row.get("Posting_Date", "")
                bu = row.get("Business_Unit", "")
            else:
                ref = row.get("Bank_UTR", "")
                sap_amt = row.get("SAP_Amount", 0) or 0
                book_amt = row.get("Bank_Amount", 0) or 0
                variance = row.get("Amount_Variance", 0) or 0
                posting = row.get("SAP_Posting_Date", "")
                bu = row.get("Bank_Name", "")

            status = row.get("Overall_Status", "")
            remarks = row.get("Reconciliation_Remarks", "")

            try:
                v = float(variance)
                var_str = "—" if abs(v) < 0.01 else (f"+{_fmt_inr(v)}" if v > 0 else f"-{_fmt_inr(abs(v))}")
            except (TypeError, ValueError):
                var_str = str(variance)

            tag = "matched" if "Matched" in str(status) and "Not" not in str(status) else (
                "review" if "review" in str(status).lower() else (
                    "missing" if "Missing" in str(status) else "mismatch"
                )
            )

            self._all_rows.append({
                "src": recon_type,
                "ref": ref,
                "bu": bu,
                "posting": str(posting),
                "sap_amt": _fmt_inr(sap_amt),
                "book_amt": _fmt_inr(book_amt),
                "variance": var_str,
                "status": str(status),
                "remarks": str(remarks),
                "tag": tag,
                "search_str": f"{ref} {bu} {recon_type} {status} {remarks}".lower(),
            })

    def _filter_table(self):
        if not hasattr(self, "_tree") or not self._tree.winfo_exists():
            return
        query = self._table_search_var.get().strip().lower()
        tab = self._active_tab

        def _keep(r):
            if tab == "Sales" and r["src"] != "Sales":
                return False
            if tab == "Coll" and r["src"] != "Collection":
                return False
            if query and query not in r["search_str"]:
                return False
            return True

        visible = [r for r in self._all_rows if _keep(r)]
        self._render_table(visible)

        all_n = len(self._all_rows)
        sales_n = sum(1 for r in self._all_rows if r["src"] == "Sales")
        coll_n = sum(1 for r in self._all_rows if r["src"] == "Collection")
        self._tab_btns["All"].config(text=f"All ({all_n})" if all_n else "All")
        self._tab_btns["Sales"].config(text=f"Sales ({sales_n})" if sales_n else "Sales")
        self._tab_btns["Coll"].config(text=f"Collection ({coll_n})" if coll_n else "Collection")

    def _render_table(self, rows: list):
        if not hasattr(self, "_tree") or not self._tree.winfo_exists():
            return
        for item in self._tree.get_children(""):
            self._tree.delete(item)
        for r in rows:
            self._tree.insert("", tk.END,
                              values=(r["src"], r["ref"], r["bu"], r["posting"],
                                      r["sap_amt"], r["book_amt"], r["variance"], r["status"]),
                              tags=(r["tag"],))
        total = len(self._all_rows)
        vis = len(rows)
        self._row_count_lbl.config(text=f"{vis:,} of {total:,} rows" if total else "0 rows")

    def _sort_tree(self, col: str):
        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        try:
            items.sort(key=lambda t: float(str(t[0]).replace("₹", "").replace(",", "").replace("—", "0") or 0))
        except ValueError:
            items.sort(key=lambda t: t[0].lower())
        if items and self._tree.set(items[0][1], col) == self._tree.set(self._tree.get_children("")[0], col):
            items.reverse()
        for idx, (_, k) in enumerate(items):
            self._tree.move(k, "", idx)

    def _set_recon_mode(self, mode: str):
        self._recon_mode.set(mode)
        self._refresh_seg()
        self._active_tab = "All" if mode == "All" else mode
        self._refresh_tab_buttons()
        self._filter_table()

    def _refresh_seg(self):
        t = self._theme
        if not hasattr(self, "_seg_btns"):
            return
        mode = self._recon_mode.get()
        for k, b in self._seg_btns.items():
            if k == mode:
                b.config(bg=t.card, fg=t.primary)
            else:
                b.config(bg=t.slate_soft, fg=t.muted)

    def _set_active_tab(self, tab: str):
        self._active_tab = tab
        self._refresh_tab_buttons()
        self._filter_table()

    def _refresh_tab_buttons(self):
        t = self._theme
        if not hasattr(self, "_tab_btns"):
            return
        for key, b in self._tab_btns.items():
            if key == self._active_tab:
                b.config(fg=t.primary, highlightthickness=2, highlightbackground=t.primary)
            else:
                b.config(fg=t.muted, highlightthickness=0)

    # ─────────────────────────────────────────────────────────────────
    # Export Engine
    # ─────────────────────────────────────────────────────────────────
    def _do_export(self):
        if self.results_df is None or self.results_df.empty or self._busy:
            messagebox.showinfo("Nothing to Export", "Run a reconciliation first.")
            return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel report", "*.xlsx")],
            initialfile=f"Reconciliation_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        if not save_path:
            return
        self._busy = True
        self._status_lbl.config(text="Exporting…")
        self._show_progress_bar(title="Exporting Excel report…",
                                phases=["Prepare", "Write sheets", "Style", "Save"])
        threading.Thread(target=self._export_worker, args=(save_path,), daemon=True).start()

    def _export_worker(self, save_path: str):
        try:
            self.exporter.export(
                save_path, self.results_df,
                progress_callback=lambda s, c, t: self.after(0, self._on_engine_progress, s, c, t),
            )
            self.after(0, lambda: self._toast(f"Saved → {os.path.basename(save_path)}"))
            self.after(0, lambda: self._complete_progress_bar(done=True))
        except Exception as err:
            self.after(0, lambda: messagebox.showerror("Export Error", str(err)))
            self.after(0, lambda: self._complete_progress_bar(cancelled=True))
        finally:
            self.after(0, self._finish_export)

    def _finish_export(self):
        self._busy = False
        self._status_lbl.config(text="Export complete")

    # ─────────────────────────────────────────────────────────────────
    # Progress Bar Overlay Controls
    # ─────────────────────────────────────────────────────────────────
    def _show_progress_bar(self, title: str, phases: list):
        t = self._theme
        self._prog_bar.config(bg=t.card, highlightbackground=t.border)
        self._prog_inner.config(bg=t.card)
        self._prog_info.config(bg=t.card)
        self._prog_title_row.config(bg=t.card)
        self._phases_frame.config(bg=t.card)
        self._prog_actions.config(bg=t.card)
        self._btn_pause.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        self._btn_prog_cancel.config(bg=t.card, fg=t.text, highlightbackground=t.border)
        self._btn_minimize.config(bg=t.card, fg=t.text, highlightbackground=t.border)

        self._prog_pct = 0.0
        self._prog_phase_idx = 0
        self._prog_phases = phases
        self._prog_paused = False
        self._prog_cancelled = False
        self._prog_title.config(text=title, fg=t.text, bg=t.card)
        self._prog_sub.config(text="Starting…", fg=t.muted, bg=t.card)
        self._prog_track_ref.config(bg=t.slate_soft)
        self._prog_ring.config(bg=t.card)
        self._prog_ring.setup(t)
        self._prog_ring.set_pct(0, t)
        self._prog_fill.config(width=0, bg=t.primary)

        for w in self._phases_frame.winfo_children():
            w.destroy()
        self._phase_chips = []
        for ph in phases:
            chip = tk.Label(self._phases_frame, text=ph,
                            font=("Segoe UI", 8, "bold"),
                            bg=t.slate_soft, fg=t.muted, padx=8, pady=3)
            chip.pack(side=tk.LEFT, padx=3)
            self._phase_chips.append(chip)

        self._btn_open_report.pack_forget()
        self._btn_prog_hide.pack_forget()
        self._btn_pause.pack(pady=2)
        self._btn_prog_cancel.pack(pady=2)
        self._btn_minimize.pack(pady=2)

        self._prog_bar.place(in_=self._main_frame, relx=0.01, rely=1.0, anchor="sw",
                             relwidth=0.98, height=130)
        self._prog_bar.lift()
        self._prog_bar_visible = True
        self._prog_minimized = False

    def _update_progress_bar(self, pct: float, sub: str = ""):
        if not self._prog_bar_visible or self._prog_cancelled:
            return
        t = self._theme
        self._prog_pct = pct
        self._prog_ring.set_pct(pct, t)

        track_w = self._prog_track_ref.winfo_width()
        if track_w > 0:
            fill_w = max(0, int(track_w * pct / 100))
            self._prog_fill.config(width=fill_w)

        if sub:
            self._prog_sub.config(text=sub)

        phase_count = len(self._prog_phases)
        if phase_count > 0:
            phase_idx = min(int(pct / 100 * phase_count), phase_count - 1)
            for i, chip in enumerate(self._phase_chips):
                if i < phase_idx:
                    chip.config(bg=t.green_soft, fg=t.green, text=f"✓ {self._prog_phases[i]}")
                elif i == phase_idx:
                    chip.config(bg=t.primary_soft, fg=t.primary, text=f"● {self._prog_phases[i]}")
                else:
                    chip.config(bg=t.slate_soft, fg=t.muted, text=self._prog_phases[i])

        if self._prog_minimized:
            self._pill_pct.config(text=f"{int(pct)}%")

    def _complete_progress_bar(self, done=False, cancelled=False, errored=False, msg: str = ""):
        t = self._theme
        if not self._prog_bar_visible:
            return
        self._prog_ring.set_pct(100.0 if done else self._prog_pct, t,
                                done=done, cancelled=cancelled or errored, errored=errored)
        if done:
            self._prog_fill.config(bg=t.green)
            for chip in self._phase_chips:
                chip.config(bg=t.green_soft, fg=t.green)
            self._prog_title.config(text="Complete ✔", fg=t.green)
            self._btn_open_report.pack(pady=2)
            self._btn_prog_hide.pack(pady=2)
            self._btn_pause.pack_forget()
            self._btn_prog_cancel.pack_forget()
            self._btn_minimize.pack_forget()
            self.after(4000, self._hide_prog)
        elif cancelled:
            self._prog_fill.config(bg=t.red)
            self._prog_title.config(text="Cancelled", fg=t.red)
            self._prog_sub.config(text="Process stopped by user")
            self._btn_pause.pack_forget()
            self.after(2000, self._hide_prog)
        elif errored:
            self._prog_fill.config(bg=t.amber)
            for chip in self._phase_chips:
                chip.config(bg=t.amber_soft, fg=t.amber)
            self._prog_title.config(text="⚠  No results", fg=t.amber)
            if msg:
                self._prog_sub.config(text=msg)
            self._btn_pause.pack_forget()
            self._btn_prog_cancel.pack_forget()
            self._btn_minimize.pack_forget()
            self._btn_prog_hide.pack(pady=2)
            self.after(5000, self._hide_prog)

    def _toggle_pause(self):
        self._prog_paused = not self._prog_paused
        self._btn_pause.config(text="▶" if self._prog_paused else "⏸")
        if self._prog_paused:
            self._prog_sub.config(text="⏸  Paused — click ▶ to resume")

    def _cancel_prog(self):
        self._cancel_event.set()
        self._prog_cancelled = True
        self._busy = False
        self._complete_progress_bar(cancelled=True)
        self._status_lbl.config(text="Cancelled")
        self._btn_run.config(bg=self._theme.primary, cursor="hand2")

    def _minimize_prog(self):
        self._prog_minimized = True
        self._prog_bar.place_forget()
        self._pill.place(in_=self._main_frame, relx=1.0, rely=1.0, anchor="se", x=-16, y=-46)
        self._pill.lift()

    def _restore_prog(self):
        self._prog_minimized = False
        self._pill.place_forget()
        self._prog_bar.place(in_=self._main_frame, relx=0.01, rely=1.0, anchor="sw",
                             relwidth=0.98, height=130)
        self._prog_bar.lift()

    def _hide_prog(self):
        self._prog_bar.place_forget()
        self._pill.place_forget()
        self._prog_bar_visible = False

    # ─────────────────────────────────────────────────────────────────
    # Toast & Widget Helpers
    # ─────────────────────────────────────────────────────────────────
    def _toast(self, msg: str):
        t = self._theme
        self._toast_lbl.config(text=f"✔  {msg}", bg=t.card, fg=t.text)
        self._toast_frame.config(bg=t.card, highlightbackground=t.green)
        self._toast_frame.place(in_=self._main_frame, relx=1.0, rely=1.0, anchor="se", x=-20, y=-160)
        self._toast_frame.lift()
        if self._toast_after:
            self.after_cancel(self._toast_after)
        self._toast_after = self.after(3200, self._toast_frame.place_forget)

    def _card(self, parent) -> tk.Frame:
        t = self._theme
        return tk.Frame(parent, bg=t.card, highlightthickness=1, highlightbackground=t.border, relief="flat")

    def _ghost_button(self, parent, text: str, command: Callable = None) -> tk.Label:
        t = self._theme
        b = tk.Label(parent, text=text, font=("Segoe UI", 9, "bold"),
                     bg=t.card, fg=t.text, padx=14, pady=7, cursor="hand2",
                     relief="flat", highlightthickness=1, highlightbackground=t.border)
        if command:
            b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg=self._theme.slate_soft))
        b.bind("<Leave>", lambda e: b.config(bg=self._theme.card))
        return b

    def _icon_button(self, parent, text: str, command: Callable = None) -> tk.Label:
        t = self._theme
        b = tk.Label(parent, text=text, font=("Segoe UI", 12),
                     bg=t.card, fg=t.text, width=3, pady=5, cursor="hand2",
                     relief="flat", highlightthickness=1, highlightbackground=t.border)
        if command:
            b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg=self._theme.slate_soft))
        b.bind("<Leave>", lambda e: b.config(bg=self._theme.card))
        return b


# ─────────────────────────────────────────────────────────────────────────────
# Application Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = ReconApp()
    app.mainloop()


if __name__ == "__main__":
    main()
