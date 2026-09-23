from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ============================================================
# MODES
# ============================================================

DRY_RUN = False

# True = після локальної обробки бот реально піде в YouTube Studio.
ENABLE_YOUTUBE_UPLOAD = False

# public / private / unlisted
UPLOAD_VISIBILITY = "private"

KEEP_BROWSER_OPEN_AFTER_UPLOAD = False

# Пауза між двома успішними роликами в batch.
UPLOAD_DELAY_SECONDS = 8

# ============================================================
# YOUTUBE PROCESSING SAFETY
# ============================================================

# Мінімум, який бот ЗАВЖДИ чекає на сторінці Visibility
# перед спробою Publish/Save.
#
# Ми ставимо 90 сек, бо на практиці YouTube інколи ще обробляє
# Short, хоча Publish уже доступний.
YOUTUBE_MIN_PROCESSING_WAIT = 90

# Максимальний загальний час очікування processing/checks.
# Якщо YouTube все ще явно обробляє відео через 10 хвилин,
# Publish НЕ натискаємо — краще retry, ніж Draft.
YOUTUBE_MAX_PROCESSING_WAIT = 600

# Як часто після мінімального cooldown перевіряти стан Studio.
YOUTUBE_PROCESSING_POLL = 2

# Скільки чистих перевірок поспіль має бути без
# "Uploading / Processing / Checking".
YOUTUBE_CLEAN_POLLS_REQUIRED = 3

# Додатковий запас після того, як processing зник.
YOUTUBE_FINAL_GRACE_WAIT = 15

# ============================================================
# PATHS
# ============================================================

FFMPEG = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
FFPROBE = Path(r"C:\ffmpeg\bin\ffprobe.exe")

TO_UPLOAD = BASE_DIR / "ToUpload"
FRAMES = BASE_DIR / "Frames"
METADATA = BASE_DIR / "Metadata"
PROCESSED = BASE_DIR / "Processed"
UPLOADED = BASE_DIR / "Uploaded"
THUMBNAILS = BASE_DIR / "Thumbnails"
WATERMARK = BASE_DIR / "Watermark"
LOGS = BASE_DIR / "Logs"
DATA = BASE_DIR / "data"
BROWSER_PROFILE = BASE_DIR / "BrowserProfile"

QUEUE_STATE_FILE = DATA / "queue_state.json"
DATABASE_FILE = DATA / "youtube_bot.db"

# ============================================================
# OLLAMA
# ============================================================

OLLAMA_HOST = "http://127.0.0.1:11434"

VISION_MODEL = "qwen3-vl:4b-instruct"
METADATA_MODEL = "qwen3:4b-instruct"

FRAME_WIDTH = 384

FRAMES_UP_TO_20S = 6
FRAMES_UP_TO_40S = 8
FRAMES_UP_TO_60S = 10
FRAMES_UP_TO_90S = 12
FRAMES_OVER_90S = 14

OLLAMA_NUM_CTX = 4096
VISION_FRAME_NUM_PREDICT = 180
VISION_MERGE_NUM_PREDICT = 300
METADATA_NUM_PREDICT = 220
OLLAMA_KEEP_ALIVE = "5m"

# ============================================================
# VIDEO / WATERMARK
# ============================================================

WATERMARK_WIDTH_RATIO = 0.14
WATERMARK_OPACITY = 0.80
WATERMARK_MARGIN_RIGHT_RATIO = 0.035
WATERMARK_MARGIN_BOTTOM_RATIO = 0.13

VIDEO_CRF = 18
VIDEO_PRESET = "medium"
AUDIO_BITRATE = "192k"

# ============================================================
# YOUTUBE
# ============================================================

STUDIO_URL = "https://studio.youtube.com/?hl=en"

FIXED_HASHTAGS = [
    "#shorts",
    "#viral",
    "#usa",
    "#funny",
]
