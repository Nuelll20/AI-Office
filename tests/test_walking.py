import math
import unittest

from office.animation.walking import WalkPlan


class WalkingTests(unittest.TestCase):
    def test_start_stop_and_zero_distance(self):
        for end in (420, -60, 180):
            plan = WalkPlan(180, end, 1, 7)

            start = plan.sample(1)
            finish = plan.sample(7)

            self.assertEqual(start, plan.sample(0))
            self.assertEqual(finish, plan.sample(8))

            self.assertEqual(start.hip[0], 180)
            self.assertEqual(finish.hip[0], end)
            self.assertEqual(finish.planted, (True, True))

            for foot in (0, 1):
                self.assertAlmostEqual(
                    finish.feet[foot][0] - start.feet[foot][0],
                    end - 180,
                )

    def test_ground_contact_and_fixed_limb_lengths(self):
        for end in (420, -60):
            plan = WalkPlan(180, end, 1, 7)
            previous = plan.sample(1)
            lifted = set()

            for index in range(1201):
                pose = plan.sample(1 + index / 200)

                # Minimal satu kaki menapak.
                self.assertTrue(any(pose.planted))

                for foot in (0, 1):
                    # Telapak tidak menembus lantai.
                    self.assertLessEqual(pose.feet[foot][1], 0)

                    if pose.planted[foot]:
                        self.assertEqual(pose.feet[foot][1], 0)

                        if previous.planted[foot]:
                            self.assertEqual(
                                pose.feet[foot],
                                previous.feet[foot],
                            )
                    else:
                        lifted.add(foot)

                    # Panjang paha tetap.
                    self.assertAlmostEqual(
                        math.dist(pose.hip, pose.knees[foot]),
                        plan.leg_length,
                    )

                    # Panjang betis tetap.
                    self.assertAlmostEqual(
                        math.dist(pose.knees[foot], pose.feet[foot]),
                        plan.leg_length,
                    )

                previous = pose

            # Kedua kaki benar-benar mendapat giliran melangkah.
            self.assertEqual(lifted, {0, 1})

    def test_scale_and_reverse_symmetry(self):
        forward = WalkPlan(0, 240, 1, 7)
        reverse = WalkPlan(0, -240, 1, 7)
        larger = WalkPlan(0, 480, 1, 7, leg_length=132.6)

        for seconds in (1, 1.5, 2.25, 3.75, 5.2, 6.9, 7):
            a = forward.sample(seconds)
            b = reverse.sample(seconds)
            c = larger.sample(seconds)

            self.assertAlmostEqual(a.hip[0], -b.hip[0])
            self.assertAlmostEqual(c.hip[0], 2 * a.hip[0])
            self.assertAlmostEqual(c.hip[1], 2 * a.hip[1])

            for foot in (0, 1):
                self.assertAlmostEqual(
                    a.feet[foot][0],
                    -b.feet[1-foot][0],
                )
                self.assertAlmostEqual(
                    a.feet[foot][1],
                    b.feet[1-foot][1],
                )

                for axis in (0, 1):
                    self.assertAlmostEqual(
                        c.feet[foot][axis],
                        2 * a.feet[foot][axis],
                    )

    def test_invalid_input_is_rejected(self):
        cases = [
            {"end_time": 1},
            {"start_time": -1},
            {"leg_length": 0},
            {"end_x": True},
            {"end_x": float("nan")},
            {"end_x": float("inf")},
            {"end_time": 1.1},
        ]

        for changes in cases:
            args = dict(
                start_x=180,
                end_x=420,
                start_time=1,
                end_time=7,
            )
            args.update(changes)

            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    WalkPlan(**args)

        with self.assertRaises(ValueError):
            WalkPlan(180, 420, 1, 7).sample(float("nan"))


if __name__ == "__main__":
    unittest.main()