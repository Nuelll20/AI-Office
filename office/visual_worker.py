"""Worker Bayu untuk storyboard dan manifest aset."""

import argparse
import json
import time
from contextlib import closing

from . import db, story_visual
from .config import OUTPUT_DIR
from .story_planner import require_real
from .story_worker import log_events, worker_lock
from .storyboard_preview import render_html


def context_from_row(row):
    brief = (
        json.loads(row["brief"])
        if row["brief"]
        else {
            "raw_text": row["idea"],
            "language": "id",
            "target_duration_sec": None,
        }
    )

    return {
        "video_id": row["id"],
        "brief": brief,
        "bible_revision": row["bible_revision"],
        "story_bible": (
            json.loads(row["story_bible"])
            if row["story_bible"]
            else None
        ),
        "script": (
            json.loads(row["script"])
            if row["script"]
            else None
        ),
    }


def load_context(video_id):
    row = db.one(
        "SELECT * FROM videos WHERE id=?",
        (video_id,),
    )

    if not row:
        raise ValueError("Pekerjaan tidak ditemukan.")

    return context_from_row(row)


def export_board(board):
    folder = OUTPUT_DIR / board["video_id"]
    folder.mkdir(parents=True, exist_ok=True)

    name = (
        f"storyboard.b{board['bible_revision']}."
        f"s{board['script_revision']}"
    )

    json_path = folder / f"{name}.json"
    temporary = json_path.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            board,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(json_path)

    html_path = folder / f"{name}.html"
    temporary_html = html_path.with_suffix(".tmp")

    temporary_html.write_text(
        render_html(board),
        encoding="utf-8",
    )

    temporary_html.replace(html_path)

    return json_path, html_path


def recover_interrupted():
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            rows = connection.execute(
                "SELECT id FROM videos "
                "WHERE status='storyboarding' "
                "AND script IS NOT NULL "
                "AND scenes IS NULL "
                "AND style_pack IS NULL"
            ).fetchall()

            for row in rows:
                connection.execute(
                    "UPDATE videos SET "
                    "status='script_ready',updated_at=? "
                    "WHERE id=?",
                    (time.time(), row["id"]),
                )

                log_events(
                    connection,
                    row["id"],
                    [
                        (
                            "bayu",
                            None,
                            "back",
                            "Perencanaan terputus; naskah tetap tersedia.",
                        )
                    ],
                )


def stop_job(video_id, error, interrupted=False):
    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                "UPDATE videos SET status=?,updated_at=? "
                "WHERE id=? "
                "AND status='storyboarding' "
                "AND scenes IS NULL",
                (
                    (
                        "script_ready"
                        if interrupted
                        else "storyboard_failed"
                    ),
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
                            "bayu",
                            None,
                            "say",
                            f"Storyboard {video_id}: "
                            f"{str(error)[:500]}",
                        ),
                        ("bayu", None, "back", ""),
                    ],
                )


def develop(video_id):
    require_real()

    context = load_context(video_id)
    expected_hash = story_visual.source_hash(context)
    video = db.get_video(video_id)

    if video["scenes"] is not None:
        existing = video["scenes"]

        if (
            isinstance(existing, dict)
            and existing.get("schema_version") == 3
            and existing.get("source_hash") == expected_hash
        ):
            print(
                f"LEWATI {video_id}: storyboard masih sesuai sumber.",
                flush=True,
            )
            return existing

        raise ValueError(
            "Sudah ada rencana visual dari sumber atau format berbeda."
        )

    story_visual.prepare_assets(context)

    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                "SELECT * FROM videos WHERE id=?",
                (video_id,),
            ).fetchone()

            if (
                not row
                or story_visual.source_hash(
                    context_from_row(row)
                ) != expected_hash
            ):
                raise ValueError(
                    "Sumber berubah sebelum pekerjaan dimulai."
                )

            cursor = connection.execute(
                "UPDATE videos SET "
                "status='storyboarding',updated_at=? "
                "WHERE id=? "
                "AND status IN ('script_ready','storyboard_failed') "
                "AND scenes IS NULL "
                "AND style_pack IS NULL",
                (time.time(), video_id),
            )

            if not cursor.rowcount:
                raise ValueError(
                    "Pekerjaan sedang diproses atau sudah "
                    "memiliki hasil produksi."
                )

            log_events(
                connection,
                video_id,
                [
                    (
                        "rina",
                        "bayu",
                        "walk_to",
                        "Naskah siap direncanakan menjadi visual.",
                    ),
                    (
                        "bayu",
                        None,
                        "work",
                        f"Menyusun shot, aset, dan gerakan {video_id}.",
                    ),
                    ("rina", None, "back", ""),
                ],
            )

    try:
        board = story_visual.build_storyboard(context)

        with closing(db._conn()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                row = connection.execute(
                    "SELECT * FROM videos WHERE id=?",
                    (video_id,),
                ).fetchone()

                if (
                    not row
                    or row["status"] != "storyboarding"
                    or row["scenes"] is not None
                    or row["style_pack"] is not None
                    or story_visual.source_hash(
                        context_from_row(row)
                    ) != expected_hash
                ):
                    raise ValueError(
                        "Sumber berubah; storyboard tidak diterapkan."
                    )

                connection.execute(
                    "UPDATE videos SET "
                    "scenes=?,status='storyboard_ready',updated_at=? "
                    "WHERE id=?",
                    (
                        json.dumps(board, ensure_ascii=False),
                        time.time(),
                        video_id,
                    ),
                )

                log_events(
                    connection,
                    video_id,
                    [
                        (
                            "bayu",
                            None,
                            "say",
                            f"Storyboard selesai: "
                            f"{len(board['scenes'])} adegan, "
                            f"{len(board['assets'])} aset.",
                        ),
                        ("bayu", None, "back", ""),
                    ],
                )

    except KeyboardInterrupt:
        stop_job(
            video_id,
            "Dihentikan pengguna.",
            interrupted=True,
        )
        raise

    except Exception as exc:
        stop_job(video_id, exc)
        raise

    try:
        paths = export_board(board)

        print(
            f"BERHASIL {video_id}\n"
            f"JSON: {paths[0]}\n"
            f"Pratinjau: {paths[1]}",
            flush=True,
        )

    except OSError:
        print(
            f"BERHASIL {video_id}: storyboard tersimpan "
            "di database; ekspor file belum berhasil.",
            flush=True,
        )

    return board


def summary(video_id):
    video = db.get_video(video_id)

    if not video:
        raise ValueError("Pekerjaan tidak ditemukan.")

    board = video["scenes"]

    if (
        not isinstance(board, dict)
        or board.get("schema_version") != 3
    ):
        return {
            "video_id": video_id,
            "status": video["status"],
            "message": "Belum ada storyboard Bayu.",
        }

    return {
        "video_id": video_id,
        "status": video["status"],
        "bible_revision": board["bible_revision"],
        "script_revision": board["script_revision"],
        "scene_count": len(board["scenes"]),
        "asset_count": len(board["assets"]),
        "scenes": [
            {
                "id": scene["id"],
                "shot": scene["visual"]["shot"],
                "lighting": scene["visual"]["lighting"]["mode"],
                "action_count": len(
                    scene["visual"]["actions"]
                ),
            }
            for scene in board["scenes"]
        ],
    }


def next_job(source):
    rows = db.query(
        "SELECT id,brief FROM videos "
        "WHERE status='script_ready' "
        "AND script IS NOT NULL "
        "AND scenes IS NULL "
        "AND style_pack IS NULL "
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

    mode.add_argument("--id")
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--summary")

    parser.add_argument(
        "--source",
        choices=("telegram", "cli", "all"),
        default="telegram",
    )

    args = parser.parse_args()

    try:
        db.init()

        if args.summary:
            print(
                json.dumps(
                    summary(args.summary),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        require_real()

        with worker_lock("visual-worker.lock", "Bayu"):
            recover_interrupted()

            if args.id:
                develop(args.id)
                return

            print(
                "Worker Bayu aktif. Ctrl+C untuk berhenti.",
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
                    print("Tidak ada naskah yang menunggu.")

                if args.once:
                    return

                time.sleep(2)

    except KeyboardInterrupt:
        print("\nWorker Bayu dihentikan.")

    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()