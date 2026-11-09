"""Render klip per adegan: gerakan kamera, narasi, dan subtitle."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess

from . import db, events
from .audio import duration, generate_audio
from .images import generate_images
from .config import OUTPUT_DIR, ROOT

WIDTH, HEIGHT, FPS = 720, 1280, 30
REVISION = 1

STYLE = (
    "FontName=Arial,FontSize=11,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,"
    "Alignment=2,MarginV=28,MarginL=14,MarginR=14"
)


def run(args, cwd=None):
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if result.returncode:
        raise RuntimeError(
            (result.stderr or result.stdout)[-3000:]
        )
    return result.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def verify(path, expected):
    info = json.loads(
        run([
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path),
        ])
    )

    video = next(
        (
            s for s in info["streams"]
            if s["codec_type"] == "video"
        ),
        {},
    )
    audio = next(
        (
            s for s in info["streams"]
            if s["codec_type"] == "audio"
        ),
        {},
    )
    actual = float(info["format"]["duration"])

    if (
        video.get("codec_name") != "h264"
        or audio.get("codec_name") != "aac"
        or video.get("width") != WIDTH
        or video.get("height") != HEIGHT
        or video.get("r_frame_rate") != f"{FPS}/1"
        or video.get("pix_fmt") != "yuv420p"
        or not math.isfinite(actual)
        or abs(actual - expected) > 0.08
    ):
        raise ValueError(
            f"Spesifikasi atau durasi klip tidak sesuai: "
            f"{path.name}"
        )

    return actual


def cached(path, fingerprint, seconds):
    try:
        meta = json.loads(
            path.with_suffix(".render.json").read_text(
                encoding="utf-8"
            )
        )

        if (
            meta["fingerprint"] != fingerprint
            or meta["sha256"] != digest(path)
        ):
            return False

        verify(path, seconds)
        return True

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ):
        return False


def camera(scene, frames):
    motion = scene.get("motion") or {}
    requested = motion.get("type", "zoom_in")
    kind = "pan_right" if requested == "parallax" else requested

    speed = motion.get("speed", "slow")
    amounts = {
        "slow": 0.06,
        "medium": 0.10,
        "fast": 0.14,
    }
    if speed not in amounts:
        raise ValueError(
            f"Kecepatan motion tidak dikenal: {speed}"
        )

    amount = amounts[speed]
    progress = f"on/{max(1, frames - 1)}"

    x = "(iw-iw/zoom)/2"
    y = "(ih-ih/zoom)/2"
    zoom = str(1 + amount)

    if kind == "zoom_in":
        zoom = f"1+{amount}*({progress})"
    elif kind == "zoom_out":
        zoom = f"1+{amount}*(1-({progress}))"
    elif kind == "pan_left":
        x = f"(iw-iw/zoom)*(1-({progress}))"
    elif kind == "pan_right":
        x = f"(iw-iw/zoom)*({progress})"
    elif kind == "tilt_up":
        y = f"(ih-ih/zoom)*(1-({progress}))"
    elif kind == "tilt_down":
        y = f"(ih-ih/zoom)*({progress})"
    elif kind == "shake":
        x = "(iw-iw/zoom)*(0.5+0.08*sin(on*0.7))"
        y = "(ih-ih/zoom)*(0.5+0.08*sin(on*0.9))"
    else:
        raise ValueError(
            f"Motion tidak dikenal: {requested}"
        )

    movement = (
        f"zoompan=z='{zoom}':x='{x}':y='{y}':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    return movement, kind


def render_clips(video_id, limit=None, check_only=False):
    if limit is not None and limit < 1:
        raise ValueError("Limit minimal 1.")

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise ValueError(
                f"{tool} belum tersedia di PATH."
            )

    if not db.get_video(video_id):
        raise ValueError(
            f"Video {video_id} tidak ditemukan."
        )

    out = OUTPUT_DIR / video_id
    scene_file = out / "scenes.json"
    data = json.loads(
        scene_file.read_text(encoding="utf-8")
    )
    scenes = data["scenes"]

    if generate_images(video_id, check_only=True) != len(scenes):
        raise ValueError(
            "Selesaikan atau perbarui semua gambar dahulu."
        )

    if generate_audio(video_id, check_only=True) != len(scenes):
        raise ValueError(
            "Selesaikan atau perbarui semua audio dahulu."
        )

    ffmpeg_version = run(
        ["ffmpeg", "-version"]
    ).splitlines()[0]

    records = []

    for scene in scenes:
        sid = scene["id"]
        image = out / "images" / f"scene-{sid:03d}.png"
        audio = out / "audio" / f"scene-{sid:03d}.mp3"
        subtitle = audio.with_suffix(".srt")

        # Bulatkan ke atas agar durasi sesuai jumlah frame.
        frames = max(1, math.ceil(duration(audio) * FPS))
        seconds = frames / FPS

        movement, kind = camera(scene, frames)

        vf = (
            f"scale={WIDTH*2}:{HEIGHT*2}:"
            "force_original_aspect_ratio=increase,"
            f"crop={WIDTH*2}:{HEIGHT*2},"
            f"{movement},setsar=1,"
            f"subtitles=filename=audio/scene-{sid:03d}.srt:"
            f"force_style='{STYLE}'"
        )

        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "revision": REVISION,
                    "ffmpeg": ffmpeg_version,
                    "image": digest(image),
                    "audio": digest(audio),
                    "subtitle": digest(subtitle),
                    "filter": vf,
                    "duration": seconds,
                    "encoding": (
                        "x264-veryfast-crf20-"
                        "aac128k-48k-stereo"
                    ),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        path = out / "renders" / f"scene-{sid:03d}.mp4"

        records.append(
            (
                scene,
                path,
                vf,
                kind,
                seconds,
                fingerprint,
                cached(path, fingerprint, seconds),
            )
        )

    ready = sum(record[-1] for record in records)

    print(
        f"Klip cocok dan tersedia: {ready}/{len(scenes)}"
    )

    if check_only:
        for scene, _, _, kind, seconds, _, valid in records:
            label = "SIAP" if valid else "PERLU DIRENDER"
            print(
                f"Scene {scene['id']:03d}: {label} "
                f"| {kind} | {seconds:.3f} detik"
            )
        return ready

    (out / "renders").mkdir(exist_ok=True)

    def mark(scene, path, kind, seconds):
        scene.update(
            render_status="ready",
            render_path=path.relative_to(ROOT).as_posix(),
            render_motion=kind,
            render_duration_sec=seconds,
        )
        scene.pop("render_error", None)

    for scene, path, _, kind, seconds, _, valid in records:
        if valid:
            mark(scene, path, kind, seconds)
        else:
            scene["render_status"] = "pending"

            for key in (
                "render_path",
                "render_duration_sec",
                "render_motion",
                "render_error",
            ):
                scene.pop(key, None)

    def save(status):
        write_json(scene_file, data)
        db.update_video(
            video_id,
            scenes=data,
            status=status,
        )

    save(
        "clips_ready"
        if ready == len(scenes)
        else "clips_processing"
    )

    made = 0

    for scene, path, vf, kind, seconds, fingerprint, valid in records:
        sid = scene["id"]

        if valid:
            print(
                f"LEWATI scene {sid:03d}: klip masih cocok."
            )
            continue

        if limit is not None and made >= limit:
            break

        temp = path.with_suffix(".part.mp4")

        try:
            events.emit(
                "sari",
                "work",
                f"Render scene {sid}: {kind}...",
                video_id=video_id,
            )

            if (
                (scene.get("motion") or {}).get("type")
                == "parallax"
            ):
                print(
                    "Parallax memakai pan_right sementara: "
                    "gambar belum memiliki lapisan kedalaman."
                )

            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-nostdin",
                    "-i", f"images/scene-{sid:03d}.png",
                    "-i", f"audio/scene-{sid:03d}.mp3",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-vf", vf,
                    "-af", "apad",
                    "-t", f"{seconds:.6f}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "20",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-ar", "48000",
                    "-ac", "2",
                    "-movflags", "+faststart",
                    f"renders/{temp.name}",
                ],
                cwd=out,
            )

            verify(temp, seconds)
            temp.replace(path)

            write_json(
                path.with_suffix(".render.json"),
                {
                    "fingerprint": fingerprint,
                    "sha256": digest(path),
                    "duration_sec": seconds,
                    "motion": kind,
                },
            )

            mark(scene, path, kind, seconds)
            ready += 1
            made += 1

            save("clips_processing")

            print(
                f"SELESAI scene {sid:03d}: "
                f"{seconds:.3f} detik."
            )

        except (Exception, KeyboardInterrupt) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)

            scene["render_status"] = (
                "pending" if interrupted else "failed"
            )
            scene["render_error"] = (
                str(exc) or "Dihentikan pengguna."
            )

            save(
                "clips_partial"
                if interrupted
                else "clips_failed"
            )

            events.emit(
                "sari",
                "say",
                f"Render berhenti pada scene {sid}.",
                video_id=video_id,
            )
            raise

        finally:
            temp.unlink(missing_ok=True)

    status = (
        "clips_ready"
        if ready == len(scenes)
        else "clips_partial"
    )
    save(status)

    events.emit(
        "sari",
        "say",
        f"Klip siap {ready}/{len(scenes)}.",
        video_id=video_id,
    )

    print(
        f"Status: {status}. "
        f"Klip baru: {made}. "
        f"Total siap: {ready}/{len(scenes)}."
    )
    return ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    db.init()

    try:
        render_clips(args.id, args.limit, args.check)
    except KeyboardInterrupt:
        parser.exit(
            130,
            "Dihentikan. Klip yang sudah selesai "
            "tetap tersimpan.\n",
        )
    except (
        RuntimeError,
        ValueError,
        OSError,
        KeyError,
        TypeError,
        ImportError,
        subprocess.SubprocessError,
    ) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()