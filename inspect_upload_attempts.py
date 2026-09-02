from database.db import (
    init_db,
    recent_upload_attempts,
)

init_db()

rows = recent_upload_attempts(50)

if not rows:
    print("Upload attempts поки немає.")
else:
    for row in rows:
        print("=" * 70)
        print(f"Attempt ID: {row['id']}")
        print(f"Video: {row['source_name']}")
        print(f"Title: {row['title']}")
        print(f"Attempt: {row['attempt_number']}")
        print(f"Result: {row['result']}")
        print(
            "Processing wait:",
            row['processing_wait_seconds'],
        )
        print(f"YouTube ID: {row['youtube_video_id']}")
        print(f"YouTube URL: {row['youtube_url']}")
        print(f"Error: {row['studio_error_text']}")
        print(f"Screenshot: {row['screenshot_path']}")
        print(f"HTML: {row['html_path']}")
        print(f"Started: {row['started_at']}")
        print(f"Finished: {row['finished_at']}")
