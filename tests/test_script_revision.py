import json
import unittest

import test_story_script as base

from office import db
from office import script_revision as revision
from office import script_worker as worker
from office import story_worker as agus
from office.story_context import get_context


class ScriptRevisionTests(unittest.TestCase):
    def setUp(self):
        base.StoryScriptTests.setUp(self)

        revision.initialize()

        self.old = worker.develop(self.video_id)

        self.writer_calls.clear()
        self.review_calls.clear()

    def ask(self, system, user, **kwargs):
        return base.StoryScriptTests.ask(
            self,
            system,
            user,
            **kwargs,
        )

    def test_success_archives_old_and_new_versions(self):
        changed = base.draft()
        changed["description"] = "Ringkasan yang diperjelas."
        self.drafts = [changed]

        new = revision.revise(
            self.video_id,
            "Perjelas sebab-akibat.",
        )

        self.assertEqual(new["script_revision"], 2)
        self.assertEqual(new["writer_version"], 2)

        self.assertEqual(
            self.writer_calls[0]["previous_script"],
            self.old,
        )

        self.assertEqual(
            self.writer_calls[0]["revision_notes"],
            "Perjelas sebab-akibat.",
        )

        self.assertEqual(
            [
                row["revision"]
                for row in revision.versions(self.video_id)
            ],
            [1, 2],
        )

        archived = db.one(
            "SELECT payload FROM story_script_versions "
            "WHERE video_id=? AND revision=1",
            (self.video_id,),
        )

        self.assertEqual(
            json.loads(archived["payload"]),
            self.old,
        )

        self.assertEqual(
            get_context(self.video_id)["bible_revision"],
            1,
        )

        self.assertTrue(
            (
                worker.OUTPUT_DIR
                / self.video_id
                / "script.b1.r1.json"
            ).exists()
        )

        self.assertTrue(
            (
                worker.OUTPUT_DIR
                / self.video_id
                / "script.b1.r2.json"
            ).exists()
        )

    def test_rejected_revision_preserves_active_script(self):
        self.reviews = [
            {
                "approved": False,
                "issues": [
                    {
                        "scene_id": None,
                        "message": "Alur belum jelas.",
                    }
                ],
            }
        ]

        with self.assertRaises(ValueError):
            revision.revise(
                self.video_id,
                "Perjelas alur.",
            )

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            self.old,
        )

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )

        self.assertFalse(
            revision.latest_draft(
                self.video_id
            )["qc"]["approved"]
        )

    def test_provider_failure_preserves_active_script(self):
        self.drafts = [
            RuntimeError("Layanan belum tersedia")
        ]

        with self.assertRaises(RuntimeError):
            revision.revise(
                self.video_id,
                "Perjelas cerita.",
            )

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            self.old,
        )

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )

    def test_visual_stage_blocks_revision(self):
        db.update_video(
            self.video_id,
            scenes={"existing": True},
        )

        with self.assertRaises(ValueError):
            revision.revise(
                self.video_id,
                "Perjelas cerita.",
            )

        self.assertEqual(self.writer_calls, [])

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            self.old,
        )

    def test_newer_status_is_not_overwritten(self):
        self.on_review = lambda: db.update_video(
            self.video_id,
            status="storyboarding",
        )

        with self.assertRaises(ValueError):
            revision.revise(
                self.video_id,
                "Perjelas cerita.",
            )

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "storyboarding",
        )

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            self.old,
        )

    def test_recovery_retains_original_revision(self):
        db.update_video(
            self.video_id,
            status="script_revising",
        )

        with agus.worker_lock("script-worker.lock", "Rina"):
            revision.restore(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            self.old,
        )

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )

    def test_invalid_notes_do_not_claim_the_job(self):
        with self.assertRaises(ValueError):
            revision.revise(self.video_id, "  ")

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )


if __name__ == "__main__":
    unittest.main()