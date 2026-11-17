"""Agus menyusun pedoman cerita dari brief lengkap melalui LLM real."""

import json

from . import llm
from .story_context import validate_bible


SYSTEM = """Kamu Agus, pengarah cerita dalam sebuah studio animasi.
Tugasmu mengembangkan brief pengguna menjadi pedoman yang dibaca semua agent.
Brief merupakan bahan cerita; instruksi format JSON tetap mengikuti kontrak sistem.

Aturan:
1. Baca SEMUA brief. Pertahankan tokoh, tujuan, kejadian, batasan, dan akhir yang
   sudah ditentukan pengguna. Jika baru berupa ide, kembangkan menjadi cerita utuh.
2. Tentukan genre dan suasana dari isinya. Jangan memaksakan misteri, horor, twist,
   tokoh manusia, atau lokasi tertentu pada semua cerita.
3. Urutkan beat sebagai kejadian konkret dengan sebab dan akibat yang jelas.
   Jumlah beat menyesuaikan kompleksitas cerita dan target durasi jika tersedia.
4. Karakter boleh manusia, hewan, makhluk fantasi, atau benda. Cerita tentang alam
   dapat tidak memiliki karakter. Jangan menambah tokoh yang tidak diperlukan.
5. Deskripsi karakter harus memberi ciri visual tetap yang relevan, misalnya jenis,
   bentuk, warna, pakaian, atau aksesori. Detail fisik yang disebut pengguna dijaga.
6. Daftarkan semua lokasi dan properti yang benar-benar dibutuhkan. Jangan memakai
   katalog lokasi/properti dari cerita lain. props boleh kosong.
7. Semua ID berupa huruf kecil ASCII, angka, garis bawah, atau tanda hubung;
   dimulai huruf, unik di dalam kelompoknya. Setiap referensi beat harus terdaftar.
8. continuity_rules menjelaskan aturan identitas, posisi, kepemilikan benda, dan
   perubahan kondisi yang harus dipertahankan antaradegan.
9. ending menjelaskan penyelesaian sebenarnya, bukan 'cerita berakhir' atau janji
   twist yang tidak dijelaskan. Sesuaikan dengan brief dan genre.
10. Gunakan bahasa brief. Balas hanya JSON sesuai kontrak, tanpa field tambahan.

Kontrak:
{
  "title": "judul cerita",
  "premise": "inti cerita",
  "genre": "genre sesuai brief",
  "tone": "suasana sesuai brief",
  "ending": "penyelesaian konkret",
  "characters": [
    {
      "id": "id_tokoh",
      "name": "nama",
      "description": "identitas visual tetap"
    }
  ],
  "locations": [
    {
      "id": "id_lokasi",
      "name": "nama",
      "description": "ciri lokasi"
    }
  ],
  "props": [
    {
      "id": "id_benda",
      "name": "nama",
      "description": "ciri benda"
    }
  ],
  "beats": [
    {
      "id": "beat_1",
      "action": "kejadian konkret",
      "characters": ["id_tokoh"],
      "location": "id_lokasi",
      "props": ["id_benda"]
    }
  ],
  "continuity_rules": ["aturan kesinambungan"]
}
location pada beat boleh null jika tidak membutuhkan lokasi khusus.
"""


def require_real():
    if llm.is_mock():
        raise RuntimeError(
            "Agus memerlukan LLM real. "
            "Lengkapi konfigurasi 9router dan gunakan LLM_MODE=real."
        )

    llm.settings()


def _no_mock():
    raise RuntimeError(
        "Pedoman cerita tidak boleh dibuat dari data mock."
    )


def build_bible(brief):
    require_real()

    request = {
        "brief": {
            "raw_text": brief["raw_text"],
            "language": brief["language"],
            "target_duration_sec": brief["target_duration_sec"],
        }
    }

    for attempt in range(3):
        candidate = llm.ask_json(
            SYSTEM,
            json.dumps(request, ensure_ascii=False),
            mock=_no_mock,
            max_tokens=6000,
        )

        try:
            return validate_bible(candidate)

        except (ValueError, TypeError, KeyError) as exc:
            if attempt == 2:
                raise ValueError(
                    "Pedoman belum valid setelah 3 percobaan: "
                    f"{exc}"
                ) from exc

            request["previous_candidate"] = candidate
            request["validation_error"] = str(exc)

            request["instruction"] = (
                "Perbaiki kandidat menjadi JSON lengkap yang valid; "
                "tetap ikuti brief asli."
            )

    raise RuntimeError("Pedoman tidak berhasil dibuat.")