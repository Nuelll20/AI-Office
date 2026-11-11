"""Render uji timeline pose menjadi MP4 tanpa audio."""
import argparse
import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

from ..bible import load_bible
from .characters import place_character
from .motions import load_timeline, sample_pose
from .preview import font


def frame(bible, timeline, seconds):
    target = bible["target"]
    visual = bible["visual"]
    palette = visual["palette"]

    image = Image.new(
        "RGB",
        (target["width"], target["height"]),
        palette["paper"],
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (40, 65),
        "UJI TIMELINE POSE",
        font=font(28),
        fill=palette["ink"],
    )

    draw.text(
        (40, 110),
        f"{seconds:.2f} / {timeline['duration_sec']:.2f} detik",
        font=font(22),
        fill=palette["ink"],
    )

    characters = {
        item["id"]: item
        for item in bible["characters"]
    }

    for n, track in enumerate(timeline["tracks"]):
        character = characters[track["character_id"]]
        bob = 4 * track["scale"] * math.sin(2 * math.pi * seconds / 3.2 + n)
        blink = (seconds + n * 0.7) % 3.5 < 0.12

        place_character(
            image, character, visual,
            x=track["x"], y=track["y"] + bob,
            scale=track["scale"], mirror=track["mirror"],
            blink=blink,
            **sample_pose(track["keyframes"], seconds),
        )

        draw.text(
            (track["x"], track["y"] + 330 * track["scale"]),
            character["name"],
            anchor="mm",
            font=font(22),
            fill=palette["ink"],
        )

    return image


def render_preview(bible, timeline, output):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg dan FFprobe harus tersedia di PATH.")

    target = bible["target"]
    width = target["width"]
    height = target["height"]
    fps = target["fps"]

    if (
        max(width, height) > 1920
        or fps > 60
        or timeline["duration_sec"] > 30
    ):
        raise ValueError(
            "Preview dibatasi sisi 1920 px, 60 fps, dan 30 detik."
        )

    frames = math.ceil(timeline["duration_sec"] * fps)
    output = Path(output)

    if output.suffix.lower() != ".mp4":
        raise ValueError("Output harus berakhiran .mp4.")

    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_suffix(".log")

    with tempfile.TemporaryDirectory(dir=output.parent) as folder:
        temporary = Path(folder) / "preview.mp4"

        command = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "rawvideo",
            "-pixel_format", "rgb24",
            "-video_size", f"{width}x{height}",
            "-framerate", str(fps),
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(temporary),
        ]

        with log.open("wb") as errors:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=errors,
            )

            try:
                for index in range(frames):
                    process.stdin.write(
                        frame(
                            bible,
                            timeline,
                            index / fps,
                        ).tobytes()
                    )

                process.stdin.close()

                if process.wait(timeout=120):
                    raise ValueError(
                        f"FFmpeg gagal. Periksa {log}."
                    )

            finally:
                if process.poll() is None:
                    process.kill()

                process.wait()
                process.stdin.close()

        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-count_frames",
                "-select_streams", "v:0",
                "-show_entries",
                "stream=codec_name,width,height,nb_read_frames,r_frame_rate",
                "-of", "json",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )

        stream = json.loads(result.stdout)["streams"][0]

        if (
            stream["codec_name"] != "h264"
            or stream["width"] != width
            or stream["height"] != height
            or int(stream["nb_read_frames"]) != frames
            or Fraction(stream["r_frame_rate"]) != fps
        ):
            raise ValueError(
                "Hasil render tidak sesuai spesifikasi preview."
            )

        temporary.replace(output)

    print(f"SELESAI: {output.resolve()}")
    print(
        f"{width}x{height} | {fps} fps | "
        f"{frames} frame | tanpa audio"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bible", required=True, type=Path)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        bible = load_bible(args.bible)
        timeline = load_timeline(args.timeline, bible)
        render_preview(bible, timeline, args.output)

    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"PREVIEW GAGAL: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())