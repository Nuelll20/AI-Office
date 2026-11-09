"""Gabungkan klip sesuai urutan scenes.json menjadi final.mp4."""
import argparse
import hashlib
import json
import math
import subprocess

from . import db, events
from .audio import duration
from .config import OUTPUT_DIR
from .render import (
    FPS,
    cached,
    digest,
    render_clips,
    run,
    verify,
    write_json,
)

REVISION = 1


def assemble(video_id, check_only=False):
    if not db.get_video(video_id):
        raise ValueError(
            f"Video {video_id} tidak ditemukan."
        )

    out = OUTPUT_DIR / video_id
    data = json.loads(
        (out / "scenes.json").read_text(encoding="utf-8")
    )
    scenes = data["scenes"]

    if (
        not scenes
        or render_clips(video_id, check_only=True) != len(scenes)
    ):
        raise ValueError(
            "Semua klip harus SIAP sebelum digabungkan."
        )

    records, filters, labels = [], [], []

    args = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-nostdin",
        "-filter_complex_threads", "2",
    ]

    # Urutan mengikuti daftar scenes, bukan urutan nama file.
    for index, scene in enumerate(scenes):
        sid = scene["id"]
        relative = f"renders/scene-{sid:03d}.mp4"

        frames = math.ceil(
            duration(
                out / "audio" / f"scene-{sid:03d}.mp3"
            ) * FPS
        )
        samples = round(frames * 48000 / FPS)

        records.append(
            {
                "scene_id": sid,
                "file": relative,
                "sha256": digest(out / relative),
                "frames": frames,
            }
        )

        args += [
            "-threads", "1",
            "-i", relative,
        ]

        filters.append(
            f"[{index}:v:0]"
            f"trim=end_frame={frames},"
            f"setpts=N/{FPS}/TB[v{index}]"
        )

        filters.append(
            f"[{index}:a:0]"
            "aresample=48000,apad,"
            f"atrim=end_sample={samples},"
            f"asetpts=N/SR/TB[a{index}]"
        )

        labels.append(f"[v{index}][a{index}]")

    filters.append(
        "".join(labels)
        + f"concat=n={len(scenes)}:v=1:a=1[v][a]"
    )
    graph = ";".join(filters)

    total_frames = sum(
        record["frames"] for record in records
    )
    expected = total_frames / FPS

    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "revision": REVISION,
                "sources": records,
                "filter": graph,
                "ffmpeg": run(
                    ["ffmpeg", "-version"]
                ).splitlines()[0],
                "encoding": (
                    "x264-veryfast-crf20-"
                    "aac128k-48k-stereo"
                ),
                "fps": FPS,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()

    final = out / "final.mp4"
    valid = cached(final, fingerprint, expected)

    print(
        f"Target: {len(scenes)} adegan, "
        f"{expected:.3f} detik."
    )

    if check_only:
        print(
            "Video final: SIAP"
            if valid
            else "Video final: PERLU DIGABUNGKAN"
        )
        return valid

    if valid:
        db.update_video(
            video_id,
            status="video_ready",
        )
        print(
            f"LEWATI: final.mp4 masih cocok.\n"
            f"Lokasi: {final}"
        )
        return final

    temporary = out / "final.part.mp4"
    db.update_video(video_id, status="assembling")

    try:
        events.emit(
            "sari",
            "work",
            f"Menggabungkan {len(scenes)} adegan...",
            video_id=video_id,
        )

        args += [
            "-filter_complex", graph,
            "-map", "[v]",
            "-map", "[a]",
            "-r", str(FPS),
            "-c:v", "libx264",
            "-threads", "4",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-ac", "2",
            "-t", f"{expected:.6f}",
            "-movflags", "+faststart",
            temporary.name,
        ]

        run(args, cwd=out)
        actual = verify(temporary, expected)

        # Periksa seluruh isi video dan audio.
        run(
            [
                "ffmpeg",
                "-v", "error",
                "-xerror",
                "-nostdin",
                "-i", temporary.name,
                "-map", "0:v:0",
                "-map", "0:a:0",
                "-f", "null",
                "-",
            ],
            cwd=out,
        )

        temporary.replace(final)

        write_json(
            final.with_suffix(".render.json"),
            {
                "video_id": video_id,
                "fingerprint": fingerprint,
                "sha256": digest(final),
                "duration_sec": actual,
                "scene_count": len(scenes),
                "frame_count": total_frames,
                "sources": records,
            },
        )

        db.update_video(
            video_id,
            status="video_ready",
        )

        events.emit(
            "sari",
            "walk_to",
            "Video selesai, simpan ke Siap Upload.",
            target="outbox",
            video_id=video_id,
        )
        events.emit(
            "sari",
            "say",
            f"final.mp4 siap: {actual:.3f} detik.",
            video_id=video_id,
        )
        events.emit(
            "sari",
            "back",
            video_id=video_id,
        )

        print(
            f"SELESAI: {final}\n"
            f"Durasi: {actual:.3f} detik. "
            "Status: video_ready."
        )
        return final

    except (Exception, KeyboardInterrupt) as exc:
        status = (
            "clips_ready"
            if isinstance(exc, KeyboardInterrupt)
            else "assembly_failed"
        )
        db.update_video(video_id, status=status)

        events.emit(
            "sari",
            "say",
            "Penggabungan berhenti; klip sumber tetap tersimpan.",
            video_id=video_id,
        )
        raise

    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    db.init()

    try:
        assemble(args.id, args.check)
    except KeyboardInterrupt:
        parser.exit(
            130,
            "Dihentikan. Klip sumber tetap tersimpan.\n",
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