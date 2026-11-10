"""Hubungkan ide dari brief ke antrean produksi video."""
import argparse
import datetime
import json
import sqlite3
import time
from contextlib import closing

from . import db
from .config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS brief_video_links (
    brief_id INTEGER NOT NULL REFERENCES content_briefs(id),
    idea_number INTEGER NOT NULL,
    video_id TEXT NOT NULL UNIQUE REFERENCES videos(id),
    idea_text TEXT NOT NULL,
    theme_text TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (brief_id, idea_number)
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def load_plan(conn, brief_id):
    row = conn.execute(
        "SELECT b.theme, p.mode, p.ideas_json FROM content_briefs b "
        "JOIN brief_plans p ON p.brief_id=b.id WHERE b.id=?",
        (brief_id,),
    ).fetchone()

    if not row:
        raise RuntimeError(
            "Brief belum memiliki hasil pengembangan."
        )

    if row["mode"] != "real":
        raise RuntimeError(
            "Hasil demo tidak boleh masuk antrean produksi."
        )

    ideas = json.loads(row["ideas_json"])

    if (
        not isinstance(ideas, list)
        or not ideas
        or any(
            not isinstance(text, str) or not text.strip()
            for text in ideas
        )
    ):
        raise RuntimeError("Daftar ide dalam brief tidak valid.")

    return row["theme"], ideas


def next_video_id(conn):
    year, week, _ = datetime.date.today().isocalendar()
    prefix = f"{year}-w{week:02d}-"

    rows = conn.execute(
        "SELECT id FROM videos WHERE id LIKE ?",
        (prefix + "%",),
    ).fetchall()

    numbers = [
        int(row["id"][len(prefix):])
        for row in rows
        if row["id"][len(prefix):].isdigit()
    ]

    return f"{prefix}{max(numbers, default=0) + 1:02d}"


def enqueue(brief_id, selected):
    messages = []

    with closing(connect()) as conn:
        with conn:
            conn.execute("BEGIN IMMEDIATE")

            theme, ideas = load_plan(conn, brief_id)
            numbers = sorted(set(selected))

            if not numbers or any(
                n < 1 or n > len(ideas) for n in numbers
            ):
                raise RuntimeError(
                    f"Nomor ide harus antara 1 dan {len(ideas)}."
                )

            added = 0

            for number in numbers:
                premise = ideas[number - 1]

                old = conn.execute(
                    "SELECT * FROM brief_video_links "
                    "WHERE brief_id=? AND idea_number=?",
                    (brief_id, number),
                ).fetchone()

                if old:
                    if (
                        old["idea_text"] != premise
                        or old["theme_text"] != theme
                    ):
                        raise RuntimeError(
                            "Isi brief berubah setelah diantrekan. "
                            "Gunakan brief baru untuk revisi tersebut."
                        )

                    exists = conn.execute(
                        "SELECT id FROM videos WHERE id=?",
                        (old["video_id"],),
                    ).fetchone()

                    if not exists:
                        raise RuntimeError(
                            "Video yang terhubung tidak ditemukan."
                        )

                    messages.append(
                        f"LEWATI ide {number}: {old['video_id']}"
                    )
                    continue

                video_id = next_video_id(conn)
                now = time.time()

                # Teruskan premis dan arahan tema ke pipeline.
                video_idea = (
                    premise + "\n\nArahan brief: " + theme
                )

                conn.execute(
                    "INSERT INTO videos"
                    "(id,idea,status,created_at,updated_at) "
                    "VALUES(?,?,?,?,?)",
                    (video_id, video_idea, "queued", now, now),
                )

                conn.execute(
                    "INSERT INTO brief_video_links "
                    "(brief_id,idea_number,video_id,"
                    "idea_text,theme_text,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        brief_id,
                        number,
                        video_id,
                        premise,
                        theme,
                        now,
                    ),
                )

                conn.execute(
                    "INSERT INTO events"
                    "(ts,actor,action,text,video_id) "
                    "VALUES(?,?,?,?,?)",
                    (
                        now,
                        "adit",
                        "say",
                        f"Brief #{brief_id}, ide {number} "
                        "masuk antrean produksi.",
                        video_id,
                    ),
                )

                added += 1
                messages.append(
                    f"ANTREKAN ide {number}: {video_id}"
                )

            if added:
                total = conn.execute(
                    "SELECT COUNT(*) FROM brief_video_links "
                    "WHERE brief_id=?",
                    (brief_id,),
                ).fetchone()[0]

                status = (
                    "production_queued"
                    if total == len(ideas)
                    else "production_partial"
                )

                conn.execute(
                    "UPDATE content_briefs SET status=? WHERE id=?",
                    (status, brief_id),
                )

    for message in messages:
        print(message)

    print(f"Video baru dalam antrean: {added}.")


def check(brief_id):
    with closing(connect()) as conn:
        _, ideas = load_plan(conn, brief_id)

        links = {
            row["idea_number"]: row
            for row in conn.execute(
                "SELECT l.idea_number,l.video_id,v.status "
                "FROM brief_video_links l "
                "LEFT JOIN videos v ON v.id=l.video_id "
                "WHERE l.brief_id=?",
                (brief_id,),
            )
        }

        for number in range(1, len(ideas) + 1):
            row = links.get(number)

            if row:
                print(
                    f"Ide {number}: {row['video_id']} | "
                    f"{row['status'] or 'VIDEO HILANG'}"
                )
            else:
                print(f"Ide {number}: belum diantrekan")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=int, required=True)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ideas", type=int, nargs="+")
    mode.add_argument("--check", action="store_true")

    args = parser.parse_args()

    if args.brief < 1:
        parser.error("ID brief harus positif.")

    try:
        db.init()

        with closing(connect()) as conn:
            conn.executescript(SCHEMA)

        if args.check:
            check(args.brief)
        else:
            enqueue(args.brief, args.ideas)

    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1) from None

    except Exception as exc:
        print(f"Antrean gagal: {type(exc).__name__}.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()