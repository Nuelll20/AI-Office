"""Alur produksi lengkap: ide -> naskah -> gambar -> suara -> final.mp4."""
import json
import time

from . import (
    assemble,
    audio,
    creative_director,
    db,
    events,
    images,
    llm,
    render,
    telegram,
    visual_director,
    writer,
)
from .config import OUTPUT_DIR, env


def _pause():
    configured = env("STEP_DELAY")
    seconds = (
        float(configured)
        if configured
        else (2.0 if llm.is_mock() else 0.0)
    )
    if seconds > 0:
        time.sleep(seconds)


def _dump(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _prepare(video):
    vid, idea = video["id"], video["idea"]
    out = OUTPUT_DIR / vid
    out.mkdir(parents=True, exist_ok=True)

    pack = video["style_pack"]

    if not pack:
        events.emit(
            "adit",
            "walk_to",
            "Ide siap diproduksi.",
            target="agus",
            video_id=vid,
        )
        _pause()

        events.emit(
            "agus",
            "work",
            "Menentukan paket gaya...",
            video_id=vid,
        )
        pack = creative_director.make_style_pack(idea)

        db.update_video(
            vid,
            style_pack=pack,
            status="style_ready",
        )
        events.emit(
            "agus",
            "say",
            "Paket gaya sudah tersimpan.",
            video_id=vid,
        )
        events.emit("adit", "back", video_id=vid)

    _dump(out / "style_pack.json", pack)

    script = video["script"]

    if not script:
        events.emit(
            "agus",
            "walk_to",
            "Silakan menulis naskah.",
            target="rina",
            video_id=vid,
        )
        _pause()

        events.emit(
            "rina",
            "work",
            "Menulis narasi per adegan...",
            video_id=vid,
        )
        script = writer.write_script(idea, pack)

        db.update_video(
            vid,
            script=script,
            status="script_ready",
        )
        events.emit(
            "rina",
            "say",
            f"Naskah selesai: {script['title']}",
            video_id=vid,
        )
        events.emit("agus", "back", video_id=vid)

    _dump(out / "script.json", script)

    # Berkas ini memuat progres media terbaru.
    scene_file = out / "scenes.json"

    if scene_file.exists():
        scenes = json.loads(
            scene_file.read_text(encoding="utf-8")
        )
    else:
        scenes = video["scenes"]

        if not scenes:
            events.emit(
                "rina",
                "walk_to",
                "Naskah siap divisualisasikan.",
                target="bayu",
                video_id=vid,
            )
            _pause()

            events.emit(
                "bayu",
                "work",
                "Menyusun prompt dan gerakan kamera...",
                video_id=vid,
            )
            scenes = visual_director.build_scenes(
                vid,
                pack,
                script,
            )

            db.update_video(
                vid,
                scenes=scenes,
                status="scenes_ready",
            )
            events.emit(
                "bayu",
                "say",
                "Rencana adegan sudah tersimpan.",
                video_id=vid,
            )
            events.emit("rina", "back", video_id=vid)

    if (
        not isinstance(scenes, dict)
        or scenes.get("video_id") != vid
        or not isinstance(scenes.get("scenes"), list)
        or not scenes["scenes"]
    ):
        raise ValueError(
            "scenes.json tidak valid atau video_id tidak cocok."
        )

    _dump(scene_file, scenes)
    db.update_video(vid, scenes=scenes)

    info = (
        f"{script['title']}\n\n"
        f"{script['description']}\n\n"
        f"{' '.join(script['hashtags'])}\n"
    )
    (out / "upload_info.txt").write_text(
        info,
        encoding="utf-8",
    )

    return script


def _notify_ready(vid, title, final):
    if not telegram.configured():
        return

    try:
        manifest = json.loads(
            final.with_suffix(".render.json").read_text(
                encoding="utf-8"
            )
        )

        marker = final.parent / "telegram_notification.json"

        try:
            previous = json.loads(
                marker.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            previous = {}

        if previous.get("sha256") == manifest["sha256"]:
            return

        message = (
            f"✅ {vid} video selesai\n\n"
            f"Judul: {title}\n"
            f"Durasi: {manifest['duration_sec']:.3f} detik\n"
            f"Adegan: {manifest['scene_count']}\n"
            f"Folder: output/{vid}/final.mp4"
        )

        if telegram.send(message):
            _dump(
                marker,
                {
                    "sha256": manifest["sha256"],
                    "sent_at": time.time(),
                },
            )
        else:
            print(
                "Video siap, tetapi notifikasi Telegram "
                "belum terkirim."
            )

    except Exception as exc:
        print(
            f"Video siap; notifikasi Telegram bermasalah: {exc}"
        )


def _run(video):
    vid = video["id"]

    print(f"\nPRODUKSI: {vid}")
    script = _prepare(video)

    print("\n[1/4] Gambar per adegan")
    images.generate_images(vid)

    events.emit(
        "bayu",
        "walk_to",
        "Gambar siap. Lanjut suara dan penyuntingan.",
        target="sari",
        video_id=vid,
    )
    _pause()
    events.emit("bayu", "back", video_id=vid)

    print("\n[2/4] Narasi dan subtitle")
    audio.generate_audio(vid)

    print("\n[3/4] Render klip")
    render.render_clips(vid)

    print("\n[4/4] Penggabungan video")
    final = assemble.assemble(vid)

    _notify_ready(vid, script["title"], final)

    print(f"\nPRODUKSI SELESAI: {final}")
    return final


def _report_stop(vid, message):
    events.emit(
        "system",
        "say",
        message,
        video_id=vid,
    )

    for actor in ("adit", "agus", "rina", "bayu", "sari"):
        events.emit(actor, "back", video_id=vid)


def produce(vid):
    video = db.get_video(vid)

    if not video:
        raise ValueError(f"Video {vid} tidak ada.")

    try:
        return _run(video)

    except KeyboardInterrupt:
        db.update_video(vid, status="paused")
        _report_stop(
            vid,
            "Produksi dihentikan. "
            "Hasil selesai tetap tersimpan.",
        )
        raise

    except Exception as exc:
        current = db.get_video(vid)

        if current["status"] not in {
            "images_failed",
            "audio_failed",
            "clips_failed",
            "assembly_failed",
        }:
            db.update_video(vid, status="failed")

        _report_stop(
            vid,
            f"Produksi {vid} berhenti: {exc}",
        )
        raise


def produce_next():
    row = db.one(
        "SELECT id FROM videos "
        "WHERE status='queued' "
        "ORDER BY created_at, id LIMIT 1"
    )

    if not row:
        print("Tidak ada video di antrean.")
        return None

    produce(row["id"])
    return row["id"]