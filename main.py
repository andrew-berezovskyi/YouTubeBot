from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import sys
import time

from config import (
    TO_UPLOAD,
    UPLOADED,
    METADATA,
    ENABLE_YOUTUBE_UPLOAD,
    UPLOAD_VISIBILITY,
    UPLOAD_DELAY_SECONDS,
)

from ai.analyzer import (
    analyze_video,
    get_duration,
)
from ai.metadata import (
    generate_metadata,
)
from video.processor import (
    add_watermark,
    get_video_size,
)
from youtube.uploader import (
    upload_video,
)

from queue.manager import (
    list_source_videos,
    sha256_file,
    get_or_create_queue,
    get_next_item,
    set_stage,
    set_waiting_stage,
    mark_done,
    mark_failed,
    session_progress,
    print_session_summary,
    finalize_session,
)

from database.db import (
    init_db,
    get_video,
    get_video_by_sha256,
    update_video,
    log_event,
    json_text,
    start_upload_attempt,
    finish_upload_attempt,
    refresh_run_counts,
    update_queue_item,
    now_iso,
)


def metadata_paths(
    video: Path,
) -> tuple[Path, Path]:
    return (
        METADATA / f"{video.stem}.json",
        METADATA / f"{video.stem}.txt",
    )


def parse_json_list(
    text: str | None,
) -> list:
    if not text:
        return []

    try:
        value = json.loads(text)

        if isinstance(value, list):
            return value

    except Exception:
        pass

    return []




def _is_inside(
    path: Path,
    folder: Path,
) -> bool:
    try:
        path.resolve().relative_to(
            folder.resolve()
        )
        return True
    except Exception:
        return False


def find_video_by_sha256(
    sha256: str,
) -> Path | None:
    """
    Try to recover a moved source file.

    Fast path:
    search ToUpload and Uploaded only.
    This is used only when the path stored by an older queue
    no longer exists.
    """

    for folder in (
        TO_UPLOAD,
        UPLOADED,
    ):
        if not folder.exists():
            continue

        for candidate in list_source_videos(
            folder
        ):
            try:
                if (
                    sha256_file(candidate)
                    == sha256
                ):
                    return candidate
            except Exception:
                continue

    return None


def resolve_source_video(
    item: dict,
    row: dict | None,
) -> Path | None:
    """
    Resolve a queue item's source safely.

    Older queue rows may still point to ToUpload even when
    the original file was already moved. We try:
      1. queue_items.source_path
      2. videos.source_path
      3. SHA-256 lookup in ToUpload / Uploaded

    When a valid file is recovered, SQLite is synchronized.
    """

    candidates: list[Path] = []

    item_path = item.get(
        "source_path"
    )

    if item_path:
        candidates.append(
            Path(item_path)
        )

    if row:
        db_path = row.get(
            "source_path"
        )

        if db_path:
            candidate = Path(
                db_path
            )

            if candidate not in candidates:
                candidates.append(
                    candidate
                )

    resolved: Path | None = None

    for candidate in candidates:
        if candidate.exists():
            resolved = candidate
            break

    if resolved is None:
        digest = str(
            item.get("sha256")
            or (
                row.get("sha256")
                if row
                else ""
            )
            or ""
        )

        if digest:
            resolved = find_video_by_sha256(
                digest
            )

    if resolved is not None:
        video_id = int(
            item["video_id"]
        )

        update_video(
            video_id,
            source_path=str(
                resolved.resolve()
            ),
            source_name=resolved.name,
        )

        update_queue_item(
            int(item["id"]),
            source_path=resolved,
        )

    return resolved


def source_required_error(
    item: dict,
) -> RuntimeError:
    return RuntimeError(
        "Source file is unavailable and this stage "
        "still needs the original video.\\n"
        f"Stored path: {item.get('source_path')}\\n"
        "If READY.mp4 exists, the bot can resume directly "
        "from ready_to_upload."
    )

def unique_uploaded_path(
    source: Path,
) -> Path:
    UPLOADED.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidate = (
        UPLOADED
        / source.name
    )

    if not candidate.exists():
        return candidate

    try:
        if (
            sha256_file(candidate)
            == sha256_file(source)
        ):
            return candidate
    except Exception:
        pass

    counter = 2

    while True:
        candidate = (
            UPLOADED
            / (
                f"{source.stem}_{counter}"
                f"{source.suffix}"
            )
        )

        if not candidate.exists():
            return candidate

        counter += 1


def archive_source_video(
    video: Path,
    db_video_id: int,
    run_id: int | None,
) -> Path:
    # Already archived: never try to move/delete the same file
    # inside Uploaded again.
    if (
        video.exists()
        and _is_inside(
            video,
            UPLOADED,
        )
    ):
        update_video(
            db_video_id,
            source_path=str(
                video.resolve()
            ),
            source_name=video.name,
        )

        return video

    if not video.exists():
        row = get_video(
            db_video_id
        )

        if row:
            current = row.get(
                "source_path"
            )

            if (
                current
                and Path(current).exists()
            ):
                return Path(current)

        raise FileNotFoundError(
            f"Source file not found: {video}"
        )

    UPLOADED.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = unique_uploaded_path(
        video
    )

    if destination.exists():
        same_file = False

        try:
            same_file = (
                sha256_file(destination)
                == sha256_file(video)
            )
        except Exception:
            pass

        if same_file:
            video.unlink()
        else:
            raise RuntimeError(
                "Unexpected destination collision: "
                f"{destination}"
            )

    else:
        shutil.move(
            str(video),
            str(destination),
        )

    update_video(
        db_video_id,
        source_path=str(
            destination.resolve()
        ),
        source_name=destination.name,
    )

    log_event(
        run_id,
        db_video_id,
        "source_moved_to_uploaded",
        str(destination),
    )

    print("")
    print("SOURCE ARCHIVE: OK")
    print(
        f"{video.name}"
        "  ->  "
        f"Uploaded\\{destination.name}"
    )

    return destination


def try_archive_source_video(
    video: Path,
    db_video_id: int,
    run_id: int | None,
) -> Path | None:
    try:
        return archive_source_video(
            video=video,
            db_video_id=db_video_id,
            run_id=run_id,
        )

    except Exception as exc:
        print("")
        print(
            "WARNING: відео published, "
            "але перенос у Uploaded не вдався:"
        )
        print(exc)

        log_event(
            run_id,
            db_video_id,
            "source_archive_error",
            str(exc),
        )

        return None


def cleanup_published_from_to_upload() -> None:
    videos = list_source_videos(
        TO_UPLOAD
    )

    if not videos:
        return

    moved = 0

    for video in videos:
        try:
            digest = sha256_file(
                video
            )

            row = get_video_by_sha256(
                digest
            )

            if (
                row
                and row.get("status")
                == "published"
            ):
                archived = (
                    try_archive_source_video(
                        video=video,
                        db_video_id=int(
                            row["id"]
                        ),
                        run_id=row.get(
                            "run_id"
                        ),
                    )
                )

                if archived:
                    moved += 1

        except Exception as exc:
            print("")
            print(
                "Startup archive warning:"
            )
            print(
                video.name,
                ":",
                exc,
            )

    if moved:
        print("")
        print("=" * 62)
        print(
            "TOUPLOAD CLEANUP".center(62)
        )
        print("=" * 62)
        print("")
        print(
            f"Перенесено вже published: {moved}"
        )


def load_analysis_from_db(
    row: dict,
) -> dict | None:
    if not (
        row.get("video_type")
        and row.get("topic")
        and row.get("summary")
    ):
        return None

    return {
        "video_type":
            row.get("video_type") or "",
        "topic":
            row.get("topic") or "",
        "summary":
            row.get("summary") or "",
        "visible_text":
            parse_json_list(
                row.get(
                    "visible_text_json"
                )
            ),
        "events":
            parse_json_list(
                row.get(
                    "events_json"
                )
            ),
    }


def load_metadata_from_db(
    row: dict,
) -> dict | None:
    if not (
        row.get("title")
        and row.get("description")
    ):
        return None

    return {
        "title":
            row.get("title") or "",
        "final_description":
            row.get("description") or "",
        "hashtags":
            parse_json_list(
                row.get(
                    "hashtags_json"
                )
            ),
    }


def process_resumable_pipeline(
    state: dict,
    item: dict,
) -> tuple[Path, dict, Path | None]:
    """
    Resume from the earliest missing checkpoint.

    Critical fix:
    ready_to_upload does NOT require the original source file.
    If metadata + READY.mp4 are already persisted, the bot can
    upload even when an old queue path in ToUpload is stale.
    """

    run_id = int(
        state["run_id"]
    )
    item_id = int(
        item["id"]
    )
    video_id = int(
        item["video_id"]
    )

    row = get_video(
        video_id
    )

    if not row:
        raise RuntimeError(
            "Video row missing from SQLite."
        )

    video = resolve_source_video(
        item,
        row,
    )

    metadata = load_metadata_from_db(
        row
    )

    ready_path = row.get(
        "ready_path"
    )

    ready_video = (
        Path(ready_path)
        if ready_path
        else None
    )

    # BEST RESUME PATH:
    # everything local is already ready, so source is optional.
    if (
        metadata is not None
        and ready_video is not None
        and ready_video.exists()
    ):
        print("")
        print(
            "SQLite resume: analysis/metadata already stored."
        )
        print(
            "SQLite resume: READY.mp4 exists — "
            "source file is not required for upload."
        )

        set_waiting_stage(
            item_id,
            "ready_to_upload",
        )

        update_video(
            video_id,
            status="ready_to_upload",
            error_message=None,
        )

        return (
            ready_video,
            metadata,
            video,
        )

    # All earlier stages require the original source.
    if (
        video is None
        or not video.exists()
    ):
        raise source_required_error(
            item
        )

    # --------------------------------------------------------
    # BASIC INFO
    # --------------------------------------------------------

    if (
        row.get("duration") is None
        or row.get("width") is None
        or row.get("height") is None
    ):
        duration = get_duration(
            video
        )

        width, height = (
            get_video_size(
                video
            )
        )

        update_video(
            video_id,
            duration=duration,
            width=width,
            height=height,
        )

        row = get_video(
            video_id
        ) or row

    # --------------------------------------------------------
    # ANALYSIS
    # --------------------------------------------------------

    analysis = load_analysis_from_db(
        row
    )

    if analysis is None:
        set_stage(
            item_id,
            "analyzing",
        )

        update_video(
            video_id,
            status="analyzing",
            error_message=None,
        )

        log_event(
            run_id,
            video_id,
            "analysis_started",
            video.name,
        )

        analysis = analyze_video(
            video
        )

        update_video(
            video_id,
            video_type=analysis.get(
                "video_type",
                "",
            ),
            topic=analysis.get(
                "topic",
                "",
            ),
            summary=analysis.get(
                "summary",
                "",
            ),
            visible_text_json=json_text(
                analysis.get(
                    "visible_text",
                    [],
                )
            ),
            events_json=json_text(
                analysis.get(
                    "events",
                    [],
                )
            ),
            status="analyzed",
            analysis_finished_at=now_iso(),
            error_message=None,
        )

        set_waiting_stage(
            item_id,
            "analyzed",
        )

        log_event(
            run_id,
            video_id,
            "analysis_success",
            analysis.get(
                "summary",
                "",
            ),
        )

        row = get_video(
            video_id
        ) or row

    else:
        print("")
        print(
            "SQLite resume: analysis already exists — SKIP."
        )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    metadata = load_metadata_from_db(
        row
    )

    if metadata is None:
        set_stage(
            item_id,
            "metadata_generating",
        )

        metadata = generate_metadata(
            video,
            analysis,
        )

        update_video(
            video_id,
            title=metadata[
                "title"
            ],
            description=metadata[
                "final_description"
            ],
            hashtags_json=json_text(
                metadata.get(
                    "hashtags",
                    [],
                )
            ),
            status="metadata_ready",
            metadata_finished_at=now_iso(),
            error_message=None,
        )

        set_waiting_stage(
            item_id,
            "metadata_ready",
        )

        log_event(
            run_id,
            video_id,
            "metadata_success",
            metadata["title"],
        )

        row = get_video(
            video_id
        ) or row

    else:
        print(
            "SQLite resume: metadata already exists — SKIP."
        )

    # --------------------------------------------------------
    # READY FILE / WATERMARK
    # --------------------------------------------------------

    ready_path = row.get(
        "ready_path"
    )

    if (
        ready_path
        and Path(ready_path).exists()
    ):
        ready_video = Path(
            ready_path
        )

        print(
            "SQLite resume: READY.mp4 already exists — "
            "FFmpeg SKIP."
        )

    else:
        set_stage(
            item_id,
            "processing",
        )

        update_video(
            video_id,
            status="processing",
            error_message=None,
        )

        ready_video = add_watermark(
            video
        )

        update_video(
            video_id,
            ready_path=str(
                ready_video.resolve()
            ),
            status="ready_to_upload",
            processed_at=now_iso(),
            error_message=None,
        )

        set_waiting_stage(
            item_id,
            "ready_to_upload",
        )

        log_event(
            run_id,
            video_id,
            "processing_success",
            str(ready_video),
        )

    return (
        ready_video,
        metadata,
        video,
    )


def process_queue_item(
    state: dict,
    item: dict,
) -> None:
    run_id = int(
        state["run_id"]
    )
    item_id = int(
        item["id"]
    )
    video_id = int(
        item["video_id"]
    )
    row = get_video(
        video_id
    )

    video = resolve_source_video(
        item,
        row,
    )

    fallback_video = Path(
        item["source_path"]
    )

    if (
        row
        and row.get("status")
        == "published"
    ):
        print("")
        print(
            "SQLite: відео вже published."
        )

        if (
            video is not None
            and video.exists()
        ):
            try_archive_source_video(
                video=video,
                db_video_id=video_id,
                run_id=run_id,
            )

        mark_done(
            item_id
        )

        refresh_run_counts(
            run_id
        )
        return

    done, failed, blocked, total = (
        session_progress(
            state
        )
    )

    print("")
    print("=" * 62)
    print(
        (
            f"VIDEO {item['queue_index']}/{total}"
        ).center(62)
    )
    print("=" * 62)
    print("")
    print(
        item.get(
            "source_name"
        )
        or (
            video.name
            if video is not None
            else fallback_video.name
        )
    )
    print(
        "Resume stage:",
        item.get(
            "stage"
        ),
    )

    ready_video, metadata, video = (
        process_resumable_pipeline(
            state,
            item,
        )
    )

    if ENABLE_YOUTUBE_UPLOAD:
        set_stage(
            item_id,
            "uploading",
        )

        update_video(
            video_id,
            status="uploading",
            upload_started_at=now_iso(),
            visibility=UPLOAD_VISIBILITY,
            error_message=None,
        )

        log_event(
            run_id,
            video_id,
            "upload_started",
            UPLOAD_VISIBILITY,
        )

        attempt_id = start_upload_attempt(
            run_id=run_id,
            video_id=video_id,
            ready_path=ready_video,
            visibility=UPLOAD_VISIBILITY,
        )

        try:
            result = upload_video(
                video=ready_video,
                title=metadata[
                    "title"
                ],
                description=metadata[
                    "final_description"
                ],
                visibility=UPLOAD_VISIBILITY,
            )

            finish_upload_attempt(
                attempt_id=attempt_id,
                result="published",
                processing_wait_seconds=(
                    result.get(
                        "processing_wait_seconds"
                    )
                ),
                youtube_video_id=(
                    result.get(
                        "video_id"
                    )
                ),
                youtube_url=(
                    result.get(
                        "video_url"
                    )
                ),
            )

        except Exception as exc:
            finish_upload_attempt(
                attempt_id=attempt_id,
                result="failed",
                processing_wait_seconds=getattr(
                    exc,
                    "processing_wait_seconds",
                    None,
                ),
                studio_error_text=(
                    getattr(
                        exc,
                        "studio_error_text",
                        "",
                    )
                    or str(exc)
                ),
                screenshot_path=getattr(
                    exc,
                    "screenshot_path",
                    None,
                ),
                html_path=getattr(
                    exc,
                    "html_path",
                    None,
                ),
            )

            update_video(
                video_id,
                status="publish_failed",
                error_message=str(exc),
            )

            mark_failed(
                item_id,
                "publish_failed",
                exc,
            )

            log_event(
                run_id,
                video_id,
                "publish_failed",
                str(exc),
            )

            raise

        update_video(
            video_id,
            youtube_video_id=result.get(
                "video_id"
            ),
            youtube_url=result.get(
                "video_url"
            ),
            visibility=result.get(
                "visibility",
                UPLOAD_VISIBILITY,
            ),
            status="published",
            published_at=now_iso(),
            error_message=None,
        )

        log_event(
            run_id,
            video_id,
            "upload_verified",
            (
                result.get(
                    "video_url"
                )
                or ""
            ),
        )

        mark_done(
            item_id
        )

        if (
            video is not None
            and video.exists()
        ):
            try_archive_source_video(
                video=video,
                db_video_id=video_id,
                run_id=run_id,
            )
        else:
            print("")
            print(
                "SOURCE ARCHIVE: skipped "
                "(original source is unavailable)."
            )

    else:
        set_waiting_stage(
            item_id,
            "ready_to_upload",
        )

    refresh_run_counts(
        run_id
    )

    done, failed, blocked, total = (
        session_progress(
            state
        )
    )

    print("")
    print(
        f"DONE: {done}/{total} ✅"
    )

    if (
        ENABLE_YOUTUBE_UPLOAD
        and UPLOAD_DELAY_SECONDS > 0
        and done < total
    ):
        print(
            f"Пауза {UPLOAD_DELAY_SECONDS} сек..."
        )

        time.sleep(
            UPLOAD_DELAY_SECONDS
        )


def main() -> None:
    print("")
    print("=" * 62)
    print(
        "VIBERUSHH BOT - SQLITE QUEUE + RESUME".center(62)
    )
    print("=" * 62)
    print("")
    print(
        "YouTube upload:",
        (
            "ENABLED"
            if ENABLE_YOUTUBE_UPLOAD
            else "DISABLED"
        ),
    )
    print(
        "Visibility:",
        UPLOAD_VISIBILITY,
    )
    print("")
    print(
        "queue_state.json: NOT USED"
    )

    init_db()

    # GUI mode can finish a previously interrupted run first,
    # then automatically start the newly requested ToUpload batch.
    chain_after_resume = (
        os.getenv(
            "YOUTUBEBOT_GUI_CHAIN_NEW_AFTER_RESUME",
            "0",
        )
        == "1"
    )

    cycle = 0

    while True:
        cycle += 1

        cleanup_published_from_to_upload()

        videos = list_source_videos(
            TO_UPLOAD
        )

        state = get_or_create_queue(
            videos
        )

        run_id = int(
            state["run_id"]
        )

        log_event(
            run_id,
            None,
            (
                "run_resumed"
                if state.get("resumed")
                else "run_started"
            ),
            str(
                state.get(
                    "session_id"
                )
            ),
        )

        print_session_summary(
            state
        )

        while True:
            item = get_next_item(
                state
            )

            if item is None:
                break

            item_id = int(
                item["id"]
            )
            video_id = int(
                item["video_id"]
            )

            try:
                process_queue_item(
                    state,
                    item,
                )

            except KeyboardInterrupt:
                print("")
                print(
                    "Stopped by user."
                )
                print(
                    "SQLite kept the current checkpoint."
                )

                refresh_run_counts(
                    run_id,
                    status="paused",
                )
                return

            except Exception as error:
                current = get_video(
                    video_id
                )

                if (
                    not current
                    or current.get(
                        "status"
                    )
                    != "publish_failed"
                ):
                    update_video(
                        video_id,
                        status="error",
                        error_message=str(
                            error
                        ),
                    )

                    # Use the live DB stage if possible, not the stale
                    # stage captured when the item was first fetched.
                    try:
                        from database.db import get_next_queue_item
                        live_stage = (
                            item.get("stage")
                            or "error"
                        )
                    except Exception:
                        live_stage = (
                            item.get("stage")
                            or "error"
                        )

                    mark_failed(
                        item_id,
                        live_stage,
                        error,
                    )

                log_event(
                    run_id,
                    video_id,
                    "error",
                    str(error),
                )

                refresh_run_counts(
                    run_id
                )

                print("")
                print("=" * 62)
                print(
                    "VIDEO FAILED - CONTINUING".center(62)
                )
                print("=" * 62)
                print("")
                print(
                    item.get(
                        "source_name"
                    )
                )
                print(
                    type(error).__name__,
                    ":",
                    error,
                )

        status = finalize_session(
            state
        )

        print_session_summary(
            state
        )

        done, failed, blocked, total = (
            session_progress(
                state
            )
        )

        print("")
        print("=" * 62)

        if status == "completed":
            print(
                "RUN COMPLETED".center(62)
            )
        else:
            print(
                "RUN FINISHED WITH ISSUES".center(62)
            )

        print("=" * 62)
        print("")
        print(
            f"Done: {done}/{total}"
        )
        print(
            f"Failed: {failed}"
        )
        print(
            f"Blocked: {blocked}"
        )
        print(
            f"Run status: {status}"
        )

        # If the GUI resumed an old *successful* interrupted run,
        # do not ignore the new videos currently visible in ToUpload.
        if (
            chain_after_resume
            and state.get("resumed")
            and status == "completed"
        ):
            remaining = list_source_videos(
                TO_UPLOAD
            )

            if remaining:
                print("")
                print("=" * 62)
                print(
                    "RESUME COMPLETE - STARTING NEW GUI BATCH".center(62)
                )
                print("=" * 62)
                print("")
                print(
                    f"New videos still in ToUpload: {len(remaining)}"
                )

                # Next loop creates a NEW run because the resumed one
                # is now completed.
                continue

        if status != "completed":
            # Let GUI/automation distinguish a completed run
            # from a run that ended with failed/blocked videos.
            raise SystemExit(2)

        break


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print("")
        print("=" * 62)
        print(
            "ERROR".center(62)
        )
        print("=" * 62)
        print("")
        print(
            type(error).__name__,
            ":",
            error,
        )
        sys.exit(1)
