# VibeRush YouTube Bot — Discovery 1.1

Source update for the existing VibeRush bot. Adds multi-source discovery,
platform downloads, OCR/vision watermark screening, persistent candidate history,
conservative duplicate detection and a bridge to the original SQLite pipeline.

**Start with [START_HERE_UK.md](START_HERE_UK.md)** for installation and operation.
The original project documentation is preserved in [README_LEGACY.md](README_LEGACY.md).

## Installation

Close the old application and back up your project. Merge this update archive's
root contents into the existing project folder. The archive contains only new
and changed files, with their relative paths preserved. Your `config.py` is not included
and is not overwritten. For a fresh installation copy `config.example.py` to
`config.py`, then configure FFmpeg/FFprobe and Ollama paths/models.

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python check_discovery.py
python run_discovery_gui.py
```

Install Tesseract OCR separately. Use `tesseract_cmd` in discovery settings if it
is not on PATH. This release runs discovery from Python; an old EXE will not
contain these changes. Do not run old EXEs alongside the new worker.

## Sources and limitations

- YouTube: keyword search and configured supported video/channel/playlist URLs.
- Reddit: public RSS search and configured video-post URLs. RSS can be blocked.
- TikTok: configured supported video/profile URLs; **no global TikTok search**.
- Vimeo: configured supported URLs.

yt-dlp availability depends on the platform, video, region, login requirements
and installed version. There is no access-control bypass or CAPTCHA solver.
Source cookies, if needed, are an explicit local Netscape cookie-file setting.
No cookies are exported automatically.

## Screening and state

Candidates are persisted in a separate `data/discovery.db`. Videos or creators
must be in user-approved reuse lists before download. A license label does not
automatically approve a source. Approved creators allow unattended future cycles.

Downloaded bytes are checked for size, dimensions, duration, decoding errors,
exact hashes and watermark evidence before entering the original pipeline.
Tesseract OCR and local Ollama vision inspect sampled frames, including nearby
frames around ambiguous marks. Missing dependencies, failed inference or
ambiguous evidence never silently pass. Reports retain timestamps and JPEGs.

Frame dHash comparisons flag possible re-encoded duplicates for review. They do
not guarantee detection of crops, mirrored copies or remixes. Watermark absence
cannot be guaranteed between sampled frames. Topic scores are heuristic, not
predictions of virality. No watermark removal is implemented.

## Automation

```powershell
python run_discovery.py                        # discovery/screening only
python run_discovery.py --watch                # repeat, no YouTube upload
python run_discovery.py --watch --process      # original pipeline, PRIVATE uploads
python run_discovery.py --watch --process --publish # PUBLIC uploads
```

Accepted files are copied into the original queue one at a time. Existing
unfinished runs block new automated processing. Pipeline locks prevent concurrent
new-code workers; legacy EXEs do not participate. Ambiguous uploads require
manual reconciliation to prevent duplicates. They are not automatically retried.

Defaults: 3 downloads per cycle, 3 upload attempts per rolling 24h, 120-minute
minimum upload interval, 60-minute search interval, 3 transient-error attempts.
The GUI must remain running for its worker to continue. Closing it stops its
worker. This is not a Windows service or a cloud-hosted scheduler.

Settings are edited in the discovery GUI as JSON; the complete field reference
is in START_HERE_UK.md. Runtime folders/settings are ignored by Git.

## Validation

```powershell
python -m unittest discover -s tests -v
```

Tests cover decision gates, canonical URLs, reuse approval, deduplication,
locking, retry state, upload limits, the original queue bridge with mocked upload,
and real FFmpeg/Tesseract processing of a generated marked MP4 with mocked vision.
Live source access, real Ollama responses, Windows GUI and actual YouTube uploads
still need a local private-video smoke test. No new Windows binaries are provided.

## Reference documentation

- [yt-dlp usage and dependencies](https://github.com/yt-dlp/yt-dlp)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation.html)

## Layout

`discovery/settings.py`: defaults and validation; `sources.py`: search/download;
`screening.py`: media, OCR, vision and fingerprints; `store.py`: candidate DB;
`service.py`: cycles and queue handoff. `run_discovery_gui.py`: separate GUI;
`check_discovery.py`: non-publishing environment diagnostics.

The original `ai/`, `database/`, `video/`, `youtube/`, GUI and pipeline are retained.
`queue/__init__.py` now exposes the standard Python queue API to avoid shadowing
errors in third-party packages while preserving `queue.manager`. The original
PyInstaller spec includes that stdlib module for the legacy app build path;
discovery itself remains a source-run feature in this release.
