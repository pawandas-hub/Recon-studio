"""Minimalist Tkinter UI Desktop Application for Sales & SAP Reconciliation."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd

from ..services.recon_engine import process_file_list
from ..export.excel_exporter import ExcelReportExporter

class MinimalReconApp:
    """Standard Tkinter Minimal UI Application."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Universal Sales Reconciliation Tool")
        self.root.geometry("640x480")
        self.root.resizable(False, False)
        self.root.configure(bg="#f0f0f0")

        self.selected_files = []
        self.exporter = ExcelReportExporter()

        # Title Header
        title_label = tk.Label(
            root, 
            text="Sales Data Reconciliation Tool", 
            font=("Segoe UI", 18, "bold"), 
            bg="#f0f0f0", 
            fg="#000000"
        )
        title_label.pack(pady=(25, 15))

        # Mode Selection
        mode_frame = tk.Frame(root, bg="#f0f0f0")
        mode_frame.pack(pady=(0, 15))

        tk.Label(
            mode_frame,
            text="Recon Mode:",
            font=("Segoe UI", 10, "bold"),
            bg="#f0f0f0"
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.mode_var = tk.StringVar(value="Auto Detect")
        self.mode_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.mode_var,
            values=[
                "Auto Detect",
                "Format 1 (Legacy / Ref. 1 vs DB)",
                "Format 2 (Retailer / Ref. 2 vs Invoice No)"
            ],
            state="readonly",
            width=38,
            font=("Segoe UI", 9)
        )
        self.mode_combo.pack(side=tk.LEFT)

        # Select Files Button (Blue)
        self.btn_select = tk.Button(
            root, 
            text="📁  Select Sales / SAP Files", 
            font=("Segoe UI", 12, "bold"), 
            bg="#2b5b9a", 
            fg="white", 
            activebackground="#204473", 
            activeforeground="white",
            bd=1, 
            relief="solid", 
            width=28, 
            height=2, 
            cursor="hand2",
            command=self.select_files
        )
        self.btn_select.pack(pady=5)

        # Status Label
        self.lbl_status = tk.Label(
            root, 
            text="", 
            font=("Segoe UI", 10, "bold"), 
            bg="#f0f0f0", 
            fg="#2e7d32"
        )
        self.lbl_status.pack(pady=10)

        # Run Button (Green)
        self.btn_run = tk.Button(
            root, 
            text="🚀  Run Reconciliation & Save Excel", 
            font=("Segoe UI", 12, "bold"), 
            bg="#0d7a42", 
            fg="white", 
            activebackground="#08542d", 
            activeforeground="white", 
            bd=1, 
            relief="solid", 
            width=28, 
            height=2, 
            cursor="hand2",
            state=tk.DISABLED,
            command=self.run_reconciliation
        )
        self.btn_run.pack(pady=10)

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Sales / SAP / Mapping Files",
            filetypes=[("Excel & TSV Files", "*.xlsx *.xls *.tsv *.csv"), ("All Files", "*.*")]
        )
        if files:
            self.selected_files = list(files)
            count = len(self.selected_files)
            self.lbl_status.config(
                text=f"Selected {count} file{'s' if count > 1 else ''}: " + ", ".join([os.path.basename(f) for f in self.selected_files]),
                fg="#2e7d32"
            )
            self.btn_run.config(state=tk.NORMAL)
        else:
            self.selected_files = []
            self.lbl_status.config(text="No files selected.", fg="#c62828")
            self.btn_run.config(state=tk.DISABLED)

    def run_reconciliation(self):
        if not self.selected_files:
            messagebox.showwarning("Warning", "Please select file(s) first!")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            initialfile="Reconciliation_Summary_Report.xlsx",
            title="Save Reconciliation Results"
        )
        if not save_path:
            return

        try:
            selected_mode = self.mode_var.get()
            recon_results = process_file_list(self.selected_files, mode=selected_mode)

            if recon_results.empty:
                messagebox.showerror("Error", "No reconciliation records could be generated from the selected files.")
                return

            self.exporter.export(save_path, recon_results)
            messagebox.showinfo("Success", f"Reconciliation complete!\n\nSaved to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Execution Error", f"An error occurred during reconciliation:\n{str(e)}")

def main():
    root = tk.Tk()
    app = MinimalReconApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

