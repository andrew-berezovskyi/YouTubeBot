from __future__ import annotations

from pathlib import Path
import json
import re
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
    LOGS,
    METADATA,
    OLLAMA_HOST,
    METADATA_MODEL,
    METADATA_NUM_PREDICT,
    OLLAMA_KEEP_ALIVE,
    FIXED_HASHTAGS,
)


CLIENT = Client(host=OLLAMA_HOST)


# ============================================================
# AI METADATA
# ============================================================
#
# Тут теж НАВМИСНО немає JSON від моделі.
#
# AI повертає лише:
# TITLE:
# HOOK:
# HASHTAGS:
#
# Усе інше Python формує сам.
# ============================================================


def _analysis_text(video: Path, analysis: dict) -> str:
    parts = [
        video.name,
        str(analysis.get("video_type", "")),
        str(analysis.get("topic", "")),
        str(analysis.get("summary", "")),
        " ".join(
            map(str, analysis.get("events", []))
        ),
        " ".join(
            map(str, analysis.get("visible_text", []))
        ),
    ]

    return " ".join(parts).lower()


def _build_prompt(
    video: Path,
    analysis: dict,
) -> str:
    analysis_json = json.dumps(
        analysis,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
Create YouTube Shorts metadata from the factual video analysis below.

Original filename:
{video.name}

FACTUAL VIDEO ANALYSIS:
{analysis_json}

RULES:
- Do not invent anything that is not supported by the analysis.
- Natural American English.
- Make this Short distinguishable from similar videos.
- Avoid generic repeated titles.
- Avoid clickbait that changes what actually happens.
- Do not include #shorts in TITLE; Python adds it.
- Do not explain your reasoning.
- Do not use JSON.
- Do not use Markdown.

TITLE:
- catchy but accurate
- preferably 35-75 characters before #shorts
- 1-2 relevant emojis
- no unnecessary hashtags
- for ranking videos, "Ranking ..." is allowed when accurate

HOOK:
- one short casual sentence
- about 6-14 words
- specific to this video
- no corporate wording such as "This video showcases"

HASHTAGS:
- 4-8 topic-specific hashtags
- do NOT include #shorts, #viral, #usa, or #funny
- space-separated
- hashtags only

Return EXACTLY these 3 labeled lines:

TITLE: <title>
HOOK: <hook>
HASHTAGS: <hashtags>
""".strip()


def _clean_space(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.strip(),
    )


def _looks_like_garbage(text: str) -> bool:
    stripped = re.sub(
        r"\s+",
        "",
        text,
    )

    if len(stripped) < 20:
        return True

    if re.fullmatch(r"(.)\1{12,}", stripped):
        return True

    if stripped:
        max_count = max(
            stripped.count(ch)
            for ch in set(stripped)
        )

        if max_count / len(stripped) > 0.80:
            return True

    return False


def _parse_ai_metadata(text: str) -> dict:
    if not text:
        raise ValueError(
            "Metadata AI повернула порожню відповідь."
        )

    text = text.strip()

    if _looks_like_garbage(text):
        raise ValueError(
            "Metadata AI повернула сміттєву відповідь."
        )

    fields = {}

    for key, label in [
        ("title", "TITLE"),
        ("hook", "HOOK"),
        ("hashtags", "HASHTAGS"),
    ]:
        match = re.search(
            rf"(?im)^\s*{label}\s*:\s*(.+?)\s*$",
            text,
        )

        if match:
            fields[key] = match.group(1).strip()

    missing = [
        key
        for key in ["title", "hook", "hashtags"]
        if key not in fields
    ]

    if missing:
        raise ValueError(
            "Не вистачає metadata-полів: "
            + ", ".join(missing)
        )

    hashtag_list = re.findall(
        r"#[A-Za-z0-9_]+",
        fields["hashtags"],
    )

    return {
        "title": _clean_space(fields["title"]),
        "hook": _clean_space(fields["hook"]),
        "hashtags": hashtag_list,
    }


def _save_raw(attempt: int, text: str) -> Path:
    LOGS.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        LOGS
        / f"metadata_ai_attempt_{attempt}.txt"
    )

    path.write_text(
        text or "<EMPTY>",
        encoding="utf-8",
    )

    return path


def generate_ai_metadata(
    video: Path,
    analysis: dict,
) -> dict:
    prompt = _build_prompt(
        video,
        analysis,
    )

    last_error = None

    for attempt in range(1, 4):
        print("")
        print(
            f"METADATA AI attempt {attempt}/3..."
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
                think=False,
                options={
                    "temperature": 0.15,
                    "num_ctx": 4096,
                    "num_predict": METADATA_NUM_PREDICT,
                },
                keep_alive=OLLAMA_KEEP_ALIVE,
            )

            content = str(
                getattr(
                    getattr(response, "message", None),
                    "content",
                    "",
                ) or ""
            ).strip()

            debug = _save_raw(
                attempt,
                content,
            )

            print(
                "metadata raw:",
                debug,
            )

            parsed = _parse_ai_metadata(
                content
            )

            print("METADATA AI: OK")
            return parsed

        except ResponseError as exc:
            last_error = exc
            print(
                "Ollama metadata API error:"
            )
            print(exc)

        except Exception as exc:
            last_error = exc
            print(
                f"METADATA AI attempt {attempt} failed:"
            )
            print(exc)

        if attempt < 3:
            time.sleep(1)

    print("")
    print(
        "AI metadata не вдалася. "
        "Використовую Python fallback."
    )

    return _fallback_ai_metadata(
        video,
        analysis,
        last_error,
    )


# ============================================================
# PYTHON FALLBACKS
# ============================================================

def _fallback_title(
    video: Path,
    analysis: dict,
) -> str:
    topic = str(
        analysis.get(
            "topic",
            "",
        )
    ).strip()

    video_type = str(
        analysis.get(
            "video_type",
            "",
        )
    ).lower()

    if not topic:
        topic = "Funny Moment"

    topic_title = topic.title()

    if "ranking" in video_type:
        return f"Ranking {topic_title} 😂"

    if "gaming" in video_type or "pov" in video_type:
        return f"POV: {topic_title} 💀🎮"

    return f"{topic_title} 😂"


def _fallback_hook(
    video: Path,
    analysis: dict,
) -> str:
    text = _analysis_text(
        video,
        analysis,
    )

    if (
        "pvp" in text
        or "gaming" in text
        or "game" in text
    ):
        return (
            "This PvP moment turns chaotic way too fast 💀🎮"
        )

    if (
        "baby" in text
        or "kid" in text
        or "child" in text
        or "cute" in text
    ):
        return (
            "These cute moments just keep getting better 😂"
        )

    if (
        "waterpark" in text
        or "water park" in text
        or "waterslide" in text
    ):
        return (
            "These water park moments get crazier every second 😂🌊"
        )

    if "phone" in text and "drop" in text:
        return (
            "These phone drops are painful to watch 💀📱"
        )

    if "fail" in text:
        return (
            "This fail gets worse every second 💀"
        )

    return (
        "This Short gets better with every moment 😂"
    )


def _fallback_ai_metadata(
    video: Path,
    analysis: dict,
    error,
) -> dict:
    return {
        "title": _fallback_title(
            video,
            analysis,
        ),
        "hook": _fallback_hook(
            video,
            analysis,
        ),
        "hashtags": [],
        "_ai_error": (
            str(error)
            if error is not None
            else ""
        ),
    }


# ============================================================
# TITLE
# ============================================================

def clean_title(title: str) -> str:
    if not isinstance(title, str):
        title = ""

    title = _clean_space(title)

    # Прибираємо hashtags з AI-title.
    words = [
        word
        for word in title.split()
        if not word.startswith("#")
    ]

    title = " ".join(words).strip()

    if not title:
        title = "Funny Viral Moment 😂"

    title += " #shorts"

    # YouTube title max is 100 chars.
    # Залишаємо невеликий запас.
    if len(title) > 95:
        without_short = title.replace(
            " #shorts",
            "",
        )

        without_short = (
            without_short[:86]
            .rstrip()
        )

        title = (
            without_short
            + " #shorts"
        )

    return title


# ============================================================
# HOOK
# ============================================================

def clean_hook(
    hook: str,
    video: Path,
    analysis: dict,
) -> str:
    if not isinstance(hook, str):
        hook = ""

    hook = _clean_space(hook)

    bad_phrases = [
        "this video showcases",
        "this video features",
        "this compilation showcases",
        "in various settings",
        "the video depicts",
    ]

    bad = any(
        phrase in hook.lower()
        for phrase in bad_phrases
    )

    if (
        not hook
        or bad
        or len(hook) > 130
    ):
        return _fallback_hook(
            video,
            analysis,
        )

    return hook


# ============================================================
# QUESTION
# ============================================================

def create_question(
    video: Path,
    analysis: dict,
) -> str:
    text = _analysis_text(
        video,
        analysis,
    )

    if (
        "ranking" in text
        or "top 5" in text
        or "rank" in text
    ):
        return (
            "Which one deserves the #1 spot?"
        )

    if "phone" in text and "drop" in text:
        return (
            "Which drop was the unluckiest?"
        )

    if (
        "water park" in text
        or "waterpark" in text
        or "waterslide" in text
    ):
        return (
            "Which moment would you try first?"
        )

    if (
        "gaming" in text
        or "game" in text
        or "pvp" in text
    ):
        return (
            "Would you chase them or let them escape?"
        )

    if (
        "fail" in text
        or "fails" in text
    ):
        return (
            "Which fail was the craziest?"
        )

    return (
        "Which moment was your favorite?"
    )


# ============================================================
# HASHTAGS
# ============================================================

def get_filename_hashtags(
    video: Path,
) -> list[str]:
    return re.findall(
        r"#[A-Za-z0-9_]+",
        video.name,
    )


def get_topic_hashtags(
    video: Path,
    analysis: dict,
) -> list[str]:
    text = _analysis_text(
        video,
        analysis,
    )

    result = []

    if (
        "ranking" in text
        or "top 5" in text
        or "rank" in text
    ):
        result.append("#ranking")

    if any(
        word in text
        for word in [
            "baby",
            "babies",
            "kid",
            "kids",
            "child",
            "children",
        ]
    ):
        result.extend([
            "#kids",
            "#cute",
            "#funnykids",
            "#babies",
        ])

    if (
        "waterpark" in text
        or "water park" in text
    ):
        result.extend([
            "#waterpark",
            "#waterslide",
            "#summer",
        ])

    if "phone" in text:
        result.append("#phone")

    if (
        "drop" in text
        or "fail" in text
    ):
        result.append("#fails")

    if (
        "gaming" in text
        or "game" in text
        or "pvp" in text
    ):
        result.extend([
            "#gaming",
            "#pvp",
            "#gamingmemes",
            "#pov",
        ])

    if "prank" in text:
        result.append("#prank")

    if "reaction" in text:
        result.append("#reaction")

    if "running" in text or "escape" in text:
        result.append("#running")

    return result


def clean_hashtags(
    video: Path,
    analysis: dict,
    ai_hashtags,
) -> list[str]:
    if not isinstance(
        ai_hashtags,
        list,
    ):
        ai_hashtags = []

    combined = (
        FIXED_HASHTAGS
        + get_filename_hashtags(video)
        + get_topic_hashtags(
            video,
            analysis,
        )
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

        hashtag = hashtag.replace(
            " ",
            "",
        )

        hashtag = re.sub(
            r"[^\w#]",
            "",
            hashtag,
        )

        if len(hashtag) <= 1:
            continue

        key = hashtag.lower()

        # Прибираємо занадто загальний #happy.
        if key == "#happy":
            continue

        # Не тримаємо одночасно #baby + #babies.
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


# ============================================================
# FINAL METADATA
# ============================================================

def create_final_metadata(
    video: Path,
    analysis: dict,
    ai_metadata: dict,
) -> dict:
    title = clean_title(
        ai_metadata.get(
            "title",
            "",
        )
    )

    hook = clean_hook(
        ai_metadata.get(
            "hook",
            "",
        ),
        video,
        analysis,
    )

    question = create_question(
        video,
        analysis,
    )

    hashtags = clean_hashtags(
        video,
        analysis,
        ai_metadata.get(
            "hashtags",
            [],
        ),
    )

    description = (
        f"{hook}\n"
        f"{question}\n\n"
        f"Subscribe for more!"
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


# ============================================================
# SAVE
# ============================================================

def save_metadata(
    video: Path,
    analysis: dict,
    metadata: dict,
) -> tuple[Path, Path]:
    METADATA.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_file = (
        METADATA
        / f"{video.stem}.json"
    )

    txt_file = (
        METADATA
        / f"{video.stem}.txt"
    )

    payload = {
        "analysis": analysis,
        "youtube": metadata,
    }

    with open(
        json_file,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=4,
        )

    text = (
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

    txt_file.write_text(
        text,
        encoding="utf-8",
    )

    return json_file, txt_file


def generate_metadata(
    video: Path,
    analysis: dict,
) -> dict:
    print("")
    print("=" * 58)
    print("AI METADATA".center(58))
    print("=" * 58)
    print("")

    ai_metadata = generate_ai_metadata(
        video,
        analysis,
    )

    final_metadata = create_final_metadata(
        video,
        analysis,
        ai_metadata,
    )

    json_file, txt_file = save_metadata(
        video,
        analysis,
        final_metadata,
    )

    print("")
    print("Metadata saved:")
    print(json_file)
    print(txt_file)

    return final_metadata
