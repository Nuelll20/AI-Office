"""Wajah profil dan bayangan kontak untuk renderer berjalan."""
import math

from PIL import Image, ImageDraw


def draw_profile_head(
    image, character, visual, x, y, scale, direction,
    mouth=0, blink=False,
):
    layer = Image.new("RGBA", (111, 101))
    draw = ImageDraw.Draw(layer)

    palette = visual["palette"]
    ink = palette["ink"]
    fill = palette["head_fill"]
    cx, cy, radius = 55, 50, 39.1

    outline = [
        (
            cx + radius * math.cos(math.radians(angle)),
            cy + radius * math.sin(math.radians(angle)),
        )
        for angle in range(8, 355, 2)
    ]
    outline.append((cx + radius + 6, cy + 2))

    draw.polygon(outline, fill=fill)
    draw.line(
        outline + [outline[0]],
        fill=ink,
        width=5,
        joint="curve",
    )

    draw.arc(
        (
            cx-radius+4, cy-radius+4,
            cx+radius-4, cy+radius-4,
        ),
        190, 295,
        fill=character["color"],
        width=8,
    )

    # Satu mata untuk wajah profil.
    if blink:
        draw.line(
            (cx+13, cy-10, cx+21, cy-10),
            fill=ink,
            width=3,
        )
    else:
        draw.ellipse(
            (cx+13, cy-14, cx+21, cy-6),
            fill=ink,
        )

    if mouth > 0.08:
        draw.polygon(
            [
                (cx+21, cy+16),
                (cx+33, cy+15),
                (cx+30, cy+17+7*mouth),
                (cx+23, cy+18+5*mouth),
            ],
            fill=ink,
        )
    else:
        smile = [
            (
                cx + 21 + i,
                cy + 16 + 3 * math.sin(math.pi * i / 13),
            )
            for i in range(14)
        ]
        draw.line(smile, fill=ink, width=3, joint="curve")

    if direction < 0:
        layer = layer.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    if scale != 1:
        layer = layer.resize(
            (round(111 * scale), round(101 * scale)),
            Image.Resampling.LANCZOS,
        )

    position = (
        round(x - 55 * layer.width / 111),
        round(y - 50 * layer.height / 101),
    )

    if image.mode == "RGBA":
        image.alpha_composite(layer, dest=position)
    else:
        image.paste(layer, position, layer)


def draw_contact_shadows(image, pose, ground_y, scale):
    left = math.floor(min(p[0] for p in pose.feet) - 25 * scale)
    right = math.ceil(max(p[0] for p in pose.feet) + 25 * scale)
    top = round(ground_y - 5 * scale)

    layer = Image.new(
        "RGBA",
        (max(1, right-left), max(1, round(12 * scale))),
    )
    draw = ImageDraw.Draw(layer)

    for index, (x, _) in enumerate(pose.feet):
        opacity = 45 if pose.planted[index] else 14

        draw.ellipse(
            (
                x-left-22*scale, 2*scale,
                x-left+22*scale, 10*scale,
            ),
            fill=(23, 54, 74, opacity),
        )

    if image.mode == "RGBA":
        image.alpha_composite(layer, dest=(left, top))
    else:
        image.paste(layer, (left, top), layer)