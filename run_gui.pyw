from __future__ import annotations

import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

BASE_DIR = Path(__file__).resolve().parent
LOGS = BASE_DIR / "Logs"

try:
    from gui.app import run
    run()

except Exception:
    LOGS.mkdir(
        parents=True,
        exist_ok=True,
    )

    details = traceback.format_exc()

    log_path = (
        LOGS
        / "gui_startup_error.log"
    )

    try:
        log_path.write_text(
            details,
            encoding="utf-8",
        )
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()

    messagebox.showerror(
        "VibeRush YouTube Bot",
        (
            "GUI failed to start.\n\n"
            "Details were saved to:\n"
            f"{log_path}"
        ),
    )

    root.destroy()
