import copy
import unittest
from unittest.mock import patch

import test_story_script as base

from office import db
from office import script_worker
from office import story_visual as visual
from office import visual_worker as worker
from office import story_worker as agus
from office.storyboard_preview import render_html


class StoryVisualTests(unittest.TestCase):
    def setUp(self):
        base.StoryScriptTests.setUp(self)

        script_worker.develop(self.video_id)
        self.original_script = copy.deepcopy(
            db.get_video(self.video_id)["script"]
        )

        output_patch = patch.object(
            worker,
            "OUTPUT_DIR",
            script_worker.OUTPUT_DIR,
        )

        output_patch.start()
        self.addCleanup(output_patch.stop)

        self.visual_calls = []
        self.change_result = lambda result: None
        self.on_visual_call = lambda: None

        api = patch.object(
            visual.llm,
            "ask_json",
            side_effect=self.visual_ask,
        )

        api.start()
        self.addCleanup(api.stop)

    def ask(self, system, user, **kwargs):
        return base.StoryScriptTests.ask(
            self,
            system,
            user,
            **kwargs,
        )

    def visual_ask(self, system, user, **kwargs):
        import json

        request = json.loads(user)
        self.visual_calls.append(request)
        self.on_visual_call()

        scenes = []

        for source in request["source_scenes"]:
            scope = request["scope"][str(source["id"])]

            actors = [
                {
                    "asset_id": asset_id,
                    "x": 0.3 + index * 0.4,
                    "y": 0.75,
                    "scale": 0.8,
                    "facing": "front",
                    "visible": True,
                    "expression": "tenang",
                }
                for index, asset_id in enumerate(scope["actors"])
            ]

            props = [
                {
                    "asset_id": asset_id,
                    "x": 0.5,
                    "y": 0.7,
                    "scale": 0.3,
                    "owner": None,
                }
                for asset_id in scope["props"]
            ]

            available = (
                scope["actors"]
                + scope["props"]
                + (
                    [scope["background"]]
                    if scope["background"]
                    else []
                )
            )

            scenes.append(
                {
                    "id": source["id"],
                    "shot": "medium",
                    "camera": {
                        "motion": "static",
                        "focus": (
                            available[0] if available else None
                        ),
                    },
                    "lighting": {
                        "mode": "day",
                        "description": "Cahaya siang netral.",
                    },
                    "composition": "Tokoh pada area tengah.",
                    "actors": actors,
                    "props": props,
                    "actions": [],
                }
            )

        result = {
            "asset_prompts": {
                asset_id: (
                    "Clean consistent illustrated asset "
                    "based on the provided description"
                )
                for asset_id in request["new_asset_ids"]
            },
            "scenes": scenes,
        }

        self.change_result(result)
        return result

    def test_success_saves_board_and_preview(self):
        board = worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "storyboard_ready",
        )

        self.assertEqual(board["schema_version"], 3)
        self.assertEqual(board["script_revision"], 1)

        self.assertEqual(
            db.get_video(self.video_id)["script"],
            self.original_script,
        )

        self.assertTrue(
            (
                worker.OUTPUT_DIR
                / self.video_id
                / "storyboard.b1.s1.html"
            ).exists()
        )

        self.assertTrue(
            all(
                "prompt" in asset
                for asset in board["assets"].values()
            )
        )

    def test_character_variants_share_identity_reference(self):
        data = copy.deepcopy(self.original_script)

        data["character_states"].append(
            {
                "id": "utama_lanjut",
                "character_id": "utama",
                "description": "Penampilan pada tahap berikutnya.",
            }
        )

        data["scenes"][1]["states"]["utama"] = "utama_lanjut"

        db.update_video(self.video_id, script=data)

        board = worker.develop(self.video_id)

        first = board["assets"][
            "character:utama:utama_awal"
        ]

        second = board["assets"][
            "character:utama:utama_lanjut"
        ]

        self.assertEqual(
            first["identity_group"],
            second["identity_group"],
        )

        self.assertEqual(
            second["reference_asset_id"],
            "character:utama:utama_awal",
        )

    def test_unknown_asset_does_not_save_a_board(self):
        def change(result):
            result["scenes"][0]["actors"][0]["asset_id"] = (
                "character:tidak_ada"
            )

        self.change_result = change

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.assertIsNone(
            db.get_video(self.video_id)["scenes"]
        )

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "storyboard_failed",
        )

    def test_invalid_dialogue_cue_is_rejected(self):
        def change(result):
            actor = result["scenes"][0]["actors"][0]["asset_id"]

            result["scenes"][0]["actions"] = [
                {
                    "actor": actor,
                    "kind": "gesture",
                    "target": None,
                    "cue": "line:999",
                    "until": "end",
                    "to": None,
                    "owner_after": None,
                    "description": "Gerakan penjelasan.",
                }
            ]

        self.change_result = change

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.assertIsNone(
            db.get_video(self.video_id)["scenes"]
        )

    def test_changed_script_blocks_stale_board(self):
        def change():
            updated = copy.deepcopy(self.original_script)
            updated["script_revision"] = 2

            db.update_video(
                self.video_id,
                script=updated,
            )

        self.on_visual_call = change

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.assertIsNone(
            db.get_video(self.video_id)["scenes"]
        )

        self.assertEqual(
            db.get_video(
                self.video_id
            )["script"]["script_revision"],
            2,
        )

    def test_existing_board_is_reused(self):
        worker.develop(self.video_id)
        calls = len(self.visual_calls)

        worker.develop(self.video_id)

        self.assertEqual(
            len(self.visual_calls),
            calls,
        )

    def test_preview_escapes_untrusted_text(self):
        board = worker.develop(self.video_id)
        board["title"] = "<script>alert(1)</script>"

        html = render_html(board)

        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_interrupted_job_returns_to_script_ready(self):
        db.update_video(
            self.video_id,
            status="storyboarding",
        )

        with agus.worker_lock(
            "visual-worker.lock",
            "Bayu",
        ):
            worker.recover_interrupted()

        self.assertEqual(
            db.get_video(self.video_id)["status"],
            "script_ready",
        )

    def test_longer_script_is_planned_in_batches(self):
        data = copy.deepcopy(self.original_script)
        scenes = []

        for index in range(6):
            original = data["scenes"][0 if index < 3 else 1]
            scene = copy.deepcopy(original)
            scene["id"] = index + 1
            scenes.append(scene)

        data["scenes"] = scenes

        data["estimated_duration_sec"] = sum(
            scene["estimated_duration_sec"]
            for scene in scenes
        )

        db.update_video(self.video_id, script=data)

        worker.develop(self.video_id)

        self.assertEqual(len(self.visual_calls), 2)

        self.assertIsNotNone(
            self.visual_calls[1]["previous_scene"]
        )

        generated_ids = [
            asset_id
            for request in self.visual_calls
            for asset_id in request["new_asset_ids"]
        ]

        self.assertEqual(
            len(generated_ids),
            len(set(generated_ids)),
        )

    def test_existing_other_visual_format_is_preserved(self):
        original = {"legacy": True}

        db.update_video(
            self.video_id,
            scenes=original,
        )

        with self.assertRaises(ValueError):
            worker.develop(self.video_id)

        self.assertEqual(
            db.get_video(self.video_id)["scenes"],
            original,
        )

        self.assertEqual(self.visual_calls, [])


if __name__ == "__main__":
    unittest.main()