from pathlib import Path
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)

# ============================================================
# YOUTUBE BOT — FINAL
# ============================================================
BASE_DIR = Path(__file__).resolve().parent

FFMPEG = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
FFPROBE = Path(r"C:\ffmpeg\bin\ffprobe.exe")

INPUT_FOLDER = BASE_DIR / "ToUpload"
FRAMES_FOLDER = BASE_DIR / "Frames"
METADATA_FOLDER = BASE_DIR / "Metadata"
PROCESSED_FOLDER = BASE_DIR / "Processed"
WATERMARK_FOLDER = BASE_DIR / "Watermark"
PROFILE_DIR = BASE_DIR / "BrowserProfile"
UPLOADED_FOLDER = BASE_DIR / "Uploaded"
LOGS_FOLDER = BASE_DIR / "Logs"
HISTORY_FILE = LOGS_FOLDER / "upload_history.jsonl"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
MODEL = "qwen2.5vl:3b"

STUDIO_URL = "https://studio.youtube.com/?hl=en"

AUTO_PUBLISH = True
PROCESS_ALL_QUEUE = False
AUDIENCE_MODE = "not_made_for_kids"

FRAME_COUNT = 6
FRAME_WIDTH = 384

FIXED_HASHTAGS = [
    "#shorts",
    "#viral",
    "#usa",
    "#funny",
]


def ensure_folders():
    for folder in [
        INPUT_FOLDER, FRAMES_FOLDER, METADATA_FOLDER,
        PROCESSED_FOLDER, WATERMARK_FOLDER,
        UPLOADED_FOLDER, LOGS_FOLDER,
    ]:
        folder.mkdir(parents=True, exist_ok=True)


def print_header(text):
    print("")
    print("=" * 56)
    print(text.center(56))
    print("=" * 56)
    print("")


def die(message):
    raise RuntimeError(message)


def safe_target(folder: Path, filename: str) -> Path:
    target = folder / filename
    if not target.exists():
        return target

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source = Path(filename)
    return folder / f"{source.stem}_{stamp}{source.suffix}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def already_published(file_hash: str) -> bool:
    if not HISTORY_FILE.exists():
        return False

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if (
                    item.get("sha256") == file_hash
                    and item.get("status") == "published"
                ):
                    return True
    except OSError:
        return False

    return False


def append_history(record: dict):
    LOGS_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def cleanup_frames():
    try:
        if FRAMES_FOLDER.exists():
            shutil.rmtree(FRAMES_FOLDER)
    except Exception:
        pass


def check_ffmpeg():
    if not FFMPEG.exists():
        die(f"Не знайдено FFmpeg:\n{FFMPEG}")
    if not FFPROBE.exists():
        die(f"Не знайдено FFprobe:\n{FFPROBE}")


def ollama_is_running():
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        names = {item.get("name", "") for item in data.get("models", [])}
        return True, names
    except Exception:
        return False, set()


def ensure_ollama():
    print("Перевіряю Ollama...")
    running, models = ollama_is_running()

    if not running:
        print("Ollama не відповідає. Пробую запустити ollama serve...")
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as error:
            die(f"Не вдалося автоматично запустити Ollama.\n{error}")

        for _ in range(15):
            time.sleep(1)
            running, models = ollama_is_running()
            if running:
                break

    if not running:
        die("Ollama не запустилась. Відкрий Ollama вручну і повтори запуск.")

    if MODEL not in models and not any(name.startswith(MODEL) for name in models):
        die(f"Не знайдено модель {MODEL}.\nВиконай: ollama pull {MODEL}")

    print(f"Ollama: OK | модель: {MODEL}")


def check_browser_profile():
    if not PROFILE_DIR.exists():
        die(
            "Не знайдено BrowserProfile.\n\n"
            'Один раз запусти звичайний Chrome так:\n'
            '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
            '--user-data-dir="C:\\YouTubeBot\\BrowserProfile"\n\n'
            "Увійди в Google і відкрий YouTube Studio."
        )


def list_source_videos():
    extensions = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
    videos = [
        file for file in INPUT_FOLDER.iterdir()
        if file.is_file() and file.suffix.lower() in extensions
    ]
    videos.sort(key=lambda file: file.stat().st_mtime)
    return videos


def find_watermark():
    png_files = [
        file for file in WATERMARK_FOLDER.iterdir()
        if file.is_file() and file.suffix.lower() == ".png"
    ]
    if not png_files:
        die(f"У папці Watermark немає PNG-файлу:\n{WATERMARK_FOLDER}")
    return png_files[0]


def get_duration(video):
    command = [
        str(FFPROBE), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        die("Не вдалося визначити тривалість відео.\n" + result.stderr)
    try:
        return float(result.stdout.strip())
    except ValueError:
        die("FFprobe повернув неправильну тривалість відео.")


def get_video_size(video):
    command = [
        str(FFPROBE), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", str(video),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        die("Не вдалося прочитати розмір відео.\n" + result.stderr)

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        die("FFprobe не знайшов відеопотік.")

    return int(streams[0]["width"]), int(streams[0]["height"])


def extract_frames(video):
    duration = get_duration(video)
    print(f"Тривалість: {duration:.2f} сек.")

    cleanup_frames()
    FRAMES_FOLDER.mkdir(parents=True, exist_ok=True)

    fractions = [0.08, 0.24, 0.40, 0.56, 0.72, 0.88]
    if FRAME_COUNT != 6:
        fractions = [(i + 1) / (FRAME_COUNT + 1) for i in range(FRAME_COUNT)]

    positions = [duration * fraction for fraction in fractions]
    frames = []

    print("Витягую кадри:")
    for index, position in enumerate(positions, start=1):
        output = FRAMES_FOLDER / f"frame_{index:02d}.jpg"
        command = [
            str(FFMPEG), "-y",
            "-ss", f"{position:.3f}",
            "-i", str(video),
            "-frames:v", "1",
            "-vf", f"scale={FRAME_WIDTH}:-2",
            "-q:v", "3",
            str(output),
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0 and output.exists():
            frames.append(output)
            print(f"  кадр {index}: {position:.2f} сек.")

    if not frames:
        die("Не вдалося витягнути кадри з відео.")
    return frames


def image_to_base64(path):
    with open(path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def print_http_error(error):
    print_header("ПОМИЛКА OLLAMA")
    print("HTTP CODE:", error.code)
    try:
        print(error.read().decode("utf-8", errors="replace"))
    except Exception:
        pass


def ollama_chat(messages, num_predict=300):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": num_predict,
        },
        "keep_alive": "5m",
    }

    request = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=1200) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        print_http_error(error)
        raise RuntimeError("Ollama повернула HTTP-помилку.")
    except urllib.error.URLError as error:
        raise RuntimeError(f"Не вдалося підключитися до Ollama:\n{error}")

    print("Ollama done_reason:", result.get("done_reason", "unknown"))

    try:
        content = result["message"]["content"]
    except KeyError:
        raise RuntimeError("Ollama не повернула message.content.")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("AI повернув неправильний JSON:")
        print(content)
        raise RuntimeError("Не вдалося розібрати JSON від AI.")


def analyze_video(video, frames):
    print_header("ЕТАП 1 — AI АНАЛІЗ")
    images = [image_to_base64(frame) for frame in frames]

    prompt = f"""
Analyze chronological frames from ONE YouTube Shorts video.

Original filename:
{video.name}

The images are the primary source.
The filename is only an additional clue.

Be factual.
NEVER invent events that are not visible.

Identify:
- video type
- main topic
- important visible text
- up to 5 factual events
- one factual overall summary

Recognize ranking videos when numbering, Top 5,
Ranking, #1, #2, etc. are visible.

Return ONLY valid short JSON:
{{
  "video_type": "ranking",
  "topic": "cute kid moments",
  "visible_text": ["visible text"],
  "events": ["factual visible event"],
  "summary": "one factual sentence"
}}
"""

    return ollama_chat(
        [{"role": "user", "content": prompt, "images": images}],
        num_predict=350,
    )


def generate_ai_metadata(video, analysis):
    print_header("ЕТАП 2 — AI METADATA")
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)

    prompt = f"""
Create metadata for a YouTube Shorts video.

Original filename:
{video.name}

FACTUAL VIDEO ANALYSIS:
{analysis_json}

Do NOT invent anything beyond this factual analysis.

TITLE:
- natural American English
- catchy but accurate
- 1-2 relevant emojis
- preferably 40-75 characters
- suitable for viral Shorts
- no keyword stuffing
- no unnecessary hashtags
- do NOT include #shorts because Python will add it

For ranking videos prefer natural titles like:
Ranking the Cutest Kid Moments 😂👶
Ranking the Funniest Water Park Moments 😂🌊
The Unluckiest Phone Drops Ever 💀📱

HOOK:
Write ONE short casual sentence about the overall theme.
Maximum about 12 words.
Do not focus on a random minor object from one frame.

HASHTAGS:
Generate 4-8 topic-specific hashtags.
Do NOT include #shorts, #viral, #usa or #funny.
Python adds those automatically.

Return ONLY JSON:
{{
  "title": "title",
  "hook": "short casual hook",
  "hashtags": ["#kids", "#cute"]
}}
"""

    return ollama_chat(
        [{"role": "user", "content": prompt}],
        num_predict=250,
    )


def analysis_text(video, analysis):
    parts = [
        video.name,
        str(analysis.get("video_type", "")),
        str(analysis.get("topic", "")),
        str(analysis.get("summary", "")),
        " ".join(map(str, analysis.get("events", []))),
        " ".join(map(str, analysis.get("visible_text", []))),
    ]
    return " ".join(parts).lower()


def create_question(video, analysis):
    text = analysis_text(video, analysis)

    if "ranking" in text or "top 5" in text or "rank" in text:
        return "Which one deserves the #1 spot?"
    if "phone" in text and "drop" in text:
        return "Which drop was the unluckiest?"
    if "water park" in text or "waterpark" in text or "waterslide" in text:
        return "Which moment would you try first?"
    if "gaming" in text or "game" in text or "pvp" in text:
        return "Which moment was the best?"
    if "fail" in text or "fails" in text:
        return "Which fail was the craziest?"
    return "Which moment was your favorite?"


def create_fallback_hook(video, analysis):
    text = analysis_text(video, analysis)

    if "phone" in text and "drop" in text:
        return "These phone drop moments are painful to watch 💀📱"
    if "waterpark" in text or "water park" in text or "waterslide" in text:
        return "These water park moments just keep getting crazier 😂🌊"
    if "gaming" in text or "pvp" in text:
        return "These gaming moments get more chaotic every second 🎮😂"
    if (
        "baby" in text or "kid" in text or "child" in text
        or "children" in text or "cute" in text
    ):
        return "These cute kid moments just keep getting better 😂"
    if "fail" in text:
        return "These fails just keep getting worse 💀"
    if "ranking" in text:
        return "These ranked moments just keep getting better 😂"
    return "This Short gets better with every moment 😂"


def clean_title(title):
    if not isinstance(title, str):
        title = ""

    title = re.sub(r"\s+", " ", title).strip()
    title = " ".join(
        word for word in title.split()
        if not word.startswith("#")
    ).strip()

    if not title:
        title = "Funny Viral Moment 😂"

    title += " #shorts"

    if len(title) > 95:
        title_without = title.replace(" #shorts", "")[:86].rstrip()
        title = title_without + " #shorts"

    return title


def clean_hook(hook, video, analysis):
    if not isinstance(hook, str):
        hook = ""

    hook = re.sub(r"\s+", " ", hook).strip()

    bad_phrases = [
        "this video showcases",
        "this video features",
        "this compilation showcases",
        "in various settings",
        "involving children and",
    ]

    bad = any(
        phrase in hook.lower()
        for phrase in bad_phrases
    )

    if not hook or bad or len(hook) > 130:
        return create_fallback_hook(video, analysis)

    return hook


def get_filename_hashtags(video):
    return re.findall(
        r"#[A-Za-z0-9_]+",
        video.name
    )


def get_topic_hashtags(video, analysis):
    text = analysis_text(video, analysis)
    result = []

    if "ranking" in text or "top 5" in text or "rank" in text:
        result.append("#ranking")

    if any(
        word in text
        for word in [
            "baby", "babies", "kid",
            "kids", "child", "children",
        ]
    ):
        result.extend([
            "#kids",
            "#cute",
            "#funnykids",
            "#babies",
        ])

    if "waterpark" in text or "water park" in text:
        result.extend([
            "#waterpark",
            "#waterslide",
            "#summer",
        ])

    if "phone" in text:
        result.append("#phone")

    if "drop" in text or "fail" in text:
        result.append("#fails")

    if "gaming" in text or "game" in text or "pvp" in text:
        result.extend([
            "#gaming",
            "#pvp",
            "#games",
        ])

    if "prank" in text:
        result.append("#prank")

    if "reaction" in text:
        result.append("#reaction")

    return result


def clean_hashtags(video, analysis, ai_hashtags):
    if not isinstance(ai_hashtags, list):
        ai_hashtags = []

    combined = (
        FIXED_HASHTAGS
        + get_filename_hashtags(video)
        + get_topic_hashtags(video, analysis)
        + ai_hashtags
    )

    result = []
    seen = set()

    for hashtag in combined:
        if not isinstance(hashtag, str):
            continue

        hashtag = hashtag.strip()
        if not hashtag:
            continue

        if not hashtag.startswith("#"):
            hashtag = "#" + hashtag

        hashtag = hashtag.replace(" ", "")
        hashtag = re.sub(r"[^\w#]", "", hashtag)

        if len(hashtag) <= 1:
            continue

        key = hashtag.lower()

        # прибираємо слабкий загальний тег
        if key == "#happy":
            continue

        # не тримаємо одночасно #baby і #babies
        if key == "#baby" and "#babies" in seen:
            continue

        if key == "#babies" and "#baby" in seen:
            result = [
                item
                for item in result
                if item.lower() != "#baby"
            ]
            seen.discard("#baby")

        if key not in seen:
            seen.add(key)
            result.append(hashtag)

    return result[:12]


def create_final_metadata(video, analysis, ai_metadata):
    title = clean_title(
        ai_metadata.get("title", "")
    )

    hook = clean_hook(
        ai_metadata.get("hook", ""),
        video,
        analysis,
    )

    question = create_question(
        video,
        analysis
    )

    hashtags = clean_hashtags(
        video,
        analysis,
        ai_metadata.get("hashtags", []),
    )

    description = (
        f"{hook}\n"
        f"{question}\n\n"
        "Subscribe for more!"
    )

    final_description = (
        description
        + "\n\n"
        + " ".join(hashtags)
    )

    return {
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "final_description": final_description,
    }


def save_metadata(video, analysis, metadata):
    METADATA_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    json_file = (
        METADATA_FOLDER
        / f"{video.stem}.json"
    )

    txt_file = (
        METADATA_FOLDER
        / f"{video.stem}.txt"
    )

    data = {
        "analysis": analysis,
        "youtube": metadata,
    }

    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4,
        )

    txt = (
        "========================================\n"
        "VIDEO ANALYSIS\n"
        "========================================\n\n"
        f"TYPE:\n{analysis.get('video_type', '')}\n\n"
        f"TOPIC:\n{analysis.get('topic', '')}\n\n"
        f"SUMMARY:\n{analysis.get('summary', '')}\n\n"
        "========================================\n"
        "YOUTUBE\n"
        "========================================\n\n"
        f"TITLE:\n{metadata['title']}\n\n"
        f"DESCRIPTION:\n{metadata['final_description']}\n"
    )

    with open(txt_file, "w", encoding="utf-8") as file:
        file.write(txt)

    return json_file, txt_file


def add_watermark(video, watermark):
    print_header("ЕТАП 3 — WATERMARK")

    PROCESSED_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    width, height = get_video_size(video)

    watermark_width = max(
        80,
        int(width * 0.14)
    )

    margin_right = max(
        20,
        int(width * 0.035)
    )

    margin_bottom = max(
        50,
        int(height * 0.13)
    )

    output_file = (
        PROCESSED_FOLDER
        / f"{video.stem}_READY.mp4"
    )

    filter_complex = (
        f"[1:v]"
        f"scale={watermark_width}:-1,"
        f"format=rgba,"
        f"colorchannelmixer=aa=0.80"
        f"[wm];"
        f"[0:v][wm]"
        f"overlay="
        f"x=W-w-{margin_right}:"
        f"y=H-h-{margin_bottom},"
        f"format=yuv420p"
        f"[video]"
    )

    command = [
        str(FFMPEG),
        "-y",
        "-i", str(video),
        "-i", str(watermark),
        "-filter_complex", filter_complex,
        "-map", "[video]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-tag:v", "avc1",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        str(output_file),
    ]

    print("Накладаю watermark...")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        print(result.stderr)
        die("FFmpeg не зміг створити готове відео.")

    print("Готове відео:")
    print(output_file)
    return output_file


def save_debug(page, name):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    screenshot = (
        LOGS_FOLDER
        / f"debug_{name}_{stamp}.png"
    )

    html_file = (
        LOGS_FOLDER
        / f"debug_{name}_{stamp}.html"
    )

    try:
        page.screenshot(
            path=str(screenshot),
            full_page=True,
        )
    except Exception:
        pass

    try:
        html_file.write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception:
        pass

    print("DEBUG:")
    print(screenshot)
    print(html_file)


def open_create_menu(page):
    print("Шукаю Create...")

    selectors = [
        "#create-icon",
        "ytcp-button#create-icon",
        'button[aria-label*="Create" i]',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first

            if locator.count() > 0:
                locator.wait_for(
                    state="visible",
                    timeout=5000,
                )

                locator.click()
                print(
                    "Create знайдено:",
                    selector
                )
                return

        except Exception:
            pass

    locator = page.get_by_role(
        "button",
        name=re.compile(
            r"^Create$",
            re.IGNORECASE,
        ),
    ).first

    locator.wait_for(
        state="visible",
        timeout=10000,
    )

    locator.click()


def click_upload_videos(page):
    print("Шукаю Upload videos...")

    page.wait_for_timeout(800)

    try:
        item = page.get_by_text(
            "Upload videos",
            exact=True,
        ).first

        item.wait_for(
            state="visible",
            timeout=10000,
        )

        item.click()
        print("Upload videos знайдено.")
        return

    except Exception:
        pass

    selector = (
        'tp-yt-paper-item:has-text("Upload videos")'
    )

    item = page.locator(selector).first

    item.wait_for(
        state="visible",
        timeout=10000,
    )

    item.click()


def click_next(page):
    try:
        button = page.locator(
            "#next-button"
        ).filter(
            visible=True
        ).first

        button.wait_for(
            state="visible",
            timeout=120000,
        )

        expect(button).to_be_enabled(
            timeout=120000
        )

        button.click()
        page.wait_for_timeout(1200)
        return

    except Exception:
        pass

    button = page.get_by_role(
        "button",
        name="Next",
        exact=True,
    ).first

    button.wait_for(
        state="visible",
        timeout=120000,
    )

    expect(button).to_be_enabled(
        timeout=120000
    )

    button.click()
    page.wait_for_timeout(1200)


def select_audience(page):
    if AUDIENCE_MODE != "not_made_for_kids":
        raise RuntimeError(
            "Невідомий AUDIENCE_MODE."
        )

    print('Вибираю "No, it\'s not made for kids"...')

    radio = page.locator(
        '[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
    ).first

    try:
        radio.wait_for(
            state="attached",
            timeout=10000,
        )

        radio.click()
        print("Audience встановлено.")
        return

    except Exception:
        pass

    option = page.get_by_text(
        re.compile(
            r"No,\s*it's not made for kids",
            re.IGNORECASE,
        )
    ).first

    option.wait_for(
        state="visible",
        timeout=10000,
    )

    option.click()
    print("Audience встановлено.")


def select_public(page):
    print("Вибираю PUBLIC...")

    selectors = [
        'tp-yt-paper-radio-button[name="PUBLIC"]',
        '[name="PUBLIC"]',
    ]

    for selector in selectors:
        try:
            radio = page.locator(
                selector
            ).filter(
                visible=True
            ).first

            if radio.count() > 0:
                radio.wait_for(
                    state="visible",
                    timeout=10000,
                )

                radio.click()
                page.wait_for_timeout(1000)

                print(
                    "PUBLIC вибрано через:",
                    selector
                )
                return

        except Exception:
            pass

    public_text = page.get_by_text(
        "Public",
        exact=True,
    ).filter(
        visible=True
    )

    for i in range(public_text.count()):
        candidate = public_text.nth(i)

        try:
            candidate.scroll_into_view_if_needed()
            candidate.click()
            page.wait_for_timeout(1000)
            print("PUBLIC вибрано через текст.")
            return
        except Exception:
            continue

    save_debug(
        page,
        "public_not_found"
    )

    raise RuntimeError(
        "Не вдалося знайти PUBLIC."
    )


def try_get_video_url(page):
    selectors = [
        'a[href*="youtube.com/shorts/"]',
        'a[href*="youtube.com/watch?v="]',
        'a[href*="youtu.be/"]',
        'a[href*="/shorts/"]',
        'a[href*="/watch?v="]',
    ]

    for selector in selectors:
        try:
            links = page.locator(selector)

            for i in range(links.count()):
                href = links.nth(i).get_attribute("href")

                if not href:
                    continue

                if href.startswith("/"):
                    href = "https://www.youtube.com" + href

                if (
                    "/shorts/" in href
                    or "watch?v=" in href
                    or "youtu.be/" in href
                ):
                    return href

        except Exception:
            pass

    return None


def publish_video(page):
    print("Чекаю готовності кнопки Publish...")

    button = page.locator(
        "#done-button"
    ).filter(
        visible=True
    ).first

    try:
        button.wait_for(
            state="visible",
            timeout=120000,
        )

        expect(button).to_be_enabled(
            timeout=600000
        )

    except Exception:
        print(
            "#done-button не підійшов, "
            "шукаю Publish за назвою..."
        )

        button = page.get_by_role(
            "button",
            name=re.compile(
                r"^(Publish|Save)$",
                re.IGNORECASE,
            )
        ).filter(
            visible=True
        ).first

        button.wait_for(
            state="visible",
            timeout=120000,
        )

        expect(button).to_be_enabled(
            timeout=600000
        )

    print_header("НАТИСКАЮ PUBLISH")
    button.click()
    page.wait_for_timeout(3000)


def verify_publish(page):
    print("Перевіряю результат публікації...")

    start = time.time()

    while time.time() - start < 120:
        try:
            success_text = page.get_by_text(
                re.compile(
                    r"(video published|"
                    r"video has been published|"
                    r"published)",
                    re.IGNORECASE,
                )
            ).filter(
                visible=True
            )

            if success_text.count() > 0:
                return True

        except Exception:
            pass

        try:
            dialog = page.locator(
                "ytcp-uploads-dialog"
            )

            if (
                dialog.count() == 0
                or not dialog.first.is_visible()
            ):
                return True

        except Exception:
            pass

        page.wait_for_timeout(1000)

    return False


def upload_to_youtube(ready_video, metadata):
    print_header("ЕТАП 4 — YOUTUBE UPLOAD")

    title = metadata["title"]
    description = metadata["final_description"]

    with sync_playwright() as p:
        context = None

        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=False,
                no_viewport=True,
                chromium_sandbox=True,
                args=["--start-maximized"],
            )

            context.set_default_timeout(30000)

            if context.pages:
                page = context.pages[0]
            else:
                page = context.new_page()

            print("Відкриваю YouTube Studio...")

            page.goto(
                STUDIO_URL,
                wait_until="domcontentloaded",
                timeout=120000,
            )

            page.wait_for_timeout(5000)

            if "accounts.google.com" in page.url:
                raise RuntimeError(
                    "Google-сесія не активна. "
                    "Потрібно заново увійти в BrowserProfile."
                )

            open_create_menu(page)
            click_upload_videos(page)

            file_input = page.locator(
                'input[type="file"]'
            ).first

            file_input.wait_for(
                state="attached",
                timeout=30000,
            )

            print("Передаю відеофайл...")
            file_input.set_input_files(
                str(ready_video)
            )

            print("Чекаю Details...")

            title_box = page.locator(
                "#title-textarea #textbox"
            ).first

            title_box.wait_for(
                state="visible",
                timeout=120000,
            )

            description_box = page.locator(
                "#description-textarea #textbox"
            ).first

            print("Вставляю TITLE...")
            title_box.fill(title)

            print("Вставляю DESCRIPTION...")
            description_box.fill(description)

            select_audience(page)
            page.wait_for_timeout(1000)

            video_url = try_get_video_url(page)

            print("Video elements...")
            click_next(page)

            print("Checks...")
            click_next(page)

            print("Visibility...")
            click_next(page)

            select_public(page)

            if not AUTO_PUBLISH:
                print(
                    "AUTO_PUBLISH=False — "
                    "зупиняюсь перед Publish."
                )
                input(
                    "Перевір браузер і натисни ENTER..."
                )
                return {
                    "success": False,
                    "published": False,
                    "url": video_url,
                }

            publish_video(page)

            success = verify_publish(page)

            if not video_url:
                video_url = try_get_video_url(page)

            if not success:
                save_debug(
                    page,
                    "publish_unconfirmed"
                )
                raise RuntimeError(
                    "Не вдалося підтвердити "
                    "успішну публікацію."
                )

            print_header("ПУБЛІКАЦІЯ УСПІШНА")

            if video_url:
                print("VIDEO URL:")
                print(video_url)

            success_screen = (
                LOGS_FOLDER
                / "publish_success.png"
            )

            try:
                page.screenshot(
                    path=str(success_screen),
                    full_page=True,
                )
            except Exception:
                pass

            return {
                "success": True,
                "published": True,
                "url": video_url,
            }

        except PlaywrightTimeoutError as error:
            if context and context.pages:
                save_debug(
                    context.pages[0],
                    "timeout"
                )
            raise RuntimeError(
                "Playwright timeout:\n"
                f"{error}"
            )

        except Exception:
            if context and context.pages:
                try:
                    save_debug(
                        context.pages[0],
                        "error"
                    )
                except Exception:
                    pass
            raise

        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


def move_source_to_uploaded(source_video):
    target = safe_target(
        UPLOADED_FOLDER,
        source_video.name
    )

    shutil.move(
        str(source_video),
        str(target)
    )

    return target


def move_duplicate_to_uploaded(source_video):
    duplicate_folder = (
        UPLOADED_FOLDER
        / "SkippedDuplicates"
    )

    duplicate_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    target = safe_target(
        duplicate_folder,
        source_video.name
    )

    shutil.move(
        str(source_video),
        str(target)
    )

    return target


def process_one_video(video, watermark):
    source_hash = sha256_file(video)

    print_header(
        f"ОБРОБКА: {video.name}"
    )

    if already_published(source_hash):
        print(
            "Цей файл уже є в історії "
            "як опублікований."
        )

        moved = move_duplicate_to_uploaded(
            video
        )

        print("Переміщено в:")
        print(moved)
        return True

    try:
        frames = extract_frames(video)

        analysis = analyze_video(
            video,
            frames
        )

        print("")
        print("AI зрозумів:")
        print(
            analysis.get(
                "summary",
                ""
            )
        )

        ai_metadata = generate_ai_metadata(
            video,
            analysis
        )

        metadata = create_final_metadata(
            video,
            analysis,
            ai_metadata
        )

        json_file, txt_file = save_metadata(
            video,
            analysis,
            metadata
        )

        print("")
        print("TITLE:")
        print(metadata["title"])

        print("")
        print("DESCRIPTION:")
        print(metadata["final_description"])

        ready_video = add_watermark(
            video,
            watermark
        )

        upload_result = upload_to_youtube(
            ready_video,
            metadata
        )

        if not upload_result.get("published"):
            print(
                "Відео не було опубліковано. "
                "Оригінал залишаю в ToUpload."
            )
            return False

        moved_source = move_source_to_uploaded(
            video
        )

        record = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "status": "published",
            "source_filename": video.name,
            "source_moved_to": str(moved_source),
            "sha256": source_hash,
            "ready_video": str(ready_video),
            "metadata_json": str(json_file),
            "metadata_txt": str(txt_file),
            "title": metadata["title"],
            "description": metadata["final_description"],
            "youtube_url": upload_result.get("url"),
        }

        append_history(record)
        cleanup_frames()

        print_header("ВІДЕО ПОВНІСТЮ ГОТОВЕ")
        print("Оригінал переміщено в:")
        print(moved_source)
        print("")
        print("Історія:")
        print(HISTORY_FILE)

        return True

    except Exception as error:
        cleanup_frames()

        append_history({
            "timestamp": datetime.now().astimezone().isoformat(),
            "status": "error",
            "source_filename": video.name,
            "sha256": source_hash,
            "error": str(error),
        })

        print_header("ПОМИЛКА ОБРОБКИ")
        print(
            type(error).__name__,
            ":",
            error
        )
        print("")
        print(
            "Оригінал НЕ переміщено. "
            "Він залишається в ToUpload."
        )

        return False


def main():
    os.environ.setdefault("PYTHONUTF8", "1")

    ensure_folders()
    check_ffmpeg()
    ensure_ollama()
    check_browser_profile()

    watermark = find_watermark()

    print_header("YOUTUBE BOT — FINAL")

    print("Watermark:")
    print(watermark)
    print("")
    print("AUTO_PUBLISH:", AUTO_PUBLISH)
    print("PROCESS_ALL_QUEUE:", PROCESS_ALL_QUEUE)
    print("YouTube Studio: English")
    print("")

    videos = list_source_videos()

    if not videos:
        print("У папці ToUpload немає відео.")
        print("Додай MP4 і запусти START_BOT.bat.")
        return

    if not PROCESS_ALL_QUEUE:
        videos = videos[:1]

    success_count = 0

    for index, video in enumerate(
        videos,
        start=1
    ):
        print(
            f"\nЧерга: {index}/{len(videos)}"
        )

        success = process_one_video(
            video,
            watermark
        )

        if success:
            success_count += 1
        else:
            # Якщо щось зламалося на одному ролику,
            # наступні автоматично не публікуємо.
            break

    print_header("СЕСІЮ ЗАВЕРШЕНО")
    print(
        f"Успішно оброблено: "
        f"{success_count}/{len(videos)}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nЗупинено користувачем.")
    except Exception as error:
        print_header("КРИТИЧНА ПОМИЛКА")
        print(
            type(error).__name__,
            ":",
            error
        )
        sys.exit(1)
