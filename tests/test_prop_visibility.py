import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageChops

from office.bible import load_bible
from office.animation import scene as renderer

ROOT = Path(__file__).resolve().parents[1]


class PropVisibilityTests(unittest.TestCase):
    def test_props_visible_before_and_during_action(self):
        bible = load_bible(
            ROOT
            / "config/animation/bible-actions.example.json"
        )

        data = renderer.load_scene(
            ROOT
            / "config/animation/scene-actions-demo.json",
            bible,
        )

        with tempfile.TemporaryDirectory() as folder:
            scene, _ = renderer.compile_scene(
                bible,
                data,
                folder,
                tone=True,
                report=lambda _: None,
            )

        self.assertTrue(
            scene["props"],
            "Daftar properti kosong.",
        )

        self.assertTrue(
            scene["action_tracks"],
            "Jadwal aksi kosong.",
        )

        action = scene["action_tracks"][0]

        middle = (
            action["start_frame"]
            + action["end_frame"]
        ) / (2 * bible["target"]["fps"])

        draw_props = renderer.draw_scene_props

        for seconds in (0, middle):
            full = renderer.frame(
                bible,
                scene,
                seconds,
            )

            for prop in scene["props"]:
                with self.subTest(
                    seconds=seconds,
                    prop=prop["id"],
                ):
                    def hide_one(
                        image,
                        items,
                        bible,
                        anchors,
                        identity=prop["id"],
                    ):
                        draw_props(
                            image,
                            [
                                item
                                for item in items
                                if item["id"] != identity
                            ],
                            bible,
                            anchors,
                        )

                    with patch(
                        "office.animation.scene.draw_scene_props",
                        side_effect=hide_one,
                    ):
                        without = renderer.frame(
                            bible,
                            scene,
                            seconds,
                        )

                    bounds = ImageChops.difference(
                        full,
                        without,
                    ).getbbox()

                    self.assertIsNotNone(
                        bounds,
                        "Properti tidak terlihat pada gambar.",
                    )

                    area = (
                        (bounds[2] - bounds[0])
                        * (bounds[3] - bounds[1])
                    )

                    self.assertGreater(
                        area,
                        400,
                        "Perubahan gambar terlalu kecil "
                        "untuk menunjukkan sebuah properti.",
                    )


if __name__ == "__main__":
    unittest.main()