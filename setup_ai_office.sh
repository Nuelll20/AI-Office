#!/usr/bin/env bash
# Setup Kantor AI - Fase 1
# Jalankan:  bash setup_ai_office.sh
set -e

PROJECT="${1:-ai-office}"
mkdir -p "$PROJECT"/{office,config,ui,data,output}
cd "$PROJECT"

# ---------------------------------------------------------------- basic files
cat > requirements.txt <<'EOF'
# Hanya dibutuhkan untuk mode asli (LLM). Mode mock jalan tanpa install apa pun.
anthropic>=0.40.0
EOF

cat > .env.example <<'EOF'
# Salin jadi .env lalu isi:  cp .env.example .env

# LLM: kosongkan API key = mode mock (tanpa biaya, buat uji alur & tampilan)
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-5-5
# auto | mock | real
LLM_MODE=auto

# Telegram (opsional di Fase 1; kalau kosong, ide hanya dicetak di terminal)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Jeda antar langkah (detik) supaya animasi kantor terlihat. Kosong = otomatis
STEP_DELAY=
EOF

cat > .gitignore <<'EOF'
.env
.venv/
data/
output/
__pycache__/
*.pyc
EOF

# ---------------------------------------------------------------- config
cat > config/agents.json <<'EOF'
{
  "agents": [
    {"id": "adit", "name": "Adit", "role": "Scout",             "emoji": "🕵️", "color": "#3b82f6", "desk": {"x": 12, "y": 22}},
    {"id": "agus", "name": "Agus", "role": "Creative Director", "emoji": "🎨", "color": "#a855f7", "desk": {"x": 37, "y": 22}},
    {"id": "rina", "name": "Rina", "role": "Writer",            "emoji": "✍️", "color": "#ec4899", "desk": {"x": 62, "y": 22}},
    {"id": "bayu", "name": "Bayu", "role": "Visual Director",   "emoji": "🎬", "color": "#f59e0b", "desk": {"x": 87, "y": 22}},
    {"id": "sari", "name": "Sari", "role": "Editor & QC",       "emoji": "🎞️", "color": "#10b981", "desk": {"x": 62, "y": 62}}
  ],
  "places": [
    {"id": "telegram", "name": "Telegram (HP Bos)", "emoji": "📱", "x": 20, "y": 70},
    {"id": "outbox",   "name": "Siap Upload",       "emoji": "📤", "x": 88, "y": 72}
  ]
}
EOF

cat > config/pools.json <<'EOF'
{
  "theme": "cerita misteri dan twist ending yang cocok untuk Shorts",
  "min_elements_different": 3,
  "history_size": 6,
  "duration_range": [25, 55],

  "genres": [
    {"id": "misteri_twist",  "desc": "misteri dengan twist ending"},
    {"id": "horor_ringan",   "desc": "horor ringan yang menggantung, tanpa gore"},
    {"id": "bagaimana_jika", "desc": "skenario 'bagaimana jika' yang mengubah sudut pandang"},
    {"id": "kisah_moral",    "desc": "kisah singkat dengan pesan moral yang menyentuh"},
    {"id": "dongeng_gelap",  "desc": "dongeng klasik dengan sisi gelap"},
    {"id": "komedi_ironi",   "desc": "komedi ironi dengan punchline di akhir"}
  ],

  "structures": [
    {"id": "cold_open",       "desc": "mulai dari momen paling mengejutkan, lalu mundur ke awal"},
    {"id": "countdown",       "desc": "dihitung mundur, tiap bagian makin tegang"},
    {"id": "tanya_jawab",     "desc": "mulai dengan satu pertanyaan, jawabannya di akhir"},
    {"id": "cerita_terbalik", "desc": "diceritakan dari akhir ke awal"},
    {"id": "tiga_babak",      "desc": "pengantar, eskalasi, kejutan"},
    {"id": "lewat_catatan",   "desc": "diceritakan lewat surat, catatan, atau rekaman"}
  ],

  "visual_styles": [
    {"id": "cat_air", "style_block": "watercolor illustration, soft paper grain, bleeding edges"},
    {"id": "anime",   "style_block": "anime style illustration, cel shading, cinematic lighting"},
    {"id": "3d_lembut", "style_block": "soft 3D render, clay-like materials, gentle studio lighting"},
    {"id": "komik",   "style_block": "graphic novel ink illustration, bold linework, halftone shading"},
    {"id": "siluet",  "style_block": "silhouette art, strong contrast, minimal detail, backlit"},
    {"id": "retro",   "style_block": "retro 1970s poster illustration, grainy print texture"}
  ],

  "palettes": [
    {"id": "biru_emas",    "colors": ["#0B1D3A", "#1F4E79", "#E8C547", "#F2EBD9"], "prompt": "deep navy blue and muted gold"},
    {"id": "merah_arang",  "colors": ["#1A1A1A", "#4A4A4A", "#B22222", "#EDE0D4"], "prompt": "charcoal black and blood red"},
    {"id": "hijau_kabut",  "colors": ["#14281D", "#2F5D50", "#A3B18A", "#DAD7CD"], "prompt": "misty forest green and pale sage"},
    {"id": "ungu_senja",   "colors": ["#2B1B4B", "#6A4C93", "#F28482", "#F6BD60"], "prompt": "twilight purple and warm coral"},
    {"id": "sepia_tua",    "colors": ["#3E2C1C", "#7F5539", "#B08968", "#EDE0D4"], "prompt": "aged sepia and warm brown"},
    {"id": "monokrom_merah","colors": ["#000000", "#555555", "#EEEEEE", "#E63946"], "prompt": "black and white with a single red accent"},
    {"id": "tosca_peach",  "colors": ["#1B4D4F", "#3AAFA9", "#FFB997", "#FFF4EC"], "prompt": "teal and soft peach"},
    {"id": "kuning_hitam", "colors": ["#101010", "#2A2A2A", "#F4D35E", "#FAF0CA"], "prompt": "pale yellow against deep black"}
  ],

  "narrators": [
    {"id": "id_male_deep_01",     "label": "Pria berat",     "speed": 0.95, "emotion": "tenang_misterius"},
    {"id": "id_female_soft_01",   "label": "Wanita lembut",  "speed": 1.0,  "emotion": "hangat"},
    {"id": "id_male_warm_02",     "label": "Pria hangat",    "speed": 1.0,  "emotion": "bercerita"},
    {"id": "id_female_calm_02",   "label": "Wanita tenang",  "speed": 0.95, "emotion": "dingin_datar"},
    {"id": "id_male_young_01",    "label": "Pria muda",      "speed": 1.08, "emotion": "antusias"},
    {"id": "id_female_dramatic_01","label": "Wanita dramatis","speed": 1.0,  "emotion": "dramatis"}
  ],

  "music": [
    {"id": "ambient_sedih",   "bpm": 70},
    {"id": "piano_tegang",    "bpm": 90},
    {"id": "drone_gelap",     "bpm": 60},
    {"id": "gamelan_misteri", "bpm": 80},
    {"id": "lofi_hangat",     "bpm": 85},
    {"id": "string_dramatis", "bpm": 100}
  ],

  "subtitles": [
    {"id": "lora_kata",   "font": "Lora Bold",       "position": "bawah_tengah", "animation": "kata_per_kata"},
    {"id": "bebas_pop",   "font": "Bebas Neue",      "position": "tengah",       "animation": "pop_in"},
    {"id": "mono_ketik",  "font": "Space Mono",      "position": "bawah_tengah", "animation": "mesin_ketik"},
    {"id": "poppins_fade","font": "Poppins SemiBold","position": "bawah_kiri",   "animation": "fade_baris"},
    {"id": "serif_besar", "font": "Playfair Display","position": "atas_tengah",  "animation": "kata_per_kata"}
  ],

  "pacing": ["tenang", "sedang", "cepat"],

  "brand": {"logo": "pojok_kecil", "intro": "sting_1_detik", "mascot": null}
}
EOF

# ---------------------------------------------------------------- package
cat > office/__init__.py <<'EOF'
EOF

cat > office/config.py <<'EOF'
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
UI_DIR = ROOT / "ui"
DB_PATH = DATA_DIR / "office.db"

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def _load_dotenv():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(key, default=""):
    return os.environ.get(key, "") or default


def load_json(name):
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))
EOF

cat > office/db.py <<'EOF'
import datetime
import json
import sqlite3
import time

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS ideas(
  id INTEGER PRIMARY KEY AUTOINCREMENT, batch TEXT, text TEXT,
  status TEXT DEFAULT 'proposed', created_at REAL);
CREATE TABLE IF NOT EXISTS videos(
  id TEXT PRIMARY KEY, idea TEXT, status TEXT DEFAULT 'queued',
  style_pack TEXT, script TEXT, scenes TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor TEXT, target TEXT,
  action TEXT, text TEXT, video_id TEXT);
"""

JSON_FIELDS = ("style_pack", "script", "scenes")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = _conn()
    c.executescript(SCHEMA)
    c.commit()
    c.close()


def run(sql, args=()):
    c = _conn()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def query(sql, args=()):
    c = _conn()
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


# ---- videos
def add_video(idea):
    y, w, _ = datetime.date.today().isocalendar()
    prefix = f"{y}-w{w:02d}-"
    n = len(query("SELECT id FROM videos WHERE id LIKE ?", (prefix + "%",))) + 1
    vid = f"{prefix}{n:02d}"
    now = time.time()
    run("INSERT INTO videos(id,idea,status,created_at,updated_at) VALUES(?,?,?,?,?)",
        (vid, idea, "queued", now, now))
    return vid


def get_video(vid):
    v = one("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        return None
    for k in JSON_FIELDS:
        if v[k]:
            v[k] = json.loads(v[k])
    return v


def update_video(vid, **fields):
    allowed = {"status", "idea", *JSON_FIELDS}
    sets, args = [], []
    for k, val in fields.items():
        if k not in allowed:
            raise ValueError(k)
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        sets.append(f"{k}=?")
        args.append(val)
    sets.append("updated_at=?")
    args += [time.time(), vid]
    run(f"UPDATE videos SET {', '.join(sets)} WHERE id=?", args)


def recent_style_packs(n):
    rows = query("SELECT style_pack FROM videos WHERE style_pack IS NOT NULL "
                 "ORDER BY created_at DESC, id DESC LIMIT ?", (n,))
    return [json.loads(r["style_pack"]) for r in rows]


def recent_ideas(n):
    return query("SELECT text FROM ideas ORDER BY id DESC LIMIT ?", (n,))
EOF

cat > office/events.py <<'EOF'
from . import db


def emit(actor, action, text="", target=None, video_id=None):
    """action: walk_to | back | work | say
    UI kantor membaca tabel ini dan menganimasikannya."""
    import time
    db.run("INSERT INTO events(ts,actor,target,action,text,video_id) VALUES(?,?,?,?,?,?)",
           (time.time(), actor, target, action, text, video_id))
    arrow = f" -> {target}" if target else ""
    print(f"[{actor}{arrow}] {action}: {text}")
EOF

cat > office/llm.py <<'EOF'
import json
import re

from .config import env

_announced = False


def is_mock():
    mode = env("LLM_MODE", "auto")
    if mode == "mock":
        return True
    if mode == "real":
        return False
    return not env("ANTHROPIC_API_KEY")


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("Tidak ada JSON di respons model")
    s = min(starts)
    e = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[s:e + 1])


def ask_json(system, user, mock, max_tokens=3000):
    """Panggil LLM dan kembalikan JSON. mock = fungsi pengganti saat mode mock."""
    global _announced
    if is_mock():
        if not _announced:
            print("MODE MOCK: LLM tidak dipanggil (isi ANTHROPIC_API_KEY di .env untuk mode asli)")
            _announced = True
        return mock()

    import anthropic
    client = anthropic.Anthropic()
    sys_prompt = system + "\n\nBalas HANYA dengan JSON valid tanpa teks lain."
    last_err = None
    for _ in range(2):
        msg = client.messages.create(
            model=env("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            max_tokens=max_tokens,
            system=sys_prompt,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        try:
            return _extract_json(text)
        except Exception as e:  # coba sekali lagi
            last_err = e
    raise RuntimeError(f"Gagal parse JSON dari model: {last_err}")
EOF

cat > office/telegram.py <<'EOF'
import json
import time
import urllib.request

from .config import DATA_DIR, env

OFFSET_FILE = DATA_DIR / "tg_offset.txt"


def configured():
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def _call(method, payload, timeout=30):
    url = f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def send(text):
    """Kirim pesan ke Telegram. Return True kalau sukses (tidak pernah raise)."""
    if not configured():
        return False
    try:
        _call("sendMessage", {"chat_id": env("TELEGRAM_CHAT_ID"), "text": text})
        return True
    except Exception as e:
        print(f"(Telegram gagal: {e})")
        return False


def _offset():
    try:
        return int(OFFSET_FILE.read_text())
    except Exception:
        return 0


def wait_reply(timeout_sec=600):
    """Tunggu 1 pesan teks dari chat bos. Return teks atau None."""
    end = time.time() + timeout_sec
    chat = str(env("TELEGRAM_CHAT_ID"))
    while time.time() < end:
        try:
            wait = int(max(1, min(20, end - time.time())))
            res = _call("getUpdates", {"offset": _offset(), "timeout": wait}, timeout=wait + 10)
        except Exception as e:
            print(f"(getUpdates gagal: {e})")
            time.sleep(3)
            continue
        for u in res.get("result", []):
            OFFSET_FILE.write_text(str(u["update_id"] + 1))
            m = u.get("message") or {}
            if str(m.get("chat", {}).get("id")) == chat and m.get("text"):
                return m["text"]
    return None
EOF

# ---------------------------------------------------------------- agents
cat > office/scout.py <<'EOF'
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
EOF

cat > office/creative_director.py <<'EOF'
"""Agus - Creative Director: memilih style pack yang dikunci per video.
Murni kode + random (bukan LLM) supaya aturan anti-monoton pasti ditegakkan."""
import copy
import random

from . import db
from .config import load_json

KEYS = ["genre", "structure", "visual_style", "palette", "narrator", "music"]


def _signature(pack):
    return {k: pack[k]["id"] for k in KEYS}


def _diff(a, b):
    sa, sb = a["signature"], b.get("signature", {})
    return sum(1 for k in KEYS if sa[k] != sb.get(k))


def _random_pack(pools, rng):
    pack = {
        "genre": rng.choice(pools["genres"]),
        "structure": rng.choice(pools["structures"]),
        "visual_style": rng.choice(pools["visual_styles"]),
        "palette": rng.choice(pools["palettes"]),
        "narrator": rng.choice(pools["narrators"]),
        "music": rng.choice(pools["music"]),
        "subtitle": rng.choice(pools["subtitles"]),
        "pacing": rng.choice(pools["pacing"]),
        "duration_sec": rng.randrange(pools["duration_range"][0], pools["duration_range"][1] + 1, 5),
        "brand": pools["brand"],
    }
    pack = copy.deepcopy(pack)
    pack["signature"] = _signature(pack)
    return pack


def make_style_pack(idea, rng=random):
    pools = load_json("pools.json")
    history = db.recent_style_packs(pools["history_size"])
    need = pools["min_elements_different"]

    best = None
    for _ in range(500):
        cand = _random_pack(pools, rng)
        worst = min((_diff(cand, h) for h in history), default=len(KEYS))
        if best is None or worst > best[0]:
            best = (worst, cand)
        if worst >= need:
            break
    worst, pack = best
    pack.update({
        "idea": idea,
        "locked": True,
        "diff_vs_history": {
            "checked_last": len(history),
            "min_elements_different": worst,
            "passed": worst >= need,
        },
    })
    return pack
EOF

cat > office/writer.py <<'EOF'
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
EOF

cat > office/visual_director.py <<'EOF'
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
EOF

cat > office/pipeline.py <<'EOF'
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
EOF

cat > office/server.py <<'EOF'
"""Server tampilan kantor (tanpa dependency). Buka http://localhost:8000"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import db
from .config import CONFIG_DIR, UI_DIR


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            self._send((UI_DIR / "index.html").read_bytes(), "text/html")
        elif u.path == "/api/agents":
            self._send((CONFIG_DIR / "agents.json").read_bytes())
        elif u.path == "/api/events":
            if "recent" in qs:
                n = int(qs["recent"][0])
                rows = db.query("SELECT * FROM (SELECT * FROM events ORDER BY id DESC LIMIT ?) ORDER BY id", (n,))
            else:
                after = int(qs.get("after", ["0"])[0])
                rows = db.query("SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (after,))
            self._send(rows)
        elif u.path == "/api/videos":
            self._send(db.query("SELECT id,idea,status,created_at FROM videos ORDER BY created_at DESC, id DESC LIMIT 20"))
        else:
            self._send({"error": "not found"}, code=404)

    def log_message(self, *a):
        pass


def serve(port=8000):
    db.init()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Kantor AI jalan di http://localhost:{port}  (Ctrl+C untuk berhenti)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
EOF

cat > office/cli.py <<'EOF'
import argparse
import re
import time

from . import db, pipeline, scout, server, telegram


def cmd_scout(a):
    scout.run(a.n)


def cmd_pick(a):
    batch = scout.latest_batch()
    if not batch:
        print("Belum ada ide. Jalankan dulu:  python -m office.cli scout")
        return
    nums = list(a.numbers)
    if not nums:
        if not telegram.configured():
            print("Telegram belum diset. Pilih manual, contoh:  python -m office.cli pick 1 3 5")
            return
        print("Menunggu balasan di Telegram (contoh: 1 3 5)...")
        end = time.time() + a.wait
        while time.time() < end and not nums:
            txt = telegram.wait_reply(int(max(1, min(60, end - time.time()))))
            if txt:
                nums = [int(x) for x in re.findall(r"\d+", txt)]
    if not nums:
        print("Tidak ada pilihan.")
        return
    picked = []
    for i, idea in enumerate(batch, 1):
        if i in nums:
            db.run("UPDATE ideas SET status='picked' WHERE id=?", (idea["id"],))
            picked.append(idea)
        elif idea["status"] == "proposed":
            db.run("UPDATE ideas SET status='rejected' WHERE id=?", (idea["id"],))
    for idea in picked:
        vid = db.add_video(idea["text"])
        print(f"Masuk antrean: {vid}  {idea['text'][:70]}")
    telegram.send(f"✅ {len(picked)} ide masuk antrean produksi")


def cmd_idea(a):
    vid = db.add_video(a.text)
    print(f"Masuk antrean: {vid}")


def cmd_produce(a):
    if a.id:
        pipeline.produce(a.id)
    elif a.all:
        while pipeline.produce_next():
            pass
    else:
        pipeline.produce_next()


def cmd_status(a):
    rows = db.query("SELECT id,status,idea FROM videos ORDER BY created_at, id")
    if not rows:
        print("Belum ada video.")
    for r in rows:
        print(f"{r['id']:<14} {r['status']:<13} {r['idea'][:60]}")


def cmd_demo(a):
    vid = db.add_video("Penjaga mercusuar menerima surat tiap malam dari orang yang sudah meninggal 50 tahun lalu")
    pipeline.produce(vid)


def main():
    p = argparse.ArgumentParser(prog="office")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(f=lambda a: print("DB siap."))
    s = sub.add_parser("scout"); s.add_argument("-n", type=int, default=6); s.set_defaults(f=cmd_scout)
    k = sub.add_parser("pick"); k.add_argument("numbers", nargs="*", type=int)
    k.add_argument("--wait", type=int, default=600); k.set_defaults(f=cmd_pick)
    i = sub.add_parser("idea"); i.add_argument("text"); i.set_defaults(f=cmd_idea)
    r = sub.add_parser("produce"); r.add_argument("--all", action="store_true")
    r.add_argument("--id"); r.set_defaults(f=cmd_produce)
    sub.add_parser("status").set_defaults(f=cmd_status)
    sub.add_parser("demo").set_defaults(f=cmd_demo)
    u = sub.add_parser("ui"); u.add_argument("--port", type=int, default=8000)
    u.set_defaults(f=lambda a: server.serve(a.port))

    a = p.parse_args()
    db.init()
    a.f(a)


if __name__ == "__main__":
    main()
EOF

# ---------------------------------------------------------------- UI
cat > ui/index.html <<'EOF'
<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kantor AI</title>
<style>
  :root{--bg:#0f1420;--panel:#171d2e;--line:#27304a;--ink:#e8ecf7;--mute:#8b95b3;--accent:#ffb84d}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,Segoe UI,sans-serif}
  h1{font-size:20px;margin:0 0 12px}
  .wrap{display:grid;grid-template-columns:1fr 330px;gap:16px;padding:16px;max-width:1280px;margin:auto}
  @media(max-width:900px){.wrap{grid-template-columns:1fr}}
  #floor{position:relative;aspect-ratio:16/10;border:1px solid var(--line);border-radius:14px;overflow:hidden;
    background:linear-gradient(var(--line) 1px,transparent 1px) 0 0/48px 48px,
               linear-gradient(90deg,var(--line) 1px,transparent 1px) 0 0/48px 48px,#121827}
  .desk,.place{position:absolute;transform:translate(-50%,-50%);text-align:center}
  .desk .top{width:96px;height:34px;background:#2a3452;border:1px solid #3a4670;border-radius:8px}
  .place .ico{font-size:34px}
  .lbl{font-size:11px;color:var(--mute);margin-top:4px;white-space:nowrap}
  .agent{position:absolute;transform:translate(-50%,-50%);text-align:center;z-index:5;
    transition:left 1.2s ease-in-out,top 1.2s ease-in-out}
  .face{width:46px;height:46px;border-radius:50%;background:var(--c);display:grid;place-items:center;
    font-size:24px;border:2px solid #ffffff44;margin:auto}
  .agent.working .face{animation:bob .45s infinite alternate}
  @keyframes bob{to{transform:translateY(-5px)}}
  .name{font-size:11px;margin-top:3px;font-weight:600}
  .bubble{position:absolute;bottom:68px;left:50%;transform:translateX(-50%);background:#fff;color:#111;
    font-size:12px;line-height:1.35;padding:7px 10px;border-radius:10px;width:max-content;max-width:210px;
    opacity:0;transition:opacity .25s;pointer-events:none;z-index:9;text-align:left}
  .bubble.show{opacity:1}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:16px}
  .panel h2{font-size:13px;margin:0 0 10px;color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
  #log{max-height:330px;overflow:auto;font-size:12.5px;line-height:1.45}
  #log div{padding:5px 0;border-bottom:1px solid var(--line)}
  #log b{color:var(--accent)}
  #log small{color:var(--mute)}
  #videos div{font-size:12.5px;padding:5px 0;border-bottom:1px solid var(--line)}
  .tag{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:99px;background:#243052;margin-left:6px}
</style>
</head>
<body>
<div class="wrap">
  <div><h1>🏢 Kantor AI</h1><div id="floor"></div></div>
  <div>
    <div class="panel"><h2>Aktivitas</h2><div id="log"></div></div>
    <div class="panel"><h2>Video</h2><div id="videos"></div></div>
  </div>
</div>
<script>
const floor = document.getElementById('floor');
const logEl = document.getElementById('log');
const sleep = ms => new Promise(r => setTimeout(r, ms));
let cfg, spots = {}, homes = {}, nodes = {}, names = {}, lastId = 0, queue = [], running = false;

function put(el, x, y){ el.style.left = x + '%'; el.style.top = y + '%'; }
function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

function stand(targetId, actorId){
  const t = spots[targetId], h = homes[actorId];
  const side = h.x <= t.x ? -1 : 1;
  return { x: clamp(t.x + side * 8, 5, 95), y: clamp(t.y + 12, 8, 92) };
}

function bubble(el, text){
  const b = el.querySelector('.bubble');
  b.textContent = text;
  b.classList.add('show');
  clearTimeout(b._t);
  b._t = setTimeout(() => b.classList.remove('show'), 3200);
}

function addLog(ev, quiet){
  const who = names[ev.actor] || ev.actor;
  const to = ev.target ? ' → ' + (names[ev.target] || ev.target) : '';
  const d = document.createElement('div');
  const t = new Date(ev.ts * 1000).toLocaleTimeString('id-ID', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  d.innerHTML = '<small>' + t + '</small> <b>' + who + to + '</b>: ';
  d.appendChild(document.createTextNode(ev.text || ev.action));
  logEl.prepend(d);
}

async function handle(ev){
  addLog(ev);
  const n = nodes[ev.actor];
  if (!n) return;
  const el = n;
  if (ev.action === 'walk_to' && spots[ev.target]){
    el.classList.remove('working');
    const p = stand(ev.target, ev.actor);
    put(el, p.x, p.y);
    await sleep(1300);
    bubble(el, ev.text);
    await sleep(2300);
  } else if (ev.action === 'back'){
    el.classList.remove('working');
    put(el, homes[ev.actor].x, homes[ev.actor].y);
    await sleep(1300);
  } else if (ev.action === 'work'){
    el.classList.add('working');
    bubble(el, ev.text);
    await sleep(1800);
  } else {
    el.classList.remove('working');
    bubble(el, ev.text);
    await sleep(2300);
  }
}

async function loop(){
  if (running) return;
  running = true;
  while (queue.length) await handle(queue.shift());
  running = false;
}

async function poll(){
  try{
    const rows = await (await fetch('/api/events?after=' + lastId)).json();
    rows.forEach(e => { lastId = e.id; queue.push(e); });
    loop();
  }catch(e){}
}

async function refreshVideos(){
  try{
    const rows = await (await fetch('/api/videos')).json();
    const box = document.getElementById('videos');
    box.innerHTML = '';
    if (!rows.length) box.textContent = 'Belum ada video.';
    rows.forEach(v => {
      const d = document.createElement('div');
      d.textContent = v.id + ' · ' + v.idea.slice(0, 45) + '…';
      const s = document.createElement('span'); s.className = 'tag'; s.textContent = v.status;
      d.appendChild(s); box.appendChild(d);
    });
  }catch(e){}
}

async function init(){
  cfg = await (await fetch('/api/agents')).json();
  cfg.places.forEach(p => {
    const d = document.createElement('div'); d.className = 'place';
    d.innerHTML = '<div class="ico">' + p.emoji + '</div><div class="lbl">' + p.name + '</div>';
    put(d, p.x, p.y); floor.appendChild(d);
    spots[p.id] = { x: p.x, y: p.y }; names[p.id] = p.name;
  });
  cfg.agents.forEach(a => {
    const desk = document.createElement('div'); desk.className = 'desk';
    desk.innerHTML = '<div class="top"></div><div class="lbl">' + a.role + '</div>';
    put(desk, a.desk.x, a.desk.y); floor.appendChild(desk);
    spots[a.id] = { x: a.desk.x, y: a.desk.y }; names[a.id] = a.name;
    homes[a.id] = { x: a.desk.x, y: a.desk.y + 13 };

    const el = document.createElement('div'); el.className = 'agent';
    el.style.setProperty('--c', a.color);
    el.innerHTML = '<div class="bubble"></div><div class="face">' + a.emoji + '</div><div class="name">' + a.name + '</div>';
    put(el, homes[a.id].x, homes[a.id].y); floor.appendChild(el);
    nodes[a.id] = el;
  });
  const recent = await (await fetch('/api/events?recent=12')).json();
  recent.forEach(e => { lastId = Math.max(lastId, e.id); addLog(e, true); });
  refreshVideos();
  setInterval(poll, 1000);
  setInterval(refreshVideos, 5000);
}
init();
</script>
</body>
</html>
EOF

cat > README.md <<'EOF'
# Kantor AI - Fase 1

Alur: Scout (Adit) -> Telegram -> Creative Director (Agus) -> Writer (Rina)
-> Visual Director (Bayu) -> Editor/QC (Sari, placeholder) -> folder output + notifikasi.

Perintah (jalankan dari folder ini):

    python3 -m office.cli scout            # Adit cari 6 ide, kirim ke Telegram / cetak
    python3 -m office.cli pick 1 3 5       # pilih manual (atau tanpa angka = tunggu balasan Telegram)
    python3 -m office.cli idea "teks ide"  # masukkan ide sendiri langsung ke antrean
    python3 -m office.cli produce          # produksi 1 video (--all untuk semua antrean)
    python3 -m office.cli status
    python3 -m office.cli ui               # tampilan kantor di http://localhost:8000
    python3 -m office.cli demo             # 1 video contoh (mercusuar)

Hasil per video ada di output/<id>/: style_pack.json, script.json, scenes.json, upload_info.txt
Daftar gaya/suara/musik bisa diedit di config/pools.json tanpa mengubah kode.
EOF

echo ""
echo "Selesai. Folder '$PROJECT' sudah dibuat."
echo "Lanjut:  cd $PROJECT && python3 -m office.cli demo"
