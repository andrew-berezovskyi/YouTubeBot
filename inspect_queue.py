from database.db import (
    init_db,
    recent_runs,
    list_queue_items,
)

init_db()

runs = recent_runs(
    limit=10
)

if not runs:
    print(
        "SQLite queue runs поки немає."
    )
    raise SystemExit(0)

for run in runs:
    run_id = int(
        run["id"]
    )

    items = list_queue_items(
        run_id
    )

    if not items:
        continue

    print("=" * 78)
    print(
        f"RUN {run_id}"
    )
    print(
        f"Session: {run['session_id']}"
    )
    print(
        f"Status: {run['status']}"
    )
    print(
        f"Requested: {run['requested']}"
    )
    print(
        f"Started: {run['started_at']}"
    )
    print(
        f"Finished: {run['finished_at']}"
    )
    print("-" * 78)

    for item in items:
        print(
            f"[{item['queue_index']}] "
            f"{item['source_name']}"
        )
        print(
            f"    Queue status: {item['status']}"
        )
        print(
            f"    Stage: {item['stage']}"
        )
        print(
            f"    Retry count: {item['retry_count']}"
        )
        print(
            f"    Video status: {item['video_status']}"
        )
        print(
            f"    YouTube: {item['youtube_url']}"
        )
        print(
            f"    Error: {item['error_message']}"
        )
        print()
