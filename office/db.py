import datetime
import json
import sqlite3
import time

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS ideas(
  id INTEGER PRIMARY KEY AUTOINCREMENT, batch TEXT, text TEXT,
  status TEXT DEFAULT 'proposed', created_at REAL);
CREATE TABLE IF NOT EXISTS videos(
  id TEXT PRIMARY KEY, idea TEXT, status TEXT DEFAULT 'queued',
  style_pack TEXT, script TEXT, scenes TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor TEXT, target TEXT,
  action TEXT, text TEXT, video_id TEXT);
"""

JSON_FIELDS = (
    "style_pack",
    "script",
    "scenes",
    "brief",
    "story_bible",
)


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def init():
    connection = _conn()

    try:
        connection.executescript(SCHEMA)
        connection.execute("BEGIN IMMEDIATE")

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(videos)")
        }

        additions = {
            "brief": "TEXT",
            "story_bible": "TEXT",
            "bible_revision": "INTEGER NOT NULL DEFAULT 0",
        }

        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE videos ADD COLUMN {name} {definition}"
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def run(sql, args=()):
    c = _conn()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def query(sql, args=()):
    c = _conn()
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


# ---- videos
def add_video(idea, *, brief=None, connection=None):
    if not isinstance(idea, str) or not idea.strip():
        raise ValueError("Cerita tidak boleh kosong.")

    if brief is not None and not isinstance(brief, dict):
        raise ValueError("Brief harus berupa objek.")

    owned = connection is None
    connection = _conn() if owned else connection

    try:
        if owned:
            connection.execute("BEGIN IMMEDIATE")
        elif not connection.in_transaction:
            raise ValueError(
                "Koneksi bersama harus berada dalam transaksi."
            )

        year, week, _ = datetime.date.today().isocalendar()
        prefix = f"{year}-w{week:02d}-"

        rows = connection.execute(
            "SELECT id FROM videos WHERE id LIKE ?",
            (prefix + "%",),
        ).fetchall()

        numbers = [
            int(row["id"][len(prefix):])
            for row in rows
            if row["id"][len(prefix):].isdigit()
        ]

        video_id = f"{prefix}{max(numbers, default=0) + 1:02d}"
        now = time.time()

        connection.execute(
            "INSERT INTO videos"
            "(id,idea,status,created_at,updated_at,brief) "
            "VALUES(?,?,?,?,?,?)",
            (
                video_id,
                idea.strip(),
                "queued",
                now,
                now,
                json.dumps(brief, ensure_ascii=False)
                if brief is not None
                else None,
            ),
        )

        if owned:
            connection.commit()

        return video_id

    except Exception:
        if owned:
            connection.rollback()
        raise

    finally:
        if owned:
            connection.close()


def get_video(vid):
    v = one("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        return None
    for k in JSON_FIELDS:
        if v[k]:
            v[k] = json.loads(v[k])
    return v


def update_video(vid, **fields):
    allowed = {"status", "idea", "style_pack", "script", "scenes"}
    sets, args = [], []
    for k, val in fields.items():
        if k not in allowed:
            raise ValueError(k)
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        sets.append(f"{k}=?")
        args.append(val)
    sets.append("updated_at=?")
    args += [time.time(), vid]
    run(f"UPDATE videos SET {', '.join(sets)} WHERE id=?", args)


def recent_style_packs(n):
    rows = query("SELECT style_pack FROM videos WHERE style_pack IS NOT NULL "
                 "ORDER BY created_at DESC, id DESC LIMIT ?", (n,))
    return [json.loads(r["style_pack"]) for r in rows]


def recent_ideas(n):
    return query("SELECT text FROM ideas ORDER BY id DESC LIMIT ?", (n,))
