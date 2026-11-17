"""Worker Agus; penerimaan Telegram berjalan pada proses terpisah."""

import argparse
import json
import time
from contextlib import closing, contextmanager

from . import db, story_planner
from .config import DATA_DIR, OUTPUT_DIR
from .story_context import get_context, save_bible


@contextmanager
def worker_lock(name="story-worker.lock", actor="Agus"):
    path = DATA_DIR / name

    with path.open("a+b") as handle:
        handle.seek(0, 2)

        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()

        handle.seek(0)

        try:
            import os

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )

            else:
                import fcntl

                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )

        except OSError:
            raise RuntimeError(
                f"Worker {actor} lain masih berjalan. "
                "Hentikan worker tersebut dahulu."
            ) from None

        try:
            yield

        finally:
            handle.seek(0)

            if os.name == "nt":
                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )

            else:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )


def log_events(connection, video_id, entries):
    now = time.time()

    connection.executemany(
        "INSERT INTO events"
        "(ts,actor,target,action,text,video_id) "
        "VALUES(?,?,?,?,?,?)",
        [
            (
                now,
                actor,
                target,
                action,
                text,
                video_id,
            )
            for actor, target, action, text in entries
        ],
    )


def recover_interrupted():
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            rows = connection.execute(
                "SELECT id FROM videos "
                "WHERE status='planning' "
                "AND brief IS NOT NULL "
                "AND story_bible IS NULL "
                "AND style_pack IS NULL "
                "AND script IS NULL "
                "AND scenes IS NULL"
            ).fetchall()

            for row in rows:
                connection.execute(
                    "UPDATE videos SET "
                    "status='queued',updated_at=? "
                    "WHERE id=?",
                    (time.time(), row["id"]),
                )

                log_events(
                    connection,
                    row["id"],
                    [
                        (
                            "agus",
                            None,
                            "back",
                            "Pekerjaan terputus dikembalikan ke antrean.",
                        )
                    ],
                )


def export_context(video_id):
    context = get_context(video_id)

    folder = OUTPUT_DIR / video_id
    folder.mkdir(parents=True, exist_ok=True)

    path = (
        folder
        / f"story_bible.r{context['bible_revision']}.json"
    )

    temporary = path.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            context,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)

    return path


def mark_stopped(video_id, error, interrupted=False):
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                "UPDATE videos SET status=?,updated_at=? "
                "WHERE id=? "
                "AND status='planning' "
                "AND story_bible IS NULL",
                (
                    "queued" if interrupted else "planning_failed",
                    time.time(),
                    video_id,
                ),
            )

            if cursor.rowcount:
                log_events(
                    connection,
                    video_id,
                    [
                        (
                            "agus",
                            None,
                            "say",
                            f"Pengembangan {video_id} berhenti: "
                            f"{str(error)[:500]}",
                        ),
                        ("agus", None, "back", ""),
                    ],
                )


def develop(video_id):
    story_planner.require_real()
    context = get_context(video_id)

    if context["story_bible"] is not None:
        print(
            f"LEWATI {video_id}: "
            f"pedoman revisi {context['bible_revision']} "
            "sudah tersimpan.",
            flush=True,
        )

        return context["bible_revision"]

    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                "UPDATE videos SET "
                "status='planning',updated_at=? "
                "WHERE id=? "
                "AND status IN ('queued','planning_failed') "
                "AND story_bible IS NULL "
                "AND style_pack IS NULL "
                "AND script IS NULL "
                "AND scenes IS NULL",
                (time.time(), video_id),
            )

            if not cursor.rowcount:
                raise ValueError(
                    "Pekerjaan sedang diproses atau "
                    "sudah memiliki hasil produksi."
                )

            log_events(
                connection,
                video_id,
                [
                    (
                        "adit",
                        "agus",
                        "walk_to",
                        f"Menyerahkan brief {video_id} kepada Agus.",
                    ),
                    (
                        "agus",
                        None,
                        "work",
                        "Mengembangkan alur dan pedoman "
                        f"cerita {video_id}...",
                    ),
                    ("adit", None, "back", ""),
                ],
            )

    try:
        bible = story_planner.build_bible(context["brief"])

        with closing(db._conn()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                row = connection.execute(
                    "SELECT status,brief FROM videos WHERE id=?",
                    (video_id,),
                ).fetchone()

                if not row or row["status"] != "planning":
                    raise ValueError(
                        "Status pekerjaan telah berubah; "
                        "hasil tidak disimpan."
                    )

                if (
                    row["brief"]
                    and json.loads(row["brief"]) != context["brief"]
                ):
                    raise ValueError(
                        "Brief berubah selama pengembangan; "
                        "hasil tidak disimpan."
                    )

                revision = save_bible(
                    video_id,
                    bible,
                    expected_revision=context["bible_revision"],
                    connection=connection,
                )

                connection.execute(
                    "UPDATE videos SET "
                    "status='bible_ready',updated_at=? "
                    "WHERE id=?",
                    (time.time(), video_id),
                )

                log_events(
                    connection,
                    video_id,
                    [
                        (
                            "agus",
                            None,
                            "say",
                            f"Pedoman '{bible['title']}' tersimpan: "
                            f"{len(bible['beats'])} beat, "
                            f"revisi {revision}.",
                        ),
                        ("agus", None, "back", ""),
                    ],
                )

    except KeyboardInterrupt:
        mark_stopped(
            video_id,
            "Dihentikan pengguna.",
            interrupted=True,
        )

        raise

    except Exception as exc:
        mark_stopped(video_id, exc)
        raise

    try:
        print(
            f"BERHASIL {video_id}: {export_context(video_id)}",
            flush=True,
        )

    except OSError:
        print(
            f"BERHASIL {video_id}: "
            "pedoman tersimpan di database; "
            "ekspor file belum berhasil.",
            flush=True,
        )

    return revision


def next_job(source):
    rows = db.query(
        "SELECT id,brief FROM videos "
        "WHERE status='queued' "
        "AND brief IS NOT NULL "
        "AND story_bible IS NULL "
        "AND style_pack IS NULL "
        "AND script IS NULL "
        "AND scenes IS NULL "
        "ORDER BY created_at,id"
    )

    for row in rows:
        if (
            source == "all"
            or json.loads(row["brief"]).get("source") == source
        ):
            return row["id"]

    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--id",
        help="Kembangkan satu ID, termasuk mengulang pekerjaan gagal",
    )

    mode.add_argument(
        "--once",
        action="store_true",
        help="Proses maksimal satu pekerjaan antrean",
    )

    parser.add_argument(
        "--source",
        choices=("telegram", "cli", "all"),
        default="telegram",
    )

    args = parser.parse_args()

    try:
        db.init()
        story_planner.require_real()

        with worker_lock():
            recover_interrupted()

            if args.id:
                develop(args.id)
                return

            print(
                f"Worker Agus aktif. Sumber: {args.source}. "
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
                    print("Tidak ada pekerjaan yang menunggu.")

                if args.once:
                    return

                time.sleep(2)

    except KeyboardInterrupt:
        print("\nWorker Agus dihentikan.")

    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()