import copy
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from office import db
from office.story_context import (
    RevisionConflict,
    create_story,
    get_context,
    make_brief,
    save_bible,
    validate_bible,
)


def bible(prefix, title):
    return {
        "title": title,
        "premise": title,
        "genre": "Sesuai brief",
        "tone": "Sesuai kebutuhan cerita",
        "ending": "Masalah terselesaikan.",
        "characters": [
            {
                "id": prefix,
                "name": prefix,
                "description": "Identitas tetap.",
            }
        ],
        "locations": [
            {
                "id": "tempat",
                "name": "Lokasi",
                "description": "Lokasi cerita.",
            }
        ],
        "props": [],
        "beats": [
            {
                "id": "awal",
                "action": title,
                "characters": [prefix],
                "location": "tempat",
                "props": [],
            }
        ],
        "continuity_rules": ["Pertahankan identitas tokoh."],
    }


class StoryContextTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

        self.database = Path(self.folder.name) / "office.db"

        self.patch = patch.object(
            db,
            "DB_PATH",
            self.database,
        )

        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_migration_preserves_existing_work(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(db.SCHEMA)

            connection.execute(
                "INSERT INTO videos(id,idea,status,script) "
                "VALUES(?,?,?,?)",
                (
                    "old",
                    "Cerita lama",
                    "script_ready",
                    '{"title":"Lama"}',
                ),
            )

            connection.commit()

        # Koneksi awal sudah ditutup sebelum migrasi dijalankan.
        db.init()
        db.init()

        self.assertEqual(
            db.get_video("old")["script"],
            {"title": "Lama"},
        )

        self.assertEqual(
            get_context("old")["brief"]["source"],
            "legacy",
        )

        self.assertEqual(
            get_context("old")["bible_revision"],
            0,
        )

    def test_two_stories_keep_separate_context(self):
        first = create_story("Seekor ikan mencari jalan pulang.")
        second = create_story("Seorang montir memperbaiki jam kota.")

        save_bible(
            first,
            bible("ikan", "Perjalanan ikan"),
            expected_revision=0,
        )

        save_bible(
            second,
            bible("montir", "Jam kota"),
            expected_revision=0,
        )

        self.assertNotEqual(first, second)

        self.assertEqual(
            get_context(first)["story_bible"]["characters"][0]["id"],
            "ikan",
        )

        self.assertEqual(
            get_context(second)["story_bible"]["characters"][0]["id"],
            "montir",
        )

    def test_stale_revision_cannot_overwrite(self):
        video_id = create_story("Sebuah cerita.")
        original = bible("tokoh", "Versi pertama")

        save_bible(video_id, original, expected_revision=0)

        with self.assertRaises(RevisionConflict):
            save_bible(
                video_id,
                bible("lain", "Versi usang"),
                expected_revision=0,
            )

        self.assertEqual(
            get_context(video_id)["story_bible"],
            original,
        )

    def test_invalid_reference_does_not_replace_bible(self):
        video_id = create_story("Sebuah cerita.")
        original = bible("tokoh", "Versi pertama")

        save_bible(video_id, original, expected_revision=0)

        invalid = copy.deepcopy(original)
        invalid["beats"][0]["characters"] = ["tidak_terdaftar"]

        with self.assertRaises(ValueError):
            save_bible(
                video_id,
                invalid,
                expected_revision=1,
            )

        self.assertEqual(
            get_context(video_id)["bible_revision"],
            1,
        )

        self.assertEqual(
            get_context(video_id)["story_bible"],
            original,
        )

    def test_existing_media_are_protected(self):
        video_id = create_story("Sebuah cerita.")

        save_bible(
            video_id,
            bible("tokoh", "Awal"),
            expected_revision=0,
        )

        db.update_video(
            video_id,
            script={"title": "Naskah tersimpan"},
        )

        with self.assertRaises(ValueError):
            save_bible(
                video_id,
                bible("lain", "Revisi"),
                expected_revision=1,
            )

        self.assertEqual(
            db.get_video(video_id)["script"]["title"],
            "Naskah tersimpan",
        )

    def test_nature_story_does_not_require_human_characters(self):
        data = bible("awan", "Perjalanan awan")
        data["characters"] = []
        data["beats"][0]["characters"] = []

        self.assertEqual(
            validate_bible(data)["characters"],
            [],
        )

    def test_video_ids_remain_unique_after_deletion(self):
        ids = [
            create_story(f"Cerita {i}")
            for i in range(3)
        ]

        db.run(
            "DELETE FROM videos WHERE id=?",
            (ids[1],),
        )

        self.assertNotIn(
            create_story("Cerita berikutnya"),
            ids,
        )

    def test_concurrent_intakes_get_different_ids(self):
        db.init()

        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(
                pool.map(
                    db.add_video,
                    [f"Cerita {i}" for i in range(12)],
                )
            )

        self.assertEqual(len(set(ids)), 12)

    def test_invalid_brief_is_rejected(self):
        for duration in (True, float("nan"), -1):
            with self.assertRaises(ValueError):
                make_brief("Cerita", duration=duration)

        with self.assertRaises(ValueError):
            make_brief("   ")


if __name__ == "__main__":
    unittest.main()