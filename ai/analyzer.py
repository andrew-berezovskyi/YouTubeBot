from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import time

try:
    from ollama import Client, ResponseError
except ImportError as exc:
    raise RuntimeError(
        "Не встановлена Python-бібліотека ollama.\n"
        "Виконай:\n"
        "python -m pip install -U ollama"
    ) from exc

from config import (
    FFMPEG,
    FFPROBE,
    FRAMES,
    LOGS,
    OLLAMA_HOST,
    VISION_MODEL,
    METADATA_MODEL,
    FRAME_WIDTH,
    FRAMES_UP_TO_20S,
    FRAMES_UP_TO_40S,
    FRAMES_UP_TO_60S,
    FRAMES_UP_TO_90S,
    FRAMES_OVER_90S,
    OLLAMA_NUM_CTX,
    VISION_FRAME_NUM_PREDICT,
    VISION_MERGE_NUM_PREDICT,
    OLLAMA_KEEP_ALIVE,
)


CLIENT = Client(host=OLLAMA_HOST)


# ============================================================
# DESIGN
# ============================================================
#
# OLD:
# 4-6 images -> one Qwen3-VL thinking request
# -> done_reason=length / empty content
#
# NEW:
# each frame -> ONE short vision request (instruct model)
# all short frame descriptions -> text-only qwen3:4b-instruct merge
#
# This is slower than one multimodal call, but much more stable
# and scales better to 30-60+ second videos.
# ============================================================


def ensure_environment() -> None:
    if not FFMPEG.exists():
        raise RuntimeError(
            f"Не знайдено FFmpeg:\n{FFMPEG}"
        )

    if not FFPROBE.exists():
        raise RuntimeError(
            f"Не знайдено FFprobe:\n{FFPROBE}"
        )

    LOGS.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)

    for model in [VISION_MODEL, METADATA_MODEL]:
        try:
            CLIENT.show(model)
        except Exception as exc:
            raise RuntimeError(
                f"Модель {model} не знайдена.\n\n"
                f"Перевір:\nollama list\n\n"
                f"Якщо це vision model, встанови:\n"
                f"ollama pull qwen3-vl:4b-instruct\n\n"
                f"Деталі: {exc}"
            ) from exc


def get_duration(video: Path) -> float:
    command = [
        str(FFPROBE),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Не вдалося визначити тривалість відео:\n"
            + result.stderr
        )

    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(
            "FFprobe повернув неправильну тривалість."
        ) from exc


def frame_count_for_duration(
    duration: float,
) -> int:
    if duration <= 20:
        return FRAMES_UP_TO_20S

    if duration <= 40:
        return FRAMES_UP_TO_40S

    if duration <= 60:
        return FRAMES_UP_TO_60S

    if duration <= 90:
        return FRAMES_UP_TO_90S

    return FRAMES_OVER_90S


def extract_frames(
    video: Path,
) -> list[tuple[Path, float]]:
    duration = get_duration(video)
    count = frame_count_for_duration(duration)

    print(
        f"Тривалість відео: {duration:.2f} сек."
    )
    print(
        f"Кадрів для аналізу: {count}"
    )

    if FRAMES.exists():
        shutil.rmtree(FRAMES)

    FRAMES.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Беремо кадри між 5% і 95% відео.
    # Це рідше ловить чорний старт/фініш.
    if count == 1:
        fractions = [0.5]
    else:
        fractions = [
            0.05
            + (0.90 * index / (count - 1))
            for index in range(count)
        ]

    frames: list[tuple[Path, float]] = []

    print("")
    print("Витягую кадри:")

    for index, fraction in enumerate(
        fractions,
        start=1,
    ):
        position = duration * fraction
        output = (
            FRAMES
            / f"frame_{index:02d}.jpg"
        )

        command = [
            str(FFMPEG),
            "-y",
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

        if (
            result.returncode == 0
            and output.exists()
        ):
            frames.append(
                (output, position)
            )

            print(
                f"Кадр {index}: "
                f"{position:.2f} сек."
            )
        else:
            print(
                f"Не вдалося створити кадр {index}."
            )

    if not frames:
        raise RuntimeError(
            "Не вдалося витягнути жодного кадру."
        )

    return frames


def _looks_like_garbage(
    text: str,
) -> bool:
    stripped = re.sub(
        r"\s+",
        "",
        text or "",
    )

    if len(stripped) < 15:
        return True

    if re.fullmatch(
        r"(.)\1{10,}",
        stripped,
    ):
        return True

    return False


def _save_raw(
    filename: str,
    text: str,
) -> Path:
    LOGS.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = LOGS / filename

    path.write_text(
        text or "<EMPTY>",
        encoding="utf-8",
    )

    return path


def analyze_single_frame(
    video: Path,
    frame: Path,
    timestamp: float,
    frame_number: int,
) -> str:
    prompt = f"""
Analyze ONE frame from a YouTube Short.

Video filename:
{video.name}

Timestamp:
{timestamp:.2f} seconds

Describe ONLY what is actually visible.

Return a concise answer in normal English with:
- main visible action/scene
- important people/objects
- useful on-screen text, including non-English text if readable

Do not explain your reasoning.
Do not guess hidden events.
Maximum 60 words.
""".strip()

    last_error = None

    for attempt in range(1, 3):
        try:
            response = CLIENT.chat(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [
                            str(frame)
                        ],
                    }
                ],
                stream=False,
                options={
                    "temperature": 0,
                    "num_ctx": OLLAMA_NUM_CTX,
                    "num_predict":
                        VISION_FRAME_NUM_PREDICT,
                },
                keep_alive=OLLAMA_KEEP_ALIVE,
            )

            content = str(
                getattr(
                    getattr(
                        response,
                        "message",
                        None,
                    ),
                    "content",
                    "",
                )
                or ""
            ).strip()

            debug = _save_raw(
                (
                    f"frame_{frame_number:02d}"
                    f"_attempt_{attempt}.txt"
                ),
                content,
            )

            if _looks_like_garbage(content):
                raise ValueError(
                    "Порожня/сміттєва vision-відповідь."
                )

            print(
                f"  AI кадр {frame_number}: OK"
            )

            return content

        except Exception as exc:
            last_error = exc

            print(
                f"  AI кадр {frame_number}, "
                f"спроба {attempt}: ERROR"
            )

            if attempt < 2:
                time.sleep(0.5)

    raise RuntimeError(
        f"Не вдалося проаналізувати кадр "
        f"{frame_number}: {last_error}"
    )


def analyze_all_frames(
    video: Path,
    frames: list[tuple[Path, float]],
) -> list[dict]:
    results = []

    print("")
    print("Аналізую кадри по одному:")

    for index, (
        frame,
        timestamp,
    ) in enumerate(
        frames,
        start=1,
    ):
        try:
            description = analyze_single_frame(
                video=video,
                frame=frame,
                timestamp=timestamp,
                frame_number=index,
            )

            results.append({
                "frame": index,
                "timestamp": timestamp,
                "description": description,
            })

        except Exception as exc:
            # Один невдалий кадр НЕ валить усе відео.
            print(
                f"  Кадр {index} пропущено: {exc}"
            )

    minimum_required = min(
        3,
        len(frames),
    )

    if len(results) < minimum_required:
        raise RuntimeError(
            "Занадто мало кадрів вдалося "
            "проаналізувати."
        )

    return results


def _merge_prompt(
    video: Path,
    frame_results: list[dict],
) -> str:
    lines = []

    for item in frame_results:
        lines.append(
            (
                f"[{item['timestamp']:.2f}s] "
                f"{item['description']}"
            )
        )

    observations = "\n".join(
        lines
    )

    return f"""
You are combining chronological observations from ONE YouTube Shorts video.

Original filename:
{video.name}

FRAME OBSERVATIONS:
{observations}

Use ONLY these observations and the filename as a minor clue.
Do not invent missing actions.
Focus on the overall concept that makes this Short distinct.

Return EXACTLY these 5 labeled lines.
Do not use JSON.
Do not use Markdown.
Do not explain reasoning.

VIDEO_TYPE: <specific short type>
TOPIC: <specific overall topic>
SUMMARY: <one factual sentence describing the whole Short>
VISIBLE_TEXT: <important visible text separated by || or NONE>
EVENTS: <up to 5 chronological factual events separated by ||>
""".strip()


def _clean(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.strip(),
    )


def _split_list(value: str) -> list[str]:
    value = _clean(value)

    if (
        not value
        or value.upper()
        in {
            "NONE",
            "N/A",
            "NO",
            "NOTHING",
        }
    ):
        return []

    return [
        _clean(part)
        for part in re.split(
            r"\s*\|\|\s*",
            value,
        )
        if _clean(part)
        and _clean(part).upper()
        not in {
            "NONE",
            "N/A",
        }
    ]


def parse_final_analysis(
    text: str,
) -> dict:
    if _looks_like_garbage(text):
        raise ValueError(
            "Merge-модель повернула "
            "порожню/сміттєву відповідь."
        )

    labels = {
        "video_type": "VIDEO_TYPE",
        "topic": "TOPIC",
        "summary": "SUMMARY",
        "visible_text": "VISIBLE_TEXT",
        "events": "EVENTS",
    }

    found = {}

    for key, label in labels.items():
        match = re.search(
            (
                rf"(?im)^\s*"
                rf"{re.escape(label)}"
                rf"\s*:\s*(.+?)\s*$"
            ),
            text,
        )

        if match:
            found[key] = (
                match.group(1).strip()
            )

    missing = [
        label
        for key, label in labels.items()
        if key not in found
    ]

    if missing:
        raise ValueError(
            "Не вистачає полів: "
            + ", ".join(missing)
        )

    result = {
        "video_type":
            _clean(found["video_type"]),
        "topic":
            _clean(found["topic"]),
        "summary":
            _clean(found["summary"]),
        "visible_text":
            _split_list(
                found["visible_text"]
            ),
        "events":
            _split_list(
                found["events"]
            )[:5],
    }

    if len(result["summary"]) < 20:
        raise ValueError(
            "SUMMARY надто короткий."
        )

    return result


def merge_frame_analyses(
    video: Path,
    frame_results: list[dict],
) -> dict:
    prompt = _merge_prompt(
        video,
        frame_results,
    )

    last_error = None

    for attempt in range(1, 3):
        print("")
        print(
            f"Об'єдную весь аналіз "
            f"(спроба {attempt}/2)..."
        )

        try:
            response = CLIENT.chat(
                model=METADATA_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                stream=False,
                options={
                    "temperature": 0,
                    "num_ctx": 4096,
                    "num_predict":
                        VISION_MERGE_NUM_PREDICT,
                },
                keep_alive=OLLAMA_KEEP_ALIVE,
            )

            content = str(
                getattr(
                    getattr(
                        response,
                        "message",
                        None,
                    ),
                    "content",
                    "",
                )
                or ""
            ).strip()

            _save_raw(
                f"vision_merge_{attempt}.txt",
                content,
            )

            result = parse_final_analysis(
                content
            )

            print(
                "FINAL VIDEO ANALYSIS: OK"
            )

            return result

        except Exception as exc:
            last_error = exc

            print(
                "Merge error:",
                exc,
            )

            if attempt < 2:
                time.sleep(0.5)

    raise RuntimeError(
        "Не вдалося об'єднати аналіз "
        f"відео: {last_error}"
    )


def analyze_video(
    video: Path,
) -> dict:
    ensure_environment()

    print("")
    print("=" * 58)
    print(
        "AI VIDEO ANALYSIS".center(58)
    )
    print("=" * 58)
    print("")

    frames = extract_frames(
        video
    )

    frame_results = analyze_all_frames(
        video,
        frames,
    )

    analysis = merge_frame_analyses(
        video,
        frame_results,
    )

    return analysis
