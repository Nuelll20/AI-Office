"""Konteks per cerita, tanpa tokoh, genre, atau lokasi bawaan."""

import argparse
import json
import math
import re
import time

from . import db


class RevisionConflict(ValueError):
    pass


def check(condition, message):
    if not condition:
        raise ValueError(message)


def make_brief(text, *, source="cli", language="id", duration=None):
    check(
        isinstance(text, str) and 1 <= len(text.strip()) <= 20000,
        "Cerita harus berisi 1-20000 karakter.",
    )

    check(
        source in {"cli", "telegram", "legacy"},
        "Sumber brief tidak dikenal.",
    )

    check(
        isinstance(language, str)
        and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", language),
        "Kode bahasa tidak valid.",
    )

    check(
        duration is None
        or (
            type(duration) in (int, float)
            and math.isfinite(duration)
            and 5 <= duration <= 600
        ),
        "Target durasi harus 5-600 detik atau None.",
    )

    return {
        "raw_text": text.strip(),
        "source": source,
        "language": language,
        "target_duration_sec": duration,
    }


def create_story(text, **options):
    brief = make_brief(text, **options)
    db.init()

    return db.add_video(brief["raw_text"], brief=brief)


def validate_bible(data):
    required = {
        "title",
        "premise",
        "genre",
        "tone",
        "ending",
        "characters",
        "locations",
        "props",
        "beats",
        "continuity_rules",
    }

    check(
        isinstance(data, dict) and set(data) == required,
        "Field story bible tidak sesuai kontrak.",
    )

    for key in ("title", "premise", "genre", "tone", "ending"):
        check(
            isinstance(data[key], str)
            and 0 < len(data[key].strip()) <= 5000,
            f"{key} harus berupa teks yang tidak kosong.",
        )

    references = {}

    for group in ("characters", "locations", "props"):
        items = data[group]

        check(
            isinstance(items, list) and len(items) <= 100,
            f"{group} harus berupa daftar.",
        )

        ids = set()

        for item in items:
            check(
                isinstance(item, dict)
                and set(item) == {"id", "name", "description"},
                f"Setiap {group} harus memiliki id, name, description.",
            )

            identity = item["id"]

            check(
                isinstance(identity, str)
                and re.fullmatch(r"[a-z][a-z0-9_-]{0,49}", identity)
                and identity not in ids,
                f"ID {group} tidak valid atau duplikat.",
            )

            ids.add(identity)

            for key in ("name", "description"):
                check(
                    isinstance(item[key], str)
                    and 0 < len(item[key].strip()) <= 5000,
                    f"{group}.{key} harus berupa teks.",
                )

        references[group] = ids

    beats = data["beats"]

    check(
        isinstance(beats, list) and 1 <= len(beats) <= 100,
        "Perlu 1-100 beat cerita.",
    )

    seen = set()

    for beat in beats:
        check(
            isinstance(beat, dict)
            and set(beat)
            == {"id", "action", "characters", "location", "props"},
            "Field beat tidak sesuai kontrak.",
        )

        identity = beat["id"]

        check(
            isinstance(identity, str)
            and re.fullmatch(r"[a-z][a-z0-9_-]{0,49}", identity)
            and identity not in seen,
            "ID beat tidak valid atau duplikat.",
        )

        seen.add(identity)

        check(
            isinstance(beat["action"], str)
            and 0 < len(beat["action"].strip()) <= 5000,
            "Aksi beat harus berupa teks.",
        )

        for group in ("characters", "props"):
            values = beat[group]

            check(
                isinstance(values, list)
                and all(isinstance(value, str) for value in values),
                f"Referensi {group} harus daftar ID.",
            )

            check(
                len(set(values)) == len(values)
                and set(values) <= references[group],
                f"Beat merujuk {group} yang tidak terdaftar atau duplikat.",
            )

        location = beat["location"]

        check(
            location is None
            or (
                isinstance(location, str)
                and location in references["locations"]
            ),
            "Beat merujuk lokasi yang tidak terdaftar.",
        )

    rules = data["continuity_rules"]

    check(
        isinstance(rules, list)
        and len(rules) <= 100
        and all(
            isinstance(rule, str)
            and 0 < len(rule.strip()) <= 5000
            for rule in rules
        ),
        "Aturan kesinambungan harus berupa daftar teks.",
    )

    return data


def get_context(video_id):
    video = db.get_video(video_id)

    if not video:
        raise ValueError(f"Pekerjaan {video_id} tidak ditemukan.")

    brief = video["brief"] or make_brief(
        video["idea"],
        source="legacy",
    )

    return {
        "video_id": video_id,
        "brief": brief,
        "story_bible": video["story_bible"],
        "bible_revision": video["bible_revision"],
        "status": video["status"],
    }


def save_bible(
    video_id,
    bible,
    *,
    expected_revision,
    connection=None,
):
    validate_bible(bible)

    check(
        type(expected_revision) is int and expected_revision >= 0,
        "expected_revision harus bilangan bulat >= 0.",
    )

    encoded = json.dumps(
        bible,
        ensure_ascii=False,
        allow_nan=False,
    )

    owned = connection is None
    connection = db._conn() if owned else connection

    try:
        if owned:
            connection.execute("BEGIN IMMEDIATE")
        else:
            check(
                connection.in_transaction,
                "Koneksi bersama harus berada dalam transaksi.",
            )

        row = connection.execute(
            "SELECT * FROM videos WHERE id=?",
            (video_id,),
        ).fetchone()

        check(row is not None, "Pekerjaan tidak ditemukan.")

        if row["bible_revision"] != expected_revision:
            raise RevisionConflict(
                "Konteks telah berubah; baca versi terbaru dahulu."
            )

        check(
            not any(
                row[key] is not None
                for key in ("style_pack", "script", "scenes")
            ),
            "Pedoman pekerjaan yang sudah diproduksi terkunci. "
            "Revisi media belum diaktifkan pada tahap ini.",
        )

        connection.execute(
            "UPDATE videos SET "
            "story_bible=?, "
            "bible_revision=bible_revision+1, "
            "updated_at=? "
            "WHERE id=?",
            (encoded, time.time(), video_id),
        )

        if owned:
            connection.commit()

        return expected_revision + 1

    except Exception:
        if owned:
            connection.rollback()
        raise

    finally:
        if owned:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    new = commands.add_parser("new")
    new.add_argument("text")
    new.add_argument("--language", default="id")
    new.add_argument("--duration", type=float)

    show = commands.add_parser("show")
    show.add_argument("video_id")

    args = parser.parse_args()

    try:
        db.init()

        if args.command == "new":
            video_id = create_story(
                args.text,
                language=args.language,
                duration=args.duration,
            )

            print(f"Brief tersimpan: {video_id}")
            print(
                "Tahap berikutnya: pengembangan pedoman cerita oleh agent."
            )

        else:
            print(
                json.dumps(
                    get_context(args.video_id),
                    ensure_ascii=False,
                    indent=2,
                )
            )

    except ValueError as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()