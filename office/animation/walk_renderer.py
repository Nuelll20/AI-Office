"""Renderer profil dengan langkah, tangan bebas, dan gestur percakapan."""

import math
from dataclasses import replace

from PIL import ImageDraw

from .gestures import GESTURES, gesture_angles
from .walk_details import draw_profile_head, draw_contact_shadows


def draw_walker(
    image,
    character,
    visual,
    plan,
    seconds,
    ground_y,
    *,
    mouth=0,
    gesture=0,
    facing=None,
    blink=False,
    gesture_kind="explain",
    gesture_phase=0.5,
    carrying=False,
):
    pose = plan.sample(seconds)
    scale = plan.leg_length / 66.3
    direction = 1 if plan.end_x >= plan.start_x else -1

    if facing is not None:
        if type(facing) is not int or facing not in (-1, 1):
            raise ValueError("facing harus -1 atau 1.")

        if facing != direction:
            if pose.activity:
                raise ValueError(
                    "Perubahan arah badan dilakukan setelah berhenti."
                )

            center = pose.hip[0]

            pose = replace(
                pose,
                knees=tuple(
                    (2 * center - x, y)
                    for x, y in pose.knees
                ),
                feet=tuple(
                    (2 * center - x, y)
                    for x, y in pose.feet
                ),
            )

            direction = facing

    for name, value in (
        ("mouth", mouth),
        ("gesture", gesture),
        ("gesture_phase", gesture_phase),
    ):
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError(
                f"{name} harus berupa angka 0 sampai 1."
            )

    if type(blink) is not bool or type(carrying) is not bool:
        raise ValueError(
            "blink dan carrying harus boolean."
        )

    if (
        not isinstance(gesture_kind, str)
        or gesture_kind not in GESTURES
    ):
        raise ValueError("Jenis gestur tidak dikenal.")

    palette = visual["palette"]
    ink = palette["ink"]
    paper = palette["paper"]
    color = character["color"]

    far_ink = tuple(
        round(
            int(ink[i:i + 2], 16) * 0.78
            + int(paper[i:i + 2], 16) * 0.22
        )
        for i in (1, 3, 5)
    )

    draw_contact_shadows(
        image,
        pose,
        ground_y,
        scale,
    )

    draw = ImageDraw.Draw(image)
    origin_y = ground_y - 6.5 * scale

    def world(point):
        return point[0], origin_y + point[1]

    def stroke(points, width=12, fill=ink):
        size = max(1, round(width * scale))

        draw.line(
            points,
            fill=fill,
            width=size,
            joint="curve",
        )

        radius = size / 2

        for x, y in points:
            draw.ellipse(
                (
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                ),
                fill=fill,
            )

    order = (0, 1) if direction == 1 else (1, 0)

    for depth, index in enumerate(order):
        tint = far_ink if depth == 0 else ink

        stroke(
            [
                world(pose.hip),
                world(pose.knees[index]),
                world(pose.feet[index]),
            ],
            fill=tint,
        )

        x, y = world(pose.feet[index])
        angle = math.radians(
            pose.foot_angles[index]
        )

        stroke(
            [
                (
                    x
                    + direction * offset * scale
                    * math.cos(angle),
                    y
                    + offset * scale
                    * math.sin(angle),
                )
                for offset in (-10, 17)
            ],
            width=13,
            fill=tint,
        )

    # Gerakan tubuh kecil saat diam.
    # Pijakan kaki tetap berada di tempatnya.
    breath = (
        0.6
        * math.sin(2 * math.pi * seconds / 3.2)
        * (1 - pose.activity)
    )

    lean = math.radians(
        4 * pose.activity + breath
    )

    co = math.cos(lean)
    si = math.sin(lean)

    head_x = (
        pose.hip[0]
        + direction * 164.9 * scale * si
    )

    head_y = (
        origin_y
        + pose.hip[1]
        - 164.9 * scale * co
    )

    head_y += (
        2 * scale * pose.activity
        * math.cos(math.pi * pose.phase) ** 2
    )

    def local(x, y):
        return (
            head_x
            + direction * (x * co - y * si) * scale,
            head_y
            + (x * si + y * co) * scale,
        )

    # Tangan depan memegang benda.
    # Jika membawa benda, gestur memakai tangan satunya.
    gesture_index = 0 if carrying else 1

    amount = (
        gesture * (1 - pose.activity)
        if gesture_kind != "none"
        else 0
    )

    target = gesture_angles(
        gesture_kind,
        gesture_phase,
    )

    swing = 24 * math.cos(
        math.pi * pose.phase
    )

    arms = []
    hands = []
    hand_angles = []

    for index, (rest, sign) in enumerate(
        ((-10, 1), (12, -1))
    ):
        upper = (
            rest * (1 - pose.activity)
            + sign * swing * pose.activity
        )

        angles = (
            upper,
            upper + 12 * pose.activity,
        )

        if index == gesture_index:
            angles = tuple(
                current + (goal - current) * amount
                for current, goal in zip(
                    angles,
                    target,
                )
            )

        points = [(0, 66.3)]

        for length, degrees in zip(
            (66.3, 73.1),
            angles,
        ):
            angle = math.radians(degrees)
            x, y = points[-1]

            points.append((
                x + length * math.sin(angle),
                y + length * math.cos(angle),
            ))

        points = [
            local(*point)
            for point in points
        ]

        arms.append(points)
        hands.append(points[-1])
        hand_angles.append(
            angles[1] - rest
        )

    def draw_arm(index):
        stroke(
            arms[index],
            fill=far_ink if index == 0 else ink,
        )

        x, y = hands[index]
        radius = 7 * scale

        draw.ellipse(
            (
                x - radius,
                y - radius,
                x + radius,
                y + radius,
            ),
            fill=color,
        )

        if (
            index == gesture_index
            and gesture_kind == "point"
            and amount > 0
        ):
            stroke(
                [
                    (x, y),
                    (
                        x
                        + direction * 14 * scale * amount,
                        y,
                    ),
                ],
                width=4,
                fill=color,
            )

    # Susunan gambar menjaga lengan belakang berada di belakang badan.
    draw_arm(0)

    stroke(
        [local(0, 45.9), world(pose.hip)],
        width=15,
    )

    stroke(
        [local(0, 62.9), local(0, 132.6)],
        width=30,
        fill=color,
    )

    draw_arm(1)

    draw_profile_head(
        image,
        character,
        visual,
        head_x,
        head_y,
        scale,
        direction,
        mouth=mouth,
        blink=blink,
    )

    return {
        "hand": hands[1],
        "hand_angle": hand_angles[1],
        "free_hand": hands[gesture_index],
        "head": (head_x, head_y),
        "hip": world(pose.hip),
        "scale": scale,
        "direction": direction,
    }