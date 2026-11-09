"""Buat narasi MP3 dan subtitle per adegan, dengan progres tersimpan."""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from . import db, events
from .config import OUTPUT_DIR, ROOT, env


def write_json(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, timeout):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            (result.stderr or result.stdout)[-2000:]
        )
    return result.stdout


def duration(path):
    info = json.loads(
        command(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries",
                "stream=codec_name:format=duration",
                "-of", "json",
                str(path),
            ],
            30,
        )
    )

    seconds = float(
        info.get("format", {}).get("duration", "nan")
    )

    if (
        not info.get("streams")
        or not math.isfinite(seconds)
        or seconds <= 0
    ):
        raise ValueError(
            f"Audio tidak memiliki durasi valid: {path.name}"
        )

    return seconds


def cached(path, fingerprint):
    try:
        meta = json.loads(
            path.with_suffix(".audio.json").read_text(
                encoding="utf-8"
            )
        )

        if (
            meta["fingerprint"] != fingerprint
            or meta["audio_sha256"] != digest(path)
            or meta["subtitle_sha256"]
            != digest(path.with_suffix(".srt"))
        ):
            return None

        return duration(path)

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ):
        return None


def synthesize(text, path, settings, executable, timeout):
    audio_temp = path.with_suffix(".part.mp3")
    sub_temp = path.with_suffix(".part.srt")

    try:
        command(
            [
                str(executable),
                "--voice", settings["voice"],
                "--rate=" + settings["rate"],
                "--text", text,
                "--write-media", str(audio_temp),
                "--write-subtitles", str(sub_temp),
            ],
            timeout,
        )

        seconds = duration(audio_temp)

        if "-->" not in sub_temp.read_text(encoding="utf-8"):
            raise ValueError(
                "Subtitle kosong atau tidak memiliki penanda waktu."
            )

        audio_temp.replace(path)
        sub_temp.replace(path.with_suffix(".srt"))
        return seconds

    finally:
        audio_temp.unlink(missing_ok=True)
        sub_temp.unlink(missing_ok=True)


def generate_audio(video_id, limit=None, check_only=False):
    if limit is not None and limit < 1:
        raise ValueError("Limit minimal 1.")

    if not db.get_video(video_id):
        raise ValueError(f"Video {video_id} tidak ditemukan.")

    if not shutil.which("ffprobe"):
        raise ValueError("FFprobe belum ditemukan di PATH.")

    executable = Path(sys.executable).parent / (
        "edge-tts.exe" if os.name == "nt" else "edge-tts"
    )

    if not check_only and not executable.is_file():
        raise ValueError(
            "Pasang edge-tts pada .venv proyek dahulu."
        )

    timeout = float(env("TTS_TIMEOUT", "180"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(
            "TTS_TIMEOUT harus berupa angka positif."
        )

    settings = {
        "provider": "edge-tts",
        "version": version("edge-tts"),
        "voice": env("TTS_VOICE", "id-ID-ArdiNeural"),
        "rate": env("TTS_RATE", "-5%"),
    }

    out = OUTPUT_DIR / video_id
    scene_file = out / "scenes.json"
    data = json.loads(
        scene_file.read_text(encoding="utf-8")
    )
    scenes = data.get("scenes")

    if (
        data.get("video_id") != video_id
        or not isinstance(scenes, list)
        or not scenes
    ):
        raise ValueError(
            "scenes.json tidak cocok "
            "atau daftar adegannya kosong."
        )

    records, seen = [], set()

    for scene in scenes:
        sid = scene.get("id")
        text = scene.get("narration")

        if type(sid) is not int or sid < 1 or sid in seen:
            raise ValueError(
                "ID scene harus bilangan positif dan unik."
            )

        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"Narasi scene {sid} kosong atau tidak valid."
            )

        seen.add(sid)

        fingerprint = hashlib.sha256(
            json.dumps(
                {**settings, "text": text},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        path = out / "audio" / f"scene-{sid:03d}.mp3"

        records.append(
            (
                scene,
                path,
                fingerprint,
                cached(path, fingerprint),
            )
        )

    ready = sum(
        seconds is not None
        for _, _, _, seconds in records
    )

    print(
        f"Audio cocok dan tersedia: {ready}/{len(scenes)}"
    )

    if check_only:
        for scene, _, _, seconds in records:
            label = (
                f"SIAP ({seconds:.3f} detik)"
                if seconds is not None
                else "PERLU DIBUAT"
            )
            print(f"Scene {scene['id']:03d}: {label}")
        return ready

    (out / "audio").mkdir(exist_ok=True)

    def mark_ready(scene, path, seconds):
        scene.update(
            audio_status="ready",
            audio_duration_sec=seconds,
            audio_path=path.relative_to(ROOT).as_posix(),
            subtitle_path=(
                path.with_suffix(".srt")
                .relative_to(ROOT)
                .as_posix()
            ),
        )
        scene.pop("audio_error", None)

    for scene, path, _, seconds in records:
        if seconds is not None:
            mark_ready(scene, path, seconds)
        else:
            scene["audio_status"] = "pending"
            for key in (
                "audio_path",
                "subtitle_path",
                "audio_duration_sec",
                "audio_error",
            ):
                scene.pop(key, None)

    def save(status):
        if all(
            s.get("audio_status") == "ready"
            for s in scenes
        ):
            data["audio_total_duration_sec"] = round(
                sum(s["audio_duration_sec"] for s in scenes),
                6,
            )
        else:
            data.pop("audio_total_duration_sec", None)

        write_json(scene_file, data)
        db.update_video(
            video_id,
            scenes=data,
            status=status,
        )

    save(
        "audio_ready"
        if ready == len(scenes)
        else "audio_processing"
    )

    made = 0

    for scene, path, fingerprint, seconds in records:
        sid = scene["id"]

        if seconds is not None:
            print(
                f"LEWATI scene {sid:03d}: audio masih cocok."
            )
            continue

        if limit is not None and made >= limit:
            break

        try:
            events.emit(
                "sari",
                "work",
                f"Membuat suara scene {sid}...",
                video_id=video_id,
            )

            seconds = synthesize(
                scene["narration"],
                path,
                settings,
                executable,
                timeout,
            )

            write_json(
                path.with_suffix(".audio.json"),
                {
                    "fingerprint": fingerprint,
                    "audio_sha256": digest(path),
                    "subtitle_sha256": digest(
                        path.with_suffix(".srt")
                    ),
                    "duration_sec": seconds,
                    "settings": settings,
                },
            )

            mark_ready(scene, path, seconds)

            made += 1
            ready += 1

            save("audio_processing")

            print(
                f"SELESAI scene {sid:03d}: "
                f"{seconds:.3f} detik."
            )

        except (Exception, KeyboardInterrupt) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)

            scene["audio_status"] = (
                "pending" if interrupted else "failed"
            )
            scene["audio_error"] = (
                str(exc) or "Dihentikan pengguna."
            )

            save(
                "audio_partial"
                if interrupted
                else "audio_failed"
            )

            events.emit(
                "sari",
                "say",
                f"Proses suara berhenti pada scene {sid}.",
                video_id=video_id,
            )
            raise

    status = (
        "audio_ready"
        if ready == len(scenes)
        else "audio_partial"
    )
    save(status)

    events.emit(
        "sari",
        "say",
        f"Audio siap {ready}/{len(scenes)}.",
        video_id=video_id,
    )

    print(
        f"Status: {status}. "
        f"Audio baru: {made}. "
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
        generate_audio(args.id, args.limit, args.check)
    except KeyboardInterrupt:
        parser.exit(
            130,
            "Dihentikan. Audio yang sudah selesai "
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