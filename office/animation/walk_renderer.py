"""Gambar tubuh berjalan dari WalkPlan, menggunakan wajah renderer karakter."""
import math

from PIL import Image, ImageDraw

from .characters import character_layer


def draw_walker(image, character, visual, plan, seconds, ground_y):
    pose = plan.sample(seconds)
    scale = plan.leg_length / 66.3
    direction = 1 if plan.end_x >= plan.start_x else -1

    ink = visual["palette"]["ink"]
    color = character["color"]
    draw = ImageDraw.Draw(image)

    # y=0 pada planner adalah pusat telapak.
    # Posisi ini menempatkan bagian bawah sol pada garis lantai.
    origin_y = ground_y - 6.5 * scale

    def world(point):
        return point[0], origin_y + point[1]

    def stroke(points, width=12, fill=ink):
        size = max(1, round(width * scale))
        draw.line(points, fill=fill, width=size, joint="curve")
        radius = size / 2

        for x, y in points:
            draw.ellipse(
                (x-radius, y-radius, x+radius, y+radius),
                fill=fill,
            )

    for index in (0, 1):
        stroke([
            world(pose.hip),
            world(pose.knees[index]),
            world(pose.feet[index]),
        ])

        x, y = world(pose.feet[index])

        stroke(
            [
                (x-10*scale*direction, y),
                (x+17*scale*direction, y),
            ],
            width=13,
        )

    head_x = pose.hip[0]
    head_y = origin_y + pose.hip[1] - 164.9 * scale

    def local(x, y):
        return (
            head_x + direction*x*scale,
            head_y + y*scale,
        )

    stroke(
        [local(0, 45.9), world(pose.hip)],
        width=15,
    )

    stroke(
        [local(0, 62.9), local(0, 132.6)],
        width=30,
        fill=color,
    )

    progress = max(
        0.0,
        min(
            1.0,
            (seconds-plan.start_time)
            / (plan.end_time-plan.start_time),
        ),
    )

    phase = (
        plan.step_count
        * progress
        * progress
        * (3 - 2 * progress)
    )

    swing = 16 * math.sin(math.pi * phase)

    for angles in (
        (-20-swing, -20+swing),
        (20+swing, 20-swing),
    ):
        points = [(0, 66.3)]

        for length, degrees in zip((66.3, 73.1), angles):
            angle = math.radians(degrees)
            x, y = points[-1]

            points.append((
                x + length * math.sin(angle),
                y + length * math.cos(angle),
            ))

        stroke([local(*point) for point in points])

        x, y = local(*points[-1])
        radius = 7 * scale

        draw.ellipse(
            (x-radius, y-radius, x+radius, y+radius),
            fill=color,
        )

    # Kontrak character_layer:
    # ukuran 301x420, pusat kepala pada (150, 60).
    layer = character_layer(
        character,
        visual,
        gaze=1,
        mirror=direction < 0,
    )

    head = layer.crop((108, 18, 193, 103))
    size = max(1, round(85 * scale))

    if size != 85:
        head = head.resize(
            (size, size),
            Image.Resampling.LANCZOS,
        )

    position = (
        round(head_x - 42 * size / 85),
        round(head_y - 42 * size / 85),
    )

    if image.mode == "RGBA":
        image.alpha_composite(head, dest=position)
    else:
        image.paste(head, position, head)