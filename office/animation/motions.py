"""Interpolasi pose berdasarkan waktu; tidak mengenal nama atau cerita."""
import json
import math
from pathlib import Path

from ..bible import (
    entries, invalid_constant, number, object_fields,
    require, text, unique_object, validate_bible,
)

POSE_FIELDS = ("gaze", "listening", "pointing")


def validate_timeline(data, bible):
    validate_bible(bible)

    object_fields(
        data,
        "timeline",
        "schema_version video_id bible_revision duration_sec tracks",
    )

    number(
        data["schema_version"],
        "timeline.schema_version",
        1, 1, integer=True,
    )

    text(data["video_id"], "timeline.video_id")
    require(
        data["video_id"] == bible["video_id"],
        "timeline.video_id",
        "tidak cocok dengan Bible",
    )

    number(
        data["bible_revision"],
        "timeline.bible_revision",
        1, 1_000_000, integer=True,
    )

    require(
        data["bible_revision"] == bible["revision"],
        "timeline.bible_revision",
        "tidak cocok dengan revisi Bible",
    )

    number(data["duration_sec"], "timeline.duration_sec", 0.1, 3600)
    duration = data["duration_sec"]

    known = {item["id"] for item in bible["characters"]}
    seen = set()
    target = bible["target"]

    for index, track in entries(data["tracks"], "tracks", 1):
        path = f"tracks[{index}]"

        object_fields(
            track, path,
            "character_id x y scale mirror keyframes",
        )

        identity = track["character_id"]
        text(identity, path + ".character_id")

        require(
            identity in known,
            path + ".character_id",
            "karakter tidak terdaftar",
        )

        require(
            identity not in seen,
            path + ".character_id",
            "track karakter duplikat",
        )
        seen.add(identity)

        number(track["scale"], path + ".scale", 0.1, 4)
        number(track["x"], path + ".x", 0, target["width"])
        number(track["y"], path + ".y", 0, target["height"])

        require(
            type(track["mirror"]) is bool,
            path + ".mirror",
            "harus boolean",
        )

        previous = -1
        keys = track["keyframes"]

        for key_index, key in entries(keys, path + ".keyframes", 2):
            location = f"{path}.keyframes[{key_index}]"

            object_fields(
                key, location,
                "time gaze listening pointing",
            )

            number(key["time"], location + ".time", 0, duration)

            require(
                key["time"] > previous,
                location + ".time",
                "waktu harus meningkat, tanpa duplikasi",
            )
            previous = key["time"]

            for name in POSE_FIELDS:
                number(
                    key[name],
                    location + "." + name,
                    -1 if name == "gaze" else 0,
                    1,
                )

        require(
            keys[0]["time"] == 0,
            path,
            "keyframe pertama harus pada detik 0",
        )

        require(
            keys[-1]["time"] == duration,
            path,
            "keyframe terakhir harus sama dengan durasi timeline",
        )

    return data


def load_timeline(path, bible):
    data = json.loads(
        Path(path).read_text(encoding="utf-8-sig"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )
    return validate_timeline(data, bible)


def sample_pose(keys, seconds):
    """Gunakan keyframes yang telah lolos validate_timeline()."""
    if type(seconds) not in (int, float) or not math.isfinite(seconds):
        raise ValueError("Waktu sampel harus berupa angka berhingga.")

    if seconds <= keys[0]["time"]:
        return {name: keys[0][name] for name in POSE_FIELDS}

    for left, right in zip(keys, keys[1:]):
        if seconds <= right["time"]:
            p = (
                (seconds - left["time"])
                / (right["time"] - left["time"])
            )

            eased = p * p * (3 - 2 * p)

            return {
                name: left[name] + (right[name] - left[name]) * eased
                for name in POSE_FIELDS
            }

    return {name: keys[-1][name] for name in POSE_FIELDS}