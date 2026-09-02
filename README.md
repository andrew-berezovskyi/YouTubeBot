# VibeRush YouTube Bot

A local Windows application for automating the preparation and publishing of YouTube Shorts.

The bot combines local AI video analysis, metadata generation, FFmpeg video processing, SQLite-based queue/resume logic, Playwright-powered YouTube Studio automation, upload verification, and a desktop GUI.

> **Current status:** stable local build / pre-release version.  
> The current backend workflow has been tested with multiple sequential uploads.

---

## Overview

VibeRush YouTube Bot is designed to reduce the repetitive work involved in preparing and publishing short-form videos.

The current workflow is:

```text
ToUpload
   ↓
SQLite queue
   ↓
AI video analysis
   ↓
AI metadata generation
   ↓
Watermark / video processing
   ↓
READY video
   ↓
YouTube Studio upload
   ↓
YouTube processing wait
   ↓
Publish
   ↓
Studio verification
   ↓
SQLite = published
   ↓
Move source to Uploaded
```

The application is currently intended to run locally on Windows.

---

## Features

### Local AI video analysis

The bot extracts representative frames from each video and analyzes them using a local Ollama vision model.

Current vision model:

```text
qwen3-vl:4b
```

The analysis can produce information such as:

- video type
- main topic
- short summary
- visible on-screen text
- important events in the clip

The current analyzer uses retry logic with fewer frames when a larger multimodal request fails.

---

### AI-generated YouTube metadata

A separate local text model is used to generate metadata for the analyzed video.

Current metadata model:

```text
qwen3:4b-instruct
```

Generated metadata includes:

- YouTube title
- description hook
- engagement question
- hashtags

Additional Python-side validation and fallback logic is used to keep the output usable even if the AI response fails.

---

### SQLite queue and resume system

The bot uses SQLite as its persistent local state store.

It tracks:

- processing runs
- videos
- processing stages
- events
- upload attempts
- errors
- YouTube video IDs
- published URLs
- retry information

The queue can resume from previously completed stages instead of restarting a video from zero.

Typical stages include:

```text
queued
analyzing
analyzed
metadata_generating
metadata_ready
processing
ready_to_upload
uploading
published
publish_failed
upload_interrupted
```

Examples:

If analysis is already complete:

```text
analysis      SKIP
metadata      continue
```

If metadata is already complete:

```text
analysis      SKIP
metadata      SKIP
processing    continue
```

If a READY video already exists:

```text
analysis      SKIP
metadata      SKIP
FFmpeg        SKIP
YouTube       continue
```

---

### YouTube Studio automation

YouTube publishing is automated using Playwright.

The bot can:

- open YouTube Studio
- upload a processed video
- set title and description
- configure visibility
- continue through the upload workflow
- wait for YouTube processing
- publish the video
- retrieve the YouTube video ID / URL
- verify the published video inside YouTube Studio

Supported visibility options from the GUI:

```text
public
private
unlisted
```

---

### Publish verification

The bot does not treat a click on **Publish** as sufficient proof of success.

After publishing, it verifies the resulting video in YouTube Studio.

Successful uploads are stored in SQLite with:

- upload attempt
- processing wait time
- YouTube video ID
- YouTube URL
- final result

If publishing fails, the bot can record diagnostic information instead of silently marking the upload as successful.

---

### File organization

After a successful verified upload:

```text
ToUpload
   ↓
Uploaded
```

Already-published files are therefore not repeatedly selected as new input.

---

## Desktop GUI

The project includes a Windows desktop interface.

The GUI provides:

- video count in `ToUpload`
- manual **Refresh** button
- number of videos to process
- `public / private / unlisted` visibility selection
- YouTube upload enable/disable option
- interrupted-upload retry option
- START / STOP controls
- queue status
- current processing status
- progress bar
- modern activity feed
- full backend details/log tab
- shortcuts to `ToUpload`, `Uploaded`, and `Logs`
- confirmation dialog when an unfinished SQLite run exists

When an unfinished run is detected, the application asks whether to:

```text
Resume previous
Start new
Cancel
```

This prevents an old queue from being resumed silently.

---

## Project structure

A typical development layout looks like this:

```text
YouTubeBot/
├── ai/
│   ├── analyzer.py
│   └── metadata.py
│
├── database/
│   └── db.py
│
├── gui/
│   ├── __init__.py
│   ├── app.py
│   └── runner.py
│
├── queue/
│   └── manager.py
│
├── video/
│   └── processor.py
│
├── youtube/
│   └── uploader.py
│
├── main.py
├── run_gui.py
├── run_gui.pyw
├── START_GUI.bat
│
├── exe_gui_entry.py
├── exe_backend_entry.py
├── YouTubeBot.spec
├── BUILD_EXE.bat
│
├── requirements.txt
├── README.md
└── .gitignore
```

The following directories are runtime/local data and should **not** be committed:

```text
BrowserProfile/
data/
Frames/
Logs/
Metadata/
Processed/
Thumbnails/
ToUpload/
Uploaded/
```

---

## Requirements

### Operating system

The current version is designed for:

```text
Windows 10 / Windows 11
```

---

### Python

Python 3.x is required for development mode.

Check:

```powershell
python --version
```

Install project packages:

```powershell
pip install -r requirements.txt
```

---

### Ollama

Install Ollama and make sure the required models are available.

Check installed models:

```powershell
ollama list
```

Recommended models for the current project:

```powershell
ollama pull qwen3-vl:4b
ollama pull qwen3:4b-instruct
```

Ollama must be running when AI processing is used.

---

### FFmpeg

FFmpeg and FFprobe are required for:

- video duration detection
- frame extraction
- video processing
- watermark rendering

Make sure both commands are available or correctly configured locally.

Example:

```powershell
ffmpeg -version
ffprobe -version
```

---

### Playwright

The uploader uses Playwright to automate YouTube Studio.

Install Playwright:

```powershell
pip install playwright
playwright install
```

The bot uses a local persistent browser profile for YouTube authentication.

---

## Running in development mode

From the project directory:

```powershell
python run_gui.py
```

Or use:

```text
START_GUI.bat
```

The normal user workflow is:

1. Put videos into `ToUpload/`
2. Open the GUI
3. Press **Refresh**
4. Select how many videos to process
5. Select visibility
6. Press **START BOT**
7. Monitor progress from the Activity tab
8. Check full backend output in Details if needed

---

## Building the Windows executable

The project contains a PyInstaller build configuration.

Build from the VS Code terminal:

```powershell
.\BUILD_EXE.bat
```

or:

```powershell
cmd /c BUILD_EXE.bat
```

The build produces:

```text
VibeRush YouTube Bot.exe
_VibeRushBackend.exe
```

### Why two executables?

`VibeRush YouTube Bot.exe`

- desktop GUI
- no console window
- the executable the user launches

`_VibeRushBackend.exe`

- internal worker process
- runs the existing processing pipeline
- provides live output to the GUI
- should not be launched manually

This architecture keeps the GUI window clean while preserving live backend logging.

---

## Local runtime data

Runtime data intentionally stays outside the executable.

The application can reuse local directories such as:

```text
BrowserProfile/
data/
ToUpload/
Uploaded/
Processed/
Frames/
Metadata/
Watermark/
Logs/
```

This is important because:

- YouTube login state remains local
- SQLite history remains local
- media files are not bundled into the EXE
- AI models are not bundled into the EXE
- local secrets are not embedded into the public repository

---

## Security

### Never commit authentication data

The following must never be pushed to a public repository:

```text
BrowserProfile/
.env
.env.*
client_secret*.json
credentials*.json
token*.json
*.pem
*.key
```

`BrowserProfile/` is especially important because it can contain an authenticated browser session.

---

### Never commit the local database

The local SQLite database may contain:

- processed video names
- titles
- upload history
- YouTube URLs
- errors
- internal runtime state

Files such as these should remain local:

```text
*.db
*.sqlite
*.sqlite3
data/
```

---

### Never commit private videos or generated runtime content

Keep these local:

```text
ToUpload/
Uploaded/
Processed/
Frames/
Metadata/
Logs/
Thumbnails/
```

---

## Important Git security note

Adding a file to `.gitignore` does **not** remove it from Git if it has already been committed.

If a private file is already tracked, remove it from the Git index:

```powershell
git rm -r --cached BrowserProfile
git rm -r --cached data
```

Then commit the cleanup.

If credentials, cookies, tokens, or browser-session files were pushed publicly, they should be treated as compromised.

Recommended actions:

1. Remove them from the repository
2. Clean them from Git history
3. Revoke / rotate affected credentials
4. Re-authenticate the local browser profile if necessary

---

## Database inspection

Development utilities can be used to inspect the local SQLite state.

Examples:

```powershell
python verify_sqlite.py
python inspect_db.py
python inspect_queue.py
python inspect_upload_attempts.py
```

---

## Upload safety

If the bot is interrupted while local processing is running, it can normally continue from SQLite checkpoints.

A crash during the actual YouTube upload is treated more carefully.

The application does not automatically retry an interrupted upload by default because it is possible that YouTube accepted the publish operation immediately before the process stopped.

The GUI therefore exposes an explicit interrupted-upload retry option.

---

## Current tested workflow

The current development version has been tested with:

- local AI frame analysis
- metadata generation
- FFmpeg processing
- watermark application
- SQLite migrations
- SQLite queue/resume
- multiple sequential videos
- YouTube upload
- processing wait
- publish verification
- YouTube video ID extraction
- YouTube URL storage
- successful `ToUpload → Uploaded` moves
- desktop GUI operation

---

## Technology stack

- **Python**
- **Tkinter / ttk**
- **Ollama**
- **Qwen3-VL**
- **Qwen3**
- **FFmpeg**
- **SQLite**
- **Playwright**
- **PyInstaller**
- **YouTube Studio**

---

## Roadmap

Possible future improvements include:

- scene-aware video sampling
- audio transcription
- automatic thumbnail generation
- thumbnail upload automation
- metadata anti-repetition
- YouTube email / copyright notification monitoring
- external notifications
- authorized source discovery
- automated downloading of owned content
- old-watermark detection
- publishing schedules and daily limits
- analytics/dashboard view

These features are intentionally outside the current stable core.

---

## Responsible use

This project should be used with content that you own or are authorized to publish.

Automated publishing does not remove the responsibility to follow:

- YouTube Community Guidelines
- copyright rules
- YouTube monetization policies
- spam / repetitive-content policies
- local laws and platform terms

---

## License

No open-source license is currently included.

Until a license is explicitly added, the source code should be considered **all rights reserved by the repository owner**.

---

## Author

Developed by **Andrew Berezovskyi**.

Repository:

```text
andrew-berezovskyi/YouTubeBot
```
