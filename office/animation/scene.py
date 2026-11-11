"""Satu timeline untuk berjalan, menghadap, properti, dan dialog."""
import argparse
import json
import math
import re
import subprocess
import tempfile
from .gestures import GESTURES, sample_gesture
from pathlib import Path

from PIL import Image, ImageDraw

from ..bible import (
    entries, invalid_constant, load_bible, number,
    object_fields, require, text, unique_object,
)
from .motion_preview import render_preview
from .preview import font
from .props import (
    draw_scene_props,
    validate_props,
    prop_center,
    resolve_appearance,
)
from .prop_actions import (
    compile_actions,
    sample_action,
    validate_actions,
)
from .scene_audio import RATE, mouth_levels, speech, write_pcm
from .walking import WalkPlan
from .walk_renderer import draw_walker
from .audio_quality import prepare_dialogue



def plan_actor(item):
    return WalkPlan(
        item["start_x"],
        item["end_x"],
        item["start_time"],
        item["end_time"],
        66.3 * item["scale"],
    )


def load_scene(path, bible):
    data = json.loads(
        Path(path).read_text(encoding="utf-8-sig"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )

    fields = (
        "schema_version video_id bible_revision title "
        "location ground_y timing actors props lines"
    )

    if isinstance(data, dict) and "actions" in data:
        fields += " actions"

    object_fields(
        data,
        "scene",
        fields,
    )

    number(
        data["schema_version"],
        "scene.schema_version",
        1,
        1,
        integer=True,
    )

    text(data["video_id"], "scene.video_id")

    number(
        data["bible_revision"],
        "scene.bible_revision",
        1,
        1_000_000,
        integer=True,
    )

    require(
        data["video_id"] == bible["video_id"]
        and data["bible_revision"] == bible["revision"],
        "scene",
        "identitas atau revisi Bible tidak cocok",
    )

    text(data["title"], "scene.title")

    require(
        len(data["title"]) <= 35,
        "scene.title",
        "maksimal 35 karakter",
    )

    text(data["location"], "scene.location")

    require(
        len(data["location"]) <= 40,
        "scene.location",
        "maksimal 40 karakter",
    )

    require(
        RATE % bible["target"]["fps"] == 0,
        "target.fps",
        "harus membagi 24000",
    )

    number(
        data["ground_y"],
        "ground_y",
        450,
        bible["target"]["height"] * 0.72,
    )

    # Validasi pengaturan waktu.
    timing = data["timing"]
    timing_fields = "after_walk_sec gap_sec tail_sec"

    if isinstance(timing, dict) and "max_pause_sec" in timing:
        timing_fields += " max_pause_sec"

    object_fields(
        timing,
        "timing",
        timing_fields,
    )

    for key, value in timing.items():
        number(
            value,
            "timing." + key,
            0,
            3,
        )

    if "max_pause_sec" in timing:
        number(
            timing["max_pause_sec"],
            "timing.max_pause_sec",
            0.15,
            1,
        )

    # Validasi tokoh yang hadir dalam adegan.
    actors = data["actors"]

    require(
        isinstance(actors, dict)
        and 1 <= len(actors) <= 4,
        "actors",
        "harus berisi 1 sampai 4 aktor",
    )

    known = {
        item["id"]
        for item in bible["characters"]
    }

    for identity, item in actors.items():
        require(
            identity in known,
            "actors",
            "karakter tidak terdaftar",
        )

        object_fields(
            item,
            identity,
            "start_x end_x start_time end_time scale look_at",
        )

        number(
            item["scale"],
            identity + ".scale",
            0.5,
            1.2,
        )

        for key in ("start_x", "end_x"):
            number(
                item[key],
                identity + "." + key,
                150 * item["scale"],
                bible["target"]["width"]
                - 150 * item["scale"],
            )

        for key in ("start_time", "end_time"):
            number(
                item[key],
                identity + "." + key,
                0,
                10,
            )

        if item["look_at"] is not None:
            text(
                item["look_at"],
                identity + ".look_at",
            )

            require(
                item["look_at"] in actors
                and item["look_at"] != identity,
                identity,
                "lawan bicara tidak valid",
            )

        plan_actor(item)

    validate_props(
        data["props"],
        bible,
        set(actors),
    )

    # Variabel line hanya digunakan di dalam perulangan ini.
    seen = set()

    for index, line in entries(data["lines"], "lines", 1):
        line_path = f"lines[{index}]"
        fields = "id speaker text"

        for optional in (
            "gesture",
            "gesture_target",
        ):
            if isinstance(line, dict) and optional in line:
                fields += " " + optional

        object_fields(
            line,
            line_path,
            fields,
        )

        text(
            line["id"],
            line_path + ".id",
            r"[a-z0-9][a-z0-9_-]*",
        )

        text(
            line["speaker"],
            line_path + ".speaker",
        )

        text(
            line["text"],
            line_path + ".text",
        )

        require(
            len(line["text"]) <= 300,
            line_path + ".text",
            "maksimal 300 karakter",
        )

        require(
            line["id"] not in seen,
            line_path + ".id",
            "ID duplikat",
        )

        seen.add(line["id"])

        require(
            line["speaker"] in actors,
            line_path + ".speaker",
            "pembicara tidak hadir",
        )

        if "gesture" in line:
            text(
                line["gesture"],
                line_path + ".gesture",
            )

            require(
                line["gesture"] in GESTURES,
                line_path + ".gesture",
                "jenis gestur tidak dikenal",
            )

        for word in bible["constraints"]["forbidden_words"]:
            require(
                re.search(
                    r"(?<!\w)"
                    + re.escape(word)
                    + r"(?!\w)",
                    line["text"],
                    re.I,
                ) is None,
                line_path + ".text",
                "memuat kata terlarang",
            )

    validate_actions(data)
    return data


def compile_scene(
    bible,
    data,
    folder,
    tone=False,
    report=print,
):
    fps = bible["target"]["fps"]
    samples_per_frame = RATE // fps

    voices = {
        item["id"]: item["voice"]
        for item in bible["characters"]
    }

    end_walk = max(
        item["end_time"]
        for item in data["actors"].values()
    )

    cursor = math.ceil(
        (
            end_walk
            + data["timing"]["after_walk_sec"]
        ) * fps
    )

    lines = []
    clips = []

    for line in data["lines"]:
        mode = "nada uji" if tone else "Edge TTS"

        report(
            f"Membuat suara kalimat "
            f"{line['id']} ({mode})..."
        )

        voice = voices[line["speaker"]]

        pcm = speech(
            line["text"],
            voice,
            Path(folder) / "voice",
            tone,
        )

        pcm, audio_stats = prepare_dialogue(
            pcm,
            shift=voice.get("shift_semitones", 0),
            max_pause=data["timing"].get("max_pause_sec"),
        )

        levels = mouth_levels(
            pcm, samples_per_frame
        )

        lines.append(dict(
            line,
            start_frame=cursor,
            end_frame=cursor + len(levels),
            levels=levels,
            audio_stats=audio_stats,
        ))

        clips.append(pcm)

        cursor += (
            len(levels)
            + round(data["timing"]["gap_sec"] * fps)
        )

    total = (
        lines[-1]["end_frame"]
        + round(data["timing"]["tail_sec"] * fps)
    )

    tracks = compile_actions(
        data, lines, fps
    )

    total = max(
        [total]
        + [
            item["end_frame"]
            for item in tracks
        ]
    )

    require(
        total <= 30 * fps,
        "scene",
        "adegan melebihi 30 detik; "
        "bagi menjadi beberapa adegan",
    )

    track = bytearray(
        total * samples_per_frame * 2
    )

    for line, pcm in zip(lines, clips):
        start = (
            line["start_frame"]
            * samples_per_frame
            * 2
        )

        track[start:start + len(pcm)] = pcm

    scene = dict(
        data,
        lines=lines,
        action_tracks=tracks,
        duration_sec=total / fps,
        total_frames=total,
        audio_mode=(
            "tone_test"
            if tone
            else "edge_tts"
        ),
    )

    return scene, bytes(track)


def frame(bible, scene, seconds):
    width = bible["target"]["width"]
    height = bible["target"]["height"]
    fps = bible["target"]["fps"]
    palette = bible["visual"]["palette"]

    image = Image.new(
        "RGB",
        (width, height),
        palette["paper"],
    )

    draw = ImageDraw.Draw(image)
    horizon = scene["ground_y"] - 90

    draw.rectangle(
        (0, horizon, width, height),
        fill=palette["head_fill"],
    )

    draw.line(
        (0, horizon, width, horizon),
        fill=palette["ink"],
        width=3,
    )

    draw.text(
        (40, 45),
        scene["title"],
        font=font(30),
        fill=palette["ink"],
    )

    draw.text(
        (40, 95),
        scene["location"],
        font=font(22),
        fill=palette["ink"],
    )

    index = round(seconds * fps)

    active = next(
        (
            line
            for line in scene["lines"]
            if line["start_frame"]
            <= index
            < line["end_frame"]
        ),
        None,
    )

    characters = {
        item["id"]: item
        for item in bible["characters"]
    }

    plans = {
        identity: plan_actor(item)
        for identity, item in scene["actors"].items()
    }

    props = {
        item["id"]: item
        for item in scene["props"]
    }

    definitions = {
        item["id"]: item
        for item in bible["props"]
    }

    carrying = {
        item["owner"]
        for item in scene["props"]
        if item["owner"] is not None
    }

    states = {}
    measured = {}
    anchors = {}

    # Tahap pertama menghitung posisi tangan dan benda.
    for order, (identity, item) in enumerate(
        scene["actors"].items()
    ):
        plan = plans[identity]
        pose = plan.sample(seconds)
        facing = None

        if (
            not pose.activity
            and item["look_at"] is not None
        ):
            other_x = plans[
                item["look_at"]
            ].sample(seconds).hip[0]

            facing = (
                1
                if other_x >= pose.hip[0]
                else -1
            )

        level = 0.0

        gesture_line = (
            active
            if active and active["speaker"] == identity
            else None
        )

        if gesture_line is not None:
            offset = index - active["start_frame"]

            recent = active["levels"][
                max(0, offset - 2):offset + 1
            ]

            level = sum(recent) / len(recent)

        kind, weight, phase = sample_gesture(
            gesture_line,
            index,
            fps,
        )

        action, action_weight = sample_action(
            scene.get("action_tracks", []),
            identity,
            index,
            fps,
        )

        states[identity] = dict(
            mouth=level,
            gesture=weight,
            facing=facing,
            gesture_kind=kind,
            gesture_phase=phase,
            carrying=identity in carrying,
            prop_action=action,
            prop_weight=action_weight,
            blink=(
                (seconds + order * 0.7) % 3.5
                < 0.1
            ),
        )

        measured[identity] = draw_walker(
            image,
            characters[identity],
            bible["visual"],
            plan,
            seconds,
            scene["ground_y"],
            measure=True,
            **states[identity],
        )

    # Tahap kedua menggambar tokoh.
    for identity in scene["actors"]:
        target = None

        if (
            active
            and active["speaker"] == identity
            and "gesture_target" in active
        ):
            item = props[
                active["gesture_target"]
            ]

            anchor = measured.get(
                item["owner"]
            )

            definition = definitions[
                item["id"]
            ]

            center = prop_center(
                item,
                definition,
                anchor,
            )

            size = resolve_appearance(
                item,
                definition,
            )["size"]

            radius = (
                size
                * (
                    1
                    if anchor is None
                    else anchor["scale"]
                )
                / 2
            )

            target = (*center, radius)

        anchors[identity] = draw_walker(
            image,
            characters[identity],
            bible["visual"],
            plans[identity],
            seconds,
            scene["ground_y"],
            point_target=target,
            measure=False,
            **states[identity],
        )

    # Wajib menggambar benda setelah seluruh tokoh digambar.
    # Pemanggilan ini berada di luar perulangan dan if active.
    draw_scene_props(
        image,
        scene["props"],
        bible,
        anchors,
    )

    if active:
        top = round(height * 0.81)

        draw.rounded_rectangle(
            (25, top, width - 25, height - 35),
            radius=18,
            fill=palette["paper"],
            outline=palette["ink"],
            width=2,
        )

        speaker = characters[
            active["speaker"]
        ]

        draw.text(
            (45, top + 15),
            speaker["name"],
            font=font(23),
            fill=speaker["color"],
        )

        rows = []
        current = ""
        subtitle_font = font(27)

        for word in active["text"].split():
            trial = (current + " " + word).strip()

            if (
                draw.textlength(
                    trial,
                    font=subtitle_font,
                ) > width - 90
                and current
            ):
                rows.append(current)
                current = word
            else:
                current = trial

        rows.append(current)

        require(
            len(rows) <= 4,
            "subtitle",
            "kalimat terlalu panjang; pecah dialog",
        )

        require(
            all(
                draw.textlength(
                    row,
                    font=subtitle_font,
                ) <= width - 90
                for row in rows
            ),
            "subtitle",
            "kata terlalu panjang untuk panel subtitle",
        )

        draw.multiline_text(
            (45, top + 50),
            "\n".join(rows),
            font=subtitle_font,
            fill=palette["ink"],
            spacing=8,
        )

    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bible", required=True, type=Path)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tone", action="store_true")
    args = parser.parse_args()

    try:
        from .. import db, events

        db.init()

        bible = load_bible(args.bible)
        data = load_scene(args.scene, bible)
        args.out_dir.mkdir(parents=True, exist_ok=True)

        events.emit(
            "bayu",
            "work",
            "Menyusun timeline adegan terpadu.",
            video_id=bible["video_id"],
        )

        def report(message):
            events.emit(
                "sari",
                "work",
                message,
                video_id=bible["video_id"],
            )

        scene, pcm = compile_scene(
            bible,
            data,
            args.out_dir,
            args.tone,
            report,
        )

        tag = "-tone" if args.tone else "-voice"
        final = args.out_dir / (
            bible["video_id"] + tag + ".mp4"
        )

        report("Merender berjalan, properti, dan dialog.")

        with tempfile.TemporaryDirectory(dir=args.out_dir) as folder:
            wav = Path(folder) / "track.wav"
            write_pcm(wav, pcm)

            render_preview(
                bible,
                scene,
                final,
                frame_renderer=frame,
                audio_path=wav,
                frame_count=scene["total_frames"],
            )

        public = dict(
            scene,
            lines=[
                {
                    key: value
                    for key, value in line.items()
                    if key != "levels"
                }
                for line in scene["lines"]
            ],
        )

        temporary = final.with_suffix(".timeline.tmp")
        temporary.write_text(
            json.dumps(public, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(final.with_suffix(".timeline.json"))

        events.emit(
            "sari",
            "say",
            "Adegan selesai; siap diperiksa.",
            video_id=bible["video_id"],
        )
        print("HASIL:", final.resolve())

    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("ADEGAN GAGAL:", exc)
        return 1

    finally:
        if "db" in locals():
            for actor in ("bayu", "sari"):
                events.emit(actor, "back")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())