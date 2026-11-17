"""Worker Rina dan pemeriksaan Sari, terpisah dari intake dan Agus."""

import argparse
import json
import time
import uuid
from contextlib import closing

from . import db, story_script
from .config import OUTPUT_DIR
from .story_context import get_context
from .story_planner import require_real
from .story_worker import log_events, worker_lock


SCHEMA = """
CREATE TABLE IF NOT EXISTS story_script_attempts(
    video_id TEXT NOT NULL,
    bible_revision INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    candidate TEXT,
    review TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    PRIMARY KEY(video_id,run_id,attempt)
);
"""


def initialize():
    db.init()

    with closing(db._conn()) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def recover_interrupted():
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            rows = connection.execute(
                "SELECT id FROM videos "
                "WHERE status='writing' "
                "AND story_bible IS NOT NULL "
                "AND script IS NULL "
                "AND style_pack IS NULL "
                "AND scenes IS NULL"
            ).fetchall()

            for row in rows:
                connection.execute(
                    "UPDATE videos SET "
                    "status='bible_ready',updated_at=? "
                    "WHERE id=?",
                    (time.time(), row["id"]),
                )

                log_events(
                    connection,
                    row["id"],
                    [
                        (
                            "rina",
                            None,
                            "back",
                            "Penulisan terputus; "
                            "pedoman tetap tersimpan.",
                        ),
                        ("sari", None, "back", ""),
                    ],
                )


def stage_events(video_id, stage, attempt):
    if stage == "write":
        entries = [
            (
                "rina",
                None,
                "work",
                f"Menulis naskah {video_id}, kandidat {attempt}.",
            )
        ]

        if attempt > 1:
            entries = [
                (
                    "sari",
                    "rina",
                    "walk_to",
                    "Perbaiki draft sesuai catatan pemeriksaan.",
                ),
                *entries,
                ("sari", None, "back", ""),
            ]

    else:
        entries = [
            (
                "rina",
                "sari",
                "walk_to",
                "Draft siap diperiksa kesinambungannya.",
            ),
            (
                "sari",
                None,
                "work",
                "Memeriksa brief, alur, lokasi, dan "
                f"perubahan tokoh {video_id}.",
            ),
            ("rina", None, "back", ""),
        ]

    with closing(db._conn()) as connection:
        with connection:
            log_events(connection, video_id, entries)


def export_script(video_id):
    script = db.get_video(video_id)["script"]

    folder = OUTPUT_DIR / video_id
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / (
        f"script.b{script['bible_revision']}."
        f"r{script['script_revision']}.json"
    )

    temporary = path.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            script,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)

    return path


def show_script(video_id):
    video = db.get_video(video_id)

    if not video:
        raise ValueError("Pekerjaan tidak ditemukan.")

    if video["script"] is not None:
        return video["script"]

    row = db.one(
        "SELECT * FROM story_script_attempts "
        "WHERE video_id=? "
        "ORDER BY created_at DESC,rowid DESC LIMIT 1",
        (video_id,),
    )

    if not row:
        return {
            "video_id": video_id,
            "status": video["status"],
            "message": "Belum ada draft naskah.",
        }

    return {
        "video_id": video_id,
        "status": video["status"],
        "bible_revision": row["bible_revision"],
        "attempt": row["attempt"],
        "candidate": json.loads(row["candidate"]),
        "qc": (
            json.loads(row["review"])
            if row["review"]
            else None
        ),
        "error": row["error"],
    }


def stop_job(video_id, status, error):
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                "UPDATE videos SET status=?,updated_at=? "
                "WHERE id=? "
                "AND status='writing' "
                "AND script IS NULL",
                (status, time.time(), video_id),
            )

            if cursor.rowcount:
                log_events(
                    connection,
                    video_id,
                    [
                        (
                            "sari",
                            None,
                            "say",
                            f"Naskah {video_id}: "
                            f"{str(error)[:500]}",
                        ),
                        ("rina", None, "back", ""),
                        ("sari", None, "back", ""),
                    ],
                )


def develop(video_id):
    require_real()

    context = get_context(video_id)
    video = db.get_video(video_id)

    if video["script"] is not None:
        print(
            f"LEWATI {video_id}: naskah sudah tersimpan.",
            flush=True,
        )

        return video["script"]

    if context["story_bible"] is None:
        raise ValueError("Pedoman Agus belum tersedia.")

    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                "UPDATE videos SET "
                "status='writing',updated_at=? "
                "WHERE id=? "
                "AND status IN "
                "('bible_ready','script_failed','script_review_required') "
                "AND story_bible IS NOT NULL "
                "AND script IS NULL "
                "AND style_pack IS NULL "
                "AND scenes IS NULL",
                (time.time(), video_id),
            )

            if not cursor.rowcount:
                raise ValueError(
                    "Pekerjaan sedang diproses atau "
                    "sudah memiliki media produksi."
                )

            log_events(
                connection,
                video_id,
                [
                    (
                        "agus",
                        "rina",
                        "walk_to",
                        "Pedoman cerita siap ditulis menjadi adegan.",
                    ),
                    ("agus", None, "back", ""),
                ],
            )

    run_id = uuid.uuid4().hex

    def record(attempt, candidate, report, error):
        db.run(
            "INSERT INTO story_script_attempts "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                video_id,
                context["bible_revision"],
                run_id,
                attempt,
                json.dumps(candidate, ensure_ascii=False),
                (
                    json.dumps(report, ensure_ascii=False)
                    if report is not None
                    else None
                ),
                error,
                time.time(),
            ),
        )

    try:
        script = story_script.write_and_review(
            context,
            record,
            lambda stage, attempt: stage_events(
                video_id,
                stage,
                attempt,
            ),
        )

        with closing(db._conn()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                row = connection.execute(
                    "SELECT * FROM videos WHERE id=?",
                    (video_id,),
                ).fetchone()

                if (
                    not row
                    or row["status"] != "writing"
                    or row["bible_revision"] != context["bible_revision"]
                    or json.loads(row["story_bible"])
                    != context["story_bible"]
                    or any(
                        row[key] is not None
                        for key in ("script", "style_pack", "scenes")
                    )
                ):
                    raise ValueError(
                        "Konteks atau hasil produksi berubah; "
                        "draft tidak disimpan sebagai naskah final."
                    )

                if (
                    row["brief"]
                    and json.loads(row["brief"]) != context["brief"]
                ):
                    raise ValueError(
                        "Brief berubah; draft tidak disimpan "
                        "sebagai naskah final."
                    )

                connection.execute(
                    "UPDATE videos SET "
                    "script=?,status='script_ready',updated_at=? "
                    "WHERE id=?",
                    (
                        json.dumps(script, ensure_ascii=False),
                        time.time(),
                        video_id,
                    ),
                )

                log_events(
                    connection,
                    video_id,
                    [
                        (
                            "sari",
                            None,
                            "say",
                            "Naskah lolos pemeriksaan: "
                            f"{len(script['scenes'])} adegan.",
                        ),
                        (
                            "rina",
                            None,
                            "say",
                            f"Naskah '{script['title']}' "
                            "siap untuk Bayu.",
                        ),
                        ("rina", None, "back", ""),
                        ("sari", None, "back", ""),
                    ],
                )

    except KeyboardInterrupt:
        stop_job(
            video_id,
            "bible_ready",
            "Penulisan dihentikan; pedoman tetap tersedia.",
        )

        raise

    except Exception as exc:
        status = (
            "script_review_required"
            if isinstance(exc, story_script.ScriptReviewRequired)
            else "script_failed"
        )

        stop_job(video_id, status, exc)
        raise

    try:
        print(
            f"BERHASIL {video_id}: {export_script(video_id)}",
            flush=True,
        )

    except OSError:
        print(
            f"BERHASIL {video_id}: "
            "naskah tersimpan di database; "
            "ekspor file belum berhasil.",
            flush=True,
        )

    return script


def next_job(source):
    rows = db.query(
        "SELECT id,brief FROM videos "
        "WHERE status='bible_ready' "
        "AND story_bible IS NOT NULL "
        "AND script IS NULL "
        "AND style_pack IS NULL "
        "AND scenes IS NULL "
        "ORDER BY created_at,id"
    )

    for row in rows:
        brief = (
            json.loads(row["brief"])
            if row["brief"]
            else {"source": "legacy"}
        )

        if source == "all" or brief.get("source") == source:
            return row["id"]

    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--id",
        help="Tulis satu pekerjaan atau ulangi pekerjaan gagal",
    )

    mode.add_argument(
        "--once",
        action="store_true",
    )

    mode.add_argument(
        "--show",
        help="Lihat naskah atau draft dan QC terbaru",
    )

    parser.add_argument(
        "--source",
        choices=("telegram", "cli", "all"),
        default="telegram",
    )

    args = parser.parse_args()

    try:
        initialize()

        if args.show:
            print(
                json.dumps(
                    show_script(args.show),
                    ensure_ascii=False,
                    indent=2,
                )
            )

            return

        require_real()

        with worker_lock("script-worker.lock", "Rina"):
            recover_interrupted()

            if args.id:
                develop(args.id)
                return

            print(
                f"Worker Rina aktif. Sumber: {args.source}. "
                "Ctrl+C untuk berhenti.",
                flush=True,
            )

            while True:
                video_id = next_job(args.source)

                if video_id:
                    try:
                        develop(video_id)

                    except (ValueError, RuntimeError, OSError) as exc:
                        if args.once:
                            raise

                        print(
                            f"GAGAL {video_id}: {exc}",
                            flush=True,
                        )

                elif args.once:
                    print(
                        "Tidak ada pedoman yang menunggu penulisan."
                    )

                if args.once:
                    return

                time.sleep(2)

    except KeyboardInterrupt:
        print("\nWorker Rina dihentikan.")

    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()