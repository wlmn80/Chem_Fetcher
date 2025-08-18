"""GUI version of results fetcher with dynamic year & paper detection.

Uses same backend helpers as fetch_results_dynamic.py.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import functools
import subprocess
import csv

# Prevent creation of __pycache__ directories
import sys as _sys
_sys.dont_write_bytecode = True

import fetch_results_dynamic as dyn  # reuse backend functions

# --------------------------- Tooltip helper ----------------------------
class Tooltip:
    """A simple tooltip that appears after hovering over a widget."""
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay  # milliseconds
        self._id = None
        self.tipwin = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._remove)
        widget.bind("<ButtonPress>", self._remove)

    def _schedule(self, _):
        self._id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tipwin or not self.text:
            return
        x, y, _cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + cy + 20
        self.tipwin = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(tw, text=self.text, background="yellow", relief="solid", borderwidth=1, padding=(4,2))
        label.pack()

    def _remove(self, _=None):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self.tipwin:
            self.tipwin.destroy()
            self.tipwin = None


def add_tooltip(widget, text):
    Tooltip(widget, text)


# Default directory to save CSV (next to script/exe)
DEFAULT_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(DEFAULT_DIR, "gui_config.json")
USER_AGENT_NOTE = f"Default save folder: {DEFAULT_DIR}"

# --------------------------- GUI LOGIC ----------------------------
class ResultsGUI(tk.Tk):
    # --------------------- status bar spinner helpers --------------------
    def _start_status_spinner(self, base: str):
        self._spinner_base = base
        self._spinner_phase = 0
        if hasattr(self, "_spinner_after_id") and self._spinner_after_id:
            self.after_cancel(self._spinner_after_id)
        self._spinner_after_id = self.after(0, self._update_spinner)

    def _update_spinner(self):
        phases = ["|", "/", "-", "\\"]
        char = phases[self._spinner_phase % len(phases)]
        self.status_var.set(f"{self._spinner_base} {char}")
        self._spinner_phase += 1
        self._spinner_after_id = self.after(200, self._update_spinner)

    def _stop_status_spinner(self):
        if hasattr(self, "_spinner_after_id") and self._spinner_after_id:
            self.after_cancel(self._spinner_after_id)
            self._spinner_after_id = None
        self.status_var.set("Ready")
    def __init__(self) -> None:
        super().__init__()
        self.title("Student Results Fetcher")
        self.resizable(False, False)

        # Style tweaks
        ttk.Style(self).configure("TButton", padding=4)



        # Load config (last used folder)
        last_dir = DEFAULT_DIR
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as cfh:
                    last_dir = json.load(cfh).get("last_folder", DEFAULT_DIR)
            except (OSError, json.JSONDecodeError):
                pass

        # Variables
        self.year_var = tk.StringVar()
        self.paper_var = tk.StringVar()
        self.filename_var = tk.StringVar()
        self.path_var = tk.StringVar(value=last_dir)
        self.range_var = tk.StringVar(value="Index range: –")
        self.single_index_var = tk.StringVar()
        # no longer used for numeric display
        self.progress_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")


        # Build UI
        self._build_widgets()

        # Disable controls until data loaded
        self._set_controls_state("disabled")

        # Load years in background
        threading.Thread(target=self._load_years, daemon=True).start()

    # -----------------------------------------------------------------
    def _build_widgets(self) -> None:
        # Menu bar
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open Output Folder", command=self._open_output_folder)
        # Mode switcher will change label dynamically
        self._mode_menu = file_menu
        file_menu.add_command(label="Switch to Single Index Mode", command=self._switch_to_single)
        self._mode_menu_index = file_menu.index("end")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "Student Results Fetcher\nDeveloped by WL"))
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

        # Main frame
        main = ttk.Frame(self, padding=10)
        main.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        # Year combobox
        self.year_lbl = ttk.Label(main, text="Year:")
        self.year_lbl.grid(row=0, column=0, sticky="w")
        self.year_cmb = ttk.Combobox(main, textvariable=self.year_var, state="readonly", width=10)
        self.year_cmb.grid(row=0, column=1, pady=2)
        self.year_cmb.bind("<<ComboboxSelected>>", self._on_year_selected)
        add_tooltip(self.year_cmb, "Select the year of the results")

        # Paper combobox
        self.paper_lbl = ttk.Label(main, text="Paper:")
        self.paper_lbl.grid(row=1, column=0, sticky="w")
        self.paper_cmb = ttk.Combobox(main, textvariable=self.paper_var, state="readonly", width=10)
        self.paper_cmb.grid(row=1, column=1, pady=2)
        self.paper_cmb.bind("<<ComboboxSelected>>", self._on_paper_selected)
        add_tooltip(self.paper_cmb, "Select the paper of the results")

        # Range label
        self.range_label = ttk.Label(main, textvariable=self.range_var)
        self.range_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 6))

        # Single index fetch row (hidden by default until single mode)
        self.single_row_widgets = []
        self.single_label = ttk.Label(main, text="Single index:")
        self.single_label.grid(row=3, column=0, sticky="w")
        idx_frame = ttk.Frame(main)
        idx_frame.grid(row=3, column=1, sticky="w", pady=2)
        # collect widgets
        self.single_row_widgets.extend([self.single_label, idx_frame])
        self.single_index_entry = ttk.Entry(idx_frame, textvariable=self.single_index_var, width=14)
        self.single_index_entry.pack(side="left")
        fetch_one_btn = ttk.Button(idx_frame, text="Fetch", command=self._start_single_index_fetch)
        fetch_one_btn.pack(side="left", padx=(4,0))

        add_tooltip(self.single_index_entry, "Enter full index number (e.g., 20275001)")
        add_tooltip(fetch_one_btn, "Fetch this index across all papers and save CSV")

        # Filename entry
        ttk.Label(main, text="Output CSV name (without .csv):").grid(row=4, column=0, sticky="w")
        self.filename_entry = ttk.Entry(main, textvariable=self.filename_var, width=20)
        self.filename_entry.grid(row=4, column=1, pady=2)

        add_tooltip(self.filename_entry, "Leave blank to auto-generate filename")

        # Path selection
        ttk.Label(main, text="Save folder:").grid(row=5, column=0, sticky="w")
        path_frame = ttk.Frame(main)
        path_frame.grid(row=5, column=1, sticky="w")
        # use readonly entry so long paths scroll
        self.path_disp = ttk.Entry(path_frame, textvariable=self.path_var, state="readonly")
        self.path_disp.pack(side="left", fill="x", expand=True)
        add_tooltip(self.path_disp, "Folder where the CSV will be saved")

        browse_btn = ttk.Button(path_frame, text="Browse", command=self._browse_folder)
        browse_btn.pack(side="left", padx=(4,0))
        add_tooltip(browse_btn, "Choose a different folder")

        default_btn = ttk.Button(path_frame, text="Make Default", command=self._make_default)
        default_btn.pack(side="left", padx=(4,0))
        add_tooltip(default_btn, "Remember this folder for next time")

        reset_btn = ttk.Button(path_frame, text="Reset", command=self._reset_default)
        reset_btn.pack(side="left", padx=(4,0))
        add_tooltip(reset_btn, "Revert to startup folder")

        # Progress bar + label
        prog_frame = ttk.Frame(main)
        prog_frame.grid(row=6, column=0, columnspan=2, sticky="we", pady=(6,0))
        prog_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(prog_frame, length=200, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky="we")
        # Numeric percentage will appear in status bar now

        # Status bar
        status_bar = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="center", padding=(4,2))
        status_bar.grid(row=1, column=0, sticky="we", padx=8, pady=(0,8))
        self.columnconfigure(0, weight=1)

        # Fetch button
        self.fetch_btn = ttk.Button(main, text="Fetch Results", command=self._start_fetch)
        self.fetch_btn.grid(row=7, column=0, columnspan=2, pady=8)
        add_tooltip(self.fetch_btn, "Start fetching results")

        self.note_lbl = ttk.Label(main, text=USER_AGENT_NOTE, font=("Segoe UI", 8, "italic"))
        self.note_lbl.grid(row=8, column=0, columnspan=2, sticky="w")

        # Build batch widget list now that all are defined (exclude path widgets so they stay visible in single mode)
        self.batch_widgets = [self.year_lbl, self.year_cmb, self.paper_lbl, self.paper_cmb, self.range_label, self.filename_entry, self.fetch_btn]

        # set initial mode
        self._current_mode = "batch"
        self._set_mode_widgets()

    # -----------------------------------------------------------------
    def _browse_folder(self):
        """Open folder chooser to change save directory."""
        new_dir = filedialog.askdirectory(initialdir=self.path_var.get(), title="Select Folder to Save CSV")
        if new_dir:
            self.path_var.set(new_dir)
            # update note label
            self.note_lbl.config(text=f"Save folder: {new_dir}")
            self._validate_fields()


    def _open_output_folder(self):
        try:
            os.startfile(self.path_var.get())
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open folder: {exc}")

    def _set_controls_state(self, state: str) -> None:
        """Enable/disable interactive widgets."""
        for w in (self.year_cmb, self.paper_cmb, self.filename_entry, self.fetch_btn):
            try:
                if state == "disabled":
                    w.state(["disabled"])
                else:
                    w.state(["!disabled"])
                    # keep comboboxes readonly
                    if isinstance(w, ttk.Combobox):
                        w.configure(state="readonly")
            except Exception:
                w.configure(state=state)

    # -----------------------------------------------------------------
    def _load_years(self) -> None:
        self.progress_var.set("Loading years…")
        try:
            keys = dyn.fetch_all_result_keys()
            self.all_keys = keys
            years = sorted({int(k.split("_", 1)[0]) for k in keys if k[:4].isdigit()})
            self.after(0, lambda: self._populate_years(years))
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("Error", f"Could not load years: {exc}"))

    def _populate_years(self, years):
        self.year_cmb["values"] = years
        self.year_cmb.set("")
        self.progress_var.set("")
        self._set_controls_state("!disabled")


    # -----------------------------------------------------------------
    def _on_year_selected(self, _):
        year = self.year_var.get()
        if not year:
            return
        papers = dyn.get_available_papers(self.all_keys, int(year))
        self.paper_cmb["values"] = papers
        self.paper_cmb.set("")
        self.range_var.set("Index range: –")

    def _on_paper_selected(self, _):
        year = self.year_var.get()
        paper = self.paper_var.get()
        if not (year and paper):
            return
        rng = dyn.detect_index_range(self.all_keys, int(year), paper)
        if not rng:
            messagebox.showwarning("No data", "No records found for that year & paper.")
            self.fetch_btn.state(["disabled"])
            self.range_var.set("Index range: –")
            return
        # Update backend globals so fetch functions build correct Firebase keys
        dyn.YEAR = int(year)
        dyn.PAPER_NAME = paper
        dyn.START_INDEX, dyn.END_INDEX = rng

        self.start_idx, self.end_idx = rng
        self.range_var.set(f"Index range: {rng[0]}-{rng[1]}")
        default_name = f"results_{year}_{paper}"
        self.filename_var.set(default_name)


    # -----------------------------------------------------------------
    def _start_fetch(self):

        # Ensure indices are set
        if not hasattr(self, 'start_idx') or not hasattr(self, 'end_idx'):
            messagebox.showerror("Missing selection", "Please select Year and Paper before fetching.")
            return

        filename = self.filename_var.get().strip()
        if not filename:
            filename = f"results_{self.year_var.get() or 'data'}_{self.paper_var.get() or ''}".strip('_')
        # Build output path
        csv_path = os.path.join(self.path_var.get(), filename + ".csv")

        # Disable UI
        self._set_controls_state("disabled")
        self.progress_var.set("0%")
        self.progress_bar['value'] = 0
        threading.Thread(target=self._worker_fetch, args=(csv_path,), daemon=True).start()

    # -----------------------------------------------------------------
    def _validate_fields(self, show_errors: bool = False) -> bool:
        """Enable/disable Fetch button based on field completeness."""
        year_ok = bool(self.year_var.get())
        paper_ok = bool(self.paper_var.get())
        name_ok = bool(self.filename_var.get().strip())
        folder_ok = os.path.isdir(self.path_var.get())
        # Validation currently unused (auto-disable removed)
        if show_errors and not all_ok:
            messagebox.showerror("Missing info", "Please complete Year, Paper, Filename, and valid Folder before fetching.")
        return True

    # -----------------------------------------------------------------
    def _reset_default(self):
        self.path_var.set(DEFAULT_DIR)
        self.note_lbl.config(text=f"Save folder: {DEFAULT_DIR}")
        self._save_config()

    def _make_default(self):
        self._save_config()
        messagebox.showinfo("Saved", "Current folder set as default.")

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as cfh:
                json.dump({"last_folder": self.path_var.get()}, cfh)
        except OSError:
            pass  # non-critical

    # -----------------------------------------------------------------
    # Single index across papers
    # Popup version no longer used
    def _single_index_prompt_disabled(self):
        """Deprecated: old popup version kept for reference."""
        pass

    # ---------------- Mode switching -----------------
    def _set_mode_widgets(self):
        if self._current_mode == "batch":
            # show batch widgets
            for w in self.single_row_widgets:
                w.grid_remove()
            for w in self.batch_widgets:
                try:
                    w.grid()
                except Exception:
                    pass
            self._mode_menu.entryconfig(self._mode_menu_index, label="Switch to Single Index Mode", command=self._switch_to_single)
        else:
            for w in self.batch_widgets:
                try:
                    w.grid_remove()
                except Exception:
                    pass
            for w in self.single_row_widgets:
                w.grid()
            self._mode_menu.entryconfig(self._mode_menu_index, label="Switch to Batch Mode", command=self._switch_to_batch)
        # Refresh
        self.update_idletasks()

    def _switch_to_single(self):
        self._current_mode = "single"
        self._set_mode_widgets()
        self.single_index_entry.focus_set()

    def _switch_to_batch(self):
        self._current_mode = "batch"
        self._set_mode_widgets()

    def _start_single_index_fetch(self):
        raw = self.single_index_var.get().strip()
        if not (raw.isdigit() and len(raw) >= 5):
            messagebox.showerror("Invalid", "Enter the complete numeric index (e.g., 20275001).")
            return
        year_val = int(raw[:4])
        if not hasattr(self, "all_keys") or year_val not in {int(k.split("_",1)[0]) for k in self.all_keys}:
            messagebox.showerror("Invalid", "The year part of the index is not available in the database.")
            return
        self._fetch_single_index_across_papers(year_val, int(raw))

    def _fetch_single_index_across_papers(self, year: int, index_number: int):
        """Background fetch for one index across all papers."""
        self._start_status_spinner("Fetching index")
        def _worker():
            papers = dyn.get_available_papers(self.all_keys, year)
            rows = []
            for paper in papers:
                dyn.YEAR = year
                dyn.PAPER_NAME = paper
                res = dyn.fetch_result_record(index_number)
                if res:
                    rows.append({
                        "Paper": paper,
                        "Mark": res.get("mark"),
                        "Grade": dyn.get_grade(res.get("mark", 0)),
                        "Rank": res.get("rank"),
                    })
            self.after(0, lambda: self._single_index_result(year, index_number, rows))
        threading.Thread(target=_worker, daemon=True).start()

    def _single_index_result(self, year: int, index_number: int, rows):
        """Show results for single index, save CSV."""
        self._stop_status_spinner()
        if not rows:
            messagebox.showinfo("No Data", "No records found for that index across any papers.")
            return
        csv_filename = f"index_{index_number}_{year}.csv"
        csv_path = os.path.join(self.path_var.get(), csv_filename)
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=["Paper","Mark","Grade","Rank"])
                writer.writeheader()
                writer.writerows(rows)
        except OSError as exc:
            messagebox.showerror("Error", f"Could not write CSV:\n{exc}")
            csv_path = None
        dlg = tk.Toplevel(self)
        dlg.title("Single Index Results")
        dlg.resizable(False, False)
        ttk.Label(dlg, text=f"Results for {index_number} ({year})", font=("Segoe UI", 10, "bold")).pack(pady=(6,4))
        txt = tk.Text(dlg, width=40, height=min(12, len(rows)+2), relief="solid", borderwidth=1)
        txt.pack(padx=6)
        txt.insert("end", "Paper\tMark\tGrade\tRank\n")
        for r in rows:
            txt.insert("end", f"{r['Paper']}\t{r['Mark']}\t{r['Grade']}\t{r['Rank']}\n")
        txt.config(state="disabled")
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=6)
        if csv_path:
            ttk.Button(btn_frame, text="Open CSV", command=lambda p=csv_path: self._open_file(p)).pack(side="left", padx=4)
            ttk.Button(btn_frame, text="Show in Folder", command=lambda p=csv_path: self._show_in_folder(p)).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side="left", padx=4)
        dlg.grab_set()

    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    def _open_file(self, path: str):
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open file:\n{exc}")

    def _show_in_folder(self, path: str):
        try:
            subprocess.run(["explorer", "/select,", path])
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open folder:\n{exc}")

    def _export_missing_csv(self, base_path: str, missing_idx: list[int]):
        if not missing_idx:
            messagebox.showinfo("Info", "No missing indexes to export.")
            return
        missing_path = os.path.splitext(base_path)[0] + "_missing.csv"
        try:
            with open(missing_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["Missing Index Numbers"])
                for idx in missing_idx:
                    writer.writerow([idx])
            messagebox.showinfo("Exported", f"Missing index list written to:\n{missing_path}")
        except OSError as exc:
            messagebox.showerror("Error", f"Could not write missing CSV:\n{exc}")

    def _retry_missing(self, missing_idx: list[int], csv_path: str):
        if not missing_idx:
            messagebox.showinfo("Info", "No missing indexes to retry.")
            return
        self._start_status_spinner("Retrying missing")
        def _worker():
            new_records = []
            still_missing = []
            for idx in missing_idx:
                res = dyn.fetch_result_record(idx)
                if res:
                    stu = dyn.fetch_student_record(idx)
                    new_records.append({
                        "Rank": res.get("rank"),
                        "Index Number": idx,
                        "Name": stu.get("name"),
                        "School": stu.get("school"),
                        "Mark": res.get("mark"),
                        "Grade": dyn.get_grade(res.get("mark", 0)),
                    })
                else:
                    still_missing.append(idx)
            if new_records:
                # append to original CSV
                try:
                    import pandas as pd
                    pd.DataFrame(new_records).to_csv(csv_path, mode="a", header=False, index=False)
                except ImportError:
                    # fallback: write manually
                    import os as _os
                    header_needed = not _os.path.exists(csv_path) or _os.path.getsize(csv_path) == 0
                    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
                        writer = csv.DictWriter(fh, fieldnames=["Rank","Index Number","Name","School","Mark","Grade"])
                        if header_needed:
                            writer.writeheader()
                        writer.writerows(new_records)
            self.after(0, lambda: (self._stop_status_spinner(), self._show_success_dialog(len(new_records), still_missing, csv_path)))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_success_dialog(self, written: int, missing_idx: list[int], path: str):
        # Reset status bar
        self.status_var.set("Ready")
        # Close any existing success dialog
        if hasattr(self, "_success_dlg") and self._success_dlg and self._success_dlg.winfo_exists():
            self._success_dlg.destroy()
        dlg = tk.Toplevel(self)
        self._success_dlg = dlg
        dlg.title("Success")
        dlg.resizable(False, False)
        missing = len(missing_idx)
        ttk.Label(dlg, text=(f"{missing} records were missing (no data)." if missing else "All requested records fetched."), wraplength=300).pack(padx=10, pady=(10,4))
        ttk.Label(dlg, text=f"Wrote {written} new records to:").pack()
        ttk.Label(dlg, text=path, foreground="blue", wraplength=300).pack(pady=(0,6))
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=(0,10))
        ttk.Button(btn_frame, text="Open", command=lambda p=path: self._open_file(p)).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Show in Folder", command=lambda p=path: self._show_in_folder(p)).pack(side="left", padx=4)
        if missing:
            ttk.Button(btn_frame, text="Export Missing CSV", command=lambda: self._export_missing_csv(path, missing_idx)).pack(side="left", padx=4)
            ttk.Button(btn_frame, text="Retry Missing", command=lambda: self._retry_missing(missing_idx, path)).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Close", command=lambda: (dlg.destroy(), setattr(self, "_success_dlg", None))).pack(side="left", padx=4)
        dlg.grab_set()

    # -----------------------------------------------------------------
    def _worker_fetch(self, csv_path: str):
        total = self.end_idx - self.start_idx + 1
        collected = []
        missing_idx = []
        for count, idx in enumerate(range(self.start_idx, self.end_idx + 1), 1):
            res = dyn.fetch_result_record(idx)
            if res:
                stu = dyn.fetch_student_record(idx)
                collected.append({
                    "Rank": res.get("rank"),
                    "Index Number": idx,
                    "Name": stu.get("name"),
                    "School": stu.get("school"),
                    "Mark": res.get("mark"),
                    "Grade": dyn.get_grade(res.get("mark", 0)),
                })
            else:
                missing_idx.append(idx)
            percent = int(count * 100 / total)
            self.after(0, lambda p=percent: (self.progress_bar.config(value=p), self.status_var.set(f"{p}%")))
        if collected:
            dyn.write_csv(collected, csv_path)
            self.after(0, lambda rp=len(collected), miss=missing_idx.copy(), path=csv_path: self._show_success_dialog(rp, miss, path))
            self._save_config()
        else:
            self.after(0, lambda: messagebox.showinfo("No Data", "No records were retrieved."))
        self.after(0, lambda: self._set_controls_state("!disabled"))
        self.after(0, lambda: (self.status_var.set("Ready"), self.progress_bar.config(value=0)))


if __name__ == "__main__":
    ResultsGUI().mainloop()
