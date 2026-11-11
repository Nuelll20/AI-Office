import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from office.bible import BibleError, load_bible
from office.animation.prop_actions import (
    compile_actions,
    sample_action,
)
from office.animation.scene import (
    compile_scene,
    frame,
    load_scene,
)
from office.animation.walk_renderer import draw_walker
from office.animation.walking import WalkPlan

ROOT = Path(__file__).resolve().parents[1]


class PropActionTests(unittest.TestCase):
    def setUp(self):
        self.bible = load_bible(
            ROOT / "config/animation/bible-actions.example.json"
        )

        self.data = load_scene(
            ROOT / "config/animation/scene-actions-demo.json",
            self.bible,
        )

    def test_action_follows_dialogue(self):
        original = copy.deepcopy(self.data)

        with tempfile.TemporaryDirectory() as folder:
            scene, pcm = compile_scene(
                self.bible,
                self.data,
                folder,
                tone=True,
                report=lambda _: None,
            )

        action = scene["action_tracks"][0]

        lines = {
            line["id"]: line
            for line in scene["lines"]
        }

        fps = self.bible["target"]["fps"]

        self.assertEqual(
            action["start_frame"],
            lines["l2"]["start_frame"],
        )

        self.assertEqual(
            action["end_frame"],
            lines["l3"]["end_frame"]
            + round(0.35 * fps),
        )

        self.assertEqual(
            sample_action(
                [action],
                "raka",
                lines["l3"]["start_frame"],
                fps,
            )[1],
            1,
        )

        self.assertEqual(self.data, original)

        self.assertEqual(
            len(pcm),
            scene["total_frames"]
            * (24000 // fps)
            * 2,
        )

    def test_invalid_actions_are_rejected(self):
        changes = (
            lambda data: data["actions"][0].update(
                actor="dimas"
            ),
            lambda data: data["actions"][0].update(
                prop="missing"
            ),
            lambda data: data["actions"][0].update(
                from_line="l3",
                to_line="l2",
            ),
            lambda data: data["lines"][-1].update(
                gesture_target="missing"
            ),
        )

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scene.json"

            for change in changes:
                data = copy.deepcopy(self.data)
                change(data)

                path.write_text(
                    json.dumps(data),
                    encoding="utf-8",
                )

                with self.assertRaises(BibleError):
                    load_scene(path, self.bible)

        duplicate = dict(
            self.data,
            actions=self.data["actions"] * 2,
        )

        lines = [
            dict(
                line,
                start_frame=index * 60,
                end_frame=index * 60 + 50,
            )
            for index, line in enumerate(
                self.data["lines"]
            )
        ]

        with self.assertRaises(BibleError):
            compile_actions(
                duplicate, lines, 30
            )

    def test_lifting_preserves_arm_lengths(self):
        for scale in (0.65, 1.2):
            for direction in (-1, 1):
                image = Image.new(
                    "RGB", (800, 1000), "white"
                )

                before = image.copy()

                plan = WalkPlan(
                    400, 400, 0, 1, 66.3 * scale
                )

                args = (
                    image,
                    self.bible["characters"][0],
                    self.bible["visual"],
                    plan,
                    2,
                    700,
                )

                base = draw_walker(
                    *args,
                    facing=direction,
                    carrying=True,
                    measure=True,
                )

                raised = draw_walker(
                    *args,
                    facing=direction,
                    carrying=True,
                    prop_action="show_prop",
                    prop_weight=1,
                    gesture=1,
                    gesture_kind="point",
                    point_target=(
                        400 + direction * 180,
                        450,
                        40,
                    ),
                    measure=True,
                )

                self.assertLess(
                    raised["hand"][1],
                    base["hand"][1] - 100 * scale,
                )

                self.assertEqual(
                    raised["hand_angle"], 0
                )

                for arm in raised["arms"]:
                    self.assertAlmostEqual(
                        math.dist(arm[0], arm[1]),
                        66.3 * scale,
                    )

                    self.assertAlmostEqual(
                        math.dist(arm[1], arm[2]),
                        73.1 * scale,
                    )

                self.assertIsNone(
                    ImageChops.difference(
                        image, before
                    ).getbbox()
                )

    def test_other_characters_and_object(self):
        bible = copy.deepcopy(self.bible)
        data = copy.deepcopy(self.data)

        mapping = {
            item["id"]: f"tokoh-{index}"
            for index, item in enumerate(
                bible["characters"]
            )
        }

        for character in bible["characters"]:
            character["id"] = mapping[
                character["id"]
            ]

        data["actors"] = {
            mapping[key]: dict(
                value,
                look_at=mapping.get(
                    value["look_at"]
                ),
            )
            for key, value in data["actors"].items()
        }

        for prop in data["props"]:
            prop["owner"] = mapping.get(
                prop["owner"]
            )

            if prop["id"] == "book-1":
                prop["id"] = "parcel-1"

        for line in data["lines"]:
            line["speaker"] = mapping[
                line["speaker"]
            ]

            if "gesture_target" in line:
                line["gesture_target"] = "parcel-1"

        data["actions"][0].update(
            actor=mapping["raka"],
            prop="parcel-1",
            kind="raise_prop",
        )

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scene.json"

            path.write_text(
                json.dumps(data),
                encoding="utf-8",
            )

            loaded = load_scene(path, bible)

            scene, _ = compile_scene(
                bible,
                loaded,
                folder,
                tone=True,
                report=lambda _: None,
            )

        self.assertEqual(
            frame(bible, scene, 5.5).size,
            (720, 1280),
        )


if __name__ == "__main__":
    unittest.main()