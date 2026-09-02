from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(BASE_DIR),
    )

import config  # noqa: E402


def _bool_env(
    name: str,
    default: bool,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


# Real GUI runtime overrides.
# config.py on disk is NOT modified.
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
    "[RUNNER] Project root:",
    BASE_DIR,
    flush=True,
)
print(
    "[RUNNER] Visibility:",
    config.UPLOAD_VISIBILITY,
    flush=True,
)
print(
    "[RUNNER] YouTube upload:",
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
