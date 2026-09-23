# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sysconfig
from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH).resolve()

playwright_datas, playwright_binaries, playwright_hidden = (
    collect_all("playwright")
)

try:
    ollama_datas, ollama_binaries, ollama_hidden = (
        collect_all("ollama")
    )
except Exception:
    ollama_datas = []
    ollama_binaries = []
    ollama_hidden = []


backend = Analysis(
    ["exe_backend_entry.py"],
    pathex=[str(project_root)],
    binaries=(
        playwright_binaries
        + ollama_binaries
    ),
    datas=(
        playwright_datas
        + ollama_datas
        + [(str(Path(sysconfig.get_path("stdlib")) / "queue.py"), ".")]
    ),
    hiddenimports=(
        playwright_hidden
        + ollama_hidden
        + [
            "playwright.sync_api",
            "queue.manager",
            "database.db",
            "ai.analyzer",
            "ai.metadata",
            "video.processor",
            "youtube.uploader",
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

backend_pyz = PYZ(
    backend.pure
)

backend_exe = EXE(
    backend_pyz,
    backend.scripts,
    backend.binaries,
    backend.datas,
    [],
    name="_VibeRushBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)


gui = Analysis(
    ["exe_gui_entry.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(Path(sysconfig.get_path("stdlib")) / "queue.py"), ".")],
    hiddenimports=[
        "database.db",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

gui_pyz = PYZ(
    gui.pure
)

gui_exe = EXE(
    gui_pyz,
    gui.scripts,
    gui.binaries,
    gui.datas,
    [],
    name="VibeRush YouTube Bot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
