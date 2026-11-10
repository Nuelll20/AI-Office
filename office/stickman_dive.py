"""Uji visual penyelaman; belum digabung ke pipeline produksi."""
import json
import math
import shutil
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw

from .config import OUTPUT_DIR
from .stickman_demo import (
    INK, BLUE, ORANGE,
    W, H, FPS, ease, mix, font,
)
from .stickman_dialogue import character, wrapped

SECONDS = 15
CUT = 4.2
TITLE = font(36)
LABEL = font(23)


@lru_cache(maxsize=2)
def face(color):
    canvas = Image.new("RGBA", (W, H))

    character(
        canvas, 330, color,
        gaze=-1 if color == ORANGE else 1,
    )

    head = canvas.crop((288, 448, 373, 533))

    if color == BLUE:
        ImageDraw.Draw(head).rounded_rectangle(
            (21, 24, 71, 44),
            radius=8,
            outline=BLUE,
            width=3,
        )

    return head


def diver(
    image, x, y, color, t,
    angle=0, scale=1, swimming=0,
    entry=0, preparing=0,
    geared=True, trapped=False,
):
    draw = ImageDraw.Draw(image)
    radians = math.radians(angle)
    co = math.cos(radians)
    si = math.sin(radians)

    def point(u, v):
        return (
            x + scale * (u * co - v * si),
            y + scale * (u * si + v * co),
        )

    def line(points, fill=INK, width=10):
        coords = [point(*p) for p in points]
        thick = max(2, round(width * scale))

        draw.line(
            coords,
            fill=fill,
            width=thick,
            joint="curve",
        )

        radius = thick / 2

        for px, py in coords:
            draw.ellipse(
                (
                    px - radius, py - radius,
                    px + radius, py + radius,
                ),
                fill=fill,
            )

    def limb(origin, lengths, angles):
        points = [origin]

        for length, degrees in zip(lengths, angles):
            a = math.radians(degrees)
            u, v = points[-1]

            points.append((
                u + length * math.sin(a),
                v + length * math.cos(a),
            ))

        return points

    if geared:
        tank = [
            point(u, v)
            for u, v in [
                (-45, 55),
                (-22, 55),
                (-22, 139),
                (-45, 139),
            ]
        ]

        draw.polygon(
            tank,
            fill="#B9C9CC",
            outline=INK,
        )

        line(
            [(-34, 55), (-34, 42), (-18, 42)],
            width=5,
        )

    # Kedua kaki bergerak bergantian saat berenang.
    for sign in (-1, 1):
        kick = math.sin(
            t * 7 + (0 if sign == 1 else math.pi)
        )

        angles = (
            mix(
                sign * 10,
                sign * 10 + 14 * kick,
                swimming,
            ),
            mix(
                sign * 10,
                sign * 10 + 28 * max(0, kick),
                swimming,
            ),
        )

        leg = limb(
            (0, 164.9),
            (66.3, 66.3),
            angles,
        )

        line(leg)

        fx, fy = leg[-1]
        line(
            [(fx - 10, fy), (fx + 17, fy)],
            width=13,
        )

    line([(0, 45.9), (0, 164.9)], width=15)
    line(
        [(0, 62.9), (0, 132.6)],
        fill=color,
        width=30,
    )

    # Gerakan tangan: bersiap, masuk air, dan berenang.
    for sign in (-1, 1):
        phase = (
            1 + math.sin(
                t * 4 + (0 if sign == 1 else math.pi)
            )
        ) / 2

        upper = mix(
            sign * 20,
            mix(35, 165, phase),
            swimming,
        )

        lower = mix(
            sign * 20,
            mix(80, 175, phase),
            swimming,
        )

        upper = mix(upper, sign * 55, preparing)
        lower = mix(lower, sign * 180, preparing)

        upper = mix(upper, sign * 170, entry)
        lower = mix(lower, sign * 175, entry)

        if trapped and sign == 1:
            upper = 135 + 10 * math.sin(t * 4)
            lower = 175 + 12 * math.sin(t * 4)

        arm = limb(
            (0, 66.3),
            (66.3, 73.1),
            (upper, lower),
        )

        line(arm)

        hx, hy = point(*arm[-1])
        radius = 7 * scale

        draw.ellipse(
            (
                hx - radius, hy - radius,
                hx + radius, hy + radius,
            ),
            fill=color,
        )

    if not geared and color == BLUE:
        canvas = Image.new("RGBA", (W, H))
        character(canvas, 330, color)
        head = canvas.crop((288, 448, 373, 533))
    else:
        head = face(color)

    size = round(85 * scale)

    head = head.resize(
        (size, size),
        Image.Resampling.LANCZOS,
    )

    image.paste(
        head,
        (
            round(x - size / 2),
            round(y - size / 2),
        ),
        head,
    )


def caption(image, text):
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (35, 1080, 685, 1230),
        radius=24,
        fill="#F7F4EA",
    )

    wrapped(draw, text, 60, 1100, 600)


def surface(t):
    image = Image.new("RGB", (W, H), "#F7F4EA")
    draw = ImageDraw.Draw(image)

    draw.text(
        (45, 85), "DIMAS MENYELIDIKI SINYAL",
        font=TITLE, fill=INK,
    )

    draw.text(
        (45, 145), "Di tepi perahu",
        font=LABEL, fill=INK,
    )

    draw.ellipse(
        (540, 285, 640, 385),
        fill="#F5D794",
    )

    draw.rectangle(
        (0, 450, W, H),
        fill="#96CED3",
    )

    for row in range(7):
        points = [
            (
                px,
                480 + row * 110
                + 8 * math.sin(px / 65 + t * 1.7 + row),
            )
            for px in range(0, W + 1, 8)
        ]

        draw.line(
            points,
            fill="#6AB4C1",
            width=4,
        )

    # Sudut kamera lebih dekat ke tepi perahu.
    draw.polygon(
        [(-130, 800), (500, 800), (440, 940), (-80, 940)],
        fill=INK,
    )

    draw.polygon(
        [(-115, 818), (479, 818), (432, 913), (-64, 913)],
        fill="#B66D4C",
    )

    draw.rounded_rectangle(
        (-120, 782, 500, 813),
        radius=10,
        fill="#E8BA83",
    )

    character(
        image, 200, ORANGE,
        mirror=True,
    )

    prepare = math.sin(
        math.pi * ease(t, 0.2, 1.5)
    )

    p = ease(t, 2.2, CUT)
    x = mix(430, 650, p)
    y = mix(490, 1080, p) - 100 * math.sin(math.pi * p)

    diver(
        image, x, y, BLUE, t,
        angle=145 * p,
        entry=ease(t, 1.55, 2.15),
        preparing=prepare,
        geared=t >= 0.9,
    )

    draw = ImageDraw.Draw(image)

    # Permukaan air menutupi bagian tubuh yang sudah masuk.
    draw.rectangle(
        (500, 950, W, H),
        fill="#96CED3",
    )

    if t > 3.35:
        spread = 20 + 70 * ease(t, 3.35, CUT)

        draw.arc(
            (635 - spread, 925, 635 + spread, 975),
            180, 355,
            fill="#E7FCF7",
            width=6,
        )

        for i in range(5):
            px = 635 + (i - 2) * 18

            py = 937 - 32 * math.sin(
                math.pi * ease(t, 3.35, CUT)
            )

            draw.ellipse(
                (px - 3, py - 6, px + 3, py + 6),
                fill="#E7FCF7",
            )

    caption(
        image,
        "Dimas menyiapkan perlengkapan selam."
        if t < 2.2
        else "Ia turun untuk mencari sumber sinyal.",
    )

    return image


def underwater(t):
    image = Image.new("RGB", (W, H), "#286977")
    draw = ImageDraw.Draw(image)

    draw.polygon(
        [(30, 0), (150, 0), (540, 1070), (210, 1070)],
        fill="#317B85",
    )

    draw.polygon(
        [(430, 0), (500, 0), (710, 1070), (570, 1070)],
        fill="#2D7380",
    )

    draw.text(
        (45, 85), "DI BAWAH PERMUKAAN",
        font=TITLE,
        fill="#F7F4EA",
    )

    for i in range(18):
        px = (i * 137 + 41) % W
        py = 200 + (i * 97 - t * 25) % 820

        draw.ellipse(
            (px, py, px + 3, py + 3),
            fill="#7CB6BD",
        )

    draw.polygon(
        [
            (0, 1060),
            (160, 1020),
            (320, 1070),
            (520, 1030),
            (720, 1060),
            (720, H),
            (0, H),
        ],
        fill="#B5A98C",
    )

    reveal = ease(t, 3.8, 5.5)

    wreck = Image.new("RGBA", (W, H))
    wd = ImageDraw.Draw(wreck)

    wd.polygon(
        [(430, 925), (715, 925), (674, 1035), (470, 1035)],
        fill="#765D4F",
        outline=INK,
    )

    wd.line(
        (650, 750, 650, 995),
        fill="#594B42",
        width=14,
    )

    wd.line(
        (590, 795, 705, 785),
        fill="#594B42",
        width=10,
    )

    for px in (500, 580, 660):
        wd.ellipse(
            (px - 18, 955, px + 18, 991),
            fill="#173D49",
            outline="#AE8C66",
            width=4,
        )

    diver(
        wreck, 580, 650, ORANGE, t,
        scale=0.9,
        trapped=True,
    )

    wd = ImageDraw.Draw(wreck)

    # Balok patah melintang di kaki sosok oranye.
    wd.polygon(
        [(530, 915), (643, 899), (649, 924), (533, 941)],
        fill="#594B42",
        outline=INK,
    )

    wd.line(
        (539, 921, 633, 908),
        fill="#A88762",
        width=3,
    )

    if reveal < 1:
        wreck.putalpha(
            wreck.getchannel("A").point(
                lambda alpha: round(alpha * reveal)
            )
        )

    image.paste(wreck, (0, 0), wreck)

    progress = ease(t, 0, 6)
    x = mix(190, 420, progress)
    y = mix(520, 620, progress)
    swim = 1 - 0.7 * ease(t, 6, 7.2)

    diver(
        image,
        x,
        y + 3 * math.sin(t * 2),
        BLUE,
        t,
        angle=mix(100, 82, progress),
        scale=0.85,
        swimming=swim,
    )

    draw = ImageDraw.Draw(image)

    for i in range(5):
        age = (t + i * 0.31) % 1.5
        bx = x + 10 - age * 24
        by = y + 10 - age * 90
        radius = 2 + age * 2

        draw.ellipse(
            (
                bx - radius, by - radius,
                bx + radius, by + radius,
            ),
            outline="#C6F3EF",
            width=2,
        )

    caption(
        image,
        "Dimas mengikuti sinyal ke arah kapal karam."
        if t < 5.5
        else "Sosok itu mirip Raka. Kakinya terjepit!",
    )

    return image


def frame(t):
    if t < CUT:
        return surface(t)

    return underwater(t - CUT)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit(
            "FFmpeg dan FFprobe harus tersedia di PATH."
        )

    folder = OUTPUT_DIR / "stickman-dive"
    folder.mkdir(parents=True, exist_ok=True)

    target = folder / "dive.mp4"
    temporary = folder / "dive.part.mp4"

    command = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo",
        "-pixel_format", "rgb24",
        "-video_size", f"{W}x{H}",
        "-framerate", str(FPS),
        "-i", "pipe:0",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(temporary),
    ]

    try:
        with (folder / "render.log").open("wb") as log:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=log,
            )

            try:
                for index in range(FPS * SECONDS):
                    process.stdin.write(
                        frame(index / FPS).tobytes()
                    )

                process.stdin.close()

                if process.wait(timeout=180):
                    raise RuntimeError(
                        "Render gagal. Periksa render.log."
                    )

            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-count_frames",
                "-select_streams", "v:0",
                "-show_entries",
                "stream=nb_read_frames,width,height",
                "-of", "json",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        stream = json.loads(result.stdout)["streams"][0]

        if (
            int(stream["nb_read_frames"]) != FPS * SECONDS
            or stream["width"] != W
            or stream["height"] != H
        ):
            raise RuntimeError(
                "Hasil render tidak sesuai target."
            )

        temporary.replace(target)

        print(f"SELESAI: {target}")
        print(
            f"{SECONDS} detik | "
            f"{FPS * SECONDS} frame | tanpa audio"
        )

    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()