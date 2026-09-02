from __future__ import annotations

from pathlib import Path
import json
import subprocess

from config import (
    FFMPEG,
    FFPROBE,
    PROCESSED,
    WATERMARK,
    WATERMARK_WIDTH_RATIO,
    WATERMARK_OPACITY,
    WATERMARK_MARGIN_RIGHT_RATIO,
    WATERMARK_MARGIN_BOTTOM_RATIO,
    VIDEO_CRF,
    VIDEO_PRESET,
    AUDIO_BITRATE,
)


def find_watermark() -> Path:
    WATERMARK.mkdir(
        parents=True,
        exist_ok=True,
    )

    png_files = sorted(
        [
            file
            for file in WATERMARK.iterdir()
            if file.is_file()
            and file.suffix.lower() == ".png"
        ],
        key=lambda file: file.name.lower(),
    )

    if not png_files:
        raise RuntimeError(
            "У папці Watermark немає PNG-файлу.\n"
            f"Поклади твій прозорий watermark сюди:\n{WATERMARK}"
        )

    return png_files[0]


def get_video_size(
    video: Path,
) -> tuple[int, int]:
    command = [
        str(FFPROBE),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
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
            "Не вдалося прочитати розмір відео:\n"
            + result.stderr
        )

    try:
        data = json.loads(
            result.stdout
        )

        streams = data.get(
            "streams",
            []
        )

        if not streams:
            raise ValueError(
                "FFprobe не знайшов відеопотік."
            )

        width = int(
            streams[0]["width"]
        )

        height = int(
            streams[0]["height"]
        )

        return width, height

    except Exception as exc:
        raise RuntimeError(
            "Не вдалося розібрати розмір відео."
        ) from exc


def validate_output(
    output_file: Path,
) -> None:
    if not output_file.exists():
        raise RuntimeError(
            "FFmpeg не створив вихідний MP4."
        )

    if output_file.stat().st_size < 100_000:
        raise RuntimeError(
            "Готовий MP4 підозріло малий — "
            "вважаю обробку невдалою."
        )

    command = [
        str(FFPROBE),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt",
        "-of", "json",
        str(output_file),
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
            "FFprobe не може прочитати готове відео:\n"
            + result.stderr
        )

    try:
        data = json.loads(
            result.stdout
        )
        streams = data.get(
            "streams",
            []
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "FFprobe повернув неправильний JSON "
            "для готового відео."
        ) from exc

    if not streams:
        raise RuntimeError(
            "У готовому MP4 немає відеопотоку."
        )

    stream = streams[0]

    if stream.get("codec_name") != "h264":
        raise RuntimeError(
            "Готове відео не H.264."
        )

    if stream.get("pix_fmt") != "yuv420p":
        raise RuntimeError(
            "Готове відео має неочікуваний pixel format: "
            f"{stream.get('pix_fmt')}"
        )


def add_watermark(
    video: Path,
) -> Path:
    print("")
    print("=" * 58)
    print(
        "VIDEO PROCESSING + WATERMARK".center(58)
    )
    print("=" * 58)
    print("")

    watermark = find_watermark()

    print("Watermark:")
    print(watermark)

    width, height = get_video_size(
        video
    )

    print("")
    print(
        f"Original size: {width}x{height}"
    )

    watermark_width = max(
        80,
        int(
            width
            * WATERMARK_WIDTH_RATIO
        ),
    )

    margin_right = max(
        20,
        int(
            width
            * WATERMARK_MARGIN_RIGHT_RATIO
        ),
    )

    margin_bottom = max(
        50,
        int(
            height
            * WATERMARK_MARGIN_BOTTOM_RATIO
        ),
    )

    PROCESSED.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        PROCESSED
        / f"{video.stem}_READY.mp4"
    )

    filter_complex = (
        f"[1:v]"
        f"scale={watermark_width}:-1,"
        f"format=rgba,"
        f"colorchannelmixer=aa={WATERMARK_OPACITY}"
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

        "-i",
        str(video),

        "-i",
        str(watermark),

        "-filter_complex",
        filter_complex,

        "-map",
        "[video]",

        "-map",
        "0:a?",

        "-c:v",
        "libx264",

        "-preset",
        VIDEO_PRESET,

        "-crf",
        str(VIDEO_CRF),

        "-pix_fmt",
        "yuv420p",

        "-profile:v",
        "high",

        "-tag:v",
        "avc1",

        "-c:a",
        "aac",

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        "48000",

        "-movflags",
        "+faststart",

        str(output_file),
    ]

    print("")
    print("Накладаю watermark...")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg не зміг обробити відео:\n\n"
            + result.stderr[-4000:]
        )

    validate_output(
        output_file
    )

    print("")
    print("WATERMARK: OK")
    print("Готове відео:")
    print(output_file)

    return output_file
