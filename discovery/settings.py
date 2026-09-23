from pathlib import Path
import json
import config

DEFAULTS = {
    "queries": ["funny moments", "funny fails", "unexpected funny moments"],
    "youtube_search": True,
    "youtube_shorts_only": False,
    "youtube_scan_limit": 40,
    "reddit_search": True,
    "source_urls": [],
    "approved_creator_urls": [],
    "approved_video_urls": [],
    "results_per_query": 5,
    "max_candidates_per_cycle": 15,
    "max_downloads_per_cycle": 3,
    "max_download_mb": 150,
    "max_storage_mb": 3000,
    "min_duration": 5,
    "max_duration": 180,
    "min_height": 720,
    "vertical_only": True,
    "interval_minutes": 60,
    "max_daily_upload_attempts": 3,
    "min_upload_interval_minutes": 120,
    "max_retries": 3,
    "retry_minutes": 30,
    "sample_interval_seconds": 3,
    "max_frames": 32,
    "vision_timeout_seconds": 120,
    "min_topic_score": 0.65,
    "tesseract_cmd": "",
    "cookie_file": "",
    "download_timeout_seconds": 600,
    "search_timeout_seconds": 45,
    "metadata_timeout_seconds": 60,
}

def root():
    return Path(config.BASE_DIR)

def load():
    path = root() / "discovery_settings.json"
    value = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    unknown = set(value) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown discovery settings: {sorted(unknown)}")
    cfg = {**DEFAULTS, **value}
    for name in ("youtube_scan_limit", "results_per_query", "max_candidates_per_cycle", "max_downloads_per_cycle", "max_download_mb", "max_storage_mb", "max_duration", "min_height", "interval_minutes", "max_daily_upload_attempts", "min_upload_interval_minutes", "max_retries", "retry_minutes", "sample_interval_seconds", "max_frames", "vision_timeout_seconds", "download_timeout_seconds", "search_timeout_seconds", "metadata_timeout_seconds"):
        if isinstance(cfg[name], bool) or not isinstance(cfg[name], (int, float)) or cfg[name] <= 0:
            raise ValueError(f"{name} must be positive")
    for name in ("youtube_scan_limit", "results_per_query", "max_candidates_per_cycle", "max_downloads_per_cycle", "max_frames", "max_retries", "max_daily_upload_attempts"):
        if not isinstance(cfg[name], int): raise ValueError(f"{name} must be an integer")
    if cfg['max_frames'] < 3: raise ValueError('max_frames must be at least 3')
    for name in ('youtube_search','youtube_shorts_only','reddit_search','vertical_only'):
        if not isinstance(cfg[name],bool): raise ValueError(f'{name} must be boolean')
    if not 0 <= cfg["min_topic_score"] <= 1: raise ValueError("min_topic_score must be 0..1")
    if not 0 <= cfg["min_duration"] < cfg["max_duration"]: raise ValueError("Invalid duration limits")
    for name in ("queries", "source_urls", "approved_creator_urls", "approved_video_urls"):
        if not isinstance(cfg[name], list) or not all(isinstance(x, str) for x in cfg[name]): raise ValueError(f"{name} must be a list of strings")
    return cfg
