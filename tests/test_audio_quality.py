import array
import math
import shutil
import sys
import unittest

from office.animation.audio_quality import prepare_dialogue
from office.animation.scene_audio import RATE


def tone(seconds, frequency=220):
    samples = array.array("h", (
        round(
            9000 * math.sin(
                2 * math.pi
                * frequency
                * index
                / RATE
            )
        )
        for index in range(
            round(seconds * RATE)
        )
    ))

    if sys.byteorder != "little":
        samples.byteswap()

    return samples.tobytes()


def quiet(seconds):
    return bytes(
        round(seconds * RATE) * 2
    )


class AudioQualityTests(unittest.TestCase):
    def test_trim_preserves_speech(self):
        voice = tone(0.5)

        source = (
            quiet(0.3)
            + voice
            + quiet(0.6)
        )

        result, stats = prepare_dialogue(source)

        self.assertIn(voice, result)

        self.assertAlmostEqual(
            len(result) / (RATE * 2),
            0.66,
            places=2,
        )

        self.assertAlmostEqual(
            stats["trimmed_edges_sec"],
            0.74,
            places=2,
        )

    def test_internal_pause_is_optional(self):
        short = (
            tone(0.3)
            + quiet(0.2)
            + tone(0.3)
        )

        long = (
            tone(0.3)
            + quiet(1.1)
            + tone(0.3)
        )

        # Jeda pendek tetap dipertahankan.
        self.assertEqual(
            prepare_dialogue(
                short,
                max_pause=0.35,
            )[0],
            short,
        )

        # Tanpa batas jeda, jeda panjang juga dipertahankan.
        self.assertEqual(
            prepare_dialogue(long)[0],
            long,
        )

        result, stats = prepare_dialogue(
            long,
            max_pause=0.35,
        )

        self.assertAlmostEqual(
            len(result) / (RATE * 2),
            0.95,
            places=2,
        )

        self.assertAlmostEqual(
            stats["shortened_pauses_sec"],
            0.75,
            places=2,
        )

    def test_invalid_audio_is_rejected(self):
        for source in (
            b"",
            b"x",
            quiet(1),
        ):
            with self.subTest(
                size=len(source)
            ):
                with self.assertRaises(ValueError):
                    prepare_dialogue(source)

    @unittest.skipUnless(
        shutil.which("ffmpeg"),
        "FFmpeg diperlukan untuk pengujian nada",
    )
    def test_pitch_changes_without_large_duration_change(self):
        for shift in (-2, 2):
            result, _ = prepare_dialogue(
                tone(2),
                shift=shift,
            )

            values = array.array("h")
            values.frombytes(result)

            if sys.byteorder != "little":
                values.byteswap()

            center = values[
                RATE // 2:RATE * 3 // 2
            ]

            crossings = sum(
                left <= 0 < right
                for left, right in zip(
                    center,
                    center[1:],
                )
            )

            expected = (
                220 * 2 ** (shift / 12)
            )

            self.assertAlmostEqual(
                crossings,
                expected,
                delta=2,
            )

            self.assertAlmostEqual(
                len(values) / RATE,
                2,
                delta=0.08,
            )


if __name__ == "__main__":
    unittest.main()