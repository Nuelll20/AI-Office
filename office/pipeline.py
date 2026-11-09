"""Alur produksi satu video. Tiap langkah = 1 node; gampang dipindah ke LangGraph nanti.
Setiap langkah menyimpan hasil ke DB, jadi kalau gagal di tengah, jalankan lagi dan
langkah yang sudah selesai dilewati."""
import json
import time

from . import creative_director, db, events, llm, telegram, visual_director, writer
from .config import OUTPUT_DIR, env


def _pause():
    d = env("STEP_DELAY")
    delay = float(d) if d else (2.0 if llm.is_mock() else 0.0)
    if delay:
        time.sleep(delay)


def _dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def produce(vid):
    v = db.get_video(vid)
    if not v:
        raise ValueError(f"Video {vid} tidak ada")
    try:
        _run(v)
    except Exception as e:
        db.update_video(vid, status="failed")
        events.emit("system", "say", f"Gagal di video {vid}: {e}", video_id=vid)
        raise


def _run(v):
    vid, idea = v["id"], v["idea"]
    out = OUTPUT_DIR / vid
    out.mkdir(parents=True, exist_ok=True)

    # 1) Adit -> Agus : style pack
    pack = v["style_pack"]
    if not pack:
        events.emit("adit", "walk_to", "Bos sudah pilih ide ini. Ini dokumennya, Gus.", target="agus", video_id=vid)
        _pause()
        events.emit("agus", "work", "Memilih paket gaya dan mengecek 6 video terakhir...", video_id=vid)
        pack = creative_director.make_style_pack(idea)
        db.update_video(vid, style_pack=pack, status="style_ready")
        d = pack["diff_vs_history"]
        events.emit("agus", "say",
                    f"Gaya terkunci: {pack['genre']['id']} / {pack['visual_style']['id']} / "
                    f"{pack['palette']['id']} ({d['min_elements_different']} elemen beda)", video_id=vid)
        events.emit("adit", "back", video_id=vid)
        _pause()
    _dump(out / "style_pack.json", pack)

    # 2) Agus -> Rina : naskah
    script = v["script"]
    if not script:
        events.emit("agus", "walk_to", "Style pack sudah dikunci, silakan menulis.", target="rina", video_id=vid)
        _pause()
        events.emit("rina", "work", "Menulis naskah dan narasi...", video_id=vid)
        script = writer.write_script(idea, pack)
        db.update_video(vid, script=script, status="script_ready")
        events.emit("rina", "say", f"Naskah selesai: \"{script['title']}\"", video_id=vid)
        events.emit("agus", "back", video_id=vid)
        _pause()
    _dump(out / "script.json", script)

    # 3) Rina -> Bayu : scene
    scenes = v["scenes"]
    if not scenes:
        events.emit("rina", "walk_to", f"Naskah {len(script['scenes'])} scene sudah siap.", target="bayu", video_id=vid)
        _pause()
        events.emit("bayu", "work", "Menyusun prompt gambar dan gerak kamera...", video_id=vid)
        scenes = visual_director.build_scenes(vid, pack, script)
        db.update_video(vid, scenes=scenes, status="scenes_ready")
        events.emit("bayu", "say", f"{len(scenes['scenes'])} scene siap dirender", video_id=vid)
        events.emit("rina", "back", video_id=vid)
        _pause()
    _dump(out / "scenes.json", scenes)

    # 4) Bayu -> Sari -> Telegram (render nyata = Fase 2)
    events.emit("bayu", "walk_to", "Scene sudah jadi, tinggal dirender ya.", target="sari", video_id=vid)
    _pause()
    events.emit("sari", "say", "Antrean render masuk (render gambar/suara = Fase 2).", video_id=vid)

    info = (f"{script['title']}\n\n{script['description']}\n\n{' '.join(script['hashtags'])}\n")
    (out / "upload_info.txt").write_text(info, encoding="utf-8")

    events.emit("sari", "walk_to", "Kabari Bos lewat Telegram.", target="telegram", video_id=vid)
    telegram.send(f"✅ {vid} naskah & scene siap\n\nJudul: {script['title']}\n"
                  f"Durasi: {pack['duration_sec']} dtk, {len(scenes['scenes'])} scene\n"
                  f"Gaya: {pack['genre']['id']} / {pack['visual_style']['id']}\n"
                  f"Folder: output/{vid}/")
    _pause()
    events.emit("sari", "back", video_id=vid)
    events.emit("bayu", "back", video_id=vid)
    print(f"\nSelesai: output/{vid}/")


def produce_next():
    row = db.one("SELECT id FROM videos WHERE status='queued' ORDER BY created_at, id LIMIT 1")
    if not row:
        print("Tidak ada video di antrean.")
        return None
    produce(row["id"])
    return row["id"]
