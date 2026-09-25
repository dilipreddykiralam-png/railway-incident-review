"""Opt-in, single-host anonymous usage totals; never stores media or IP addresses."""
import os
import sqlite3
from pathlib import Path


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, session TEXT NOT NULL)')
    return db


def record_usage(path, session, record, backend):
    # A video counts once, and only when every sampled frame completed successfully.
    if backend != 'vlm' or not record or record.get('error') or not record.get('prediction'):
        return False
    if record.get('media_type') == 'video' and (
        not record.get('frames') or any(f.get('error') or not f.get('prediction') for f in record['frames'])
    ):
        return False
    if not session or not record.get('id'):
        return False
    with connect(path) as db:
        inserted = db.execute('INSERT OR IGNORE INTO analyses VALUES (?, ?)', (record['id'], session)).rowcount
    return bool(inserted)


def totals(path):
    with connect(path) as db:
        analyses, sessions = db.execute('SELECT COUNT(*), COUNT(DISTINCT session) FROM analyses').fetchone()
    return {'completed_analyses': analyses, 'testing_sessions': sessions}


def configured_path():
    return os.getenv('RAILREVIEW_USAGE_DB') if os.getenv('RAILREVIEW_PUBLIC') == '1' else None


def badge(counts):
    return {'schemaVersion': 1, 'label': 'testing sessions',
            'message': str(counts['testing_sessions']), 'color': 'blue', 'cacheSeconds': 300}
