"""Rina menulis naskah; Sari memeriksa kesinambungannya."""

import json

from . import llm
from .story_context import check
from .story_planner import require_real


VERSION = 2

WRITER = """Kamu Rina, penulis naskah animasi. Baca brief asli dan SELURUH pedoman Agus.
Tulis cerita yang jelas, setia pada tujuan dan akhir yang ditentukan. Gunakan bahasa brief.
Jangan memaksakan misteri, twist, tokoh manusia, atau durasi tertentu pada semua cerita.

Kontrak JSON tanpa field tambahan:
{
 "title":"judul",
 "description":"ringkasan",
 "hashtags":["#cerita"],
 "character_states":[
   {
     "id":"state_id",
     "character_id":"id_dari_bible",
     "description":"penampilan pada tahap ini"
   }
 ],
 "scenes":[
   {
     "id":1,
     "beat_id":"id_beat",
     "location":"id_lokasi_atau_null",
     "time_label":"penanda waktu cerita",
     "action":"satu aksi utama yang dapat divisualisasikan",
     "characters":["id_tokoh"],
     "states":{"id_tokoh":"state_id"},
     "extras":["deskripsi figur latar anonim"],
     "props":["id_benda"],
     "conditions":["kondisi yang penting untuk aksi/properti"],
     "lines":[
       {"speaker":null,"text":"Narasi luar layar"},
       {"speaker":"id_tokoh","text":"Dialog tokoh"}
     ]
   }
 ]
}

Aturan:
- Semua beat harus tercakup dalam urutan pedoman. Satu beat boleh dipecah menjadi
  beberapa scene. Setiap scene memiliki SATU lokasi dan satu aksi utama.
- Tokoh, lokasi, dan properti wajib berasal dari pedoman. Jangan menambah tokoh
  bernama atau properti penting secara diam-diam. Figur latar anonim boleh ada
  di extras; tidak memiliki dialog individual atau identitas utama.
- states harus mencakup semua characters dalam scene. Definisikan state berbeda
  jika umur, pakaian, cedera, atau kondisi fisik berubah. Pertahankan ciri identitas.
  Jangan menggambar anak dengan penampilan dewasa tanpa transisi waktu yang jelas.
- Rinci penghubung sebab-akibat yang tersirat dalam pedoman. Jangan membuat hasil
  seperti beasiswa/hadiah muncul tanpa persiapan atau alasan yang dapat dipahami.
- Penanda waktu, conditions, dan action harus sejalan. Misalnya pemakaian alat
  yang hanya berlaku pada kondisi tertentu harus menjelaskan kondisinya.
- Setiap speaker dialog harus hadir di characters. speaker null berarti narator.
  lines boleh kosong untuk adegan tanpa ucapan. Maksimal 60 kata terucap per scene.
- Susun jumlah adegan dan panjang ucapan sesuai target durasi jika tersedia.
  Tanpa target, pilih panjang yang cukup untuk menceritakan alur dengan jelas.
- Pedoman adalah acuan identitas/alur; penampilan tiap tahap diperjelas dalam
  character_states. Hindari gabungan aksi berpindah lokasi dalam satu scene.
- Jika ada feedback revisi, perbaiki seluruh naskah sambil mempertahankan brief.
- Pergantian tujuan, kesempatan, kompetisi, atau proses penting harus dihubungkan
  lewat ucapan/narasi yang dipahami penonton; jangan hanya ditulis dalam action.
- Hindari menempatkan benda pada dua tempat tanpa aksi perpindahan yang jelas.
  Satu action harus memiliki satu fokus; pecah langkah berurutan bila diperlukan.
- Jika ada previous_script dan revision_notes, perbaiki bagian yang bermasalah
  sambil mempertahankan bagian yang sudah baik, brief, dan akhir cerita.
"""

REVIEWER = """Kamu Sari, editor kesinambungan naskah animasi. Bandingkan brief,
pedoman Agus, dan naskah Rina. Ini pemeriksaan makna, bukan sekadar format JSON.
Periksa kesetiaan brief/akhir, sebab-akibat, seluruh beat, penanda waktu dan
perubahan usia/penampilan, konsistensi properti/kondisinya, lokasi dan aksi utama,
figur latar, kejelasan dialog, serta kelayakan panjang cerita.
Perubahan yang memang dijelaskan oleh cerita bukan kesalahan. Jangan meminta
cerita mengikuti selera genre tertentu. Laporkan hanya masalah konkret yang
mengganggu pemahaman atau produksi, disertai usulan perbaikan yang dapat dilakukan.

Format persis:
{"approved":true,"issues":[]}

atau:
{
  "approved":false,
  "issues":[
    {
      "scene_id":1,
      "message":"masalah konkret dan usulan perbaikan"
    }
  ]
}

scene_id boleh null untuk masalah keseluruhan cerita.
approved true harus tanpa issues.
approved false harus memiliki sedikitnya satu issue.

Informasi penting yang hanya muncul pada action/conditions tidak otomatis
terdengar dalam audio. Pergantian tujuan atau kesempatan harus memiliki
penghubung yang dipahami melalui ucapan/narasi atau aksi visual yang jelas.
Periksa pula aksi yang menumpuk dan perpindahan benda antartempat yang ambigu.
"""

class ScriptReviewRequired(ValueError):
    pass


def fields(value, names, label):
    check(
        isinstance(value, dict)
        and set(value) == set(names.split()),
        f"Field {label} tidak sesuai kontrak.",
    )


def texts(values, label, limit=100):
    check(
        isinstance(values, list)
        and len(values) <= limit
        and all(
            isinstance(value, str)
            and 0 < len(value.strip()) <= 2000
            for value in values
        ),
        f"{label} harus daftar teks.",
    )


def compile_script(candidate, context):
    revision = context.get("next_script_revision", 1)

    check(
        type(revision) is int and revision >= 1,
        "Revisi naskah harus bilangan bulat positif.",
    )

    fields(
        candidate,
        "title description hashtags character_states scenes",
        "naskah",
    )

    for key in ("title", "description"):
        check(
            isinstance(candidate[key], str)
            and 0 < len(candidate[key].strip()) <= 2000,
            f"{key} tidak valid.",
        )

    texts(candidate["hashtags"], "hashtags", 12)

    check(
        all(
            value.startswith("#")
            and not any(character.isspace() for character in value)
            for value in candidate["hashtags"]
        ),
        "Format hashtag tidak valid.",
    )

    bible = context["story_bible"]

    cast = {item["id"] for item in bible["characters"]}
    locations = {item["id"] for item in bible["locations"]}
    props = {item["id"] for item in bible["props"]}

    beats = {
        item["id"]: index
        for index, item in enumerate(bible["beats"])
    }

    variants = candidate["character_states"]

    check(
        isinstance(variants, list) and len(variants) <= 200,
        "character_states harus daftar.",
    )

    states = {}

    for item in variants:
        fields(
            item,
            "id character_id description",
            "character_state",
        )

        identity = item["id"]

        import re

        check(
            isinstance(identity, str)
            and re.fullmatch(r"[a-z][a-z0-9_-]{0,49}", identity)
            and identity not in states,
            "ID state tidak valid/duplikat.",
        )

        check(
            isinstance(item["character_id"], str)
            and item["character_id"] in cast,
            "State merujuk tokoh yang tidak terdaftar.",
        )

        check(
            isinstance(item["description"], str)
            and 0 < len(item["description"].strip()) <= 2000,
            "Deskripsi state tidak valid.",
        )

        states[identity] = item["character_id"]

    scenes = candidate["scenes"]

    check(
        isinstance(scenes, list) and 1 <= len(scenes) <= 100,
        "Naskah perlu 1-100 scene.",
    )

    result = []
    coverage = set()
    order = []

    for number, scene in enumerate(scenes, 1):
        fields(
            scene,
            "id beat_id location time_label action characters "
            "states extras props conditions lines",
            "scene",
        )

        check(
            type(scene["id"]) is int and scene["id"] == number,
            "ID scene harus berurutan mulai 1.",
        )

        beat = scene["beat_id"]

        check(
            isinstance(beat, str) and beat in beats,
            "Beat scene tidak terdaftar.",
        )

        coverage.add(beat)
        order.append(beats[beat])

        for key in ("time_label", "action"):
            check(
                isinstance(scene[key], str)
                and 0 < len(scene[key].strip()) <= 2000,
                f"{key} scene tidak valid.",
            )

        location = scene["location"]

        check(
            location is None
            or (
                isinstance(location, str)
                and location in locations
            ),
            "Lokasi scene tidak terdaftar.",
        )

        for group, known in (
            ("characters", cast),
            ("props", props),
        ):
            values = scene[group]

            texts(values, group)

            check(
                len(values) == len(set(values))
                and set(values) <= known,
                f"Referensi {group} tidak valid.",
            )

        mapping = scene["states"]

        check(
            isinstance(mapping, dict)
            and set(mapping) == set(scene["characters"]),
            "Setiap tokoh scene harus memiliki state.",
        )

        for character_id, state_id in mapping.items():
            check(
                isinstance(state_id, str)
                and states.get(state_id) == character_id,
                "State scene tidak cocok dengan tokohnya.",
            )

        texts(scene["extras"], "extras", 20)
        texts(scene["conditions"], "conditions", 30)

        lines = scene["lines"]

        check(
            isinstance(lines, list) and len(lines) <= 30,
            "lines harus daftar.",
        )

        for line in lines:
            fields(line, "speaker text", "line")

            speaker = line["speaker"]

            check(
                speaker is None
                or (
                    isinstance(speaker, str)
                    and speaker in scene["characters"]
                ),
                "Pembicara tidak hadir dalam scene.",
            )

            check(
                isinstance(line["text"], str)
                and bool(line["text"].strip()),
                "Ucapan tidak boleh kosong.",
            )

        narration = " ".join(
            line["text"].strip()
            for line in lines
        )

        words = len(narration.split())

        check(
            words <= 60,
            f"Scene {number} melebihi 60 kata; pecah adegannya.",
        )

        seconds = round(max(2, words / 2.4 + 0.5), 2)

        result.append(
            {
                **scene,
                "narration": narration,
                "word_count": words,
                "estimated_duration_sec": seconds,
            }
        )

    check(
        coverage == set(beats)
        and order == sorted(order),
        "Semua beat harus tercakup sesuai urutan pedoman.",
    )

    duration = round(
        sum(scene["estimated_duration_sec"] for scene in result),
        2,
    )

    check(
        duration <= 600,
        "Estimasi melebihi 600 detik; ringkas naskah.",
    )

    target = context["brief"]["target_duration_sec"]

    if target is not None:
        check(
            target * 0.75 <= duration <= target * 1.2,
            f"Estimasi {duration} detik belum sesuai "
            f"target {target} detik.",
        )

    return {
        **candidate,
        "schema_version": 2,
        "bible_revision": context["bible_revision"],
        "script_revision": revision,
        "scenes": result,
        "estimated_duration_sec": duration,
    }


def review_script(candidate, context):
    require_real()

    request = {
        "brief": context["brief"]["raw_text"],
        "story_bible": context["story_bible"],
        "script": candidate,
    }

    report = llm.ask_json(
        REVIEWER,
        json.dumps(request, ensure_ascii=False),
        mock=lambda: None,
        max_tokens=3000,
    )

    fields(report, "approved issues", "laporan QC")

    check(
        type(report["approved"]) is bool,
        "QC approved harus boolean.",
    )

    issues = report["issues"]

    check(
        isinstance(issues, list) and len(issues) <= 100,
        "QC issues harus daftar.",
    )

    for issue in issues:
        fields(issue, "scene_id message", "issue QC")

        scene_id = issue["scene_id"]

        check(
            scene_id is None
            or (
                type(scene_id) is int
                and 1 <= scene_id <= len(candidate["scenes"])
            ),
            "Scene pada QC tidak valid.",
        )

        check(
            isinstance(issue["message"], str)
            and 0 < len(issue["message"].strip()) <= 2000,
            "Pesan QC tidak valid.",
        )

    check(
        report["approved"] == (len(issues) == 0),
        "Keputusan QC tidak sesuai daftar masalah.",
    )

    return report


def write_and_review(
    context,
    on_attempt,
    on_stage=lambda stage, attempt: None,
):
    require_real()

    request = {
        "brief": {
            "raw_text": context["brief"]["raw_text"],
            "language": context["brief"]["language"],
            "target_duration_sec": (
                context["brief"]["target_duration_sec"]
            ),
        },
        "story_bible": context["story_bible"],
    }

    if context.get("previous_script") is not None:
        request["previous_script"] = context["previous_script"]

        request["revision_notes"] = context.get(
            "revision_notes",
            "",
        )

    for attempt in range(1, 4):
        on_stage("write", attempt)

        candidate = llm.ask_json(
            WRITER,
            json.dumps(request, ensure_ascii=False),
            mock=lambda: None,
            max_tokens=10000,
        )

        report = None
        error = None
        compiled = None

        try:
            compiled = compile_script(candidate, context)

        except (ValueError, TypeError, KeyError) as exc:
            error = str(exc)

        if compiled is not None:
            on_stage("review", attempt)

            try:
                report = review_script(compiled, context)

            except Exception as exc:
                on_attempt(
                    attempt,
                    candidate,
                    None,
                    f"QC belum berhasil: {exc}",
                )

                raise

        on_attempt(
            attempt,
            candidate,
            report,
            error,
        )

        if (
            compiled is not None
            and report is not None
            and report["approved"]
            and not error
        ):
            return {
                **compiled,
                "qc": report,
                "writer_version": VERSION,
            }

        request["previous_candidate"] = candidate
        request["feedback"] = {
            "validation_error": error,
            "qc": report,
        }

    raise ScriptReviewRequired(
        "Naskah belum lolos setelah 3 kandidat. "
        "Periksa draft dan catatan QC yang tersimpan."
    )