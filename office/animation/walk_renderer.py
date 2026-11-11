"""Renderer berjalan dengan profil, bayangan, dan jangkar genggaman."""
import math

from PIL import ImageDraw

from .walk_details import draw_profile_head, draw_contact_shadows


def draw_walker(image, character, visual, plan, seconds, ground_y):
    pose = plan.sample(seconds)
    scale = plan.leg_length / 66.3
    direction = 1 if plan.end_x >= plan.start_x else -1

    ink = visual["palette"]["ink"]
    paper = visual["palette"]["paper"]
    color = character["color"]

    draw_contact_shadows(image, pose, ground_y, scale)
    draw = ImageDraw.Draw(image)
    origin_y = ground_y - 6.5 * scale

    def world(point):
        return point[0], origin_y + point[1]

    far_ink = tuple(
        round(
            int(ink[i:i+2], 16) * 0.78
            + int(paper[i:i+2], 16) * 0.22
        )
        for i in (1, 3, 5)
    )

    def stroke(points, width=12, fill=ink):
        size = max(1, round(width * scale))
        draw.line(points, fill=fill, width=size, joint="curve")
        radius = size / 2

        for x, y in points:
            draw.ellipse(
                (x-radius, y-radius, x+radius, y+radius),
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
        angle = math.radians(pose.foot_angles[index])

        stroke(
            [
                (
                    x + direction * offset * scale * math.cos(angle),
                    y + offset * scale * math.sin(angle),
                )
                for offset in (-10, 17)
            ],
            width=13,
            fill=tint,
        )

    lean = math.radians(4) * pose.activity
    co, si = math.cos(lean), math.sin(lean)

    head_x = pose.hip[0] + direction * 164.9 * scale * si
    head_y = origin_y + pose.hip[1] - 164.9 * scale * co

    # Kompresi tubuh ringan ketika menerima beban langkah.
    head_y += (
        2 * scale * pose.activity
        * math.cos(math.pi * pose.phase) ** 2
    )

    def local(x, y):
        return (
            head_x + direction * (x*co - y*si) * scale,
            head_y + (x*si + y*co) * scale,
        )

    stroke([local(0, 45.9), world(pose.hip)], width=15)
    stroke(
        [local(0, 62.9), local(0, 132.6)],
        width=30,
        fill=color,
    )

    swing = 24 * math.cos(math.pi * pose.phase)
    hands = []
    hand_angles = []

    for index, (rest, sign) in enumerate(((-20, 1), (20, -1))):
        upper = (
            rest * (1-pose.activity)
            + sign * swing * pose.activity
        )
        angles = (upper, upper + 12 * pose.activity)
        points = [(0, 66.3)]

        for length, degrees in zip((66.3, 73.1), angles):
            angle = math.radians(degrees)
            x, y = points[-1]

            points.append((
                x + length * math.sin(angle),
                y + length * math.cos(angle),
            ))

        stroke(
            [local(*point) for point in points],
            fill=far_ink if index == 0 else ink,
        )

        x, y = local(*points[-1])
        hands.append((x, y))
        hand_angles.append(angles[1] - rest)

        radius = 7 * scale
        draw.ellipse(
            (x-radius, y-radius, x+radius, y+radius),
            fill=color,
        )

    draw_profile_head(
        image,
        character,
        visual,
        head_x,
        head_y,
        scale,
        direction,
    )

    return {
        "hand": hands[1],
        "hand_angle": hand_angles[1],
        "head": (head_x, head_y),
        "hip": world(pose.hip),
        "scale": scale,
        "direction": direction,
    }