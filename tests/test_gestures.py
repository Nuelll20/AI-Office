import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

from office.bible import BibleError, load_bible
from office.animation.gestures import sample_gesture
from office.animation.scene import frame, load_scene
from office.animation.walk_renderer import draw_walker
from office.animation.walking import WalkPlan

ROOT = Path(__file__).resolve().parents[1]


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.bible = load_bible(
            ROOT
            / "config/animation/bible-audio-quality.example.json"
        )

    def actor(self, *, facing=1, scale=1, **options):
        image = Image.new(
            "RGB", (800, 1000), "white"
        )

        plan = WalkPlan(
            400, 400, 0, 1, 66.3 * scale
        )

        anchor = draw_walker(
            image,
            self.bible["characters"][0],
            self.bible["visual"],
            plan,
            2,
            700,
            facing=facing,
            **options,
        )

        return image, anchor

    def test_standing_feet_stay_close(self):
        for scale in (0.65, 1, 1.2):
            for end in (200, 400, 600):
                plan = WalkPlan(
                    400, end, 1, 5, 66.3 * scale
                )

                for seconds in (0, 1, 5, 6):
                    pose = plan.sample(seconds)

                    self.assertLessEqual(
                        abs(
                            pose.feet[0][0]
                            - pose.feet[1][0]
                        ),
                        0.21 * plan.leg_length,
                    )

                    self.assertEqual(
                        pose.planted,
                        (True, True),
                    )

    def test_gesture_enters_and_exits_smoothly(self):
        line = {
            "start_frame": 30,
            "end_frame": 120,
            "gesture": "ask",
        }

        self.assertEqual(
            sample_gesture(line, 30, 30)[1], 0
        )

        self.assertEqual(
            sample_gesture(line, 60, 30)[1], 1
        )

        self.assertLess(
            sample_gesture(line, 119, 30)[1],
            0.04,
        )

        self.assertEqual(
            sample_gesture(line, 120, 30),
            ("none", 0, 0),
        )

    def test_held_hand_stays_fixed_during_gestures(self):
        for facing in (-1, 1):
            for scale in (0.65, 1.2):
                _, rest = self.actor(
                    facing=facing,
                    scale=scale,
                    carrying=True,
                )

                for kind in ("ask", "explain", "point"):
                    _, active = self.actor(
                        facing=facing,
                        scale=scale,
                        carrying=True,
                        gesture=1,
                        gesture_kind=kind,
                        gesture_phase=0.5,
                    )

                    self.assertEqual(
                        rest["hand"], active["hand"]
                    )

                    self.assertEqual(
                        rest["hand_angle"],
                        active["hand_angle"],
                    )

                    self.assertGreater(
                        math.dist(
                            rest["free_hand"],
                            active["free_hand"],
                        ),
                        50 * scale,
                    )

    def test_walking_keeps_its_arm_swing(self):
        plan = WalkPlan(
            250, 400, 0.5, 3.5
        )

        images = []

        for weight in (0, 1):
            image = Image.new(
                "RGB", (800, 1000), "white"
            )

            draw_walker(
                image,
                self.bible["characters"][0],
                self.bible["visual"],
                plan,
                1.5,
                700,
                gesture=weight,
                gesture_kind="point",
                carrying=True,
            )

            images.append(image)

        self.assertIsNone(
            ImageChops.difference(*images).getbbox()
        )

    def test_scene_gestures_do_not_depend_on_volume(self):
        data = load_scene(
            ROOT
            / "config/animation/scene-audio-quality.json",
            self.bible,
        )

        data["lines"][0]["gesture"] = "point"

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scene.json"

            path.write_text(
                json.dumps(data),
                encoding="utf-8",
            )

            load_scene(path, self.bible)

            data["lines"][0]["gesture"] = "unknown"

            path.write_text(
                json.dumps(data),
                encoding="utf-8",
            )

            with self.assertRaises(BibleError):
                load_scene(path, self.bible)

        data["lines"][0]["gesture"] = "point"

        scene = dict(
            data,
            lines=[
                dict(
                    data["lines"][0],
                    start_frame=90,
                    end_frame=150,
                    levels=[0] * 60,
                )
            ],
        )

        with patch(
            "office.animation.scene.draw_walker",
            wraps=draw_walker,
        ) as render:
            frame(self.bible, scene, 4)

        speaker = next(
            call
            for call in render.call_args_list
            if call.args[1]["id"]
            == scene["lines"][0]["speaker"]
        )

        self.assertEqual(
            speaker.kwargs["mouth"], 0
        )

        self.assertEqual(
            speaker.kwargs["gesture"], 1
        )

        self.assertEqual(
            speaker.kwargs["gesture_kind"],
            "point",
        )

        self.assertTrue(
            speaker.kwargs["carrying"]
        )


if __name__ == "__main__":
    unittest.main()