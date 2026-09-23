# VibeRush YouTube Bot

A local Python workflow for discovering, screening, preparing, and uploading short videos. The repository combines the original SQLite-based processing pipeline with a newer discovery module, a GUI, and command-line entry points. The discovery module searches configured sources, checks candidate media, and passes accepted files to the original queue.

Start with the detailed [setup guide](START_HERE_UK.md) (Ukrainian). [README_LEGACY.md](README_LEGACY.md) documents the earlier pipeline.

## Requirements and setup

Run on a machine with Python, FFmpeg/FFprobe, Tesseract OCR, and Ollama configured for the models used by the project. Some source downloads may require additional yt-dlp runtime dependencies. From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

For a fresh setup, copy `config.example.py` to the local `config.py` and set the paths and models for your machine. Review `discovery_settings.example.json` for discovery settings. Keep credentials, browser profiles, cookies, and runtime databases out of Git.

Check dependencies before processing:

```powershell
python check_discovery.py
python run_discovery_gui.py
```

The Windows batch files `INSTALL_DISCOVERY.bat` and `START_DISCOVERY.bat` provide corresponding shortcuts. The newer discovery module runs from Python source; an older EXE does not automatically include it.

## Sources and review

- YouTube: keyword search and configured video, channel, or playlist URLs.
- Reddit: public RSS search and configured video-post URLs.
- TikTok: configured video or profile URLs; no global keyword search.
- Vimeo: configured URLs.

Availability depends on the source, region, authentication, and yt-dlp version. The project does not bypass access controls. Candidates are saved in `data/discovery.db`; only videos or creators explicitly approved for reuse can proceed to download. Screening checks media properties, decoding, exact and possible visual duplicates, and watermark evidence using OCR and local vision inference. Ambiguous or failed checks require review. These checks cannot guarantee that every watermark or modified duplicate is detected.

## Command-line operation

```powershell
python run_discovery.py                        # one discovery/screening cycle, no upload
python run_discovery.py --watch                # repeated discovery, no upload
python run_discovery.py --watch --process      # process and upload privately
python run_discovery.py --watch --process --publish # public uploads
```

The worker must keep running for repeat cycles; this is not a cloud scheduler or Windows service. Do not run an older EXE concurrently with the new worker. Uncertain upload results need manual reconciliation before retrying. Review the settings and safety limits in [START_HERE_UK.md](START_HERE_UK.md) before enabling uploads, especially public uploads.

## Tests and layout

```powershell
python -m unittest discover -s tests -v
```

- `discovery/` — source search, screening, candidate storage, and queue handoff.
- `ai/`, `video/`, `youtube/`, `database/`, `queue/` — original processing pipeline.
- `gui/` and `run_discovery_gui.py` — local interface.
- `tests/` — automated checks.

Automated tests do not replace a local end-to-end check of live sources, installed tools, the GUI, and an actual private YouTube upload.
