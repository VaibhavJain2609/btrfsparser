import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import sys

import btrfs_parser


# =========================
# Stdout Redirector
# =========================
class StdoutRedirector:
    """
    Redirect stdout/stderr to a READ-ONLY Tkinter Text widget
    """
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, text):
        self.text_widget.configure(state="normal")
        self.text_widget.insert(tk.END, text)
        self.text_widget.see(tk.END)
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


# =========================
# GUI Application
# =========================
class BtrfsParserGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Btrfs Forensic Parser GUI")
        self.geometry("900x600")
        self.resizable(True, True)

        # Variables
        self.image_path = tk.StringVar()
        self.partition_offset = tk.StringVar(value="4198400s")
        self.output_format = tk.StringVar(value="console")
        self.output_file = tk.StringVar()
        self.info_only = tk.BooleanVar()
        self.verbose = tk.BooleanVar()
        self.status_text = tk.StringVar(value="Status: Idle")

        self.build_ui()

    # =========================
    # UI Layout
    # =========================
    def build_ui(self):
        # Disk Image
        frame_img = tk.LabelFrame(self, text="Disk Image")
        frame_img.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_img, textvariable=self.image_path, width=80).pack(
            side="left", padx=5, pady=5
        )
        tk.Button(frame_img, text="Browse", command=self.browse_image).pack(
            side="left", padx=5
        )

        # Parser Options
        frame_opts = tk.LabelFrame(self, text="Parser Options")
        frame_opts.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_opts, text="Partition Offset:").grid(row=0, column=0, sticky="w")
        tk.Entry(frame_opts, textvariable=self.partition_offset, width=15).grid(
            row=0, column=1
        )

        tk.Label(frame_opts, text="Output Format:").grid(row=1, column=0, sticky="w")
        tk.OptionMenu(
            frame_opts,
            self.output_format,
            "console", "json", "csv", "tree"
        ).grid(row=1, column=1, sticky="w")

        tk.Checkbutton(
            frame_opts, text="Info Only", variable=self.info_only
        ).grid(row=2, column=0, sticky="w")

        tk.Checkbutton(
            frame_opts, text="Verbose", variable=self.verbose
        ).grid(row=2, column=1, sticky="w")

        # Output File (for JSON / CSV)
        frame_out = tk.LabelFrame(self, text="Output File (for JSON / CSV)")
        frame_out.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_out, textvariable=self.output_file, width=80).pack(
            side="left", padx=5, pady=5
        )
        tk.Button(frame_out, text="Browse", command=self.browse_output_file).pack(
            side="left", padx=5
        )

        # Run Button
        tk.Button(
            self,
            text="Run Btrfs Parser",
            height=2,
            command=self.run_parser
        ).pack(pady=10)

        # Output Console (READ-ONLY)
        frame_console = tk.LabelFrame(self, text="Parser Output")
        frame_console.pack(fill="both", expand=True, padx=10, pady=5)

        self.output_console = scrolledtext.ScrolledText(
            frame_console,
            wrap=tk.WORD,
            font=("Consolas", 10),
            state="disabled"
        )
        self.output_console.pack(fill="both", expand=True)

        # Status Bar
        tk.Label(
            self,
            textvariable=self.status_text,
            anchor="w",
            relief=tk.SUNKEN
        ).pack(fill="x", side="bottom")

    # =========================
    # Actions
    # =========================
    def browse_image(self):
        path = filedialog.askopenfilename(
            title="Select Disk Image",
            filetypes=[("Disk Images", "*.img *.dd *.raw"), ("All Files", "*.*")]
        )
        if path:
            self.image_path.set(path)

    def browse_output_file(self):
        path = filedialog.asksaveasfilename(
            title="Save Output File",
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )
        if path:
            self.output_file.set(path)

    def run_parser(self):
        if not self.image_path.get():
            messagebox.showerror("Error", "Please select a disk image.")
            return

        # Clear console safely
        self.output_console.configure(state="normal")
        self.output_console.delete("1.0", tk.END)
        self.output_console.configure(state="disabled")

        self.status_text.set("Status: Parsing in progress...")

        threading.Thread(target=self._run_parser_thread, daemon=True).start()

    def _run_parser_thread(self):
        args = [
            self.image_path.get(),
            "-p", self.partition_offset.get(),
            "-o", self.output_format.get()
        ]

        if self.output_file.get():
            args.extend(["-f", self.output_file.get()])

        if self.info_only.get():
            args.append("--info-only")
        if self.verbose.get():
            args.append("-v")

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = sys.stderr = StdoutRedirector(self.output_console)

        try:
            btrfs_parser.main(args)
            self.status_text.set("Status: Parsing completed")

            # ✅ Completion popup restored
            messagebox.showinfo(
                "Parsing Completed",
                "Btrfs parsing completed successfully."
            )

        except Exception as e:
            self.status_text.set("Status: Parsing failed")
            messagebox.showerror("Parser Error", str(e))

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


# =========================
# Entry Point
# =========================
if __name__ == "__main__":
    app = BtrfsParserGUI()
    app.mainloop()
