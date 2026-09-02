from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox


# ============================================================
# DPI
# ============================================================

def enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)  # PER_MONITOR_AWARE_V2
        )
        return
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


enable_windows_dpi_awareness()


def _application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


BASE_DIR = _application_root()
TO_UPLOAD = BASE_DIR / "ToUpload"
UPLOADED = BASE_DIR / "Uploaded"
LOGS = BASE_DIR / "Logs"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".avi",
}

sys.path.insert(0, str(BASE_DIR))

try:
    import config  # type: ignore

    DEFAULT_VISIBILITY = getattr(
        config,
        "UPLOAD_VISIBILITY",
        "public",
    )

    DEFAULT_UPLOAD_ENABLED = bool(
        getattr(
            config,
            "ENABLE_YOUTUBE_UPLOAD",
            True,
        )
    )
except Exception:
    DEFAULT_VISIBILITY = "public"
    DEFAULT_UPLOAD_ENABLED = True


# ============================================================
# THEME
# ============================================================

BG = "#0A0F15"
CARD = "#111923"
CARD_SOFT = "#151F2B"
CARD_HOVER = "#1A2735"
BORDER = "#263545"

TEXT = "#F6F8FB"
MUTED = "#91A1B4"

ACCENT = "#FF3347"
ACCENT_HOVER = "#E92F42"

GREEN = "#35D07F"
GREEN_BG = "#113421"

YELLOW = "#F7B955"
YELLOW_BG = "#3A2A10"

RED = "#FF6879"
RED_BG = "#3B171D"

BLUE = "#78B7FF"
BLUE_BG = "#132A42"


class YouTubeBotGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("VibeRush YouTube Bot")
        self.root.geometry("1180x790")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG)

        self._apply_tk_dpi_scaling()
        self._configure_styles()

        self.process: subprocess.Popen | None = None
        self.reader_thread: threading.Thread | None = None

        self.output_buffer: deque[str] = deque()
        self.output_lock = threading.Lock()

        self.current_video = 0
        self.total_videos = 0
        self.run_had_error = False

        self.count_var = tk.StringVar(value="1")
        self.visibility_var = tk.StringVar(
            value=DEFAULT_VISIBILITY
        )
        self.upload_enabled_var = tk.BooleanVar(
            value=DEFAULT_UPLOAD_ENABLED
        )
        self.retry_interrupted_upload_var = tk.BooleanVar(
            value=False
        )

        self.available_var = tk.StringVar(value="0")
        self.pending_var = tk.StringVar(value="None")
        self.stage_var = tk.StringVar(value="Ready")
        self.progress_text_var = tk.StringVar(
            value="Waiting to start"
        )
        self.run_status_var = tk.StringVar(value="IDLE")

        self.unfinished_run: dict | None = None
        self.resume_choice: bool | None = None

        self._build_ui()
        self.refresh_state(show_feedback=False)
        self._poll_output()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close,
        )

    # ========================================================
    # DPI / STYLES
    # ========================================================

    def _apply_tk_dpi_scaling(self) -> None:
        if os.name != "nt":
            return

        try:
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)

            if dpi:
                self.root.tk.call(
                    "tk",
                    "scaling",
                    dpi / 72.0,
                )
        except Exception:
            pass

    def _configure_styles(self) -> None:
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            ".",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 10),
        )

        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="white",
            borderwidth=0,
            padding=(18, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", ACCENT_HOVER),
                ("pressed", ACCENT_HOVER),
                ("disabled", "#55222B"),
            ],
            foreground=[
                ("disabled", "#9B7F84"),
            ],
        )

        style.configure(
            "Secondary.TButton",
            background=CARD_SOFT,
            foreground=TEXT,
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(12, 8),
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("active", CARD_HOVER),
                ("pressed", CARD_HOVER),
            ],
            foreground=[
                ("active", TEXT),
                ("pressed", TEXT),
            ],
            bordercolor=[
                ("active", "#37506A"),
            ],
        )

        style.configure(
            "Danger.TButton",
            background="#31171C",
            foreground="#FF9CA7",
            borderwidth=0,
            padding=(16, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Danger.TButton",
            background=[
                ("active", "#482027"),
                ("pressed", "#482027"),
                ("disabled", "#25171A"),
            ],
            foreground=[
                ("disabled", "#775B61"),
            ],
        )

        style.configure(
            "TEntry",
            fieldbackground=CARD_SOFT,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=7,
        )
        style.map(
            "TEntry",
            fieldbackground=[
                ("focus", "#172332"),
            ],
            bordercolor=[
                ("focus", "#49637F"),
            ],
        )

        style.configure(
            "TCombobox",
            fieldbackground=CARD_SOFT,
            background=CARD_SOFT,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", CARD_SOFT),
                ("active", CARD_HOVER),
            ],
            background=[
                ("readonly", CARD_SOFT),
                ("active", CARD_HOVER),
            ],
            foreground=[
                ("readonly", TEXT),
                ("active", TEXT),
            ],
            arrowcolor=[
                ("active", TEXT),
            ],
        )

        style.configure(
            "TCheckbutton",
            background=CARD,
            foreground=TEXT,
            padding=3,
        )
        style.map(
            "TCheckbutton",
            background=[
                ("active", CARD),
            ],
            foreground=[
                ("active", TEXT),
            ],
        )

        style.configure(
            "Accent.Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor="#202C39",
            bordercolor="#202C39",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )

        # Dark scrollbar - avoids white hover/active state.
        style.configure(
            "Dark.Vertical.TScrollbar",
            gripcount=0,
            background="#263443",
            troughcolor="#101720",
            bordercolor="#101720",
            lightcolor="#263443",
            darkcolor="#263443",
            arrowcolor=MUTED,
            relief="flat",
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[
                ("active", "#34495E"),
                ("pressed", "#3B536A"),
            ],
            arrowcolor=[
                ("active", TEXT),
                ("pressed", TEXT),
            ],
            troughcolor=[
                ("active", "#101720"),
            ],
        )

        style.configure(
            "Dark.TNotebook",
            background=CARD,
            borderwidth=0,
        )
        style.configure(
            "Dark.TNotebook.Tab",
            background=CARD_SOFT,
            foreground=MUTED,
            padding=(14, 8),
            borderwidth=0,
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[
                ("selected", CARD_HOVER),
                ("active", "#182534"),
            ],
            foreground=[
                ("selected", TEXT),
                ("active", TEXT),
            ],
        )

    # ========================================================
    # BUFFER
    # ========================================================

    def _buffer_put(self, text: str) -> None:
        with self.output_lock:
            self.output_buffer.append(text)

    def _buffer_get(self) -> str | None:
        with self.output_lock:
            if not self.output_buffer:
                return None

            return self.output_buffer.popleft()

    # ========================================================
    # UI
    # ========================================================

    def _build_ui(self) -> None:
        shell = tk.Frame(
            self.root,
            bg=BG,
        )
        shell.pack(
            fill="both",
            expand=True,
            padx=22,
            pady=18,
        )

        # Header
        header = tk.Frame(
            shell,
            bg=BG,
        )
        header.pack(
            fill="x",
            pady=(0, 16),
        )

        left_header = tk.Frame(
            header,
            bg=BG,
        )
        left_header.pack(side="left")

        tk.Label(
            left_header,
            text="VibeRush YouTube Bot",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 25, "bold"),
        ).pack(anchor="w")

        tk.Label(
            left_header,
            text=(
                "Local AI analysis  •  SQLite queue  •  "
                "verified YouTube publishing"
            ),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(
            anchor="w",
            pady=(4, 0),
        )

        self.status_badge = tk.Label(
            header,
            textvariable=self.run_status_var,
            bg="#1A2530",
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
        )
        self.status_badge.pack(
            side="right",
            anchor="n",
        )

        # Overview
        overview = tk.Frame(
            shell,
            bg=BG,
        )
        overview.pack(
            fill="x",
            pady=(0, 12),
        )

        queue_card = self._card(
            overview
        )
        queue_card.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 6),
        )

        qhead = tk.Frame(
            queue_card,
            bg=CARD,
        )
        qhead.pack(
            fill="x",
            padx=16,
            pady=(13, 5),
        )

        tk.Label(
            qhead,
            text="QUEUE",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        self.refresh_button = ttk.Button(
            qhead,
            text="Refresh",
            style="Secondary.TButton",
            command=lambda:
                self.refresh_state(
                    show_feedback=True
                ),
        )
        self.refresh_button.pack(
            side="right",
        )

        qmetrics = tk.Frame(
            queue_card,
            bg=CARD,
        )
        qmetrics.pack(
            fill="x",
            padx=16,
            pady=(3, 15),
        )

        self._metric(
            qmetrics,
            "New videos",
            self.available_var,
        ).pack(
            side="left",
            fill="x",
            expand=True,
        )

        self._metric(
            qmetrics,
            "Unfinished run",
            self.pending_var,
            value_font=("Segoe UI", 13, "bold"),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(18, 0),
        )

        status_card = self._card(
            overview
        )
        status_card.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(6, 0),
        )

        tk.Label(
            status_card,
            text="CURRENT STATUS",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(
            anchor="w",
            padx=16,
            pady=(14, 4),
        )

        tk.Label(
            status_card,
            textvariable=self.stage_var,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(
            anchor="w",
            padx=16,
        )

        tk.Label(
            status_card,
            textvariable=self.progress_text_var,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(
            anchor="w",
            padx=16,
            pady=(3, 15),
        )

        # Body
        body = tk.Frame(
            shell,
            bg=BG,
        )
        body.pack(
            fill="both",
            expand=True,
        )

        # Settings
        settings_card = self._card(
            body,
            width=320,
        )
        settings_card.pack(
            side="left",
            fill="y",
            padx=(0, 8),
        )
        settings_card.pack_propagate(False)

        tk.Label(
            settings_card,
            text="Run settings",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(
            anchor="w",
            padx=17,
            pady=(17, 14),
        )

        settings_content = tk.Frame(
            settings_card,
            bg=CARD,
        )
        settings_content.pack(
            fill="both",
            expand=True,
            padx=17,
            pady=(0, 14),
        )

        self._field_label(
            settings_content,
            "Videos to process",
        ).pack(
            anchor="w",
            pady=(0, 5),
        )

        ttk.Entry(
            settings_content,
            textvariable=self.count_var,
        ).pack(
            fill="x",
            pady=(0, 14),
        )

        self._field_label(
            settings_content,
            "Visibility",
        ).pack(
            anchor="w",
            pady=(0, 5),
        )

        ttk.Combobox(
            settings_content,
            textvariable=self.visibility_var,
            values=(
                "public",
                "private",
                "unlisted",
            ),
            state="readonly",
        ).pack(
            fill="x",
            pady=(0, 14),
        )

        ttk.Checkbutton(
            settings_content,
            text="Upload to YouTube",
            variable=self.upload_enabled_var,
        ).pack(
            anchor="w",
            pady=3,
        )

        ttk.Checkbutton(
            settings_content,
            text="Retry interrupted upload",
            variable=self.retry_interrupted_upload_var,
        ).pack(
            anchor="w",
            pady=3,
        )

        tk.Label(
            settings_content,
            text=(
                "Resume is chosen in a confirmation window "
                "when an unfinished run exists."
            ),
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=270,
            font=("Segoe UI", 9),
        ).pack(
            anchor="w",
            pady=(8, 14),
        )

        self.start_button = ttk.Button(
            settings_content,
            text="START BOT",
            style="Primary.TButton",
            command=self.start_bot,
        )
        self.start_button.pack(
            fill="x",
            pady=(0, 8),
        )

        self.stop_button = ttk.Button(
            settings_content,
            text="STOP",
            style="Danger.TButton",
            command=self.stop_bot,
            state="disabled",
        )
        self.stop_button.pack(
            fill="x",
        )

        # Folder buttons stay inside the frame using a dedicated footer.
        folder_footer = tk.Frame(
            settings_card,
            bg=CARD,
        )
        folder_footer.pack(
            side="bottom",
            fill="x",
            padx=17,
            pady=(0, 17),
        )

        for label, folder in (
            ("Open ToUpload", TO_UPLOAD),
            ("Open Uploaded", UPLOADED),
            ("Open Logs", LOGS),
        ):
            ttk.Button(
                folder_footer,
                text=label,
                style="Secondary.TButton",
                command=lambda p=folder:
                    self.open_folder(p),
            ).pack(
                fill="x",
                pady=3,
            )

        # Activity
        right = self._card(
            body
        )
        right.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(8, 0),
        )

        activity_header = tk.Frame(
            right,
            bg=CARD,
        )
        activity_header.pack(
            fill="x",
            padx=15,
            pady=(14, 8),
        )

        tk.Label(
            activity_header,
            text="Activity",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        ttk.Button(
            activity_header,
            text="Clear",
            style="Secondary.TButton",
            command=self.clear_activity,
        ).pack(side="right")

        self.progress = ttk.Progressbar(
            right,
            mode="determinate",
            maximum=100,
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress.pack(
            fill="x",
            padx=15,
            pady=(0, 10),
        )

        notebook = ttk.Notebook(
            right,
            style="Dark.TNotebook",
        )
        notebook.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=(0, 15),
        )

        activity_tab = tk.Frame(
            notebook,
            bg=CARD_SOFT,
        )
        details_tab = tk.Frame(
            notebook,
            bg=CARD_SOFT,
        )

        notebook.add(
            activity_tab,
            text="Activity",
        )
        notebook.add(
            details_tab,
            text="Details",
        )

        self.activity = tk.Text(
            activity_tab,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 10),
            background=CARD_SOFT,
            foreground=TEXT,
            relief="flat",
            padx=13,
            pady=10,
            spacing1=4,
            spacing3=6,
            cursor="arrow",
        )
        self.activity.pack(
            side="left",
            fill="both",
            expand=True,
        )

        activity_scroll = ttk.Scrollbar(
            activity_tab,
            orient="vertical",
            style="Dark.Vertical.TScrollbar",
            command=self.activity.yview,
        )
        activity_scroll.pack(
            side="right",
            fill="y",
        )
        self.activity.configure(
            yscrollcommand=activity_scroll.set
        )

        self.activity.tag_configure(
            "time",
            foreground=MUTED,
            font=("Segoe UI", 9),
        )
        self.activity.tag_configure(
            "info",
            foreground=TEXT,
        )
        self.activity.tag_configure(
            "success",
            foreground=GREEN,
            font=("Segoe UI", 10, "bold"),
        )
        self.activity.tag_configure(
            "warning",
            foreground=YELLOW,
            font=("Segoe UI", 10, "bold"),
        )
        self.activity.tag_configure(
            "error",
            foreground=RED,
            font=("Segoe UI", 10, "bold"),
        )
        self.activity.tag_configure(
            "accent",
            foreground=BLUE,
            font=("Segoe UI", 10, "bold"),
        )

        self.details = tk.Text(
            details_tab,
            wrap="word",
            state="disabled",
            font=("Cascadia Mono", 9),
            background="#0B1118",
            foreground="#C7D3DF",
            relief="flat",
            padx=12,
            pady=10,
            insertbackground=TEXT,
            selectbackground="#26384C",
        )
        self.details.pack(
            side="left",
            fill="both",
            expand=True,
        )

        details_scroll = ttk.Scrollbar(
            details_tab,
            orient="vertical",
            style="Dark.Vertical.TScrollbar",
            command=self.details.yview,
        )
        details_scroll.pack(
            side="right",
            fill="y",
        )
        self.details.configure(
            yscrollcommand=details_scroll.set
        )

    def _card(
        self,
        parent,
        width: int | None = None,
    ) -> tk.Frame:
        kwargs = {}

        if width is not None:
            kwargs["width"] = width

        return tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            **kwargs,
        )

    def _metric(
        self,
        parent,
        title: str,
        variable: tk.StringVar,
        value_font=("Segoe UI", 18, "bold"),
    ) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=CARD,
        )

        tk.Label(
            frame,
            text=title,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        tk.Label(
            frame,
            textvariable=variable,
            bg=CARD,
            fg=TEXT,
            font=value_font,
        ).pack(
            anchor="w",
            pady=(2, 0),
        )

        return frame

    def _field_label(
        self,
        parent,
        text: str,
    ) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )

    # ========================================================
    # STATE / REFRESH
    # ========================================================

    def refresh_state(
        self,
        show_feedback: bool = True,
    ) -> None:
        TO_UPLOAD.mkdir(
            parents=True,
            exist_ok=True,
        )

        count = sum(
            1
            for path in TO_UPLOAD.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                in VIDEO_EXTENSIONS
            )
        )

        self.available_var.set(
            str(count)
        )

        self.unfinished_run = None

        try:
            from database.db import (
                init_db,
                find_unfinished_run,
                queue_counts,
            )

            init_db()

            run = find_unfinished_run()

            if run:
                counts = queue_counts(
                    int(run["id"])
                )

                self.unfinished_run = {
                    "run": run,
                    "counts": counts,
                }

                self.pending_var.set(
                    (
                        f"Run #{run['id']}  "
                        f"{counts['done']}/{counts['total']}"
                    )
                )
            else:
                self.pending_var.set(
                    "None"
                )

        except Exception:
            self.pending_var.set(
                "Unknown"
            )

        if (
            self.count_var.get().strip().isdigit()
            and count > 0
            and int(self.count_var.get().strip()) > count
        ):
            self.count_var.set(
                str(count)
            )

        if show_feedback:
            self._activity_event(
                (
                    f"Refreshed: {count} new video"
                    + ("" if count == 1 else "s")
                    + " found in ToUpload."
                ),
                "accent",
            )

    # ========================================================
    # RESUME POPUP
    # ========================================================

    def _ask_resume_choice(self) -> bool:
        """
        Returns True if startup should continue.
        self.resume_choice:
            True  -> resume old queue
            False -> cancel old queue and start new
            None  -> user cancelled
        """

        if not self.unfinished_run:
            self.resume_choice = False
            return True

        data = self.unfinished_run
        run = data["run"]
        counts = data["counts"]

        result = {
            "choice": None,
        }

        win = tk.Toplevel(
            self.root
        )
        win.title(
            "Unfinished run found"
        )
        win.configure(
            bg=BG
        )
        win.resizable(
            False,
            False,
        )
        win.transient(
            self.root
        )
        win.grab_set()

        width = 500
        height = 315

        self.root.update_idletasks()

        x = (
            self.root.winfo_rootx()
            + (
                self.root.winfo_width()
                - width
            ) // 2
        )
        y = (
            self.root.winfo_rooty()
            + (
                self.root.winfo_height()
                - height
            ) // 2
        )

        win.geometry(
            f"{width}x{height}+{x}+{y}"
        )

        card = tk.Frame(
            win,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(
            fill="both",
            expand=True,
            padx=14,
            pady=14,
        )

        tk.Label(
            card,
            text="Unfinished SQLite run found",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 16, "bold"),
        ).pack(
            anchor="w",
            padx=18,
            pady=(18, 6),
        )

        tk.Label(
            card,
            text=(
                "Choose what the bot should do before "
                "starting this run."
            ),
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(
            anchor="w",
            padx=18,
        )

        info = tk.Frame(
            card,
            bg=CARD_SOFT,
        )
        info.pack(
            fill="x",
            padx=18,
            pady=16,
        )

        details = (
            f"Run ID: #{run['id']}\n"
            f"Progress: {counts['done']} / {counts['total']}\n"
            f"Queued: {counts['queued']}   "
            f"Failed: {counts['failed']}   "
            f"Blocked: {counts['blocked']}"
        )

        tk.Label(
            info,
            text=details,
            bg=CARD_SOFT,
            fg=TEXT,
            justify="left",
            font=("Segoe UI", 10),
            padx=13,
            pady=11,
        ).pack(
            anchor="w"
        )

        buttons = tk.Frame(
            card,
            bg=CARD,
        )
        buttons.pack(
            fill="x",
            padx=18,
            pady=(0, 18),
        )

        def choose(value):
            result["choice"] = value
            win.destroy()

        ttk.Button(
            buttons,
            text="Resume previous",
            style="Primary.TButton",
            command=lambda:
                choose(True),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 5),
        )

        ttk.Button(
            buttons,
            text="Start new",
            style="Secondary.TButton",
            command=lambda:
                choose(False),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=5,
        )

        ttk.Button(
            buttons,
            text="Cancel",
            style="Secondary.TButton",
            command=lambda:
                choose(None),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(5, 0),
        )

        win.protocol(
            "WM_DELETE_WINDOW",
            lambda:
                choose(None),
        )

        self.root.wait_window(
            win
        )

        self.resume_choice = result[
            "choice"
        ]

        return (
            self.resume_choice
            is not None
        )

    # ========================================================
    # RUN BOT
    # ========================================================

    def start_bot(self) -> None:
        if (
            self.process
            and self.process.poll() is None
        ):
            return

        # Manual refresh at START guarantees the count is current,
        # but the app does NOT poll the folder continuously.
        self.refresh_state(
            show_feedback=False
        )

        count_text = (
            self.count_var.get().strip()
        )

        if not count_text:
            messagebox.showerror(
                "VibeRush YouTube Bot",
                "Enter the number of videos.",
            )
            return

        if count_text.lower() != "all":
            try:
                count = int(
                    count_text
                )

                if count <= 0:
                    raise ValueError

                available = int(
                    self.available_var.get()
                )

                if (
                    not self.unfinished_run
                    and count > available
                ):
                    messagebox.showwarning(
                        "VibeRush YouTube Bot",
                        (
                            f"Only {available} new video(s) "
                            "are currently in ToUpload."
                        ),
                    )
                    return

            except ValueError:
                messagebox.showerror(
                    "VibeRush YouTube Bot",
                    (
                        "Videos to process must be "
                        "a positive number or ALL."
                    ),
                )
                return

        if not self._ask_resume_choice():
            return

        env = os.environ.copy()

        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"

        env[
            "YOUTUBEBOT_GUI_COUNT"
        ] = count_text

        env[
            "YOUTUBEBOT_GUI_VISIBILITY"
        ] = self.visibility_var.get()

        env[
            "YOUTUBEBOT_GUI_UPLOAD_ENABLED"
        ] = (
            "1"
            if self.upload_enabled_var.get()
            else "0"
        )

        env[
            "YOUTUBEBOT_GUI_RESUME"
        ] = (
            "1"
            if self.resume_choice is True
            else "0"
        )

        env[
            "YOUTUBEBOT_GUI_RETRY_INTERRUPTED"
        ] = (
            "1"
            if self.retry_interrupted_upload_var.get()
            else "0"
        )

        env[
            "YOUTUBEBOT_GUI_CHAIN_NEW_AFTER_RESUME"
        ] = (
            "1"
            if self.resume_choice is True
            else "0"
        )

        if getattr(sys, "frozen", False):
            backend_exe = (
                BASE_DIR
                / "_VibeRushBackend.exe"
            )

            if not backend_exe.exists():
                messagebox.showerror(
                    "VibeRush YouTube Bot",
                    (
                        "Backend executable is missing:\n\n"
                        f"{backend_exe}\n\n"
                        "Run BUILD_EXE.bat again."
                    ),
                )
                return

            command = [
                str(backend_exe),
            ]

        else:
            command = [
                sys.executable,
                "-u",
                str(
                    BASE_DIR
                    / "gui"
                    / "runner.py"
                ),
            ]

        env[
            "YOUTUBEBOT_RUNTIME_ROOT"
        ] = str(BASE_DIR)

        creationflags = 0

        if os.name == "nt":
            creationflags |= getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(BASE_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=creationflags,
            )

        except Exception as exc:
            messagebox.showerror(
                "VibeRush YouTube Bot",
                f"Could not start bot:\n{exc}",
            )
            return

        self.run_had_error = False
        self.current_video = 0
        self.total_videos = 0

        self.progress["value"] = 0
        self.progress_text_var.set(
            "Preparing run"
        )
        self.stage_var.set(
            "Starting"
        )
        self.run_status_var.set(
            "RUNNING"
        )
        self._set_badge(
            "running"
        )

        self.start_button.configure(
            state="disabled"
        )
        self.stop_button.configure(
            state="normal"
        )
        self.refresh_button.configure(
            state="disabled"
        )

        action = (
            "Resume previous run"
            if self.resume_choice is True
            else "Start new run"
        )

        self._activity_event(
            action,
            "accent",
        )
        self._activity_event(
            (
                f"Requested {count_text} video(s) • "
                f"{self.visibility_var.get()} • "
                f"YouTube "
                f"{'ON' if self.upload_enabled_var.get() else 'OFF'}"
            ),
            "info",
        )

        self._append_details(
            "\n"
            + "=" * 68
            + "\n"
            + "GUI RUN STARTED\n"
            + f"Action: {action}\n"
            + f"Videos requested: {count_text}\n"
            + f"Visibility: {self.visibility_var.get()}\n"
            + f"YouTube upload: "
            + (
                "ON\n"
                if self.upload_enabled_var.get()
                else "OFF\n"
            )
            + "=" * 68
            + "\n\n"
        )

        self.reader_thread = threading.Thread(
            target=self._read_process_output,
            daemon=True,
        )
        self.reader_thread.start()

    def _read_process_output(self) -> None:
        if (
            not self.process
            or not self.process.stdout
        ):
            return

        for line in self.process.stdout:
            self._buffer_put(
                line
            )

        code = self.process.wait()

        self._buffer_put(
            (
                "\n[GUI] Backend finished "
                f"with code {code}\n"
            )
        )
        self._buffer_put(
            "__PROCESS_FINISHED__"
        )

    # ========================================================
    # OUTPUT
    # ========================================================

    def _poll_output(self) -> None:
        while True:
            line = self._buffer_get()

            if line is None:
                break

            if line == "__PROCESS_FINISHED__":
                self._process_finished()
                continue

            self._append_details(
                line
            )
            self._update_from_backend_line(
                line
            )

        self.root.after(
            100,
            self._poll_output,
        )

    def _update_from_backend_line(
        self,
        line: str,
    ) -> None:
        text = line.strip()

        if not text:
            return

        upper = text.upper()

        video_match = re.search(
            r"VIDEO\s+(\d+)\s*/\s*(\d+)",
            upper,
        )

        if video_match:
            self.current_video = int(
                video_match.group(1)
            )
            self.total_videos = int(
                video_match.group(2)
            )

            self.progress_text_var.set(
                (
                    f"Video {self.current_video} "
                    f"of {self.total_videos}"
                )
            )

            if self.total_videos > 0:
                self.progress[
                    "value"
                ] = (
                    (
                        self.current_video
                        - 1
                    )
                    / self.total_videos
                ) * 100

            self._activity_event(
                (
                    f"Processing video "
                    f"{self.current_video}/{self.total_videos}"
                ),
                "accent",
            )
            return

        events = (
            (
                "AI VIDEO ANALYSIS",
                "Analyzing video with local AI",
                "info",
            ),
            (
                "METADATA AI",
                "Generating YouTube metadata",
                "info",
            ),
            (
                "READY.MP4 EXISTS",
                "Local processing already complete",
                "success",
            ),
            (
                "YOUTUBE UPLOAD",
                "Uploading video to YouTube Studio",
                "accent",
            ),
            (
                "WAITING FOR YOUTUBE PROCESSING",
                "Waiting for YouTube processing/checks",
                "warning",
            ),
            (
                "НАТИСКАЮ PUBLISH",
                "Publishing video",
                "accent",
            ),
            (
                "STUDIO VERIFY: OK",
                "Publication verified in YouTube Studio",
                "success",
            ),
            (
                "YOUTUBE UPLOAD: VERIFIED",
                "YouTube upload verified",
                "success",
            ),
            (
                "SOURCE ARCHIVE: OK",
                "Source moved to Uploaded",
                "success",
            ),
            (
                "RESUME COMPLETE - STARTING NEW GUI BATCH",
                "Previous run completed; starting selected new videos",
                "success",
            ),
            (
                "PUBLISH FAILED",
                "Publish failed",
                "error",
            ),
            (
                "VIDEO FAILED",
                "Video processing failed",
                "error",
            ),
            (
                "RUN COMPLETED",
                "Run completed successfully",
                "success",
            ),
            (
                "RUN FINISHED WITH ISSUES",
                "Run finished with issues",
                "error",
            ),
        )

        for needle, message, level in events:
            if needle in upper:
                self.stage_var.set(
                    message
                )
                self._activity_event(
                    message,
                    level,
                )

                if level == "error":
                    self.run_had_error = True
                    self._set_badge(
                        "error"
                    )

                return

        if (
            "YOUTUBEUPLOADERROR" in upper
            or "RUNTIMEERROR" in upper
            or "TRACEBACK" in upper
        ):
            self.run_had_error = True
            self._activity_event(
                text[:300],
                "error",
            )
            return

        done_match = re.search(
            r"DONE:\s*(\d+)\s*/\s*(\d+)",
            upper,
        )

        if done_match:
            done = int(
                done_match.group(1)
            )
            total = int(
                done_match.group(2)
            )

            self.progress_text_var.set(
                f"{done} of {total} completed"
            )

            if total > 0:
                self.progress[
                    "value"
                ] = (
                    done / total
                ) * 100

    def _activity_event(
        self,
        message: str,
        level: str = "info",
    ) -> None:
        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        marker = {
            "info": "•",
            "success": "✓",
            "warning": "!",
            "error": "×",
            "accent": "→",
        }.get(
            level,
            "•",
        )

        self.activity.configure(
            state="normal"
        )

        self.activity.insert(
            "end",
            f"{timestamp}  ",
            "time",
        )
        self.activity.insert(
            "end",
            f"{marker}  {message}\n",
            level,
        )

        self.activity.see(
            "end"
        )
        self.activity.configure(
            state="disabled"
        )

    def _append_details(
        self,
        text: str,
    ) -> None:
        self.details.configure(
            state="normal"
        )
        self.details.insert(
            "end",
            text,
        )
        self.details.see(
            "end"
        )
        self.details.configure(
            state="disabled"
        )

    def clear_activity(self) -> None:
        for widget in (
            self.activity,
            self.details,
        ):
            widget.configure(
                state="normal"
            )
            widget.delete(
                "1.0",
                "end",
            )
            widget.configure(
                state="disabled"
            )

    # ========================================================
    # STOP / FINISH
    # ========================================================

    def _kill_process_tree(self) -> None:
        if (
            not self.process
            or self.process.poll() is not None
        ):
            return

        if os.name == "nt":
            flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

            try:
                subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(self.process.pid),
                        "/T",
                        "/F",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    check=False,
                )
                return
            except Exception:
                pass

        try:
            self.process.terminate()
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass

    def stop_bot(self) -> None:
        if (
            not self.process
            or self.process.poll() is not None
        ):
            return

        if not messagebox.askyesno(
            "Stop current run",
            (
                "Stop the current bot run?\n\n"
                "SQLite checkpoints already saved "
                "will remain available for resume."
            ),
        ):
            return

        self.stage_var.set(
            "Stopping"
        )
        self._activity_event(
            "Stopping bot process",
            "warning",
        )
        self._kill_process_tree()

    def _process_finished(self) -> None:
        code = (
            self.process.poll()
            if self.process
            else None
        )

        self.start_button.configure(
            state="normal"
        )
        self.stop_button.configure(
            state="disabled"
        )
        self.refresh_button.configure(
            state="normal"
        )

        if (
            code == 0
            and not self.run_had_error
        ):
            self.run_status_var.set(
                "FINISHED"
            )
            self._set_badge(
                "success"
            )
            self.stage_var.set(
                "Ready"
            )
            self._activity_event(
                "Backend finished successfully",
                "success",
            )
        else:
            self.run_status_var.set(
                "ERROR"
            )
            self._set_badge(
                "error"
            )
            self.stage_var.set(
                "Run needs attention"
            )
            self._activity_event(
                (
                    "Backend stopped with an error"
                    if code not in (
                        None,
                        0,
                    )
                    else "Run completed with errors"
                ),
                "error",
            )

        # Do not silently auto-refresh all the time.
        # Refresh once after a run because the run itself changed state.
        self.refresh_state(
            show_feedback=False
        )

    def _set_badge(
        self,
        status: str,
    ) -> None:
        if status == "running":
            self.status_badge.configure(
                bg=YELLOW_BG,
                fg=YELLOW,
            )
        elif status == "success":
            self.status_badge.configure(
                bg=GREEN_BG,
                fg=GREEN,
            )
        elif status == "error":
            self.status_badge.configure(
                bg=RED_BG,
                fg=RED,
            )
        else:
            self.status_badge.configure(
                bg="#1A2530",
                fg=MUTED,
            )

    def on_close(self) -> None:
        if (
            self.process
            and self.process.poll() is None
        ):
            if not messagebox.askyesno(
                "Exit VibeRush YouTube Bot",
                (
                    "The bot is still running.\n"
                    "Stop it and close the app?"
                ),
            ):
                return

            self._kill_process_tree()

        self.root.destroy()

    # ========================================================
    # FOLDERS
    # ========================================================

    def open_folder(
        self,
        path: Path,
    ) -> None:
        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            os.startfile(
                str(path)
            )
        except Exception as exc:
            messagebox.showerror(
                "VibeRush YouTube Bot",
                f"Could not open folder:\n{exc}",
            )


def run() -> None:
    root = tk.Tk()
    YouTubeBotGUI(root)
    root.mainloop()
