"""Checkpoint percakapan stickman dengan waktu berbasis audio."""
import array
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .config import OUTPUT_DIR
from .stickman_demo import (
    actor, ease, font,
    INK, BLUE, ORANGE, W, H, FPS,
)

RATE = 24000
SAMPLES = RATE // FPS
VOICE = "id-ID-ArdiNeural"

LINES = [
    {
        "id": "radio",
        "name": "RADIO",
        "rate": "-5%",
        "pitch": "-12Hz",
        "text": (
            "Darurat! Penyelam Raka meminta bantuan. "
            "Kedalaman empat puluh meter."
        ),
    },
    {
        "id": "dimas",
        "name": "DIMAS",
        "rate": "-5%",
        "pitch": "+0Hz",
        "text": (
            "Raka? Tapi kamu ada di sini. "
            "Siapa yang mengirim sinyal itu?"
        ),
    },
    {
        "id": "raka",
        "name": "RAKA",
        "rate": "+3%",
        "pitch": "+14Hz",
        "text": (
            "Bukan aku, Dim. "
            "Aku belum menyelam hari ini."
        ),
    },
]

TITLE = font(37)
TEXT = font(29)
SMALL = font(23)


def run(command):
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=180,
    )

    if result.returncode:
        raise RuntimeError(
            f"{Path(command[0]).name} gagal, "
            f"kode {result.returncode}."
        )

    return result


def read_pcm(path):
    with wave.open(str(path), "rb") as source:
        settings = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
        )

        if settings != (1, 2, RATE):
            raise RuntimeError(
                "Format WAV harus mono, PCM 16-bit, 24000 Hz."
            )

        pcm = source.readframes(source.getnframes())

    if not pcm:
        raise RuntimeError("Audio kosong.")

    return pcm


def speech(folder, line):
    path = folder / (line["id"] + ".wav")
    meta = path.with_suffix(".json")

    signature = hashlib.sha256(
        json.dumps(
            {
                "line": line,
                "voice": VOICE,
                "revision": 1,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()

    if path.exists() and meta.exists():
        try:
            saved = json.loads(
                meta.read_text(encoding="utf-8")
            )

            matches = (
                saved["signature"] == signature
                and saved["sha256"]
                == hashlib.sha256(path.read_bytes()).hexdigest()
            )

            if matches:
                pcm = read_pcm(path)
                print(
                    f"LEWATI suara {line['name']}: masih cocok."
                )
                return pcm

        except (
            ValueError, KeyError, OSError,
            RuntimeError, wave.Error,
        ):
            pass

    executable = Path(sys.executable).with_name(
        "edge-tts.exe" if os.name == "nt" else "edge-tts"
    )

    if not executable.exists():
        raise RuntimeError(
            "edge-tts belum tersedia di environment Python ini."
        )

    mp3 = folder / (line["id"] + ".part.mp3")
    temporary = folder / (line["id"] + ".part.wav")

    print(f"Membuat suara {line['name']}...")

    try:
        run([
            str(executable),
            "--voice", VOICE,
            "--rate=" + line["rate"],
            "--pitch=" + line["pitch"],
            "--text", line["text"],
            "--write-media", str(mp3),
        ])

        command = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(mp3),
        ]

        if line["id"] == "radio":
            command += [
                "-af",
                "highpass=f=450,lowpass=f=2800",
            ]

        run(command + [
            "-ar", str(RATE),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(temporary),
        ])

        pcm = read_pcm(temporary)
        temporary.replace(path)

        meta.write_text(
            json.dumps(
                {
                    "signature": signature,
                    "sha256": hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return pcm

    finally:
        mp3.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def prepare(folder):
    cursor = FPS
    timeline = []
    sounds = []

    for line in LINES:
        pcm = speech(folder, line)
        count = math.ceil(len(pcm) / (2 * SAMPLES))

        samples = array.array("h")
        samples.frombytes(pcm)

        if sys.byteorder != "little":
            samples.byteswap()

        levels = []

        for index in range(count):
            chunk = samples[
                index * SAMPLES:(index + 1) * SAMPLES
            ]

            rms = math.sqrt(
                sum(v * v for v in chunk)
                / max(1, len(chunk))
            )

            levels.append(
                min(1.0, max(0.0, (rms - 180) / 2200))
            )

        item = dict(
            line,
            start=cursor,
            end=cursor + count,
            levels=levels,
        )

        timeline.append(item)
        sounds.append(pcm)

        print(
            f"{line['name']}: "
            f"{cursor / FPS:.2f} - "
            f"{(cursor + count) / FPS:.2f} detik"
        )

        cursor += count + round(0.7 * FPS)

    total = timeline[-1]["end"] + round(1.5 * FPS)
    track = bytearray(total * SAMPLES * 2)

    for item, pcm in zip(timeline, sounds):
        offset = item["start"] * SAMPLES * 2
        track[offset:offset + len(pcm)] = pcm

    audio = folder / "dialogue.wav"

    with wave.open(str(audio), "wb") as dest:
        dest.setparams((
            1, 2, RATE, 0, "NONE", "not compressed",
        ))
        dest.writeframes(track)

    public = [
        {
            key: value
            for key, value in item.items()
            if key != "levels"
        }
        for item in timeline
    ]

    (folder / "timeline.json").write_text(
        json.dumps(
            {
                "fps": FPS,
                "total_frames": total,
                "lines": public,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return timeline, total, audio


def character(
    image, x, color,
    gaze=1, mouth=0, surprised=False,
    listening=0, gesture=0, mirror=False,
):
    layer = Image.new("RGBA", (301, 420))
    draw = ImageDraw.Draw(layer)

    actor(
        draw, 150, 60, color, 0,
        listening=listening,
        pointing=gesture,
    )

    cx, cy, radius = 150, 60, 23 * 1.7

    draw.ellipse(
        (
            cx - radius, cy - radius,
            cx + radius, cy + radius,
        ),
        fill="#FFFDF5",
        outline=INK,
        width=5,
    )

    draw.arc(
        (
            cx - radius + 4, cy - radius + 4,
            cx + radius - 4, cy + radius - 4,
        ),
        190, 345,
        fill=color,
        width=8,
    )

    # Seluruh wajah bergeser sedikit ketika menoleh.
    face_x = cx + 4 * max(-1.0, min(1.0, gaze))
    eye_y = cy - 8

    # Kacamata mengelilingi kedua mata.
    if color == ORANGE:
        draw.rounded_rectangle(
            (
                face_x - 25, cy - 18,
                face_x + 25, cy + 2,
            ),
            radius=8,
            outline=ORANGE,
            width=3,
        )

    # Dua mata bulat.
    for eye_x in (face_x - 10, face_x + 10):
        draw.ellipse(
            (
                eye_x - 4, eye_y - 4,
                eye_x + 4, eye_y + 4,
            ),
            fill=INK,
        )

    # Hidung kecil.
    draw.line(
        [
            (face_x + 1, cy - 1),
            (face_x + 3, cy + 6),
            (face_x - 1, cy + 6),
        ],
        fill=INK,
        width=2,
        joint="curve",
    )

    # Mulut melengkung, membuka mengikuti intensitas suara.
    opening = max(0.0, min(1.0, mouth))
    upper = []
    lower = []

    for index in range(25):
        p = index / 24
        curve = math.sin(math.pi * p)
        px = face_x - 12 + 24 * p

        upper.append((
            px,
            cy + 12 + 2 * curve,
        ))

        lower.append((
            px,
            cy + 12 + (5 + 7 * opening) * curve,
        ))

    if opening > 0.05:
        draw.polygon(
            upper + list(reversed(lower)),
            fill=INK,
        )
    else:
        draw.line(
            lower,
            fill=INK,
            width=3,
            joint="curve",
        )

    if mirror:
        layer = ImageOps.mirror(layer)

    image.paste(
        layer,
        (round(x) - 150, 430),
        layer,
    )

def wrapped(draw, text, x, y, width):
    line = ""

    for word in text.split():
        candidate = (line + " " + word).strip()

        if (
            draw.textlength(candidate, font=TEXT) > width
            and line
        ):
            draw.text(
                (x, y), line,
                font=TEXT, fill=INK,
            )
            y += 40
            line = word
        else:
            line = candidate

    draw.text((x, y), line, font=TEXT, fill=INK)


def frame(index, timeline):
    t = index / FPS

    active = next(
        (
            item for item in timeline
            if item["start"] <= index < item["end"]
        ),
        None,
    )

    role = active["id"] if active else None
    level = (
        active["levels"][index - active["start"]]
        if active else 0
    )

    radio_end = timeline[0]["end"] / FPS
    question_start = timeline[1]["start"] / FPS
    question_end = timeline[1]["end"] / FPS
    answer_start = timeline[2]["start"] / FPS
    answer_end = timeline[2]["end"] / FPS

    image = Image.new("RGB", (W, H), "#F7F4EA")
    draw = ImageDraw.Draw(image)

    draw.text(
        (45, 85), "SINYAL DARI KEDALAMAN",
        font=TITLE, fill=INK,
    )

    draw.text(
        (45, 145),
        "Dimas dan Raka berada di atas perahu.",
        font=SMALL,
        fill=INK,
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

    listen = (
        ease(t, 0.1, 0.8)
        * (1 - 0.65 * ease(t, radio_end, radio_end + 0.6))
    )

    question = (
        ease(t, question_start - 0.3, question_start + 0.3)
        * (1 - ease(t, question_end, question_end + 0.4))
    )

    answer = (
        ease(t, answer_start - 0.2, answer_start + 0.3)
        * (1 - ease(t, answer_end, answer_end + 0.4))
    )

    character(
        image, 330, BLUE,
        gaze=-1 + 2 * ease(t, radio_end, radio_end + 0.5),
        mouth=level if role == "dimas" else 0,
        surprised=t >= radio_end,
        listening=listen,
        gesture=0.3 * question,
    )

    character(
        image, 540, ORANGE,
        mouth=level if role == "raka" else 0,
        surprised=t >= question_start,
        gesture=0.45 * answer,
        mirror=True,
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (290, 415), "DIMAS",
        font=SMALL, fill=INK,
    )

    draw.text(
        (510, 415), "RAKA",
        font=SMALL, fill=INK,
    )

    if role == "radio":
        draw.rounded_rectangle(
            (65, 275, 465, 365),
            radius=18,
            fill="white",
            outline=INK,
            width=3,
        )

        draw.ellipse(
            (87, 309, 105, 327),
            fill=ORANGE if level > 0.1 else INK,
        )

        draw.text(
            (125, 302), "SOS / RAKA / 40 M",
            font=TEXT, fill=INK,
        )

    draw.rounded_rectangle(
        (35, 1010, 685, 1225),
        radius=24,
        fill="#F7F4EA",
    )

    if active:
        color = (
            BLUE if role == "dimas"
            else ORANGE if role == "raka"
            else INK
        )

        draw.text(
            (60, 1030), active["name"],
            font=SMALL, fill=color,
        )

        wrapped(
            draw, active["text"],
            60, 1070, 600,
        )

    else:
        wrapped(
            draw,
            "Suara dari kedalaman..."
            if index < timeline[0]["start"]
            else "...",
            60, 1070, 600,
        )

    return image


def render(folder, timeline, total, audio):
    target = folder / "dialogue-face-v2.mp4"
    temporary = folder / "dialogue-face-v2.part.mp4"

    command = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo",
        "-pixel_format", "rgb24",
        "-video_size", f"{W}x{H}",
        "-framerate", str(FPS),
        "-i", "pipe:0",
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", str(total / FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
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
                for index in range(total):
                    process.stdin.write(
                        frame(index, timeline).tobytes()
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

        result = run([
            "ffprobe", "-v", "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(temporary),
        ])

        info = json.loads(result.stdout)

        video = next(
            stream for stream in info["streams"]
            if stream["codec_type"] == "video"
        )

        sound = next(
            stream for stream in info["streams"]
            if stream["codec_type"] == "audio"
        )

        if (
            int(video["nb_read_frames"]) != total
            or video["width"] != W
            or video["height"] != H
            or sound["codec_name"] != "aac"
            or abs(
                float(info["format"]["duration"])
                - total / FPS
            ) > 0.1
        ):
            raise RuntimeError(
                "Hasil render belum sesuai target."
            )

        temporary.replace(target)

        print(f"SELESAI: {target}")
        print(
            f"Durasi: {total / FPS:.2f} detik | "
            f"{total} frame | audio AAC"
        )

    finally:
        temporary.unlink(missing_ok=True)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit(
            "FFmpeg dan FFprobe harus tersedia di PATH."
        )

    folder = OUTPUT_DIR / "stickman-dialogue"
    folder.mkdir(parents=True, exist_ok=True)

    try:
        timeline, total, audio = prepare(folder)
        render(folder, timeline, total, audio)

    except KeyboardInterrupt:
        raise SystemExit(
            "Proses dihentikan. Suara yang sudah tersimpan "
            "dapat dipakai ulang."
        )

    except Exception as exc:
        print(f"GAGAL: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()