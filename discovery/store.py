import json
import sqlite3
import time
import os
from datetime import datetime
from contextlib import contextmanager
from .settings import root

@contextmanager
def connect():
    path = root() / "data" / "discovery.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT,
            source TEXT, creator TEXT, status TEXT NOT NULL DEFAULT 'found',
            reason TEXT DEFAULT '', info TEXT DEFAULT '{}', report TEXT DEFAULT '{}',
            sha256 TEXT, fingerprint TEXT, path TEXT, attempts INTEGER DEFAULT 0,
            updated REAL NOT NULL, created REAL NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS upload_reservations (
            id INTEGER PRIMARY KEY, candidate_id INTEGER, started REAL, outcome TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, at REAL, message TEXT)''')
        db.execute("""CREATE TABLE IF NOT EXISTS worker_progress (
            id INTEGER PRIMARY KEY CHECK(id=1), pid INTEGER, phase TEXT,
            started REAL, heartbeat REAL, timeout REAL)""")
        yield db
        db.commit()
    finally:
        db.close()

def add(url, title, source):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO candidates(url,title,source,updated,created) VALUES(?,?,?,?,?)", (url,title,source,time.time(),time.time()))

def update(cid, **fields):
    allowed = {"title", "creator", "status", "reason", "info", "report", "sha256", "fingerprint", "path", "attempts"}
    if set(fields) - allowed: raise ValueError("Unknown candidate field")
    fields["updated"] = time.time()
    with connect() as db:
        db.execute("UPDATE candidates SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), cid))

def rows():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM candidates ORDER BY id DESC")]

def event(message):
    print(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}", flush=True)
    with connect() as db:
        db.execute("INSERT INTO events(at,message) VALUES(?,?)", (time.time(),message))

def reserve_upload(cid, cfg):
    now = time.time()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        count, last = db.execute("SELECT COUNT(*),MAX(started) FROM upload_reservations WHERE started>?", (now-86400,)).fetchone()
        if count >= cfg["max_daily_upload_attempts"] or (last and now-last < cfg["min_upload_interval_minutes"]*60): return None
        cur = db.execute("INSERT INTO upload_reservations(candidate_id,started,outcome) VALUES(?,?,'pending')", (cid,now))
        return cur.lastrowid

def finish_upload(reservation, outcome):
    with connect() as db:
        db.execute("UPDATE upload_reservations SET outcome=? WHERE id=?", (outcome,reservation))


def progress(phase, timeout=None):
    now=time.time()
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO worker_progress(id,pid,phase,started,heartbeat,timeout) VALUES(1,?,?,?,?,?)",
                   (os.getpid(),phase,now,now,timeout))


def heartbeat():
    with connect() as db:
        db.execute("UPDATE worker_progress SET heartbeat=? WHERE id=1 AND pid=?", (time.time(),os.getpid()))


def current_progress():
    with connect() as db:
        row=db.execute("SELECT * FROM worker_progress WHERE id=1").fetchone()
        return dict(row) if row else None
