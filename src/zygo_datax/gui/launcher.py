"""Small desktop launcher that starts the zygo-dataX local web app."""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from zygo_datax.web.app import app


def _find_free_port(preferred: int = 8017) -> int:
    for port in [preferred, *range(8020, 8100)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free local port found between 8017 and 8099")


class ZygoDataXLauncher:
    def __init__(self, preferred_port: int = 8017) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.messagebox = messagebox
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title("zygo-dataX")
        self.root.geometry("640x360")
        self.root.minsize(560, 320)
        self.port = _find_free_port(preferred_port)
        self.url = f"http://127.0.0.1:{self.port}"
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        tk = self.tk
        ttk = self.ttk
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="zygo-dataX", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Zygo DATX analysis, wavefront reports, and Zemax export").pack(anchor="w", pady=(2, 14))
        self.status = tk.StringVar(value="Starting local web service...")
        ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.url_var = tk.StringVar(value=self.url)
        url_row = ttk.Frame(frame)
        url_row.pack(fill=tk.X, pady=(8, 12))
        ttk.Entry(url_row, textvariable=self.url_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(url_row, text="Open", command=self.open_browser).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(url_row, text="Copy", command=self.copy_url).pack(side=tk.LEFT, padx=(8, 0))
        button_row = ttk.Frame(frame)
        button_row.pack(fill=tk.X, pady=(2, 12))
        ttk.Button(button_row, text="Restart Service", command=self.restart).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Stop and Exit", command=self.close).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(frame, text="Runs are saved under the local runs folder next to the executable when possible.").pack(anchor="w")
        self.log = tk.Text(frame, height=7, wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log.insert("end", "Starting...\n")
        self.log.configure(state="disabled")

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self) -> None:
        os.environ.setdefault("MPLBACKEND", "Agg")
        os.environ.setdefault("ZYGO_DATAX_RUN_ROOT", str(Path.cwd() / "runs"))
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self.root.after(500, self._mark_started)

    def _mark_started(self) -> None:
        self.status.set("Local web service is running")
        self.append_log(f"Service URL: {self.url}")
        self.open_browser()

    def open_browser(self) -> None:
        webbrowser.open(self.url)

    def copy_url(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url)
        self.append_log("Copied URL to clipboard")

    def restart(self) -> None:
        self.append_log("Restarting service...")
        self.stop_server()
        time.sleep(0.3)
        self.start()

    def stop_server(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=3)
        self.server = None
        self.thread = None

    def close(self) -> None:
        self.stop_server()
        self.root.destroy()

    def run(self) -> None:
        try:
            self.start()
            self.root.mainloop()
        except Exception as exc:
            self.messagebox.showerror("zygo-dataX", str(exc))
            raise


def main() -> None:
    parser = argparse.ArgumentParser(prog="zygo-dataX-launcher")
    parser.add_argument("--port", type=int, default=8017, help="Preferred local port")
    args = parser.parse_args()
    ZygoDataXLauncher(preferred_port=args.port).run()


if __name__ == "__main__":
    main()
