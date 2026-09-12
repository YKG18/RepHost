import os
import re
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser

import customtkinter as ctk


# ============================================================
# Paths / Python package setup
# ============================================================

CLI_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CLI_DIR)
MAIN_PY = os.path.join(CLI_DIR, "main.py")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# Application configuration
# ============================================================

APP_TITLE = "RepHost"

# Light theme
BG = "#F5F5F7"
CARD_BG = "#FFFFFF"
TEXT = "#1D1D1F"
SECONDARY = "#6E6E73"

BLUE = "#007AFF"
BLUE_HOVER = "#006FE6"

RED = "#FF3B30"
GREEN = "#34C759"

# Dark theme
DARK_BG = "#0F1115"
DARK_CARD_BG = "#181B21"
DARK_CARD_BORDER = "#292D35"
DARK_INPUT_BG = "#22262E"
DARK_TEXT = "#F5F5F7"
DARK_SECONDARY = "#A1A1AA"

DARK_BLUE = "#0A84FF"
DARK_BLUE_HOVER = "#409CFF"

DARK_BUTTON = "#292D35"
DARK_BUTTON_HOVER = "#353A44"

# Terminal
TERMINAL_BG = "#111318"
TERMINAL_HEADER = "#191C22"
TERMINAL_TEXT = "#E5E5E5"

TERMINAL_INFO = "#8FD3FF"
TERMINAL_SUCCESS = "#65D98B"
TERMINAL_WARNING = "#FFD166"
TERMINAL_ERROR = "#FF6B6B"


class RepHostGUI:
    def __init__(self, root):
        self.root = root

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root.title(APP_TITLE)
        self.root.geometry("900x720")
        self.root.minsize(760, 600)
        self.root.configure(bg=BG)

        self.dark_mode = False

        self.process = None
        self.reader_thread = None
        self.running = False

        self.local_url = ""
        self.public_url = ""

        self._build_ui()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )

    # ========================================================
    # UI
    # ========================================================

    def _build_ui(self):
        self.main = ctk.CTkFrame(
            self.root,
            fg_color=BG,
            corner_radius=0
        )

        self.main.pack(
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        self.header = ctk.CTkFrame(
            self.main,
            fg_color="transparent"
        )

        self.header.pack(
            fill="x",
            padx=35,
            pady=(28, 20)
        )

        title_area = ctk.CTkFrame(
            self.header,
            fg_color="transparent"
        )

        title_area.pack(
            side="left",
            fill="x",
            expand=True
        )

        self.title_label = ctk.CTkLabel(
            title_area,
            text="RepHost",
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=32,
                weight="bold"
            )
        )

        self.title_label.pack(
            anchor="w"
        )

        self.subtitle_label = ctk.CTkLabel(
            title_area,
            text="Host GitHub projects locally and expose them securely.",
            text_color=SECONDARY,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12
            )
        )

        self.subtitle_label.pack(
            anchor="w",
            pady=(3, 0)
        )

        # ----------------------------------------------------
        # Theme switch
        # ----------------------------------------------------

        self.theme_switch = ctk.CTkSwitch(
            self.header,
            text="Dark mode",
            command=self.toggle_theme,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold"
            ),
            text_color=TEXT,
            fg_color="#D1D1D6",
            progress_color=BLUE,
            button_color="#FFFFFF",
            button_hover_color="#F2F2F7",
            width=48,
            height=24
        )

        self.theme_switch.pack(
            side="right",
            padx=(15, 0)
        )

        # ----------------------------------------------------
        # Repository card
        # ----------------------------------------------------

        repo_card = self._create_card(
            self.main
        )

        repo_card.pack(
            fill="x",
            padx=35,
            pady=(0, 14)
        )

        self.repo_title = ctk.CTkLabel(
            repo_card,
            text="GitHub Repository URL",
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12,
                weight="bold"
            )
        )

        self.repo_title.pack(
            anchor="w",
            padx=20,
            pady=(17, 8)
        )

        input_row = ctk.CTkFrame(
            repo_card,
            fg_color="transparent"
        )

        input_row.pack(
            fill="x",
            padx=20,
            pady=(0, 18)
        )

        self.repo_entry = ctk.CTkEntry(
            input_row,
            height=42,
            corner_radius=10,
            border_width=1,
            border_color="#E5E5EA",
            fg_color="#F2F2F7",
            text_color=TEXT,
            placeholder_text="https://github.com/user/project",
            placeholder_text_color=SECONDARY,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12
            )
        )

        self.repo_entry.pack(
            fill="x",
            expand=True
        )

        self.repo_entry.insert(
            0,
            "https://github.com/user/project"
        )

        # ----------------------------------------------------
        # Controls
        # ----------------------------------------------------

        controls = ctk.CTkFrame(
            self.main,
            fg_color="transparent"
        )

        controls.pack(
            fill="x",
            padx=35,
            pady=(0, 14)
        )

        self.host_button = ctk.CTkButton(
            controls,
            text="Host Repository",
            command=self.start_hosting,
            width=145,
            height=40,
            corner_radius=10,
            fg_color=BLUE,
            hover_color=BLUE_HOVER,
            text_color="white",
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold"
            ),
            cursor="hand2"
        )

        self.host_button.pack(
            side="left"
        )

        self.stop_button = ctk.CTkButton(
            controls,
            text="Stop",
            command=self.stop_hosting,
            width=90,
            height=40,
            corner_radius=10,
            fg_color="#E5E5EA",
            hover_color="#D1D1D6",
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold"
            ),
            cursor="hand2",
            state="disabled"
        )

        self.stop_button.pack(
            side="left",
            padx=(10, 0)
        )

        status_frame = ctk.CTkFrame(
            controls,
            fg_color="transparent"
        )

        status_frame.pack(
            side="right",
            padx=5
        )

        self.status_dot = ctk.CTkLabel(
            status_frame,
            text="●",
            text_color=SECONDARY,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12
            )
        )

        self.status_dot.pack(
            side="left",
            padx=(0, 5)
        )

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Ready",
            text_color=SECONDARY,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold"
            )
        )

        self.status_label.pack(
            side="left"
        )

        # ----------------------------------------------------
        # URLs
        # ----------------------------------------------------

        urls_card = self._create_card(
            self.main
        )

        urls_card.pack(
            fill="x",
            padx=35,
            pady=(0, 14)
        )

        self.endpoints_title = ctk.CTkLabel(
            urls_card,
            text="Endpoints",
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=13,
                weight="bold"
            )
        )

        self.endpoints_title.pack(
            anchor="w",
            padx=20,
            pady=(17, 14)
        )

        self.local_row = self._create_url_row(
            urls_card,
            "Localhost"
        )

        self.public_row = self._create_url_row(
            urls_card,
            "Public Tunnel"
        )

        self._set_url_row(
            self.local_row,
            ""
        )

        self._set_url_row(
            self.public_row,
            ""
        )

        # ----------------------------------------------------
        # Terminal
        # ----------------------------------------------------

        terminal_card = self._create_terminal_card(
            self.main
        )

        terminal_card.pack(
            fill="both",
            expand=True,
            padx=35,
            pady=(0, 28)
        )

        self.write_terminal(
            "[RepHost] Ready.\n",
            "info"
        )

    # ========================================================
    # Card helpers
    # ========================================================

    def _create_card(self, parent):
        card_color = (
            DARK_CARD_BG
            if self.dark_mode
            else CARD_BG
        )

        border_color = (
            DARK_CARD_BORDER
            if self.dark_mode
            else "#E5E5EA"
        )

        return ctk.CTkFrame(
            parent,
            fg_color=card_color,
            border_width=1,
            border_color=border_color,
            corner_radius=14
        )

    def _create_terminal_card(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=TERMINAL_BG,
            border_width=1,
            border_color=(
                DARK_CARD_BORDER
                if self.dark_mode
                else "#E5E5EA"
            ),
            corner_radius=14
        )

        terminal_header = ctk.CTkFrame(
            card,
            fg_color=TERMINAL_HEADER,
            height=38,
            corner_radius=0
        )

        terminal_header.pack(
            fill="x"
        )

        terminal_header.pack_propagate(False)

        dots = ctk.CTkFrame(
            terminal_header,
            fg_color="transparent"
        )

        dots.pack(
            side="left",
            padx=12
        )

        for color in (
            "#FF5F57",
            "#FEBC2E",
            "#28C840"
        ):
            dot = ctk.CTkLabel(
                dots,
                text="●",
                text_color=color,
                font=ctk.CTkFont(
                    family="Segoe UI",
                    size=11
                ),
                width=10
            )

            dot.pack(
                side="left",
                padx=2
            )

        terminal_title = ctk.CTkLabel(
            terminal_header,
            text="RepHost Terminal",
            text_color="#BFBFBF",
            font=ctk.CTkFont(
                family="Segoe UI",
                size=10,
                weight="bold"
            )
        )

        terminal_title.pack(
            side="left",
            padx=7
        )

        terminal_body = ctk.CTkFrame(
            card,
            fg_color=TERMINAL_BG,
            corner_radius=0
        )

        terminal_body.pack(
            fill="both",
            expand=True,
            padx=1,
            pady=1
        )

        self.terminal = ctk.CTkTextbox(
            terminal_body,
            fg_color=TERMINAL_BG,
            text_color=TERMINAL_TEXT,
            border_width=0,
            corner_radius=0,
            wrap="word",
            font=ctk.CTkFont(
                family="Cascadia Mono",
                size=11
            ),
            activate_scrollbars=True
        )

        self.terminal.pack(
            fill="both",
            expand=True,
            padx=7,
            pady=7
        )

        self.terminal.tag_config(
            "normal",
            foreground=TERMINAL_TEXT
        )

        self.terminal.tag_config(
            "info",
            foreground=TERMINAL_INFO
        )

        self.terminal.tag_config(
            "success",
            foreground=TERMINAL_SUCCESS
        )

        self.terminal.tag_config(
            "warning",
            foreground=TERMINAL_WARNING
        )

        self.terminal.tag_config(
            "error",
            foreground=TERMINAL_ERROR
        )

        return card

    def _create_url_row(self, parent, title):
        row = ctk.CTkFrame(
            parent,
            fg_color="transparent"
        )

        row.pack(
            fill="x",
            padx=20,
            pady=(0, 12)
        )

        left = ctk.CTkFrame(
            row,
            fg_color="transparent"
        )

        left.pack(
            side="left",
            fill="x",
            expand=True
        )

        title_label = ctk.CTkLabel(
            left,
            text=title,
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold"
            )
        )

        title_label.pack(
            anchor="w"
        )

        url_label = ctk.CTkLabel(
            left,
            text="Not available",
            text_color=SECONDARY,
            font=ctk.CTkFont(
                family="Cascadia Mono",
                size=11
            ),
            anchor="w"
        )

        url_label.pack(
            anchor="w",
            pady=(3, 0)
        )

        buttons = ctk.CTkFrame(
            row,
            fg_color="transparent"
        )

        buttons.pack(
            side="right"
        )

        copy_button = ctk.CTkButton(
            buttons,
            text="Copy",
            command=lambda: self.copy_url(url_label),
            width=62,
            height=30,
            corner_radius=8,
            fg_color="#F2F2F7",
            hover_color="#D1D1D6",
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=10,
                weight="bold"
            ),
            cursor="hand2",
            state="disabled"
        )

        copy_button.pack(
            side="left",
            padx=(0, 6)
        )

        open_button = ctk.CTkButton(
            buttons,
            text="Open",
            command=lambda: self.open_url(url_label),
            width=62,
            height=30,
            corner_radius=8,
            fg_color="#F2F2F7",
            hover_color="#D1D1D6",
            text_color=TEXT,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=10,
                weight="bold"
            ),
            cursor="hand2",
            state="disabled"
        )

        open_button.pack(
            side="left"
        )

        return {
            "url": url_label,
            "copy": copy_button,
            "open": open_button,
            "title": title_label
        }

    def _set_url_row(self, row, url):
        if url:
            row["url"].configure(
                text=url,
                text_color=(
                    DARK_BLUE
                    if self.dark_mode
                    else BLUE
                )
            )

            row["copy"].configure(
                state="normal"
            )

            row["open"].configure(
                state="normal"
            )

        else:
            row["url"].configure(
                text="Not available",
                text_color=(
                    DARK_SECONDARY
                    if self.dark_mode
                    else SECONDARY
                )
            )

            row["copy"].configure(
                state="disabled"
            )

            row["open"].configure(
                state="disabled"
            )

    # ========================================================
    # Theme
    # ========================================================

    def toggle_theme(self):
        self.dark_mode = bool(
            self.theme_switch.get()
        )

        if self.dark_mode:
            ctk.set_appearance_mode("dark")
            self._apply_dark_theme()
        else:
            ctk.set_appearance_mode("light")
            self._apply_light_theme()

    def _apply_dark_theme(self):
        self.root.configure(
            bg=DARK_BG
        )

        self.main.configure(
            fg_color=DARK_BG
        )

        self.title_label.configure(
            text_color=DARK_TEXT
        )

        self.subtitle_label.configure(
            text_color=DARK_SECONDARY
        )

        self.repo_title.configure(
            text_color=DARK_TEXT
        )

        self.endpoints_title.configure(
            text_color=DARK_TEXT
        )

        self.theme_switch.configure(
            text_color=DARK_TEXT,
            fg_color="#3A3F48",
            progress_color=DARK_BLUE,
            button_color="#F5F5F7",
            button_hover_color="#FFFFFF"
        )

        self.repo_entry.configure(
            fg_color=DARK_INPUT_BG,
            border_color=DARK_CARD_BORDER,
            text_color=DARK_TEXT,
            placeholder_text_color=DARK_SECONDARY
        )

        self.stop_button.configure(
            fg_color=DARK_BUTTON,
            hover_color=DARK_BUTTON_HOVER,
            text_color=DARK_TEXT
        )

        self.host_button.configure(
            fg_color=DARK_BLUE,
            hover_color=DARK_BLUE_HOVER
        )

        for row in (
            self.local_row,
            self.public_row
        ):
            row["title"].configure(
                text_color=DARK_TEXT
            )

            row["copy"].configure(
                fg_color=DARK_BUTTON,
                hover_color=DARK_BUTTON_HOVER,
                text_color=DARK_TEXT
            )

            row["open"].configure(
                fg_color=DARK_BUTTON,
                hover_color=DARK_BUTTON_HOVER,
                text_color=DARK_TEXT
            )

        self._set_url_row(
            self.local_row,
            self.local_url
        )

        self._set_url_row(
            self.public_row,
            self.public_url
        )

    def _apply_light_theme(self):
        self.root.configure(
            bg=BG
        )

        self.main.configure(
            fg_color=BG
        )

        self.title_label.configure(
            text_color=TEXT
        )

        self.subtitle_label.configure(
            text_color=SECONDARY
        )

        self.repo_title.configure(
            text_color=TEXT
        )

        self.endpoints_title.configure(
            text_color=TEXT
        )

        self.theme_switch.configure(
            text_color=TEXT,
            fg_color="#D1D1D6",
            progress_color=BLUE,
            button_color="#FFFFFF",
            button_hover_color="#F2F2F7"
        )

        self.repo_entry.configure(
            fg_color="#F2F2F7",
            border_color="#E5E5EA",
            text_color=TEXT,
            placeholder_text_color=SECONDARY
        )

        self.stop_button.configure(
            fg_color="#E5E5EA",
            hover_color="#D1D1D6",
            text_color=TEXT
        )

        self.host_button.configure(
            fg_color=BLUE,
            hover_color=BLUE_HOVER
        )

        for row in (
            self.local_row,
            self.public_row
        ):
            row["title"].configure(
                text_color=TEXT
            )

            row["copy"].configure(
                fg_color="#F2F2F7",
                hover_color="#D1D1D6",
                text_color=TEXT
            )

            row["open"].configure(
                fg_color="#F2F2F7",
                hover_color="#D1D1D6",
                text_color=TEXT
            )

        self._set_url_row(
            self.local_row,
            self.local_url
        )

        self._set_url_row(
            self.public_row,
            self.public_url
        )

    # ========================================================
    # Terminal
    # ========================================================

    def write_terminal(self, text, tag="normal"):
        self.terminal.configure(
            state="normal"
        )

        self.terminal.insert(
            "end",
            text,
            tag
        )

        self.terminal.see(
            "end"
        )

        self.terminal.configure(
            state="disabled"
        )

    def classify_log(self, line):
        lower = line.lower()

        if any(
            word in lower
            for word in (
                "traceback",
                "exception",
                "error",
                "failed",
                "[-]"
            )
        ):
            return "error"

        if any(
            word in lower
            for word in (
                "warning",
                "warn",
                "waiting"
            )
        ):
            return "warning"

        if any(
            word in lower
            for word in (
                "[+]",
                "health check passed",
                "cloudflare tunnel:",
                "repository cloned",
                "docker available"
            )
        ):
            return "success"

        if any(
            word in lower
            for word in (
                "[rephost]",
                "->",
                "cloning",
                "detecting",
                "checking",
                "starting"
            )
        ):
            return "info"

        return "normal"

    # ========================================================
    # Start hosting
    # ========================================================

    def start_hosting(self):
        if self.running:
            return

        repository = self.repo_entry.get().strip()

        if not repository:
            messagebox.showwarning(
                APP_TITLE,
                "Please enter a GitHub repository URL."
            )
            return

        if not (
            repository.startswith("https://")
            or repository.startswith("http://")
            or repository.startswith("git@")
        ):
            messagebox.showwarning(
                APP_TITLE,
                "Please enter a valid GitHub repository URL."
            )
            return

        if not os.path.isfile(MAIN_PY):
            messagebox.showerror(
                APP_TITLE,
                f"Could not find main.py:\n\n{MAIN_PY}"
            )
            return

        self.running = True

        self.local_url = ""
        self.public_url = ""

        self._set_url_row(
            self.local_row,
            ""
        )

        self._set_url_row(
            self.public_row,
            ""
        )

        self.host_button.configure(
            state="disabled"
        )

        self.stop_button.configure(
            state="normal"
        )

        self.repo_entry.configure(
            state="disabled"
        )

        self.status_label.configure(
            text="Starting…",
            text_color=(
                DARK_BLUE
                if self.dark_mode
                else BLUE
            )
        )

        self.status_dot.configure(
            text_color=(
                DARK_BLUE
                if self.dark_mode
                else BLUE
            )
        )

        self.write_terminal(
            "\n[RepHost] Starting hosting process...\n",
            "info"
        )

        # ----------------------------------------------------
        # Environment
        # ----------------------------------------------------

        env = os.environ.copy()

        existing_pythonpath = env.get(
            "PYTHONPATH",
            ""
        )

        if existing_pythonpath:
            paths = existing_pythonpath.split(
                os.pathsep
            )

            if PROJECT_ROOT not in paths:
                env["PYTHONPATH"] = (
                    PROJECT_ROOT
                    + os.pathsep
                    + existing_pythonpath
                )
        else:
            env["PYTHONPATH"] = PROJECT_ROOT

        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        # ----------------------------------------------------
        # Start main.py
        # ----------------------------------------------------

        command = [
            sys.executable,
            "-u",
            MAIN_PY,
            repository
        ]

        try:
            creationflags = 0

            if os.name == "nt":
                creationflags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                )

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                creationflags=creationflags,
                cwd=PROJECT_ROOT,
                env=env
            )

        except Exception as exc:
            self.running = False

            self.write_terminal(
                f"[ERROR] Could not start main.py: {exc}\n",
                "error"
            )

            self._reset_controls()
            return

        # ----------------------------------------------------
        # Background log reader
        # ----------------------------------------------------

        self.reader_thread = threading.Thread(
            target=self._read_process_output,
            daemon=True
        )

        self.reader_thread.start()

    # ========================================================
    # Read main.py output
    # ========================================================

    def _read_process_output(self):
        process = self.process

        if process is None:
            return

        try:
            for line in iter(
                process.stdout.readline,
                ""
            ):
                if not line:
                    break

                self.root.after(
                    0,
                    self._handle_log_line,
                    line
                )

        except Exception as exc:
            self.root.after(
                0,
                self._handle_log_line,
                f"[GUI] Log reader error: {exc}\n"
            )

        finally:
            try:
                return_code = process.wait()
            except Exception:
                return_code = None

            self.root.after(
                0,
                self._process_finished,
                return_code
            )

    # ========================================================
    # Process log
    # ========================================================

    def _handle_log_line(self, line):
        tag = self.classify_log(line)

        self.write_terminal(
            line,
            tag
        )

        # ----------------------------------------------------
        # Localhost
        # ----------------------------------------------------

        local_matches = re.findall(
            r"https?://127\.0\.0\.1:\d+",
            line
        )

        if local_matches:
            self.local_url = local_matches[-1]

            self._set_url_row(
                self.local_row,
                self.local_url
            )

            self.status_label.configure(
                text="Application running",
                text_color=GREEN
            )

            self.status_dot.configure(
                text_color=GREEN
            )

        # ----------------------------------------------------
        # Cloudflare
        # ----------------------------------------------------

        cloudflare_matches = re.findall(
            r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",
            line
        )

        if cloudflare_matches:
            self.public_url = (
                cloudflare_matches[-1]
            )

            self._set_url_row(
                self.public_row,
                self.public_url
            )

            self.status_label.configure(
                text="Ready",
                text_color=GREEN
            )

            self.status_dot.configure(
                text_color=GREEN
            )

        # ----------------------------------------------------
        # Health
        # ----------------------------------------------------

        if (
            "health check passed" in line.lower()
            or "[health]" in line.lower()
        ):
            self.status_label.configure(
                text="Healthy",
                text_color=GREEN
            )

            self.status_dot.configure(
                text_color=GREEN
            )

        # ----------------------------------------------------
        # Errors
        # ----------------------------------------------------

        if (
            "[-]" in line
            or "error" in line.lower()
            or "failed" in line.lower()
            or "traceback" in line.lower()
        ):
            self.status_label.configure(
                text="Error",
                text_color=RED
            )

            self.status_dot.configure(
                text_color=RED
            )

    # ========================================================
    # Stop hosting
    # ========================================================

    def stop_hosting(self):
        process = self.process

        if process is None:
            return

        if process.poll() is not None:
            return

        self.status_label.configure(
            text="Stopping…",
            text_color=(
                DARK_SECONDARY
                if self.dark_mode
                else SECONDARY
            )
        )

        self.status_dot.configure(
            text_color=(
                DARK_SECONDARY
                if self.dark_mode
                else SECONDARY
            )
        )

        self.write_terminal(
            "\n[RepHost] Stopping hosting process...\n",
            "warning"
        )

        threading.Thread(
            target=self._stop_process,
            args=(process,),
            daemon=True
        ).start()

    def _stop_process(self, process):
        try:
            if process.poll() is not None:
                return

            if os.name == "nt":
                try:
                    process.send_signal(
                        signal.CTRL_BREAK_EVENT
                    )
                except Exception:
                    process.terminate()

            else:
                try:
                    process.send_signal(
                        signal.SIGINT
                    )
                except Exception:
                    process.terminate()

            try:
                process.wait(
                    timeout=10
                )

            except subprocess.TimeoutExpired:
                process.terminate()

                try:
                    process.wait(
                        timeout=3
                    )
                except subprocess.TimeoutExpired:
                    process.kill()

        except Exception as exc:
            self.root.after(
                0,
                self._handle_log_line,
                f"[GUI] Stop error: {exc}\n"
            )

    # ========================================================
    # Process finished
    # ========================================================

    def _process_finished(self, return_code):
        self.process = None
        self.running = False

        current_status = self.status_label.cget(
            "text"
        )

        if current_status == "Stopping…":
            color = (
                DARK_SECONDARY
                if self.dark_mode
                else SECONDARY
            )

            self.status_label.configure(
                text="Stopped",
                text_color=color
            )

            self.status_dot.configure(
                text_color=color
            )

        elif return_code == 0:
            color = (
                DARK_SECONDARY
                if self.dark_mode
                else SECONDARY
            )

            self.status_label.configure(
                text="Stopped",
                text_color=color
            )

            self.status_dot.configure(
                text_color=color
            )

        elif return_code is None:
            color = (
                DARK_SECONDARY
                if self.dark_mode
                else SECONDARY
            )

            self.status_label.configure(
                text="Stopped",
                text_color=color
            )

            self.status_dot.configure(
                text_color=color
            )

        else:
            self.status_label.configure(
                text="Exited",
                text_color=RED
            )

            self.status_dot.configure(
                text_color=RED
            )

        self._reset_controls(
            keep_urls=True
        )

    def _reset_controls(self, keep_urls=False):
        self.running = False

        self.host_button.configure(
            state="normal"
        )

        self.stop_button.configure(
            state="disabled"
        )

        self.repo_entry.configure(
            state="normal"
        )

        if not keep_urls:
            self._set_url_row(
                self.local_row,
                ""
            )

            self._set_url_row(
                self.public_row,
                ""
            )

    # ========================================================
    # URL actions
    # ========================================================

    def copy_url(self, label):
        url = label.cget(
            "text"
        )

        if not url or url == "Not available":
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.root.update()

        self.status_label.configure(
            text="Copied",
            text_color=GREEN
        )

        self.status_dot.configure(
            text_color=GREEN
        )

    def open_url(self, label):
        url = label.cget(
            "text"
        )

        if not url or url == "Not available":
            return

        try:
            webbrowser.open(
                url
            )

        except Exception as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Could not open URL:\n{exc}"
            )

    # ========================================================
    # Closing
    # ========================================================

    def on_close(self):
        if (
            self.process is not None
            and self.process.poll() is None
        ):
            answer = messagebox.askyesno(
                APP_TITLE,
                "A repository is currently being hosted.\n\n"
                "Stop it and exit RepHost?"
            )

            if not answer:
                return

            self.stop_hosting()

            self.root.after(
                250,
                self._wait_for_close
            )

            return

        self.root.destroy()

    def _wait_for_close(self):
        if (
            self.process is not None
            and self.process.poll() is None
        ):
            self.root.after(
                250,
                self._wait_for_close
            )

        else:
            self.root.destroy()


# ============================================================
# Entry point
# ============================================================

def main():
    root = ctk.CTk()

    app = RepHostGUI(root)

    root.mainloop()


if __name__ == "__main__":
    main()
