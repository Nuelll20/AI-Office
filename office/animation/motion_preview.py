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


def render_preview(
    bible, timeline, output, *,
    frame_renderer=None,
    audio_path=None,
    frame_count=None,
):
    render_frame = frame if frame_renderer is None else frame_renderer
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

    frames = (
        math.ceil(timeline["duration_sec"] * fps)
        if frame_count is None
        else frame_count
    )

    if type(frames) is not int or frames < 1:
        raise ValueError(
            "Jumlah frame harus bilangan bulat positif."
        )

    if abs(frames / fps - timeline["duration_sec"]) > 1 / fps:
        raise ValueError("Jumlah frame dan durasi tidak cocok.")
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

        if audio_path is not None:
            position = command.index("-an")

            command[position:position+1] = [
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:a", "aac",
                "-b:a", "128k",
            ]

        with log.open("wb") as errors:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=errors,
            )

            try:
                for index in range(frames):
                    current = render_frame(
                        bible,
                        timeline,
                        index / fps,
                    )

                    if (
                        current.mode != "RGB"
                        or current.size != (width, height)
                    ):
                        raise ValueError(
                            f"Frame {index} harus RGB "
                            f"berukuran {width}x{height}."
                        )

                    process.stdin.write(current.tobytes())

                # Di luar loop: tutup setelah semua frame terkirim.
                process.stdin.close()

                if process.wait(timeout=120):
                    raise ValueError(
                        f"FFmpeg gagal. Periksa {log}."
                    )

            except BrokenPipeError as exc:
                raise ValueError(
                    "FFmpeg berhenti menerima frame. "
                    f"Periksa {log}."
                ) from exc

            finally:
                if process.poll() is None:
                    process.kill()

                process.wait()

                if not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except OSError:
                        # Pertahankan pesan error awal.
                        pass

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
        if audio_path is not None:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries",
                    "stream=codec_type,duration",
                    "-of", "json",
                    str(temporary),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )

            streams = json.loads(probe.stdout)["streams"]

            if sorted(
                item["codec_type"] for item in streams
            ) != ["audio", "video"]:
                raise ValueError(
                    "Hasil harus memiliki satu video dan satu audio."
                )

            for item in streams:
                duration = float(item.get("duration", "nan"))

                if (
                    not math.isfinite(duration)
                    or abs(duration - frames/fps) > 1/fps + 0.01
                ):
                    raise ValueError(
                        "Durasi audio/video tidak sesuai jadwal frame."
                    )
        temporary.replace(output)

    audio_label = (
        "dengan audio"
        if audio_path is not None
        else "tanpa audio"
    )

    print(
        f"{width}x{height} | {fps} fps | "
        f"{frames} frame | {audio_label}"
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