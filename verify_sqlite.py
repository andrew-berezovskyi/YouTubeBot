from pathlib import Path
import sqlite3

from config import DATABASE_FILE
from database.db import init_db

REQUIRED = {
    "runs": {
        "id", "session_id", "started_at", "finished_at",
        "requested", "ready_count", "uploaded_count",
        "error_count", "status",
    },
    "videos": {
        "id", "run_id", "queue_index",
        "source_path", "source_name", "sha256",
        "duration", "width", "height",
        "video_type", "topic", "summary",
        "visible_text_json", "events_json",
        "title", "description", "hashtags_json",
        "ready_path",
        "youtube_video_id", "youtube_url", "visibility",
        "status", "error_message",
        "created_at", "updated_at",
        "analysis_finished_at", "metadata_finished_at",
        "processed_at", "upload_started_at", "published_at",
    },
    "events": {
        "id", "run_id", "video_id",
        "event_type", "message", "created_at",
    },
}

def columns(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}

def count_rows(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

print("=" * 70)
print("YOUTUBEBOT SQLITE VERIFY".center(70))
print("=" * 70)
print()
print("Database:")
print(DATABASE_FILE)
print()

# Also performs automatic migration if needed.
init_db()

if not Path(DATABASE_FILE).exists():
    raise SystemExit("ERROR: youtube_bot.db was not created.")

conn = sqlite3.connect(DATABASE_FILE)

all_ok = True

for table, required_columns in REQUIRED.items():
    print("-" * 70)
    print(f"TABLE: {table}")

    existing = columns(conn, table)

    if not existing:
        print("ERROR: table does not exist.")
        all_ok = False
        continue

    missing = sorted(required_columns - existing)

    print(f"Rows: {count_rows(conn, table)}")
    print(f"Columns: {len(existing)}")

    if missing:
        print("MISSING:")
        for name in missing:
            print(f"  - {name}")
        all_ok = False
    else:
        print("Schema: OK")

print("-" * 70)

try:
    conn.execute("SELECT run_id FROM videos LIMIT 1").fetchall()
    print("videos.run_id query: OK")
except Exception as exc:
    print("videos.run_id query: ERROR")
    print(exc)
    all_ok = False

conn.close()

print()
print("=" * 70)

if all_ok:
    print("SQLITE MIGRATION TEST: PASSED".center(70))
    print("=" * 70)
    print()
    print("Step 1 is complete.")
    print("Next: one full live upload test.")
else:
    print("SQLITE MIGRATION TEST: FAILED".center(70))
    print("=" * 70)
    print()
    print("Send the full console output before running main.py.")