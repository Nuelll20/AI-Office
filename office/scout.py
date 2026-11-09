"""Adit - Scout: mencari ide, kirim ke Telegram."""
import random
import time

from . import db, events, llm, telegram
from .config import load_json

SYSTEM = (
    "Kamu Adit, Scout ide untuk channel YouTube Shorts berbahasa Indonesia. "
    "Tugasmu menghasilkan ide cerita singkat (satu kalimat, konkret, punya premis kuat "
    "dan potensi twist). Hindari ide yang mirip dengan daftar ide lama."
)

MOCK_IDEAS = [
    "Penjaga mercusuar menerima surat tiap malam dari orang yang sudah meninggal 50 tahun lalu",
    "Seorang kurir menemukan paket yang alamat tujuannya adalah rumahnya sendiri, tertanggal 20 tahun lagi",
    "Anak kecil selalu bicara dengan 'teman' di cermin, sampai ibunya sadar cermin itu tidak memantulkan kamar mereka",
    "Tukang tambal ban desa tahu kapan orang akan celaka, karena ban mereka selalu bocor lebih dulu",
    "Seorang dalang wayang menemukan satu tokoh baru di kotaknya yang tidak pernah ia buat",
    "Radio tua di warung kopi hanya menyiarkan berita besok pagi",
    "Penjual jam di pasar tidak pernah menjual jam yang menunjuk waktu sekarang",
    "Seorang nenek menjahit baju untuk cucu yang belum lahir, dan ukurannya selalu tepat",
    "Satpam gedung kosong mencatat satu pengunjung tiap malam padahal pintu terkunci",
    "Pemain gamelan menyadari ada satu bunyi yang bukan berasal dari alat mana pun",
]


def _mock(n, past):
    pool = [i for i in MOCK_IDEAS if i not in past]
    random.shuffle(pool)
    return pool[:n] or [f"Ide cadangan {i + 1}" for i in range(n)]


def latest_batch():
    last = db.one("SELECT batch FROM ideas ORDER BY id DESC LIMIT 1")
    if not last:
        return []
    return db.query("SELECT * FROM ideas WHERE batch=? ORDER BY id", (last["batch"],))


def run(n=6):
    pools = load_json("pools.json")
    past = [i["text"] for i in db.recent_ideas(40)]
    events.emit("adit", "work", "Riset ide cerita baru...")
    user = (f"Tema channel: {pools['theme']}.\n"
            f"Buat {n} ide baru. Ide lama (jangan diulang):\n- " + "\n- ".join(past[:30]) +
            '\n\nFormat: {"ideas": ["...", "..."]}')
    data = llm.ask_json(SYSTEM, user, mock=lambda: {"ideas": _mock(n, past)})
    ideas = [s.strip() for s in data["ideas"] if isinstance(s, str) and s.strip()][:n]

    batch = time.strftime("%Y%m%d-%H%M%S")
    for t in ideas:
        db.run("INSERT INTO ideas(batch,text,created_at) VALUES(?,?,?)", (batch, t, time.time()))

    msg = ("💡 Ide minggu ini dari Adit:\n\n" +
           "\n".join(f"{i}. {t}" for i, t in enumerate(ideas, 1)) +
           "\n\nBalas dengan nomor pilihan, contoh: 1 3 5")
    events.emit("adit", "walk_to", f"Kirim {len(ideas)} ide ke Bos lewat Telegram", target="telegram")
    if not telegram.send(msg):
        print("\n" + msg + "\n")
    events.emit("adit", "back")
    return ideas
