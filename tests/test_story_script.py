import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from office import db
from office import script_worker as worker
from office import story_script as script
from office import story_worker as agus
from office.story_context import (
    create_story,
    get_context,
    save_bible,
)


def bible():
    return {
        "title": "Perjalanan tokoh",
        "premise": "Tokoh belajar mengatasi masalah.",
        "genre": "Petualangan",
        "tone": "Hangat",
        "ending": "Tokoh menemukan jalan pulang.",
        "characters": [
            {
                "id": "utama",
                "name": "Tokoh",
                "description": "Tokoh dengan ciri tetap.",
            }
        ],
        "locations": [
            {
                "id": "tempat",
                "name": "Lokasi",
                "description": "Tempat cerita.",
            }
        ],
        "props": [],
        "continuity_rules": [
            "Pertahankan ciri identitas."
        ],
        "beats": [
            {
                "id": identity,
                "action": action,
                "characters": ["utama"],
                "location": "tempat",
                "props": [],
            }
            for identity, action in (
                ("awal", "Tokoh menghadapi masalah."),
                ("akhir", "Tokoh menemukan jalan pulang."),
            )
        ],
    }


def draft():
    return {
        "title": "Perjalanan tokoh",
        "description": (
            "Tokoh belajar dan menemukan jalan pulang."
        ),
        "hashtags": ["#cerita"],
        "character_states": [
            {
                "id": "utama_awal",
                "character_id": "utama",
                "description": "Penampilan awal tokoh.",
            }
        ],
        "scenes": [
            {
                "id": number,
                "beat_id": beat,
                "location": "tempat",
                "time_label": "Hari itu",
                "action": action,
                "characters": ["utama"],
                "states": {"utama": "utama_awal"},
                "extras": [],
                "props": [],
                "conditions": [],
                "lines": [
                    {
                        "speaker": None,
                        "text": action,
                    }
                ],
            }
            for number, (beat, action) in enumerate(
                (
                    (
                        "awal",
                        "Tokoh menghadapi masalah di perjalanan.",
                    ),
                    (
                        "akhir",
                        "Setelah belajar, tokoh berhasil "
                        "menemukan jalan pulang.",
                    ),
                ),
                1,
            )
        ],
    }


class StoryScriptTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)

        root = Path(folder.name)
        (root / "data").mkdir()

        for replacement in (
            patch.object(db, "DB_PATH", root / "office.db"),
            patch.object(worker, "OUTPUT_DIR", root / "output"),
            patch.object(agus, "DATA_DIR", root / "data"),
            patch.object(
                script.llm,
                "is_mock",
                return_value=False,
            ),
            patch.object(
                script.llm,
                "settings",
                return_value=None,
            ),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

        worker.initialize()

        self.video_id = create_story(
            "Tokoh mencari jalan pulang.",
            source="telegram",
        )

        save_bible(
            self.video_id,
            bible(),
            expected_revision=0,
        )

        db.update_video(
            self.video_id,
            status="bible_ready",
        )

        self.drafts = [draft()]
        self.reviews = [
            {"approved": True, "issues": []}
        ]

        self.writer_calls = []
        self.review_calls = []
        self.on_review = lambda: None

        api = patch.object(
            script.llm,
            "ask_json",
            side_effect=self.ask,
        )

        api.start()
        self.addCleanup(api.stop)

    def ask(self, system, user, **kwargs):
        if system == script.WRITER:
            self.writer_calls.append(json.loads(user))

            value = self.drafts[
                min(
                    len(self.writer_calls) - 1,
                    len(self.drafts) - 1,
                )
            ]

        else:
            self.review_calls.append(json.loads(user))
            self.on_review()

            value = self.reviews[
                min(
                    len(self.review_calls) - 1,
                    len(self.reviews) - 1,
                )
            ]

        if isinstance(value, BaseException):
            raise value

        return copy.deepcopy(value)

    def test_approved_script_keeps_bible_and_exports_versioned_result(self):
        original = get_context(self.video_id)["story_bible"]

        result = worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )

        self.assertEqual(result["bible_revision"], 1)
        self.assertEqual(result["schema_version"], 2)
        self.assertTrue(result["qc"]["approved"])

        self.assertEqual(
            get_context(self.video_id)["story_bible"],
            original,
        )

        self.assertTrue(
            (
                worker.OUTPUT_DIR
                / self.video_id
                / "script.b1.r1.json"
            ).exists()
        )

        self.assertEqual(len(self.writer_calls), 1)
        self.assertEqual(len(self.review_calls), 1)

    def test_wrong_cast_location_prop_and_state_references_are_rejected(self):
        changes = [
            lambda scene: scene.update(location="tidak_ada"),
            lambda scene: scene.update(props=["tidak_ada"]),
            lambda scene: scene.update(characters=["tidak_ada"]),
            lambda scene: scene.update(
                states={"utama": "tidak_ada"}
            ),
            lambda scene: scene.update(
                lines=[
                    {
                        "speaker": "tidak_ada",
                        "text": "Dialog",
                    }
                ]
            ),
        ]

        for change in changes:
            data = draft()
            change(data["scenes"][0])

            with self.assertRaises(ValueError):
                script.compile_script(
                    data,
                    get_context(self.video_id),
                )

    def test_multiple_states_keep_one_character_identity(self):
        data = draft()

        data["character_states"].append(
            {
                "id": "utama_lanjut",
                "character_id": "utama",
                "description": (
                    "Penampilan setelah bertahun-tahun."
                ),
            }
        )

        data["scenes"][1]["states"]["utama"] = "utama_lanjut"
        data["scenes"][1]["time_label"] = "Bertahun-tahun kemudian"

        result = script.compile_script(
            data,
            get_context(self.video_id),
        )

        self.assertEqual(
            result["scenes"][1]["characters"],
            ["utama"],
        )

        self.assertEqual(
            result["scenes"][1]["states"]["utama"],
            "utama_lanjut",
        )

    def test_beats_cannot_be_omitted_or_reversed(self):
        variations = (
            [draft()["scenes"][0]],
            list(reversed(draft()["scenes"])),
        )

        for scenes in variations:
            data = draft()
            data["scenes"] = scenes

            for number, scene in enumerate(scenes, 1):
                scene["id"] = number

            with self.assertRaises(ValueError):
                script.compile_script(
                    data,
                    get_context(self.video_id),
                )

    def test_one_beat_can_be_split_into_multiple_scenes(self):
        data = draft()

        data["scenes"].insert(
            1,
            copy.deepcopy(data["scenes"][0]),
        )

        for number, scene in enumerate(data["scenes"], 1):
            scene["id"] = number

        result = script.compile_script(
            data,
            get_context(self.video_id),
        )

        self.assertEqual(len(result["scenes"]), 3)

    def test_long_scene_and_unrealistic_duration_are_rejected(self):
        data = draft()
        data["scenes"][0]["lines"][0]["text"] = "kata " * 61

        with self.assertRaises(ValueError):
            script.compile_script(
                data,
                get_context(self.video_id),
            )

        context = get_context(self.video_id)
        context["brief"]["target_duration_sec"] = 60

        with self.assertRaises(ValueError):
            script.compile_script(draft(), context)

    def test_qc_feedback_reaches_writer_and_repair_is_saved(self):
        issue = {
            "approved": False,
            "issues": [
                {
                    "scene_id": 2,
                    "message": "Jelaskan lompatan waktu.",
                }
            ],
        }

        repaired = draft()
        repaired["scenes"][1]["time_label"] = "Sebulan kemudian"

        self.drafts = [draft(), repaired]
        self.reviews = [
            issue,
            {"approved": True, "issues": []},
        ]

        result = worker.develop(self.video_id)

        self.assertEqual(
            self.writer_calls[1]["feedback"]["qc"],
            issue,
        )

        self.assertEqual(
            result["scenes"][1]["time_label"],
            "Sebulan kemudian",
        )

        self.assertEqual(
            len(
                db.query(
                    "SELECT * FROM story_script_attempts"
                )
            ),
            2,
        )

    def test_repeated_qc_failure_keeps_draft_for_review(self):
        self.reviews = [
            {
                "approved": False,
                "issues": [
                    {
                        "scene_id": None,
                        "message": (
                            "Hubungan sebab-akibat belum jelas."
                        ),
                    }
                ],
            }
        ]

        with self.assertRaises(script.ScriptReviewRequired):
            worker.develop(self.video_id)

        self.assertEqual(len(self.writer_calls), 3)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_review_required",
        )

        self.assertIsNone(
            db.get_video(self.video_id)["script"]
        )

        self.assertFalse(
            worker.show_script(self.video_id)["qc"]["approved"]
        )

    def test_invalid_structure_never_reaches_semantic_qc(self):
        self.drafts = [{"title": "Tidak lengkap"}]

        with self.assertRaises(script.ScriptReviewRequired):
            worker.develop(self.video_id)

        self.assertEqual(len(self.review_calls), 0)

        self.assertIsNotNone(
            worker.show_script(self.video_id)["error"]
        )

    def test_malformed_qc_is_not_treated_as_approval(self):
        self.reviews = [
            {"approved": "true", "issues": []}
        ]

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_failed",
        )

        self.assertIsNotNone(
            worker.show_script(self.video_id)["candidate"]
        )

        self.assertEqual(len(self.writer_calls), 1)

    def test_changed_bible_prevents_stale_script_from_being_saved(self):
        def change():
            save_bible(
                self.video_id,
                bible(),
                expected_revision=1,
            )

        self.on_review = change

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.assertEqual(
            get_context(self.video_id)["bible_revision"],
            2,
        )

        self.assertIsNone(
            db.get_video(self.video_id)["script"]
        )

    def test_stored_script_is_reused_without_new_llm_calls(self):
        worker.develop(self.video_id)
        worker.develop(self.video_id)

        self.assertEqual(len(self.writer_calls), 1)
        self.assertEqual(len(self.review_calls), 1)

    def test_model_failure_does_not_destroy_bible(self):
        self.drafts = [
            RuntimeError("Layanan tidak tersedia")
        ]

        with self.assertRaises(RuntimeError):
            worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_failed",
        )

        self.assertIsNotNone(
            get_context(self.video_id)["story_bible"]
        )

    def test_interruption_preserves_plan_and_returns_job_to_queue(self):
        self.drafts = [KeyboardInterrupt()]

        with self.assertRaises(KeyboardInterrupt):
            worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "bible_ready",
        )

        self.assertIsNotNone(
            get_context(self.video_id)["story_bible"]
        )

    def test_interrupted_writing_can_be_recovered(self):
        db.update_video(
            self.video_id,
            status="writing",
        )

        with agus.worker_lock("script-worker.lock", "Rina"):
            worker.recover_interrupted()

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "bible_ready",
        )

    def test_agus_and_rina_can_run_but_duplicate_rina_cannot(self):
        with agus.worker_lock():
            with agus.worker_lock("script-worker.lock", "Rina"):
                with self.assertRaises(RuntimeError):
                    with agus.worker_lock(
                        "script-worker.lock",
                        "Rina",
                    ):
                        self.fail("Worker Rina ganda")

    def test_final_event_failure_rolls_back_final_script(self):
        original = worker.log_events

        def fail(connection, video_id, entries):
            if entries[0][3].startswith(
                "Naskah lolos pemeriksaan"
            ):
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
            side_effect=fail,
        ):
            with self.assertRaises(ValueError):
                worker.develop(self.video_id)

        self.assertIsNone(
            db.get_video(self.video_id)["script"]
        )

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_failed",
        )

    def test_export_failure_preserves_approved_database_script(self):
        with patch.object(
            worker,
            "export_script",
            side_effect=OSError("Gagal menulis file"),
        ):
            worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )

        self.assertTrue(
            db.get_video(self.video_id)["script"]["qc"]["approved"]
        )


if __name__ == "__main__":
    unittest.main()