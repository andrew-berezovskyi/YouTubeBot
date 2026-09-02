from __future__ import annotations

import os
import sys
from pathlib import Path


def runtime_root() -> Path:
    value = os.getenv(
        "YOUTUBEBOT_RUNTIME_ROOT"
    )

    if value:
        return Path(value).resolve()

    if getattr(sys, "frozen", False):
        return Path(
            sys.executable
        ).resolve().parent

    return Path(
        __file__
    ).resolve().parent


ROOT = runtime_root()

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


import config  # noqa: E402


# ============================================================
# RUNTIME PATH OVERRIDES
# ============================================================
#
# config.py is bundled into the EXE, so its __file__ points to
# the PyInstaller bundle. The bot's real working folders must
# stay next to the executable instead.
#
# This changes only this backend process in memory.
# The original config.py on disk is NOT edited.
# ============================================================

config.BASE_DIR = ROOT

config.TO_UPLOAD = ROOT / "ToUpload"
config.FRAMES = ROOT / "Frames"
config.METADATA = ROOT / "Metadata"
config.PROCESSED = ROOT / "Processed"
config.UPLOADED = ROOT / "Uploaded"
config.THUMBNAILS = ROOT / "Thumbnails"
config.WATERMARK = ROOT / "Watermark"
config.LOGS = ROOT / "Logs"
config.DATA = ROOT / "data"
config.BROWSER_PROFILE = ROOT / "BrowserProfile"

config.QUEUE_STATE_FILE = (
    config.DATA
    / "queue_state.json"
)

config.DATABASE_FILE = (
    config.DATA
    / "youtube_bot.db"
)


for directory in (
    config.TO_UPLOAD,
    config.FRAMES,
    config.METADATA,
    config.PROCESSED,
    config.UPLOADED,
    config.THUMBNAILS,
    config.WATERMARK,
    config.LOGS,
    config.DATA,
    config.BROWSER_PROFILE,
):
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


def _bool_env(
    name: str,
    default: bool,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return (
        value.strip().lower()
        in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
    )


# GUI runtime options.
config.UPLOAD_VISIBILITY = os.getenv(
    "YOUTUBEBOT_GUI_VISIBILITY",
    getattr(
        config,
        "UPLOAD_VISIBILITY",
        "public",
    ),
)

config.ENABLE_YOUTUBE_UPLOAD = _bool_env(
    "YOUTUBEBOT_GUI_UPLOAD_ENABLED",
    bool(
        getattr(
            config,
            "ENABLE_YOUTUBE_UPLOAD",
            True,
        )
    ),
)


print(
    "[EXE BACKEND] Runtime root:",
    ROOT,
    flush=True,
)

print(
    "[EXE BACKEND] Visibility:",
    config.UPLOAD_VISIBILITY,
    flush=True,
)

print(
    "[EXE BACKEND] YouTube upload:",
    (
        "ON"
        if config.ENABLE_YOUTUBE_UPLOAD
        else "OFF"
    ),
    flush=True,
)


import main  # noqa: E402


if __name__ == "__main__":
    main.main()
