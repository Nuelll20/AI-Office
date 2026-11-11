"""Gambar karakter dari Bible yang sudah divalidasi; tanpa properti otomatis."""
import math

from PIL import Image, ImageDraw, ImageOps

SS = 3  # faktor supersampling untuk antialiasing


def _bounded(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} harus berupa angka berhingga.")
    return max(low, min(high, value))


class _Scaled:
    """Bungkus ImageDraw: koordinat dan lebar garis dikali SS."""

    def __init__(self, draw, k):
        self._d, self._k = draw, k

    def _s(self, v):
        k = self._k
        return [
            tuple(c * k for c in p) if isinstance(p, (tuple, list)) else p * k
            for p in v
        ]

    def _w(self, kw):
        if "width" in kw:
            kw = {**kw, "width": max(1, round(kw["width"] * self._k))}
        return kw

    def ellipse(self, xy, **kw):
        self._d.ellipse(self._s(xy), **self._w(kw))

    def arc(self, xy, a, b, **kw):
        self._d.arc(self._s(xy), a, b, **self._w(kw))

    def line(self, xy, **kw):
        self._d.line(self._s(xy), **self._w(kw))

    def polygon(self, xy, **kw):
        self._d.polygon(self._s(xy), **kw)


def _face(draw, color, palette, gaze, mouth, blink=False):
    cx, cy, radius = 150, 60, 23 * 1.7
    ink = palette["ink"]

    draw.ellipse(
        (cx-radius, cy-radius, cx+radius, cy+radius),
        fill=palette["head_fill"], outline=ink, width=5,
    )
    draw.arc(
        (cx-radius+4, cy-radius+4, cx+radius-4, cy+radius-4),
        190, 345, fill=color, width=8,
    )

    face_x = cx + 4 * gaze
    eye_y = cy - 8

    for eye_x in (face_x - 10, face_x + 10):
        if blink:
            draw.line(
                [(eye_x - 4, eye_y), (eye_x + 4, eye_y)],
                fill=ink, width=2,
            )
        else:
            draw.ellipse(
                (eye_x-4, eye_y-4, eye_x+4, eye_y+4), fill=ink,
            )

    draw.line(
        [(face_x+1, cy-1), (face_x+3, cy+6), (face_x-1, cy+6)],
        fill=ink, width=2, joint="curve",
    )

    upper, lower = [], []

    for index in range(25):
        p = index / 24
        curve = math.sin(math.pi * p)
        px = face_x - 12 + 24 * p
        upper.append((px, cy + 12 + 2 * curve))
        lower.append((px, cy + 12 + (5 + 7 * mouth) * curve))

    if mouth > 0.05:
        draw.polygon(upper + list(reversed(lower)), fill=ink)
    else:
        draw.line(lower, fill=ink, width=3, joint="curve")


def character_layer(character, visual, *, gaze=1, mouth=0,
                    listening=0, pointing=0, mirror=False, blink=False):
    """RGBA 301x420; pusat kepala (150, 60). Pose belum memiliki timeline."""
    if (visual["style"] != "stickman_2d"
            or visual["face"] != "two_eyes_nose_curved_mouth"):
        raise ValueError("Gaya atau wajah belum didukung renderer ini.")

    if type(blink) is not bool:
        raise ValueError("blink harus berupa boolean.")

    if type(mirror) is not bool:
        raise ValueError("mirror harus berupa boolean.")

    gaze = _bounded(gaze, -1, 1, "gaze")
    mouth = _bounded(mouth, 0, 1, "mouth")
    listening = _bounded(listening, 0, 1, "listening")
    pointing = _bounded(pointing, 0, 1, "pointing")

    color = character["color"]
    palette = visual["palette"]
    ink = palette["ink"]

    big = Image.new("RGBA", (301 * SS, 420 * SS))
    draw = _Scaled(ImageDraw.Draw(big), SS)
    x, y, scale = 150, 60, 1.7

    def point(px, py):
        return x + px * scale, y + py * scale

    def stroke(points, fill=ink, width=7):
        coords = [point(*p) for p in points]
        size = max(1, round(width * scale))
        draw.line(coords, fill=fill, width=size, joint="curve")
        radius = size / 2

        for px, py in coords:
            draw.ellipse(
                (px-radius, py-radius, px+radius, py+radius),
                fill=fill,
            )

    def chain(origin, lengths, angles):
        points = [origin]

        for length, degrees in zip(lengths, angles):
            angle = math.radians(degrees)
            px, py = points[-1]

            points.append((
                px + math.sin(angle) * length,
                py + math.cos(angle) * length,
            ))

        return points

    reach = 76
    spread = reach * math.sin(math.radians(10)) * scale
    ground = y + (97 + reach * math.cos(math.radians(10))) * scale

    for world_x in (x - spread, x + spread):
        side = 1 if world_x > x else -1
        fx, fy = (world_x - x) / scale, (ground - y) / scale
        dx, dy = fx, fy - 97
        distance = max(0.0001, math.hypot(dx, dy))
        bend = math.sqrt(max(0.0, 39 ** 2 - (distance / 2) ** 2)) * side

        knee = (
            dx / 2 + dy / distance * bend,
            97 + dy / 2 - dx / distance * bend,
        )

        stroke([(0, 97), knee, (fx, fy)])
        stroke([(fx - 6, fy), (fx + 10, fy)], width=8)

    stroke([(0, 27), (0, 97)], width=9)
    stroke([(0, 37), (0, 78)], fill=color, width=18)

    left = chain((0, 39), (39, 43), (
        -20 + (-55 + 20) * listening,
        -20 + (-180 + 20) * listening,
    ))

    right = chain((0, 39), (39, 43), (
        20 + (110 - 20) * pointing,
        20 + (80 - 20) * pointing,
    ))

    stroke(left)
    stroke(right)

    for hand in (left[-1], right[-1]):
        hx, hy = point(*hand)
        draw.ellipse((hx-7, hy-7, hx+7, hy+7), fill=color)

    _face(draw, color, palette, gaze, mouth, blink)

    layer = big.resize((301, 420), Image.Resampling.LANCZOS)
    return ImageOps.mirror(layer) if mirror else layer


def place_character(image, character, visual, *, x, y, scale=1, **pose):
    """Letakkan pusat kepala pada (x, y) dalam piksel kanvas tujuan."""
    for name, value in (("x", x), ("y", y), ("scale", scale)):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{name} harus berupa angka berhingga.")

    if not 0.1 <= scale <= 4:
        raise ValueError("scale harus di antara 0.1 dan 4.")

    if image.mode not in ("RGB", "RGBA"):
        raise ValueError("Kanvas harus memakai mode RGB atau RGBA.")

    layer = character_layer(character, visual, **pose)

    if scale != 1:
        layer = layer.resize(
            (round(layer.width * scale), round(layer.height * scale)),
            Image.Resampling.LANCZOS,
        )

    position = (
        round(x - 150 * layer.width / 301),
        round(y - 60 * layer.height / 420),
    )

    if image.mode == "RGBA":
        image.alpha_composite(layer, dest=position)
    else:
        image.paste(layer, position, layer)