"""Rina - Writer: menulis naskah narasi per scene."""
from . import llm

SYSTEM = (
    "Kamu Rina, penulis naskah YouTube Shorts berbahasa Indonesia. "
    "Tulis narasi singkat, kuat di 3 detik pertama (hook), kalimat pendek yang enak dibacakan, "
    "dan ending yang memuaskan. Jangan memakai kata kasar atau konten yang melanggar kebijakan YouTube."
)


def _mock(idea, n):
    base = [
        idea + ".",
        "Awalnya semua tampak biasa saja.",
        "Lalu ada satu hal yang janggal.",
        "Ia mulai mencari tahu.",
        "Semakin dalam, semakin aneh.",
        "Sampai ia menemukan satu petunjuk.",
        "Dan kebenarannya mengubah segalanya.",
        "Ternyata jawabannya selalu ada di dekatnya.",
    ]
    lines = [base[i % len(base)] for i in range(n - 1)] + [base[-1]]
    return {
        "title": "Misteri yang Tidak Pernah Selesai",
        "scenes": [{"id": i + 1, "narration": t} for i, t in enumerate(lines)],
        "description": idea + ". Tonton sampai akhir untuk twist-nya!",
        "hashtags": ["#shorts", "#misteri", "#ceritaindonesia", "#twist"],
    }


def write_script(idea, pack):
    dur = pack["duration_sec"]
    n = max(4, round(dur / 5))
    max_words = int((dur / n) * 2.4)
    user = (
        f"Ide: {idea}\n"
        f"Genre: {pack['genre']['desc']}\n"
        f"Struktur: {pack['structure']['desc']}\n"
        f"Gaya narator: {pack['narrator']['emotion']}\n"
        f"Durasi total: {dur} detik, dibagi {n} scene (maksimal {max_words} kata per scene).\n\n"
        'Format: {"title": "...", "scenes": [{"id": 1, "narration": "..."}], '
        '"description": "...", "hashtags": ["#shorts", "..."]}\n'
        f"Jumlah scene harus tepat {n}. Judul maksimal 70 karakter."
    )
    data = llm.ask_json(SYSTEM, user, mock=lambda: _mock(idea, n))
    data["scenes"] = [{"id": i + 1, "narration": s["narration"]} for i, s in enumerate(data["scenes"])]
    return data
