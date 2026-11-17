"""Revisi naskah sebelum tahap visual dengan arsip versi."""

import argparse
import json
import time
import uuid
from contextlib import closing

from . import db, script_worker, story_script
from .story_context import get_context
from .story_planner import require_real
from .story_worker import log_events, worker_lock


SCHEMA = """
CREATE TABLE IF NOT EXISTS story_script_versions(
    video_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(video_id,revision)
);
"""


def initialize():
    script_worker.initialize()

    with closing(db._conn()) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def versions(video_id):
    return db.query(
        "SELECT revision,created_at "
        "FROM story_script_versions "
        "WHERE video_id=? ORDER BY revision",
        (video_id,),
    )


def revise(video_id, notes):
    if (
        not isinstance(notes, str)
        or not 1 <= len(notes.strip()) <= 6000
    ):
        raise ValueError(
            "Catatan revisi harus berisi 1-6000 karakter."
        )

    require_real()

    context = get_context(video_id)
    video = db.get_video(video_id)
    old = video["script"]

    if (
        not isinstance(old, dict)
        or old.get("schema_version") != 2
    ):
        raise ValueError(
            "Pekerjaan belum memiliki naskah "
            "dari Rina versi baru."
        )

    revision = old.get("script_revision")

    if type(revision) is not int or revision < 1:
        raise ValueError(
            "Nomor revisi naskah lama tidak valid."
        )

    if old.get("bible_revision") != context["bible_revision"]:
        raise ValueError(
            "Naskah aktif tidak sesuai revisi pedoman terbaru."
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
                or row["status"] != "script_ready"
                or not row["script"]
                or json.loads(row["script"]) != old
                or row["style_pack"] is not None
                or row["scenes"] is not None
            ):
                raise ValueError(
                    "Revisi hanya tersedia untuk naskah siap "
                    "yang belum masuk tahap visual."
                )

            connection.execute(
                "UPDATE videos SET "
                "status='script_revising',updated_at=? "
                "WHERE id=?",
                (time.time(), video_id),
            )

            log_events(
                connection,
                video_id,
                [
                    (
                        "rina",
                        None,
                        "work",
                        f"Menyiapkan revisi naskah {revision + 1} "
                        f"untuk {video_id}.",
                    )
                ],
            )

    context.update(
        previous_script=old,
        revision_notes=notes.strip(),
        next_script_revision=revision + 1,
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
        new = story_script.write_and_review(
            context,
            record,
            lambda stage, attempt: script_worker.stage_events(
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
                    or row["status"] != "script_revising"
                    or not row["script"]
                    or json.loads(row["script"]) != old
                    or row["bible_revision"]
                    != context["bible_revision"]
                    or json.loads(row["story_bible"])
                    != context["story_bible"]
                    or (
                        row["brief"]
                        and json.loads(row["brief"])
                        != context["brief"]
                    )
                    or row["style_pack"] is not None
                    or row["scenes"] is not None
                ):
                    raise ValueError(
                        "Konteks berubah selama revisi; "
                        "versi baru tidak diterapkan."
                    )

                previous = connection.execute(
                    "SELECT payload FROM story_script_versions "
                    "WHERE video_id=? AND revision=?",
                    (video_id, revision),
                ).fetchone()

                if (
                    previous
                    and json.loads(previous["payload"]) != old
                ):
                    raise ValueError(
                        "Arsip versi lama berbeda "
                        "dari naskah aktif."
                    )

                if not previous:
                    connection.execute(
                        "INSERT INTO story_script_versions "
                        "VALUES(?,?,?,?)",
                        (
                            video_id,
                            revision,
                            json.dumps(old, ensure_ascii=False),
                            time.time(),
                        ),
                    )

                connection.execute(
                    "INSERT INTO story_script_versions "
                    "VALUES(?,?,?,?)",
                    (
                        video_id,
                        revision + 1,
                        json.dumps(new, ensure_ascii=False),
                        time.time(),
                    ),
                )

                connection.execute(
                    "UPDATE videos SET "
                    "script=?,status='script_ready',updated_at=? "
                    "WHERE id=?",
                    (
                        json.dumps(new, ensure_ascii=False),
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
                            f"Revisi naskah {revision + 1} "
                            "lolos pemeriksaan.",
                        ),
                        ("rina", None, "back", ""),
                        ("sari", None, "back", ""),
                    ],
                )

    except BaseException:
        restore(video_id, revision)
        raise

    try:
        print(
            f"BERHASIL {video_id}: "
            f"{script_worker.export_script(video_id)}",
            flush=True,
        )

    except OSError:
        print(
            "Versi baru tersimpan di database; "
            "ekspor file belum berhasil.",
            flush=True,
        )

    return new


def restore(video_id, revision=None):
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                "SELECT status,script FROM videos WHERE id=?",
                (video_id,),
            ).fetchone()

            if (
                row
                and row["status"] == "script_revising"
                and row["script"]
            ):
                old = json.loads(row["script"])

                if (
                    revision is not None
                    and old.get("script_revision") != revision
                ):
                    return

                connection.execute(
                    "UPDATE videos SET "
                    "status='script_ready',updated_at=? "
                    "WHERE id=?",
                    (time.time(), video_id),
                )

                log_events(
                    connection,
                    video_id,
                    [
                        (
                            "rina",
                            None,
                            "say",
                            "Revisi belum diterapkan; "
                            "naskah sebelumnya tetap tersimpan.",
                        ),
                        ("rina", None, "back", ""),
                        ("sari", None, "back", ""),
                    ],
                )


def latest_draft(video_id):
    row = db.one(
        "SELECT * FROM story_script_attempts "
        "WHERE video_id=? "
        "ORDER BY created_at DESC,rowid DESC LIMIT 1",
        (video_id,),
    )

    if not row:
        return {"message": "Belum ada draft."}

    return {
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)

    mode = parser.add_mutually_exclusive_group(required=True)

    mode.add_argument(
        "--notes",
        help="Perbaiki naskah sesuai catatan",
    )

    mode.add_argument(
        "--versions",
        action="store_true",
        help="Daftar versi yang diarsipkan",
    )

    mode.add_argument(
        "--draft",
        action="store_true",
        help="Lihat draft dan QC terakhir",
    )

    mode.add_argument(
        "--recover",
        action="store_true",
        help="Pulihkan status setelah revisi terputus",
    )

    args = parser.parse_args()

    try:
        initialize()

        if args.versions:
            print(
                json.dumps(
                    versions(args.id),
                    indent=2,
                )
            )
            return

        if args.draft:
            print(
                json.dumps(
                    latest_draft(args.id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        with worker_lock("script-worker.lock", "Rina"):
            if args.recover:
                restore(args.id)
            else:
                revise(args.id, args.notes)

    except KeyboardInterrupt:
        print(
            "\nRevisi dihentikan; "
            "naskah sebelumnya dipertahankan."
        )

    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()