from database.db import init_db, recent_videos

init_db()
rows = recent_videos(limit=100)

if not rows:
    print('База поки порожня.')
else:
    for row in rows:
        print('=' * 78)
        print(f"ID: {row['id']}")
        print(f"File: {row['source_name']}")
        print(f"Duration: {row['duration']}")
        print(f"Size: {row['width']}x{row['height']}")
        print(f"Type: {row['video_type']}")
        print(f"Topic: {row['topic']}")
        print(f"Title: {row['title']}")
        print(f"Status: {row['status']}")
        print(f"Visibility: {row['visibility']}")
        print(f"YouTube: {row['youtube_url']}")
        print(f"Published: {row['published_at']}")
        if row['error_message']:
            print('Error:', row['error_message'])
