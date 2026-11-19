"""Persistent, private SQLite job metadata."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.getenv("IMAGE_STUDIO_DATA", "data")).expanduser().resolve()
DATA.mkdir(parents=True, exist_ok=True)
MEDIA = DATA / "media"
MEDIA.mkdir(exist_ok=True)
DATABASE = DATA / "jobs.sqlite3"


def connection():
    db = sqlite3.connect(DATABASE, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, mode TEXT NOT NULL, prompt TEXT NOT NULL,
            status TEXT NOT NULL, created TEXT NOT NULL, error TEXT,
            output TEXT
        )""")
        db.execute("UPDATE jobs SET status='failed', error='Server restarted during processing' WHERE status IN ('queued','running')")


def create(job_id, mode, prompt):
    with connection() as db:
        db.execute("INSERT INTO jobs(id,mode,prompt,status,created) VALUES(?,?,?,'queued',?)",
                   (job_id, mode, prompt, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def update(job_id, status, error=None, output=None):
    with connection() as db:
        db.execute("UPDATE jobs SET status=?,error=?,output=? WHERE id=?", (status, error, output, job_id))


def get(job_id):
    with connection() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def recent():
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC,rowid DESC LIMIT 100")]


def delete(job_id):
    with connection() as db:
        db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
