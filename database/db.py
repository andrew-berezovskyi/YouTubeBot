from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import sqlite3
from typing import Any

from config import DATABASE_FILE


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def connect() -> sqlite3.Connection:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_columns(
    conn: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing = _table_columns(conn, table_name)

    for column_name, definition in columns.items():
        if column_name in existing:
            continue

        print(
            f"SQLite migration: "
            f"{table_name}.{column_name}"
        )

        conn.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {definition}
            """
        )


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE,
                started_at TEXT,
                finished_at TEXT,
                requested INTEGER NOT NULL DEFAULT 0,
                ready_count INTEGER NOT NULL DEFAULT 0,
                uploaded_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'running'
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                queue_index INTEGER,
                source_path TEXT,
                source_name TEXT,
                sha256 TEXT,
                duration REAL,
                width INTEGER,
                height INTEGER,
                video_type TEXT,
                topic TEXT,
                summary TEXT,
                visible_text_json TEXT,
                events_json TEXT,
                title TEXT,
                description TEXT,
                hashtags_json TEXT,
                ready_path TEXT,
                youtube_video_id TEXT,
                youtube_url TEXT,
                visibility TEXT,
                status TEXT NOT NULL DEFAULT 'discovered',
                error_message TEXT,
                created_at TEXT,
                updated_at TEXT,
                analysis_finished_at TEXT,
                metadata_finished_at TEXT,
                processed_at TEXT,
                upload_started_at TEXT,
                published_at TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                video_id INTEGER,
                event_type TEXT,
                message TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS upload_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                video_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                ready_path TEXT,
                visibility TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                result TEXT NOT NULL DEFAULT 'started',
                processing_wait_seconds INTEGER,
                youtube_video_id TEXT,
                youtube_url TEXT,
                studio_error_text TEXT,
                screenshot_path TEXT,
                html_path TEXT
            );

            CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                queue_index INTEGER NOT NULL,
                source_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT NOT NULL DEFAULT 'queued',
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(run_id, queue_index)
            );
            """
        )

        _ensure_columns(
            conn,
            "runs",
            {
                "session_id": "TEXT",
                "started_at": "TEXT",
                "finished_at": "TEXT",
                "requested": "INTEGER NOT NULL DEFAULT 0",
                "ready_count": "INTEGER NOT NULL DEFAULT 0",
                "uploaded_count": "INTEGER NOT NULL DEFAULT 0",
                "error_count": "INTEGER NOT NULL DEFAULT 0",
                "status": "TEXT NOT NULL DEFAULT 'running'",
            },
        )

        _ensure_columns(
            conn,
            "videos",
            {
                "run_id": "INTEGER",
                "queue_index": "INTEGER",
                "source_path": "TEXT",
                "source_name": "TEXT",
                "sha256": "TEXT",
                "duration": "REAL",
                "width": "INTEGER",
                "height": "INTEGER",
                "video_type": "TEXT",
                "topic": "TEXT",
                "summary": "TEXT",
                "visible_text_json": "TEXT",
                "events_json": "TEXT",
                "title": "TEXT",
                "description": "TEXT",
                "hashtags_json": "TEXT",
                "ready_path": "TEXT",
                "youtube_video_id": "TEXT",
                "youtube_url": "TEXT",
                "visibility": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'discovered'",
                "error_message": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "analysis_finished_at": "TEXT",
                "metadata_finished_at": "TEXT",
                "processed_at": "TEXT",
                "upload_started_at": "TEXT",
                "published_at": "TEXT",
            },
        )

        _ensure_columns(
            conn,
            "events",
            {
                "run_id": "INTEGER",
                "video_id": "INTEGER",
                "event_type": "TEXT",
                "message": "TEXT",
                "created_at": "TEXT",
            },
        )

        _ensure_columns(
            conn,
            "upload_attempts",
            {
                "run_id": "INTEGER",
                "video_id": "INTEGER",
                "attempt_number": "INTEGER NOT NULL DEFAULT 1",
                "ready_path": "TEXT",
                "visibility": "TEXT",
                "started_at": "TEXT",
                "finished_at": "TEXT",
                "result": "TEXT NOT NULL DEFAULT 'started'",
                "processing_wait_seconds": "INTEGER",
                "youtube_video_id": "TEXT",
                "youtube_url": "TEXT",
                "studio_error_text": "TEXT",
                "screenshot_path": "TEXT",
                "html_path": "TEXT",
            },
        )

        _ensure_columns(
            conn,
            "queue_items",
            {
                "run_id": "INTEGER",
                "video_id": "INTEGER",
                "queue_index": "INTEGER",
                "source_path": "TEXT",
                "sha256": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'queued'",
                "stage": "TEXT NOT NULL DEFAULT 'queued'",
                "retry_count": "INTEGER NOT NULL DEFAULT 0",
                "error_message": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "started_at": "TEXT",
                "finished_at": "TEXT",
            },
        )

        now = now_iso()

        conn.execute(
            """
            UPDATE videos
            SET created_at = COALESCE(created_at, ?)
            WHERE created_at IS NULL
            """,
            (now,),
        )

        conn.execute(
            """
            UPDATE videos
            SET updated_at = COALESCE(updated_at, created_at, ?)
            WHERE updated_at IS NULL
            """,
            (now,),
        )

        conn.execute(
            """
            UPDATE videos
            SET status = COALESCE(status, 'discovered')
            WHERE status IS NULL
            """
        )

        conn.execute(
            """
            UPDATE events
            SET created_at = COALESCE(created_at, ?)
            WHERE created_at IS NULL
            """,
            (now,),
        )

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_videos_status
                ON videos(status);
            CREATE INDEX IF NOT EXISTS idx_videos_run_id
                ON videos(run_id);
            CREATE INDEX IF NOT EXISTS idx_videos_sha256
                ON videos(sha256);
            CREATE INDEX IF NOT EXISTS idx_events_video_id
                ON events(video_id);
            CREATE INDEX IF NOT EXISTS idx_events_run_id
                ON events(run_id);
            CREATE INDEX IF NOT EXISTS idx_runs_session_id
                ON runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_upload_attempts_video_id
                ON upload_attempts(video_id);
            CREATE INDEX IF NOT EXISTS idx_upload_attempts_run_id
                ON upload_attempts(run_id);
            CREATE INDEX IF NOT EXISTS idx_upload_attempts_result
                ON upload_attempts(result);
            CREATE INDEX IF NOT EXISTS idx_queue_items_run_id
                ON queue_items(run_id);
            CREATE INDEX IF NOT EXISTS idx_queue_items_status
                ON queue_items(status);
            CREATE INDEX IF NOT EXISTS idx_queue_items_stage
                ON queue_items(stage);
            CREATE INDEX IF NOT EXISTS idx_queue_items_video_id
                ON queue_items(video_id);
            """
        )


def ensure_video(
    run_id: int,
    queue_index: int,
    source_path: Path,
    sha256: str,
) -> int:
    init_db()
    source_path = source_path.resolve()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM videos
            WHERE sha256 = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()

        if row:
            video_id = int(row["id"])

            conn.execute(
                """
                UPDATE videos
                SET
                    run_id = ?,
                    queue_index = ?,
                    source_path = ?,
                    source_name = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    run_id,
                    queue_index,
                    str(source_path),
                    source_path.name,
                    now_iso(),
                    video_id,
                ),
            )
            return video_id

        cursor = conn.execute(
            """
            INSERT INTO videos (
                run_id,
                queue_index,
                source_path,
                source_name,
                sha256,
                status,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?,
                'discovered', ?, ?
            )
            """,
            (
                run_id,
                queue_index,
                str(source_path),
                source_path.name,
                sha256,
                now_iso(),
                now_iso(),
            ),
        )

        return int(cursor.lastrowid)


def get_video(video_id: int) -> dict | None:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM videos
            WHERE id = ?
            """,
            (video_id,),
        ).fetchone()

    return dict(row) if row else None


def get_video_by_sha256(
    sha256: str,
) -> dict | None:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM videos
            WHERE sha256 = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()

    return dict(row) if row else None


def update_video(
    video_id: int,
    **fields: Any,
) -> None:
    if not fields:
        return

    init_db()

    allowed = {
        "run_id",
        "queue_index",
        "source_path",
        "source_name",
        "sha256",
        "duration",
        "width",
        "height",
        "video_type",
        "topic",
        "summary",
        "visible_text_json",
        "events_json",
        "title",
        "description",
        "hashtags_json",
        "ready_path",
        "youtube_video_id",
        "youtube_url",
        "visibility",
        "status",
        "error_message",
        "analysis_finished_at",
        "metadata_finished_at",
        "processed_at",
        "upload_started_at",
        "published_at",
    }

    unknown = set(fields) - allowed

    if unknown:
        raise ValueError(
            "Unknown DB fields: "
            + ", ".join(sorted(unknown))
        )

    fields["updated_at"] = now_iso()

    assignments = ", ".join(
        f"{key} = ?"
        for key in fields
    )

    values = list(fields.values())
    values.append(video_id)

    with connect() as conn:
        conn.execute(
            f"""
            UPDATE videos
            SET {assignments}
            WHERE id = ?
            """,
            values,
        )


def log_event(
    run_id: int | None,
    video_id: int | None,
    event_type: str,
    message: str = "",
) -> None:
    init_db()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events (
                run_id,
                video_id,
                event_type,
                message,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                video_id,
                event_type,
                message,
                now_iso(),
            ),
        )


def json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
    )


def start_upload_attempt(
    run_id: int | None,
    video_id: int,
    ready_path: Path,
    visibility: str,
) -> int:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(MAX(attempt_number), 0) + 1
                    AS next_attempt
            FROM upload_attempts
            WHERE video_id = ?
            """,
            (video_id,),
        ).fetchone()

        attempt_number = int(
            row["next_attempt"]
            if row
            else 1
        )

        cursor = conn.execute(
            """
            INSERT INTO upload_attempts (
                run_id,
                video_id,
                attempt_number,
                ready_path,
                visibility,
                started_at,
                result
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, 'started'
            )
            """,
            (
                run_id,
                video_id,
                attempt_number,
                str(ready_path.resolve()),
                visibility,
                now_iso(),
            ),
        )

        return int(cursor.lastrowid)


def finish_upload_attempt(
    attempt_id: int,
    result: str,
    processing_wait_seconds: int | None = None,
    youtube_video_id: str | None = None,
    youtube_url: str | None = None,
    studio_error_text: str | None = None,
    screenshot_path: str | None = None,
    html_path: str | None = None,
) -> None:
    init_db()

    with connect() as conn:
        conn.execute(
            """
            UPDATE upload_attempts
            SET
                result = ?,
                processing_wait_seconds = ?,
                youtube_video_id = ?,
                youtube_url = ?,
                studio_error_text = ?,
                screenshot_path = ?,
                html_path = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (
                result,
                processing_wait_seconds,
                youtube_video_id,
                youtube_url,
                studio_error_text,
                screenshot_path,
                html_path,
                now_iso(),
                attempt_id,
            ),
        )


def recent_upload_attempts(
    limit: int = 50,
) -> list[dict]:
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                ua.*,
                v.source_name,
                v.title
            FROM upload_attempts ua
            JOIN videos v
                ON v.id = ua.video_id
            ORDER BY ua.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def create_run(
    session_id: str,
    requested: int,
) -> int:
    init_db()

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (
                session_id,
                started_at,
                requested,
                ready_count,
                uploaded_count,
                error_count,
                status
            )
            VALUES (
                ?, ?, ?, 0, 0, 0, 'running'
            )
            """,
            (
                session_id,
                now_iso(),
                requested,
            ),
        )

        return int(cursor.lastrowid)


def get_run(run_id: int) -> dict | None:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

    return dict(row) if row else None


def find_unfinished_run() -> dict | None:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT r.*
            FROM runs r
            WHERE r.status IN (
                'running',
                'paused'
            )
            AND EXISTS (
                SELECT 1
                FROM queue_items qi
                WHERE qi.run_id = r.id
                AND qi.status != 'done'
            )
            ORDER BY r.id DESC
            LIMIT 1
            """
        ).fetchone()

    return dict(row) if row else None


def cancel_run(run_id: int) -> None:
    init_db()

    with connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET
                status = 'cancelled',
                finished_at = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                run_id,
            ),
        )


def create_queue_item(
    run_id: int,
    video_id: int,
    queue_index: int,
    source_path: Path,
    sha256: str,
    stage: str = "queued",
) -> int:
    init_db()
    now = now_iso()

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO queue_items (
                run_id,
                video_id,
                queue_index,
                source_path,
                sha256,
                status,
                stage,
                retry_count,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?,
                'queued', ?, 0, ?, ?
            )
            """,
            (
                run_id,
                video_id,
                queue_index,
                str(source_path.resolve()),
                sha256,
                stage,
                now,
                now,
            ),
        )

        return int(cursor.lastrowid)


def list_queue_items(
    run_id: int,
) -> list[dict]:
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                qi.*,
                v.source_name,
                v.title,
                v.youtube_url,
                v.status AS video_status
            FROM queue_items qi
            JOIN videos v
                ON v.id = qi.video_id
            WHERE qi.run_id = ?
            ORDER BY qi.queue_index ASC
            """,
            (run_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_next_queue_item(
    run_id: int,
) -> dict | None:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                qi.*,
                v.source_name,
                v.ready_path,
                v.title,
                v.description,
                v.status AS video_status
            FROM queue_items qi
            JOIN videos v
                ON v.id = qi.video_id
            WHERE qi.run_id = ?
            AND qi.status = 'queued'
            ORDER BY qi.queue_index ASC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

    return dict(row) if row else None


def update_queue_item(
    item_id: int,
    *,
    status: str | None = None,
    stage: str | None = None,
    error_message: str | None = None,
    source_path: Path | str | None = None,
    increment_retry: bool = False,
    started: bool = False,
    finished: bool = False,
) -> None:
    init_db()

    fields: dict[str, Any] = {
        "updated_at": now_iso(),
    }

    if status is not None:
        fields["status"] = status

    if stage is not None:
        fields["stage"] = stage

    if error_message is not None:
        fields["error_message"] = error_message

    if source_path is not None:
        fields["source_path"] = str(
            Path(source_path).resolve()
        )

    if started:
        fields["started_at"] = now_iso()

    if finished:
        fields["finished_at"] = now_iso()

    assignments = [
        f"{key} = ?"
        for key in fields
    ]

    values = list(fields.values())

    if increment_retry:
        assignments.append(
            "retry_count = retry_count + 1"
        )

    values.append(item_id)

    with connect() as conn:
        conn.execute(
            f"""
            UPDATE queue_items
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            values,
        )


def derive_resume_stage(
    video_row: dict,
) -> str:
    if video_row.get("status") == "published":
        return "published"

    ready_path = video_row.get("ready_path")

    if (
        ready_path
        and Path(ready_path).exists()
        and video_row.get("title")
        and video_row.get("description")
    ):
        return "ready_to_upload"

    if (
        video_row.get("title")
        and video_row.get("description")
    ):
        return "metadata_ready"

    if (
        video_row.get("video_type")
        and video_row.get("topic")
        and video_row.get("summary")
    ):
        return "analyzed"

    return "queued"


def recover_run_for_resume(
    run_id: int,
    retry_interrupted_uploads: bool,
) -> dict:
    init_db()

    items = list_queue_items(run_id)

    interrupted_uploads = 0
    retried = 0

    for item in items:
        if item["status"] == "done":
            continue

        video = get_video(
            int(item["video_id"])
        )

        if not video:
            update_queue_item(
                int(item["id"]),
                status="failed",
                stage="error",
                error_message=(
                    "Video row missing from SQLite."
                ),
                finished=True,
            )
            continue

        old_stage = str(
            item.get("stage")
            or "queued"
        )

        if old_stage == "uploading":
            interrupted_uploads += 1

            if retry_interrupted_uploads:
                resume_stage = (
                    derive_resume_stage(
                        video
                    )
                )

                if resume_stage == "published":
                    update_queue_item(
                        int(item["id"]),
                        status="done",
                        stage="published",
                        error_message="",
                        finished=True,
                    )
                else:
                    update_queue_item(
                        int(item["id"]),
                        status="queued",
                        stage="ready_to_upload",
                        error_message="",
                        increment_retry=True,
                    )
                    retried += 1

            else:
                update_queue_item(
                    int(item["id"]),
                    status="blocked",
                    stage="upload_interrupted",
                    error_message=(
                        "Previous run stopped during YouTube "
                        "upload. Not auto-retried to avoid "
                        "possible duplicate."
                    ),
                    finished=True,
                )

            continue

        resume_stage = derive_resume_stage(
            video
        )

        if resume_stage == "published":
            update_queue_item(
                int(item["id"]),
                status="done",
                stage="published",
                error_message="",
                finished=True,
            )
            continue

        update_queue_item(
            int(item["id"]),
            status="queued",
            stage=resume_stage,
            error_message="",
            increment_retry=(
                item["status"] in {
                    "failed",
                    "blocked",
                    "processing",
                }
            ),
        )

        if item["status"] in {
            "failed",
            "blocked",
            "processing",
        }:
            retried += 1

    with connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET
                status = 'running',
                finished_at = NULL
            WHERE id = ?
            """,
            (run_id,),
        )

    refresh_run_counts(run_id)

    return {
        "interrupted_uploads":
            interrupted_uploads,
        "retried":
            retried,
    }


def queue_counts(run_id: int) -> dict:
    init_db()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,

                SUM(
                    CASE
                    WHEN status = 'done'
                    THEN 1 ELSE 0 END
                ) AS done,

                SUM(
                    CASE
                    WHEN status = 'failed'
                    THEN 1 ELSE 0 END
                ) AS failed,

                SUM(
                    CASE
                    WHEN status = 'blocked'
                    THEN 1 ELSE 0 END
                ) AS blocked,

                SUM(
                    CASE
                    WHEN status = 'queued'
                    THEN 1 ELSE 0 END
                ) AS queued,

                SUM(
                    CASE
                    WHEN status = 'processing'
                    THEN 1 ELSE 0 END
                ) AS processing

            FROM queue_items
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    return {
        "total": int(row["total"] or 0),
        "done": int(row["done"] or 0),
        "failed": int(row["failed"] or 0),
        "blocked": int(row["blocked"] or 0),
        "queued": int(row["queued"] or 0),
        "processing": int(row["processing"] or 0),
    }


def refresh_run_counts(
    run_id: int,
    status: str | None = None,
) -> None:
    init_db()
    counts = queue_counts(run_id)

    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS uploaded
            FROM queue_items qi
            JOIN videos v
                ON v.id = qi.video_id
            WHERE qi.run_id = ?
            AND v.status = 'published'
            """,
            (run_id,),
        ).fetchone()

        uploaded = int(
            row["uploaded"] or 0
        )

        run_status = status

        if run_status is None:
            run = conn.execute(
                """
                SELECT status
                FROM runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()

            run_status = (
                run["status"]
                if run
                else "running"
            )

        conn.execute(
            """
            UPDATE runs
            SET
                ready_count = ?,
                uploaded_count = ?,
                error_count = ?,
                status = ?
            WHERE id = ?
            """,
            (
                counts["done"],
                uploaded,
                counts["failed"] + counts["blocked"],
                run_status,
                run_id,
            ),
        )


def finalize_run(run_id: int) -> str:
    init_db()
    counts = queue_counts(run_id)

    if (
        counts["done"]
        == counts["total"]
        and counts["total"] > 0
    ):
        status = "completed"

    elif (
        counts["failed"] > 0
        or counts["blocked"] > 0
    ):
        status = "completed_with_errors"

    elif (
        counts["queued"] > 0
        or counts["processing"] > 0
    ):
        status = "paused"

    else:
        status = "completed"

    with connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET
                status = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (
                status,
                now_iso(),
                run_id,
            ),
        )

    refresh_run_counts(
        run_id,
        status=status,
    )

    return status


def recent_runs(
    limit: int = 20,
) -> list[dict]:
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def recent_videos(
    limit: int = 50,
) -> list[dict]:
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                source_name,
                source_path,
                duration,
                video_type,
                topic,
                title,
                status,
                visibility,
                youtube_url,
                error_message,
                created_at,
                published_at
            FROM videos
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]
