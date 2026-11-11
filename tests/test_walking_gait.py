import math
import unittest

from office.animation.walking import WalkPlan


class WalkingGaitTests(unittest.TestCase):
    def test_middle_speed_is_even(self):
        plan = WalkPlan(180, 500, 1, 7)

        positions = [
            plan.sample(2 + i * 0.25).hip[0]
            for i in range(13)
        ]

        distances = [
            b - a
            for a, b in zip(positions, positions[1:])
        ]

        self.assertLess(max(distances) - min(distances), 1e-8)

    def test_support_leg_does_not_stay_crouched(self):
        for end in (500, -140):
            plan = WalkPlan(180, end, 1, 7)

            for i in range(1201):
                pose = plan.sample(1 + i / 200)

                for foot in (0, 1):
                    if pose.planted[foot]:
                        self.assertGreater(
                            math.dist(pose.hip, pose.feet[foot]),
                            1.96 * plan.leg_length,
                        )

    def test_rotated_soles_stay_above_ground(self):
        plan = WalkPlan(180, 500, 1, 7)

        for i in range(1201):
            pose = plan.sample(1 + i / 200)

            for foot in (0, 1):
                angle = math.radians(pose.foot_angles[foot])

                bottom = pose.feet[foot][1] + max(
                    -10 * math.sin(angle),
                    17 * math.sin(angle),
                ) * plan.leg_length / 66.3

                self.assertLessEqual(bottom, 1e-8)

                if pose.planted[foot]:
                    self.assertEqual(pose.foot_angles[foot], 0)

    def test_activity_stops_outside_walk(self):
        plan = WalkPlan(180, 500, 1, 7)

        for t in (0, 1, 7, 8):
            self.assertEqual(plan.sample(t).activity, 0)

        for t in (2, 4, 6):
            self.assertEqual(plan.sample(t).activity, 1)


if __name__ == "__main__":
    unittest.main()