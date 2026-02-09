import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import sys
import re

# Import your existing parser
# Directory structure:
# ├── btrfs_parser.py
# └── btrfs_gui.py
import btrfs_parser


# =========================
# Output Formatting Helper
# =========================
def format_parser_output(text: str) -> str:
    """
    Fix concatenated BTRFS output lines by inserting newlines
    before known field labels.
    """
    fields = [
        "Label:",
        "UUID:",
        "Generation:",
        "Bytes used:",
        "Node size:",
        "Sector size:",
        "Devices:",
        "Chunk tree addr:",
        "Root tree addr:",
        "Checksum type:"
    ]

    for field in fields:
        text = re.sub(rf"(?<!\n)({re.escape(field)})", r"\n\1", text)

    return text


# =========================
# Stdout Redirector
# =========================
class StdoutRedirector:
    """
    Redirects stdout/stderr to Tkinter Text widget
    with output formatting
    """
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, text):
        formatted = format_parser_output(text)
        self.text_widget.insert(tk.END, formatted)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


# =========================
# Main GUI Application
# =========================
class BtrfsParserGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Btrfs Forensic Parser GUI")
        self.geometry("900x550")
        self.resizable(True, True)

        # Variables
        self.image_path = tk.StringVar()
        self.partition_offset = tk.StringVar(value="4198400s")
        self.output_format = tk.StringVar(value="console")
        self.output_file = tk.StringVar()
        self.info_only = tk.BooleanVar()
        self.verbose = tk.BooleanVar()

        self._build_ui()

    def _build_ui(self):
        # ===== Disk Image =====
        frame_img = tk.LabelFrame(self, text="Disk Image")
        frame_img.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_img, textvariable=self.image_path, width=80).pack(
            side="left", padx=5, pady=5
        )
        tk.Button(frame_img, text="Browse", command=self.browse_image).pack(
            side="left", padx=5
        )

        # ===== Parser Options =====
        frame_opts = tk.LabelFrame(self, text="Parser Options")
        frame_opts.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_opts, text="Partition Offset:").grid(row=0, column=0, sticky="w", padx=5)
        tk.Entry(frame_opts, textvariable=self.partition_offset, width=15).grid(
            row=0, column=1, padx=5
        )
        tk.Label(
            frame_opts,
            text="(e.g. 4198400s, 0x80280000, 2149580800)"
        ).grid(row=0, column=2, sticky="w")

        tk.Label(frame_opts, text="Output Format:").grid(row=1, column=0, sticky="w", padx=5)
        tk.OptionMenu(
            frame_opts,
            self.output_format,
            "console", "json", "csv", "tree"
        ).grid(row=1, column=1, sticky="w", padx=5)

        tk.Checkbutton(
            frame_opts,
            text="Info Only (superblock)",
            variable=self.info_only
        ).grid(row=2, column=0, sticky="w", padx=5, pady=2)

        tk.Checkbutton(
            frame_opts,
            text="Verbose",
            variable=self.verbose
        ).grid(row=2, column=1, sticky="w", padx=5, pady=2)

        # ===== Output File =====
        frame_out = tk.LabelFrame(self, text="Output File (Optional)")
        frame_out.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_out, textvariable=self.output_file, width=80).pack(
            side="left", padx=5, pady=5
        )
        tk.Button(frame_out, text="Browse", command=self.browse_output_file).pack(
            side="left", padx=5
        )

        # ===== Run Button =====
        tk.Button(
            self,
            text="Run Btrfs Parser",
            height=2,
            command=self.run_parser
        ).pack(pady=10)

        # ===== Output Console =====
        frame_console = tk.LabelFrame(self, text="Parser Output")
        frame_console.pack(fill="both", expand=True, padx=10, pady=5)

        self.output_console = scrolledtext.ScrolledText(
            frame_console,
            wrap=tk.WORD,
            font=("Consolas", 10)
        )
        self.output_console.pack(fill="both", expand=True)

    # =========================
    # GUI Actions
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
            title="Select Output File",
            defaultextension=".txt",
            filetypes=[
                ("JSON", "*.json"),
                ("CSV", "*.csv"),
                ("Text", "*.txt"),
                ("All Files", "*.*")
            ]
        )
        if path:
            self.output_file.set(path)

    def run_parser(self):
        if not self.image_path.get():
            messagebox.showerror("Error", "Please select a disk image.")
            return

        self.output_console.delete("1.0", tk.END)
        threading.Thread(target=self._run_parser_thread, daemon=True).start()

    def _run_parser_thread(self):
        args = [self.image_path.get()]

        if self.partition_offset.get():
            args.extend(["-p", self.partition_offset.get()])

        if self.output_format.get():
            args.extend(["-o", self.output_format.get()])

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
        except Exception as e:
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
