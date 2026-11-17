import copy
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from office import db
from office import story_planner as planner
from office import story_worker as worker
from office.story_context import (
    create_story,
    get_context,
    save_bible,
)


def bible():
    return {
        "title": "Jalan pulang",
        "premise": "Ikan menemukan kelompoknya.",
        "genre": "Petualangan",
        "tone": "Hangat",
        "ending": "Ikan pulang bersama kelompoknya.",
        "characters": [
            {
                "id": "ikan",
                "name": "Ikan",
                "description": "Ikan kecil bersisik biru.",
            }
        ],
        "locations": [
            {
                "id": "laut",
                "name": "Laut",
                "description": "Laut dengan karang berwarna.",
            }
        ],
        "props": [],
        "beats": [
            {
                "id": "awal",
                "action": "Ikan mencari kelompoknya.",
                "characters": ["ikan"],
                "location": "laut",
                "props": [],
            }
        ],
        "continuity_rules": [
            "Warna sisik ikan tetap biru."
        ],
    }


class StoryPlannerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)

        root = Path(folder.name)
        (root / "data").mkdir()

        replacements = [
            patch.object(
                db,
                "DB_PATH",
                root / "office.db",
            ),
            patch.object(
                worker,
                "OUTPUT_DIR",
                root / "output",
            ),
            patch.object(
                worker,
                "DATA_DIR",
                root / "data",
            ),
            patch.object(
                planner.llm,
                "is_mock",
                return_value=False,
            ),
            patch.object(
                planner.llm,
                "settings",
                return_value=None,
            ),
        ]

        for replacement in replacements:
            replacement.start()
            self.addCleanup(replacement.stop)

        api = patch.object(
            planner.llm,
            "ask_json",
            return_value=bible(),
        )

        self.api = api.start()
        self.addCleanup(api.stop)

        self.video_id = create_story(
            "Ikan biru mencari kelompoknya.",
            source="telegram",
        )

    def test_success_saves_context_status_export_and_events(self):
        self.assertEqual(
            worker.develop(self.video_id),
            1,
        )

        context = get_context(self.video_id)

        self.assertEqual(
            context["status"],
            "bible_ready",
        )

        self.assertEqual(
            context["story_bible"]["characters"][0]["id"],
            "ikan",
        )

        path = (
            worker.OUTPUT_DIR
            / self.video_id
            / "story_bible.r1.json"
        )

        exported = json.loads(
            path.read_text(encoding="utf-8")
        )

        self.assertEqual(
            exported["story_bible"],
            context["story_bible"],
        )

        actions = [
            row["action"]
            for row in db.query(
                "SELECT action FROM events ORDER BY id"
            )
        ]

        self.assertEqual(
            actions,
            ["walk_to", "work", "back", "say", "back"],
        )

    def test_full_brief_is_sent_without_telegram_metadata(self):
        brief = {
            "raw_text": (
                "Awal cerita.\n"
                + "Rincian penting. " * 300
                + "Akhir harus bahagia."
            ),
            "language": "id",
            "target_duration_sec": 60,
            "telegram": {"chat_id": "private"},
        }

        planner.build_bible(brief)

        payload = json.loads(
            self.api.call_args.args[1]
        )

        self.assertEqual(
            payload["brief"]["raw_text"],
            brief["raw_text"],
        )

        self.assertNotIn(
            "telegram",
            payload["brief"],
        )

    def test_schema_error_is_returned_to_model_for_repair(self):
        invalid = copy.deepcopy(bible())
        invalid["beats"][0]["characters"] = ["tidak_ada"]

        self.api.side_effect = [invalid, bible()]

        worker.develop(self.video_id)

        self.assertEqual(self.api.call_count, 2)

        repair = json.loads(
            self.api.call_args.args[1]
        )

        self.assertIn("validation_error", repair)

        self.assertEqual(
            repair["previous_candidate"],
            invalid,
        )

    def test_three_invalid_candidates_do_not_save_a_bible(self):
        self.api.return_value = {"title": "Belum lengkap"}

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        context = get_context(self.video_id)

        self.assertEqual(self.api.call_count, 3)
        self.assertEqual(context["status"], "planning_failed")
        self.assertEqual(context["bible_revision"], 0)
        self.assertIsNone(context["story_bible"])

    def test_mock_mode_does_not_claim_a_job(self):
        with patch.object(
            planner.llm,
            "is_mock",
            return_value=True,
        ):
            with self.assertRaises(RuntimeError):
                worker.develop(self.video_id)

        self.assertEqual(
            get_context(self.video_id)["status"],
            "queued",
        )

        self.api.assert_not_called()

    def test_existing_plan_is_not_generated_again(self):
        worker.develop(self.video_id)

        self.assertEqual(
            worker.develop(self.video_id),
            1,
        )

        self.assertEqual(self.api.call_count, 1)

    def test_failed_job_needs_explicit_retry(self):
        self.api.side_effect = RuntimeError(
            "Layanan belum tersedia"
        )

        with self.assertRaises(RuntimeError):
            worker.develop(self.video_id)

        self.assertIsNone(
            worker.next_job("telegram")
        )

        self.api.side_effect = None

        self.assertEqual(
            worker.develop(self.video_id),
            1,
        )

        self.assertEqual(
            len(db.query("SELECT id FROM videos")),
            1,
        )

    def test_existing_media_are_not_overwritten(self):
        db.update_video(
            self.video_id,
            script={"title": "Lama"},
        )

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.api.assert_not_called()

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            {"title": "Lama"},
        )

    def test_external_transaction_can_roll_back_the_bible(self):
        with closing(db._conn()) as connection:
            with self.assertRaises(RuntimeError):
                with connection:
                    connection.execute("BEGIN IMMEDIATE")

                    save_bible(
                        self.video_id,
                        bible(),
                        expected_revision=0,
                        connection=connection,
                    )

                    raise RuntimeError(
                        "Rollback transaksi pemanggil"
                    )

        self.assertIsNone(
            get_context(self.video_id)["story_bible"]
        )

        self.assertEqual(
            get_context(self.video_id)["bible_revision"],
            0,
        )

    def test_export_failure_keeps_valid_database_result(self):
        with patch.object(
            worker,
            "export_context",
            side_effect=OSError(
                "Tidak dapat menulis file"
            ),
        ):
            self.assertEqual(
                worker.develop(self.video_id),
                1,
            )

        self.assertEqual(
            get_context(self.video_id)["status"],
            "bible_ready",
        )

    def test_interrupted_job_returns_to_queue(self):
        self.api.side_effect = KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            worker.develop(self.video_id)

        self.assertEqual(
            get_context(self.video_id)["status"],
            "queued",
        )

        self.assertIsNone(
            get_context(self.video_id)["story_bible"]
        )

    def test_orphaned_planning_job_is_recovered(self):
        db.update_video(
            self.video_id,
            status="planning",
        )

        with worker.worker_lock():
            worker.recover_interrupted()

        self.assertEqual(
            get_context(self.video_id)["status"],
            "queued",
        )

    def test_one_agus_worker_at_a_time(self):
        with worker.worker_lock():
            with self.assertRaises(RuntimeError):
                with worker.worker_lock():
                    self.fail(
                        "Dua worker tidak boleh berjalan bersamaan"
                    )

    def test_source_filter_keeps_cli_jobs_separate(self):
        cli_id = create_story(
            "Cerita CLI",
            source="cli",
        )

        self.assertEqual(
            worker.next_job("telegram"),
            self.video_id,
        )

        self.assertEqual(
            worker.next_job("cli"),
            cli_id,
        )

    def test_final_event_failure_rolls_back_bible_and_revision(self):
        original = worker.log_events

        def failing_event(connection, video_id, entries):
            if entries[0][3].startswith("Pedoman '"):
                raise ValueError(
                    "Gagal menyimpan event akhir"
                )

            return original(
                connection,
                video_id,
                entries,
            )

        with patch.object(
            worker,
            "log_events",
            side_effect=failing_event,
        ):
            with self.assertRaises(ValueError):
                worker.develop(self.video_id)

        context = get_context(self.video_id)

        self.assertIsNone(context["story_bible"])
        self.assertEqual(context["bible_revision"], 0)
        self.assertEqual(context["status"], "planning_failed")


if __name__ == "__main__":
    unittest.main()