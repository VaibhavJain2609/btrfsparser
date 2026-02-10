import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import sys

import btrfs_parser


# =========================
# Stdout Redirector
# =========================
class StdoutRedirector:
    def __init__(self, gui):
        self.gui = gui

    def write(self, text):
        self.gui.append_output(text)

    def flush(self):
        pass


# =========================
# GUI Application
# =========================
class BtrfsParserGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Btrfs Forensic Parser GUI")
        self.geometry("950x650")
        self.resizable(True, True)

        # Variables
        self.image_path = tk.StringVar()
        self.partition_offset = tk.StringVar(value="4198400s")
        self.output_format = tk.StringVar(value="console")
        self.output_file = tk.StringVar()
        self.info_only = tk.BooleanVar()
        self.verbose = tk.BooleanVar()
        self.status_text = tk.StringVar(value="Status: Idle")
        self.search_var = tk.StringVar()

        self.full_output = ""
        self.search_enabled = False

        self.build_ui()

    # =========================
    # UI Layout
    # =========================
    def build_ui(self):
        # Disk Image
        frame_img = tk.LabelFrame(self, text="Disk Image")
        frame_img.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_img, textvariable=self.image_path, width=85).pack(
            side="left", padx=5, pady=5
        )
        tk.Button(frame_img, text="Browse", command=self.browse_image).pack(side="left")

        # Parser Options
        frame_opts = tk.LabelFrame(self, text="Parser Options")
        frame_opts.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_opts, text="Partition Offset:").grid(row=0, column=0, sticky="w")
        tk.Entry(frame_opts, textvariable=self.partition_offset, width=15).grid(
            row=0, column=1
        )

        tk.Label(frame_opts, text="Output Format:").grid(row=1, column=0, sticky="w")
        tk.OptionMenu(
            frame_opts, self.output_format, "console", "json", "csv", "tree"
        ).grid(row=1, column=1, sticky="w")

        tk.Checkbutton(
            frame_opts, text="Info Only", variable=self.info_only
        ).grid(row=2, column=0, sticky="w")

        tk.Checkbutton(
            frame_opts, text="Verbose", variable=self.verbose
        ).grid(row=2, column=1, sticky="w")

        # Output File + Run Button
        frame_out = tk.LabelFrame(self, text="Output File (JSON / CSV)")
        frame_out.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_out, textvariable=self.output_file, width=65).pack(
            side="left", padx=5, pady=5
        )
        tk.Button(frame_out, text="Browse", command=self.browse_output_file).pack(
            side="left", padx=5
        )
        tk.Button(
            frame_out,
            text="Run Btrfs Parser",
            command=self.run_parser
        ).pack(side="left", padx=15)

        # Parser Output
        frame_console = tk.LabelFrame(self, text="Parser Output")
        frame_console.pack(fill="both", expand=True, padx=10, pady=5)

        self.output_console = scrolledtext.ScrolledText(
            frame_console,
            wrap=tk.WORD,
            font=("Consolas", 10)
        )
        self.output_console.pack(fill="both", expand=True)

        self.make_readonly_but_selectable(self.output_console)

        # Search / Filter
        frame_search = tk.Frame(self)
        frame_search.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_search, text="Search:").pack(side="left")
        self.search_entry = tk.Entry(
            frame_search,
            textvariable=self.search_var,
            state="disabled",
            width=40
        )
        self.search_entry.pack(side="left", padx=5)

        self.search_button = tk.Button(
            frame_search,
            text="Filter",
            state="disabled",
            command=self.apply_search
        )
        self.search_button.pack(side="left", padx=5)

        tk.Button(
            frame_search,
            text="Clear",
            command=self.clear_search
        ).pack(side="left", padx=5)

        # Status Bar
        tk.Label(
            self,
            textvariable=self.status_text,
            anchor="w",
            relief=tk.SUNKEN
        ).pack(fill="x", side="bottom")

    # =========================
    # Read-only but selectable
    # =========================
    def make_readonly_but_selectable(self, widget):
        widget.bind("<Key>", lambda e: "break")
        widget.bind("<<Paste>>", lambda e: "break")
        widget.bind("<<Cut>>", lambda e: "break")
        widget.bind("<<Copy>>", lambda e: None)

    # =========================
    # Output Handling
    # =========================
    def append_output(self, text):
        self.full_output += text
        self.output_console.insert(tk.END, text)
        self.output_console.see(tk.END)

    # =========================
    # Search & Filter
    # =========================
    def apply_search(self):
        if not self.search_enabled:
            return

        keyword = self.search_var.get().lower()
        self.output_console.delete("1.0", tk.END)

        for line in self.full_output.splitlines():
            if keyword in line.lower():
                self.output_console.insert(tk.END, line + "\n")

    def clear_search(self):
        self.output_console.delete("1.0", tk.END)
        self.output_console.insert(tk.END, self.full_output)

    # =========================
    # GUI Actions
    # =========================
    def browse_image(self):
        path = filedialog.askopenfilename()
        if path:
            self.image_path.set(path)

    def browse_output_file(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")]
        )
        if path:
            self.output_file.set(path)

    def run_parser(self):
        if not self.image_path.get():
            messagebox.showerror("Error", "Please select a disk image.")
            return

        self.full_output = ""
        self.search_enabled = False
        self.search_entry.configure(state="disabled")
        self.search_button.configure(state="disabled")

        self.output_console.delete("1.0", tk.END)
        self.status_text.set("Status: Parsing in progress...")

        threading.Thread(target=self.run_parser_thread, daemon=True).start()

    def run_parser_thread(self):
        argv_backup = sys.argv[:]

        try:
            sys.argv = [
                "btrfs_parser.py",
                self.image_path.get(),
                "-p", self.partition_offset.get(),
                "-o", self.output_format.get()
            ]

            if self.output_file.get():
                sys.argv.extend(["-f", self.output_file.get()])
            if self.info_only.get():
                sys.argv.append("--info-only")
            if self.verbose.get():
                sys.argv.append("-v")

            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = sys.stderr = StdoutRedirector(self)

            btrfs_parser.main()

            self.status_text.set("Status: Parsing completed")
            self.search_enabled = True
            self.search_entry.configure(state="normal")
            self.search_button.configure(state="normal")

            messagebox.showinfo("Completed", "Parsing completed successfully.")

        except Exception as e:
            self.status_text.set("Status: Parsing failed")
            messagebox.showerror("Parser Error", str(e))

        finally:
            sys.argv = argv_backup
            sys.stdout = old_stdout
            sys.stderr = old_stderr


# =========================
# Entry Point
# =========================
if __name__ == "__main__":
    app = BtrfsParserGUI()
    app.mainloop()
