"""Preview berjalan dari JSON; belum terhubung ke produksi cerita."""
import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from ..bible import (
    entries,
    invalid_constant,
    load_bible,
    number,
    object_fields,
    require,
    text,
    unique_object,
)
from .motion_preview import render_preview
from .preview import font
from .walking import WalkPlan
from .walk_renderer import draw_walker


def make_plan(item):
    return WalkPlan(
        start_x=item["start_x"],
        end_x=item["end_x"],
        start_time=item["start_time"],
        end_time=item["end_time"],
        leg_length=66.3 * item["scale"],
    )


def load_walk_scene(path, bible):
    data = json.loads(
        Path(path).read_text(encoding="utf-8-sig"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )

    object_fields(
        data,
        "walk_scene",
        "schema_version video_id bible_revision duration_sec walks",
    )

    number(data["schema_version"], "schema_version", 1, 1, integer=True)
    number(
        data["bible_revision"],
        "bible_revision",
        1, 1_000_000,
        integer=True,
    )

    require(
        data["video_id"] == bible["video_id"],
        "video_id",
        "Bible tidak cocok",
    )

    require(
        data["bible_revision"] == bible["revision"],
        "bible_revision",
        "revisi tidak cocok",
    )

    number(data["duration_sec"], "duration_sec", 0.1, 30)

    known = {item["id"] for item in bible["characters"]}
    seen = set()

    for index, item in entries(data["walks"], "walks", 1):
        path = f"walks[{index}]"

        object_fields(
            item,
            path,
            "character_id start_x end_x start_time end_time ground_y scale",
        )

        identity = item["character_id"]
        text(identity, path + ".character_id")

        require(identity in known, path, "karakter tidak terdaftar")
        require(identity not in seen, path, "karakter duplikat")
        seen.add(identity)

        number(item["scale"], path + ".scale", 0.5, 1.4)
        margin = 150 * item["scale"]

        for key in ("start_x", "end_x"):
            number(
                item[key],
                path + "." + key,
                margin,
                bible["target"]["width"] - margin,
            )

        for key in ("start_time", "end_time"):
            number(
                item[key],
                path + "." + key,
                0,
                data["duration_sec"],
            )

        number(
            item["ground_y"],
            path + ".ground_y",
            350 * item["scale"],
            bible["target"]["height"] - 60,
        )

        make_plan(item)

    return data


def frame(bible, scene, seconds):
    target = bible["target"]
    visual = bible["visual"]
    ink = visual["palette"]["ink"]

    image = Image.new(
        "RGB",
        (target["width"], target["height"]),
        visual["palette"]["paper"],
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (40, 45),
        "UJI GERAK BERJALAN",
        font=font(28),
        fill=ink,
    )

    draw.text(
        (40, 90),
        f"{seconds:.2f} / {scene['duration_sec']:.2f} detik",
        font=font(22),
        fill=ink,
    )

    characters = {
        item["id"]: item
        for item in bible["characters"]
    }

    for item in scene["walks"]:
        character = characters[item["character_id"]]
        plan = make_plan(item)
        floor = item["ground_y"]

        draw.line(
            (40, floor, target["width"]-40, floor),
            fill=ink,
            width=2,
        )

        draw_walker(
            image,
            character,
            visual,
            plan,
            seconds,
            floor,
        )

        direction = "diam" if plan.end_x == plan.start_x else (
            "kanan" if plan.end_x > plan.start_x else "kiri"
        )

        draw.text(
            (40, floor+15),
            f"{character['name']} / {direction}",
            font=font(22),
            fill=ink,
        )

    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bible", required=True, type=Path)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        bible = load_bible(args.bible)
        scene = load_walk_scene(args.scene, bible)

        render_preview(
            bible,
            scene,
            args.output,
            frame_renderer=frame,
        )

    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"PREVIEW GAGAL: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())