"""Kontrak awal Production Bible; validasi data tanpa API atau render."""
import argparse
import json
import math
import re
from pathlib import Path


class BibleError(ValueError):
    pass


def require(condition, path, message):
    if not condition:
        raise BibleError(f"{path}: {message}")


def object_fields(value, path, fields):
    require(isinstance(value, dict), path, "harus berupa objek")
    expected = set(fields.split())
    missing = expected - value.keys()
    extra = value.keys() - expected
    require(not missing, path, f"field wajib hilang: {sorted(missing)}")
    require(not extra, path, f"field tidak dikenal: {sorted(extra)}")


def text(value, path, pattern=None):
    require(isinstance(value, str), path, "harus berupa teks")
    require(bool(value.strip()), path, "tidak boleh kosong")
    require(value == value.strip(), path, "hapus spasi di awal/akhir")
    if pattern:
        require(re.fullmatch(pattern, value) is not None,
                path, "format tidak sesuai")


def number(value, path, minimum, maximum, integer=False):
    allowed = (int,) if integer else (int, float)
    require(type(value) in allowed, path, "tipe angka tidak sesuai")
    require(minimum <= value <= maximum, path,
            f"harus di antara {minimum} dan {maximum}")
    require(math.isfinite(value), path, "harus berupa angka berhingga")


def entries(value, path, minimum=0):
    require(isinstance(value, list), path, "harus berupa daftar")
    require(len(value) >= minimum, path,
            f"minimal {minimum} entri")
    return enumerate(value)


def voice(value, path):
    object_fields(value, path, "provider id rate pitch")
    require(value["provider"] == "edge_tts", path + ".provider",
            "versi kontrak ini menggunakan edge_tts")
    text(value["id"], path + ".id")
    text(value["rate"], path + ".rate", r"[+-][0-9]+%")
    text(value["pitch"], path + ".pitch", r"[+-][0-9]+Hz")
    require(-100 < int(value["rate"][:-1]) <= 100,
            path + ".rate", "harus lebih dari -100% dan maksimal +100%")


def validate_prop_style(value, path):
    require(isinstance(value, dict), path, "harus objek")

    fields = "asset size accent"
    if "label" in value:
        fields += " label"

    object_fields(value, path, fields)

    text(
        value["asset"],
        path + ".asset",
        r"[a-z0-9][a-z0-9_-]*",
    )
    number(value["size"], path + ".size", 4, 300)
    text(value["accent"], path + ".accent", r"#[0-9A-Fa-f]{6}")

    if "label" in value:
        text(value["label"], path + ".label")
        require(
            len(value["label"]) <= 40,
            path + ".label",
            "maksimal 40 karakter",
        )

def validate_bible(data):
    object_fields(data, "bible",
                  "schema_version revision video_id idea target visual "
                  "characters props narration constraints")
    number(data["schema_version"], "schema_version", 1, 3, integer=True)
    number(data["revision"], "revision", 1, 1_000_000, integer=True)
    text(data["video_id"], "video_id", r"[a-z0-9][a-z0-9_-]*")
    text(data["idea"], "idea")

    target = data["target"]
    object_fields(target, "target", "width height fps duration_sec language")
    for key in ("width", "height"):
        number(target[key], "target." + key, 2, 7680, integer=True)
        require(target[key] % 2 == 0, "target." + key,
                "harus genap untuk keluaran yuv420p")
    number(target["fps"], "target.fps", 1, 120, integer=True)
    number(target["duration_sec"], "target.duration_sec", 1, 3600)
    text(target["language"], "target.language")

    visual = data["visual"]
    object_fields(visual, "visual", "style face palette")
    require(visual["style"] == "stickman_2d", "visual.style",
            "versi kontrak ini menggunakan stickman_2d")
    require(visual["face"] == "two_eyes_nose_curved_mouth", "visual.face",
            "gunakan wajah dua mata, hidung, dan mulut melengkung")
    object_fields(visual["palette"], "visual.palette", "ink paper head_fill")
    for key, value in visual["palette"].items():
        text(value, "visual.palette." + key, r"#[0-9A-Fa-f]{6}")

    identifiers = set()

    for group in ("characters", "props"):
        minimum = 1 if group == "characters" else 0

        for index, item in entries(data[group], group, minimum):
            path = f"{group}[{index}]"
            fields = "id name description"

            if group == "characters":
                fields += " color voice"
            elif data["schema_version"] >= 2:
                appearance = item["appearance"]

                if data["schema_version"] == 3:
                    object_fields(
                        appearance,
                        path + ".appearance",
                        "asset size accent views",
                    )

                    views = appearance["views"]

                    require(
                        isinstance(views, dict),
                        path + ".appearance.views",
                        "harus objek",
                    )

                    for key, value in views.items():
                        text(
                            key,
                            path + ".view_id",
                            r"[a-z0-9][a-z0-9_-]*",
                        )
                        validate_prop_style(
                            value,
                            path + ".views." + key,
                        )

                    validate_prop_style(
                        {
                            key: value
                            for key, value in appearance.items()
                            if key != "views"
                        },
                        path + ".appearance",
                    )

                else:
                    object_fields(
                        appearance,
                        path + ".appearance",
                        "asset size accent",
                    )
                    validate_prop_style(
                        appearance,
                        path + ".appearance",
                    )

    narration = data["narration"]
    object_fields(narration, "narration", "tone words_per_second voice")
    text(narration["tone"], "narration.tone")
    number(narration["words_per_second"], "narration.words_per_second", 0.1, 10)
    voice(narration["voice"], "narration.voice")

    constraints = data["constraints"]
    object_fields(constraints, "constraints", "forbidden_words forbidden_visuals")
    for key, values in constraints.items():
        for index, value in entries(values, "constraints." + key):
            text(value, f"constraints.{key}[{index}]")
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON", f"key duplikat: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise BibleError(f"JSON: konstanta {value} tidak diizinkan")


def load_bible(path):
    data = json.loads(
        Path(path).read_text(encoding="utf-8-sig"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )
    return validate_bible(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    try:
        data = load_bible(args.file)
    except (OSError, ValueError) as exc:
        print(f"BIBLE DITOLAK: {exc}")
        return 1
    print("Struktur Production Bible: VALID")
    print(f"Video: {data['video_id']} | Revisi: {data['revision']}")
    print(f"Karakter: {len(data['characters'])} | Properti: {len(data['props'])}")
    print("Pemeriksaan struktur saja; belum penguncian, QC cerita, atau render.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())