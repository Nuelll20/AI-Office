"""Uji animasi aktor 2D; belum terhubung ke produksi utama."""
import json
import math
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

from .config import OUTPUT_DIR

W, H, FPS, SECONDS = 720, 1280, 30, 8
INK = "#17364A"
BLUE = "#287FD0"
ORANGE = "#F28C38"


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass

    return ImageFont.load_default(size=size)


TITLE_FONT = font(38)
TEXT_FONT = font(27)
SMALL_FONT = font(21)


def ease(t, start, end):
    p = max(0.0, min(1.0, (t - start) / (end - start)))
    return p * p * (3 - 2 * p)


def mix(a, b, p):
    return a + (b - a) * p


def actor(
    draw, x, y, color, phase,
    walking=0, listening=0, pointing=0, walk_path=None,
):
    scale = 1.7
    spread = 78 * math.sin(math.radians(10)) * scale
    ground = y + (97 + 78 * math.cos(math.radians(10))) * scale

    feet = [
        [x - spread, ground],
        [x + spread, ground],
    ]
    cycle = 0.0

    if walk_path is not None:
        start, end = walk_path
        progress = max(
            0.0,
            min(1.0, (x - start) / (end - start)),
        )

        cycle = progress * 4

        feet = [
            [start - spread, ground],
            [start + spread, ground],
        ]

        stride = (end - start) / 2

        for step in range(4):
            leg_index = step % 2

            feet[leg_index][0] += (
                stride * ease(cycle, step, step + 1)
            )

            if step <= cycle < step + 1:
                lift = math.sin(
                    math.pi * (cycle - step)
                ) ** 2

                feet[leg_index][1] -= 12 * scale * lift

        y += (
            3 + 1.2 * math.sin(math.pi * cycle) ** 2
        ) * scale * walking

    def point(px, py):
        return (x + px * scale, y + py * scale)

    def stroke(points, fill=INK, width=7):
        coords = [point(*p) for p in points]
        size = max(1, round(width * scale))

        draw.line(
            coords,
            fill=fill,
            width=size,
            joint="curve",
        )

        radius = size / 2

        for px, py in coords:
            draw.ellipse(
                (
                    px - radius, py - radius,
                    px + radius, py + radius,
                ),
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

    # Posisi lutut dihitung dari posisi pinggul dan telapak kaki.
    # Panjang paha dan betis tetap sama selama animasi.
    for world_x, world_y in feet:
        fx = (world_x - x) / scale
        fy = (world_y - y) / scale

        dx, dy = fx, fy - 97
        distance = max(0.0001, math.hypot(dx, dy))

        bend = math.sqrt(
            max(0.0, 39 ** 2 - (distance / 2) ** 2)
        )

        knee = (
            dx / 2 + dy / distance * bend,
            97 + dy / 2 - dx / distance * bend,
        )

        stroke([(0, 97), knee, (fx, fy)])
        stroke(
            [(fx - 6, fy), (fx + 10, fy)],
            width=8,
        )

    stroke([(0, 27), (0, 97)], width=9)
    stroke([(0, 37), (0, 78)], fill=color, width=18)

    swing = math.sin(math.pi * cycle) * 16 * walking

    left = chain(
        (0, 39),
        (39, 43),
        (
            mix(-20 - swing, -55, listening),
            mix(-20 + swing, -180, listening),
        ),
    )

    right = chain(
        (0, 39),
        (39, 43),
        (
            mix(20 + swing, 110, pointing),
            mix(20 - swing, 80, pointing),
        ),
    )

    stroke(left)
    stroke(right)

    for hand in (left[-1], right[-1]):
        hx, hy = point(*hand)

        draw.ellipse(
            (hx - 7, hy - 7, hx + 7, hy + 7),
            fill=color,
        )

    radius = 23 * scale

    draw.ellipse(
        (
            x - radius, y - radius,
            x + radius, y + radius,
        ),
        fill="#FFFDF5",
        outline=INK,
        width=5,
    )

    draw.arc(
        (
            x - radius + 4, y - radius + 4,
            x + radius - 4, y + radius - 4,
        ),
        190, 345, fill=color, width=8,
    )

    draw.ellipse(
        (x + 4, y - 4, x + 10, y + 2),
        fill=INK,
    )

    draw.line(
        (x + 4, y + 12, x + 14, y + 12),
        fill=INK,
        width=3,
    )

    if color == BLUE:
        hx, hy = point(*left[-1])

        draw.rounded_rectangle(
            (hx - 12, hy - 23, hx + 12, hy + 13),
            radius=5,
            fill=INK,
        )

        draw.line(
            (hx + 5, hy - 23, hx + 5, hy - 39),
            fill=INK,
            width=3,
        )

        draw.rectangle(
            (hx - 7, hy - 15, hx + 7, hy - 6),
            fill="#73E8E0",
        )

    else:
        draw.rounded_rectangle(
            (x - 18, y - 9, x + 19, y + 8),
            radius=5,
            outline=ORANGE,
            width=4,
        )

def frame(t):
    image = Image.new("RGB", (W, H), "#F7F4EA")
    draw = ImageDraw.Draw(image)

    draw.text(
        (48, 70), "KANTOR AI / UJI ANIMASI",
        font=SMALL_FONT, fill=INK,
    )

    draw.text(
        (48, 115), "Aktor bergerak dalam adegan",
        font=TITLE_FONT, fill=INK,
    )

    draw.text(
        (48, 174), "Penolong biru  /  Penyelam oranye",
        font=TEXT_FONT, fill=INK,
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

        draw.line(points, fill="#6AB4C1", width=4)

    draw.polygon(
        [(40, 800), (680, 800), (615, 940), (115, 940)],
        fill=INK,
    )

    draw.polygon(
        [(58, 818), (660, 818), (608, 913), (123, 913)],
        fill="#B66D4C",
    )

    draw.rounded_rectangle(
        (45, 782, 675, 813),
        radius=10,
        fill="#E8BA83",
    )

    for px in (150, 570):
        draw.line(
            (px, 785, px, 705),
            fill=INK,
            width=6,
        )

    draw.line(
        (150, 707, 570, 707),
        fill=INK,
        width=5,
    )

    walking = 1 - ease(t, 2.0, 2.8)
    listening = ease(t, 2.8, 4.0)
    pointing = ease(t, 5.2, 6.3)
    x = mix(155, 330, ease(t, 0, 2.8))

    actor(draw, 540, 490, ORANGE, t * 7)

    actor(
        draw, x, 490, BLUE, t * 9,
        walking, listening, pointing,
        walk_path=(155, 330),
    )

    if t >= 4:
        draw.rounded_rectangle(
            (65, 310, 440, 400),
            radius=18,
            fill="white",
            outline=INK,
            width=3,
        )

        draw.text(
            (88, 337), "RADIO: SOS - 40 meter",
            font=TEXT_FONT, fill=INK,
        )

        draw.line(
            (180, 400, x - 42, 500),
            fill=INK,
            width=3,
        )

    labels = (
        "Berjalan mendekati penyelam",
        "Mengangkat radio dan mendengar SOS",
        "Menunjuk arah sumber sinyal",
    )

    label = labels[
        0 if t < 2.8 else 1 if t < 5.2 else 2
    ]

    draw.rounded_rectangle(
        (35, 1040, 685, 1190),
        radius=24,
        fill="#F7F4EA",
    )

    draw.text(
        (62, 1060), label,
        font=TEXT_FONT, fill=INK,
    )

    draw.text(
        (62, 1110),
        "Uji gerakan saja - belum video cerita final",
        font=SMALL_FONT,
        fill=INK,
    )

    return image


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit(
            "FFmpeg dan FFprobe harus tersedia di PATH."
        )

    folder = OUTPUT_DIR / "stickman-test"
    folder.mkdir(parents=True, exist_ok=True)

    target = folder / "actor-demo-walk-v2.mp4"
    temporary = folder / "actor-demo-walk-v2.part.mp4"
    log = folder / "render.log"

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
        with log.open("wb") as errors:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=errors,
            )

            try:
                for index in range(FPS * SECONDS):
                    process.stdin.write(
                        frame(index / FPS).tobytes()
                    )

                process.stdin.close()

                if process.wait(timeout=120) != 0:
                    raise RuntimeError(
                        "FFmpeg gagal. Periksa render.log."
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
                "-show_entries", "stream=nb_read_frames",
                "-of", "json",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        count = int(
            json.loads(result.stdout)["streams"][0]["nb_read_frames"]
        )

        if count != FPS * SECONDS:
            raise RuntimeError(
                "Jumlah frame hasil render tidak sesuai."
            )

        temporary.replace(target)

        print(f"SELESAI: {target}")
        print(
            f"{W}x{H}, {FPS} fps, {SECONDS} detik, "
            f"{count} frame. Tanpa audio."
        )

    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()