"""Pengatur langkah 2D. Lantai pada y=0; nilai y negatif berada di atasnya."""
import math
from dataclasses import dataclass


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} harus berupa angka berhingga.")


def _smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


@dataclass(frozen=True)
class WalkPose:
    hip: tuple
    knees: tuple
    feet: tuple
    planted: tuple
    phase: float = 0.0
    activity: float = 0.0
    foot_angles: tuple = (0.0, 0.0)


@dataclass(frozen=True)
class WalkPlan:
    start_x: float
    end_x: float
    start_time: float
    end_time: float
    leg_length: float = 66.3

    def __post_init__(self):
        for name in (
            "start_x", "end_x",
            "start_time", "end_time", "leg_length",
        ):
            _finite(getattr(self, name), name)

        if self.start_time < 0 or self.end_time <= self.start_time:
            raise ValueError(
                "Waktu mulai harus >= 0 dan waktu selesai harus lebih besar."
            )

        if not 0.1 <= self.leg_length <= 1000:
            raise ValueError(
                "Panjang satu ruas kaki harus di antara 0.1 dan 1000."
            )

        _finite(self.end_x - self.start_x, "jarak")
        _finite(self.end_time - self.start_time, "durasi")

        if self.end_time - self.start_time < self.step_count * 0.2:
            raise ValueError(
                "Durasi terlalu singkat untuk jumlah langkah; tambah durasi."
            )

    @property
    def step_count(self):
        distance = abs(self.end_x - self.start_x)
        return 2 * math.ceil(distance / (1.4 * self.leg_length))

    def sample(self, seconds):
        _finite(seconds, "seconds")

        duration = self.end_time - self.start_time
        t = max(
            0.0,
            min(1.0, (seconds - self.start_time) / duration),
        )
        ramp = min(0.15, 0.45 / duration)

        # Akselerasi singkat; bagian tengah memiliki kecepatan stabil.
        def acceleration(value):
            u = value / ramp
            return (
                ramp * (u ** 3 - 0.5 * u ** 4)
                / (1 - ramp)
            )

        if t < ramp:
            progress = acceleration(t)
            activity = _smooth(t / ramp)
        elif t > 1 - ramp:
            progress = 1 - acceleration(1 - t)
            activity = _smooth((1 - t) / ramp)
        else:
            progress = (t - ramp / 2) / (1 - ramp)
            activity = 1.0

        distance = self.end_x - self.start_x
        direction = 1 if distance >= 0 else -1
        steps = self.step_count

        phase = progress * steps
        completed = min(math.floor(phase), steps)
        fraction = phase - completed
        spread = self.leg_length * 0.10

        feet = [
            [self.start_x - spread, 0.0],
            [self.start_x + spread, 0.0],
        ]
        planted = [True, True]
        foot_angles = [0.0, 0.0]

        if steps:
            stride = distance / (steps // 2)
            first = 0 if direction == 1 else 1
            other = 1 - first

            feet[first][0] += ((completed + 1) // 2) * stride
            feet[other][0] += (completed // 2) * stride

            if completed < steps and fraction > 0:
                swing = first if completed % 2 == 0 else other

                feet[swing][0] += stride * _smooth(fraction)

                feet[swing][1] = (
                    -self.leg_length * 0.12
                    * math.sin(math.pi * fraction) ** 2
                )

                foot_angles[swing] = (
                    -18
                    * math.sin(2 * math.pi * fraction)
                    * math.sin(math.pi * fraction) ** 2
                )

                planted[swing] = False
        else:
            activity = 0.0

        hip_x = self.start_x + distance * progress

        # Tinggi pinggul mengikuti jangkauan kaki.
        # Kaki tumpuan hampir lurus, dengan sedikit kelenturan.
        reach_limit = self.leg_length * 1.99

        heights = [
            math.sqrt(
                max(
                    0.0,
                    reach_limit ** 2 - (foot[0] - hip_x) ** 2,
                )
            ) - foot[1]
            for foot in feet
        ]

        lowest = min(heights)
        softness = self.leg_length * 0.01

        # Peralihan tinggi yang halus ketika berganti kaki tumpuan.
        height = lowest - softness * math.log(
            sum(
                math.exp((lowest - value) / softness)
                for value in heights
            )
        )

        hip = (hip_x, -height)
        knees = []

        for foot in feet:
            dx = foot[0] - hip[0]
            dy = foot[1] - hip[1]
            reach = math.hypot(dx, dy)

            if reach > 2 * self.leg_length + 1e-7:
                raise ValueError(
                    "Kaki tidak dapat mencapai target tanpa meregang."
                )

            bend = math.sqrt(
                max(
                    0.0,
                    self.leg_length ** 2 - (reach / 2) ** 2,
                )
            )

            knees.append((
                hip[0] + dx / 2 + direction * dy / reach * bend,
                hip[1] + dy / 2 - direction * dx / reach * bend,
            ))

        return WalkPose(
            hip=hip,
            knees=tuple(knees),
            feet=tuple(tuple(foot) for foot in feet),
            planted=tuple(planted),
            phase=phase,
            activity=activity,
            foot_angles=tuple(foot_angles),
        )