from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import os
import uuid

from database.db import (
    init_db,
    create_run,
    cancel_run,
    find_unfinished_run,
    ensure_video,
    get_video,
    create_queue_item,
    get_next_queue_item,
    list_queue_items,
    queue_counts,
    recover_run_for_resume,
    update_queue_item,
    refresh_run_counts,
    finalize_run,
)


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".avi",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def list_source_videos(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)

    videos = [
        file
        for file in folder.iterdir()
        if (
            file.is_file()
            and file.suffix.lower() in VIDEO_EXTENSIONS
        )
    ]

    videos.sort(
        key=lambda file:
        file.stat().st_mtime
    )

    return videos



def _env_bool(
    name: str,
) -> bool | None:
    value = os.getenv(name)

    if value is None:
        return None

    value = value.strip().lower()

    if value in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }:
        return True

    if value in {
        "0",
        "false",
        "no",
        "n",
        "off",
    }:
        return False

    return None


def _gui_requested_count(
    available: int,
) -> int | None:
    value = os.getenv(
        "YOUTUBEBOT_GUI_COUNT"
    )

    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    if value.lower() == "all":
        return available

    try:
        count = int(value)
    except ValueError:
        return None

    if count <= 0:
        return None

    return min(
        count,
        available,
    )

def ask_video_count(available: int) -> int:
    if available <= 0:
        raise RuntimeError(
            "У ToUpload немає відео."
        )

    gui_count = _gui_requested_count(
        available
    )

    if gui_count is not None:
        print("")
        print(
            f"[GUI] Requested videos: {gui_count}"
        )
        return gui_count

    while True:
        print("")
        print(
            f"Доступно нових відео: {available}"
        )
        print(
            "Скільки обробити? "
            "Введи число або ALL."
        )

        answer = input("> ").strip()

        if answer.lower() == "all":
            return available

        try:
            count = int(answer)
        except ValueError:
            print(
                "Введи ціле число або ALL."
            )
            continue

        if count <= 0:
            print(
                "Кількість має бути більшою за 0."
            )
            continue

        return min(count, available)


def _ask_yes_no(
    question: str,
    default: bool = True,
) -> bool:
    suffix = (
        "[Y/n]"
        if default
        else "[y/N]"
    )

    while True:
        answer = input(
            f"{question} {suffix}\n> "
        ).strip().lower()

        if not answer:
            return default

        if answer in {
            "y",
            "yes",
            "т",
            "так",
        }:
            return True

        if answer in {
            "n",
            "no",
            "н",
            "ні",
        }:
            return False

        print(
            "Введи Y або N."
        )


def _stage_from_existing_video(
    video: dict,
) -> str:
    if video.get("status") == "published":
        return "published"

    ready_path = video.get("ready_path")

    if (
        ready_path
        and Path(ready_path).exists()
        and video.get("title")
        and video.get("description")
    ):
        return "ready_to_upload"

    if (
        video.get("title")
        and video.get("description")
    ):
        return "metadata_ready"

    if (
        video.get("video_type")
        and video.get("topic")
        and video.get("summary")
    ):
        return "analyzed"

    return "queued"


def _new_session_id() -> str:
    return (
        datetime.now()
        .strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid.uuid4().hex[:6]
    )


def create_new_queue(
    videos: list[Path],
) -> dict:
    count = ask_video_count(
        len(videos)
    )

    selected = videos[:count]
    session_id = _new_session_id()

    run_id = create_run(
        session_id=session_id,
        requested=count,
    )

    for index, video_path in enumerate(
        selected,
        start=1,
    ):
        digest = sha256_file(
            video_path
        )

        video_id = ensure_video(
            run_id=run_id,
            queue_index=index,
            source_path=video_path,
            sha256=digest,
        )

        video = get_video(
            video_id
        ) or {}

        stage = _stage_from_existing_video(
            video
        )

        item_id = create_queue_item(
            run_id=run_id,
            video_id=video_id,
            queue_index=index,
            source_path=video_path,
            sha256=digest,
            stage=stage,
        )

        if stage == "published":
            update_queue_item(
                item_id,
                status="done",
                stage="published",
                finished=True,
            )

    refresh_run_counts(
        run_id
    )

    return {
        "run_id": run_id,
        "session_id": session_id,
        "requested": count,
        "resumed": False,
    }


def get_or_create_queue(
    videos: list[Path],
) -> dict:
    init_db()

    unfinished = find_unfinished_run()

    if unfinished:
        run_id = int(
            unfinished["id"]
        )

        counts = queue_counts(
            run_id
        )

        print("")
        print("=" * 62)
        print(
            "ЗНАЙДЕНО НЕЗАВЕРШЕНУ SQLITE-ЧЕРГУ".center(62)
        )
        print("=" * 62)
        print("")
        print(
            f"Run ID: {run_id}"
        )
        print(
            f"Session: {unfinished.get('session_id')}"
        )
        print(
            f"Done: {counts['done']}/{counts['total']}"
        )
        print(
            f"Failed: {counts['failed']}"
        )
        print(
            f"Blocked: {counts['blocked']}"
        )

        resume = _env_bool(
            "YOUTUBEBOT_GUI_RESUME"
        )

        if resume is None:
            resume = _ask_yes_no(
                "Продовжити цю чергу?",
                default=True,
            )
        else:
            print(
                "[GUI] Resume unfinished queue:",
                "YES" if resume else "NO",
            )

        if resume:
            items = list_queue_items(
                run_id
            )

            has_uploading = any(
                str(
                    item.get("stage")
                    or ""
                )
                == "uploading"
                for item in items
                if item.get("status") != "done"
            )

            retry_uploads = False

            if has_uploading:
                print("")
                print(
                    "Є відео, де попередній запуск "
                    "обірвався ПІД ЧАС YouTube upload."
                )
                print(
                    "Автоповтор може теоретично створити "
                    "дублікат, якщо Publish встиг пройти."
                )

                retry_uploads = _env_bool(
                    "YOUTUBEBOT_GUI_RETRY_INTERRUPTED"
                )

                if retry_uploads is None:
                    retry_uploads = _ask_yes_no(
                        "Повторити такі upload?",
                        default=False,
                    )
                else:
                    print(
                        "[GUI] Retry interrupted upload:",
                        (
                            "YES"
                            if retry_uploads
                            else "NO"
                        ),
                    )

            info = recover_run_for_resume(
                run_id,
                retry_interrupted_uploads=(
                    retry_uploads
                ),
            )

            print("")
            print(
                "SQLite resume prepared."
            )
            print(
                f"Retried items: "
                f"{info['retried']}"
            )

            return {
                "run_id": run_id,
                "session_id":
                    unfinished.get(
                        "session_id"
                    ),
                "requested":
                    unfinished.get(
                        "requested"
                    ),
                "resumed": True,
            }

        cancel_run(
            run_id
        )

        print("")
        print(
            "Стару чергу позначено cancelled."
        )

    if not videos:
        raise RuntimeError(
            "У ToUpload немає нових відео."
        )

    return create_new_queue(
        videos
    )


def get_next_item(
    state: dict,
) -> dict | None:
    return get_next_queue_item(
        int(state["run_id"])
    )


def set_stage(
    item_id: int,
    stage: str,
) -> None:
    update_queue_item(
        item_id,
        status="processing",
        stage=stage,
        error_message="",
        started=True,
    )


def set_waiting_stage(
    item_id: int,
    stage: str,
) -> None:
    update_queue_item(
        item_id,
        status="processing",
        stage=stage,
        error_message="",
    )


def mark_done(
    item_id: int,
) -> None:
    update_queue_item(
        item_id,
        status="done",
        stage="published",
        error_message="",
        finished=True,
    )


def mark_failed(
    item_id: int,
    stage: str,
    error: Exception | str,
) -> None:
    update_queue_item(
        item_id,
        status="failed",
        stage=stage,
        error_message=str(error),
        finished=True,
    )


def session_progress(
    state: dict,
) -> tuple[int, int, int, int]:
    counts = queue_counts(
        int(state["run_id"])
    )

    return (
        counts["done"],
        counts["failed"],
        counts["blocked"],
        counts["total"],
    )


def print_session_summary(
    state: dict,
) -> None:
    counts = queue_counts(
        int(state["run_id"])
    )

    print("")
    print("=" * 62)
    print(
        "SQLITE QUEUE STATUS".center(62)
    )
    print("=" * 62)
    print("")
    print(
        f"Run ID: {state['run_id']}"
    )
    print(
        f"Done: {counts['done']}/{counts['total']}"
    )
    print(
        f"Queued: {counts['queued']}"
    )
    print(
        f"Processing: {counts['processing']}"
    )
    print(
        f"Failed: {counts['failed']}"
    )
    print(
        f"Blocked: {counts['blocked']}"
    )


def finalize_session(
    state: dict,
) -> str:
    return finalize_run(
        int(state["run_id"])
    )
