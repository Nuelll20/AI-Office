"""Bayu - Visual Director: mengubah naskah jadi daftar scene (prompt gambar + gerak kamera).
Gaya (style_block) ditempel oleh KODE, bukan LLM, supaya semua gambar seragam."""
from . import llm

MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "parallax", "shake"]
SPEEDS = ["slow", "medium", "fast"]
TRANSITIONS = ["fade", "cut", "dissolve", "hard_cut_to_black", "whip"]

SYSTEM = (
    "Kamu Bayu, Visual Director untuk video pendek bergaya gambar yang dianimasikan. "
    "Tulis prompt gambar dalam bahasa Inggris untuk tiap scene: konkret, satu subjek utama, "
    "variasikan ukuran shot (wide, medium, close-up). JANGAN menulis gaya seni atau warna "
    "(sudah ditambahkan otomatis). JANGAN minta teks/huruf di dalam gambar. Komposisi vertikal 9:16."
)


def _mock(script):
    out = []
    for i, s in enumerate(script["scenes"]):
        out.append({
            "id": s["id"],
            "image_prompt": f"scene {s['id']}: cinematic illustration of: {s['narration']}",
            "has_character": i % 2 == 0,
            "motion": MOTIONS[i % len(MOTIONS)],
            "speed": SPEEDS[i % 3],
            "transition": TRANSITIONS[i % len(TRANSITIONS)],
            "sfx": "ambient_wind",
        })
    return {"character_sheet": "an elderly man with gray beard and a worn raincoat", "scenes": out}


def build_scenes(video_id, pack, script):
    scenes_in = script["scenes"]
    user = (
        f"Gaya visual: {pack['visual_style']['id']}; palet: {pack['palette']['id']}; ritme: {pack['pacing']}.\n"
        f"Opsi motion: {MOTIONS}\nOpsi speed: {SPEEDS}\nOpsi transition: {TRANSITIONS}\n\n"
        "Naskah per scene:\n" +
        "\n".join(f"{s['id']}. {s['narration']}" for s in scenes_in) +
        '\n\nBuat juga "character_sheet": deskripsi tetap tokoh utama dalam bahasa Inggris '
        '(kosongkan jika tidak ada tokoh).\n'
        'Format: {"character_sheet": "...", "scenes": [{"id": 1, "image_prompt": "...", '
        '"has_character": true, "motion": "zoom_in", "speed": "slow", "transition": "fade", "sfx": "storm_wind"}]}'
    )
    data = llm.ask_json(SYSTEM, user, mock=lambda: _mock(script))
    by_id = {s["id"]: s for s in data["scenes"]}

    style_block = ", ".join([
        pack["visual_style"]["style_block"],
        pack["palette"]["prompt"] + " color palette",
        "vertical 9:16 composition",
        "no text, no letters",
    ])
    sheet = (data.get("character_sheet") or "").strip()
    total = pack["duration_sec"]
    n = len(scenes_in)
    per = round(total / n, 1)

    scenes = []
    for i, s in enumerate(scenes_in):
        v = by_id.get(s["id"], {})
        prompt = v.get("image_prompt", s["narration"])
        if sheet and v.get("has_character"):
            prompt = f"{prompt}. Main character: {sheet}"
        motion = v.get("motion") if v.get("motion") in MOTIONS else "zoom_in"
        speed = v.get("speed") if v.get("speed") in SPEEDS else "slow"
        trans = v.get("transition") if v.get("transition") in TRANSITIONS else "fade"
        scenes.append({
            "id": s["id"],
            "duration_sec": per if i < n - 1 else round(total - per * (n - 1), 1),
            "narration": s["narration"],
            "image_prompt": prompt,
            "final_prompt": f"{prompt}, {style_block}",
            "motion": {"type": motion, "speed": speed},
            "transition": trans,
            "sfx": v.get("sfx", ""),
            "render": "image",
            "status": "pending",
        })
    return {"video_id": video_id, "aspect": "9:16", "style_block": style_block,
            "character_sheet": sheet, "scenes": scenes}
