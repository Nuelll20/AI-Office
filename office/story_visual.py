"""Storyboard dinamis dan manifest aset berdasarkan naskah yang disetujui."""

import copy
import hashlib
import json
import math

from . import llm
from .story_context import check
from .story_planner import require_real
from .story_script import fields


VERSION = 1
BATCH_SIZE = 4

STYLE = {
    "id": "warm_clay_2_5d",
    "description": (
        "rounded stylized 2.5D clay-like illustration, "
        "simple expressive faces, soft dimensional shading, "
        "soft contact shadows, clean shapes, warm cream presentation, "
        "consistent character identity"
    ),
    "negative_prompt": (
        "photorealism, inconsistent character identity, "
        "extra limbs, distorted anatomy, watermark, logo, "
        "text embedded inside the illustration"
    ),
    "palette": {
        "paper": "#F7EDDC",
        "ink": "#40332D",
        "teal": "#28A99C",
        "coral": "#D97C60",
        "gold": "#E7B94C",
    },
}

SYSTEM = """Kamu Bayu, sutradara visual animasi cerita.
Baca brief, pedoman, naskah, dan daftar aset yang disediakan.
Rencanakan visual sesuai cerita; jangan mengganti narasi atau dialog.

Kontrak JSON persis:
{
  "asset_prompts": {
    "ID_ASET_BARU": "English image prompt for this asset"
  },
  "scenes": [
    {
      "id": 1,
      "shot": "medium",
      "camera": {
        "motion": "static",
        "focus": "ID_ASET_ATAU_NULL"
      },
      "lighting": {
        "mode": "day",
        "description": "pencahayaan sesuai waktu dan kondisi cerita"
      },
      "composition": "penjelasan komposisi",
      "actors": [
        {
          "asset_id": "ID_ASET_TOKOH",
          "x": 0.35,
          "y": 0.75,
          "scale": 0.8,
          "facing": "right",
          "visible": true,
          "expression": "ekspresi sesuai cerita"
        }
      ],
      "props": [
        {
          "asset_id": "ID_ASET_PROPERTI",
          "x": 0.5,
          "y": 0.7,
          "scale": 0.3,
          "owner": null
        }
      ],
      "actions": [
        {
          "actor": "ID_ASET_PELAKU",
          "kind": "gesture",
          "target": null,
          "cue": "start",
          "until": "end",
          "to": null,
          "owner_after": null,
          "description": "aksi konkret sesuai naskah"
        }
      ]
    }
  ]
}

Aturan:
- asset_prompts harus berisi tepat semua ID pada new_asset_ids.
  Jika new_asset_ids kosong, gunakan objek kosong.
- Tulis prompt aset dalam bahasa Inggris. Pertahankan warna, spesies, pakaian,
  benda, dan ciri identitas yang ditentukan cerita.
- Untuk tokoh, current state menentukan umur/pakaian/kondisi saat ini.
  Pertahankan ciri identitas dari identity description.
- Background dibuat sebagai set dengan pencahayaan netral. Pencahayaan per
  adegan ditentukan terpisah agar lokasi yang sama dapat dipakai ulang.
- Prompt tokoh/properti: objek utuh terisolasi, tanpa latar adegan dan tanpa teks.
- Jangan menciptakan ID aset, dialog, tokoh, atau properti baru.
- scenes harus tepat sama ID dan urutannya dengan source_scenes.
- actors harus mencakup tepat seluruh scope.actors pada scene.
  Tokoh di luar framing tetap dicatat dengan visible false.
- props harus mencakup tepat seluruh scope.props.
- x berada pada 0.05-0.95, y pada 0.25-0.85.
  scale berada pada 0.1-1.5.
- facing: left, right, atau front.
- shot: wide, medium, close_up, atau detail.
- camera.motion: static, push_in, pan_left, atau pan_right.
- close_up harus fokus pada tokoh yang visible.
  detail harus memiliki focus yang terdaftar pada scene.
- lighting.mode: day, night, warm, dark, atau dusk.
  Cocokkan description dengan time_label dan conditions.
- owner adalah ID aset tokoh pemegang benda, atau null jika tidak dipegang.
- kind aksi: move, gesture, interact, react, atau ambient.
- actor dan target memakai ID aset yang tersedia pada scene.
- cue/until: start, end, atau line:1, line:2, dan seterusnya.
  Nomor line mengikuti urutan lines dalam naskah.
  cue menandai awal ucapan; until menandai akhir ucapan tersebut.
- move memerlukan to berupa {"x":0.5,"y":0.75}.
  Aksi selain move memakai to null.
- owner_after hanya berlaku pada interact yang target-nya properti.
  Isikan pemegang setelah interaksi, atau null jika benda dilepas/diletakkan.
- Jaga arah percakapan, kondisi benda, dan kontinuitas antaradegan.
  previous_scene disediakan untuk menjaga kesinambungan antarbatch.
- Keluaran ini adalah rencana visual; jangan mengklaim gambar/video sudah dibuat.
"""


def text(value, label):
    check(
        isinstance(value, str)
        and 0 < len(value.strip()) <= 2000,
        f"{label} harus berupa teks.",
    )


def number(value, low, high, label):
    check(
        type(value) in (int, float)
        and math.isfinite(value)
        and low <= value <= high,
        f"{label} harus berada pada {low}-{high}.",
    )


def choice(value, values, label):
    check(
        isinstance(value, str) and value in values,
        f"{label} tidak didukung.",
    )


def source_hash(context):
    brief = context["brief"]

    payload = {
        "video_id": context["video_id"],
        "brief": {
            "raw_text": brief["raw_text"],
            "language": brief["language"],
            "target_duration_sec": brief["target_duration_sec"],
        },
        "bible_revision": context["bible_revision"],
        "story_bible": context["story_bible"],
        "script": context["script"],
        "style": STYLE,
        "planner_version": VERSION,
    }

    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def prepare_assets(context):
    script = context["script"]
    bible = context["story_bible"]

    check(
        isinstance(script, dict)
        and script.get("schema_version") == 2,
        "Gunakan naskah dari worker Rina yang baru.",
    )

    check(
        isinstance(script.get("qc"), dict)
        and script["qc"].get("approved") is True,
        "Naskah belum lolos pemeriksaan Sari.",
    )

    check(
        script["bible_revision"] == context["bible_revision"],
        "Naskah tidak sesuai revisi pedoman.",
    )

    cast = {item["id"]: item for item in bible["characters"]}
    locations = {item["id"]: item for item in bible["locations"]}
    props = {item["id"]: item for item in bible["props"]}

    states = {
        item["id"]: item
        for item in script["character_states"]
    }

    assets = {}
    scopes = {}
    first_character_asset = {}

    def add(asset_id, kind, name, description, **metadata):
        if asset_id not in assets:
            assets[asset_id] = {
                "kind": kind,
                "name": name,
                "description": description,
                "reference_asset_id": None,
                **metadata,
            }

    for scene in script["scenes"]:
        actors = []

        for character_id in scene["characters"]:
            state_id = scene["states"][character_id]
            state = states[state_id]

            check(
                state["character_id"] == character_id,
                "State tidak cocok dengan tokohnya.",
            )

            character = cast[character_id]
            asset_id = f"character:{character_id}:{state_id}"

            first = first_character_asset.setdefault(
                character_id,
                asset_id,
            )

            add(
                asset_id,
                "character",
                character["name"],
                (
                    f"Identity description: {character['description']}\n"
                    f"Current state: {state['description']}\n"
                    "Current state takes precedence for age, "
                    "clothing, and physical condition."
                ),
                character_id=character_id,
                state_id=state_id,
                identity_group=(
                    f"{context['video_id']}:{character_id}"
                ),
                reference_asset_id=(
                    None if first == asset_id else first
                ),
            )

            actors.append(asset_id)

        prop_ids = []

        for prop_id in scene["props"]:
            item = props[prop_id]
            asset_id = f"prop:{prop_id}"

            add(
                asset_id,
                "prop",
                item["name"],
                item["description"],
            )

            prop_ids.append(asset_id)

        background = None

        if scene["location"] is not None:
            item = locations[scene["location"]]
            background = f"location:{scene['location']}"

            add(
                background,
                "location",
                item["name"],
                item["description"],
            )

        extra_ids = []

        for index, description in enumerate(scene["extras"], 1):
            asset_id = f"extra:{scene['id']}:{index}"

            add(
                asset_id,
                "extra",
                f"Figur latar {index}",
                description,
            )

            extra_ids.append(asset_id)

        scopes[scene["id"]] = {
            "actors": actors,
            "props": prop_ids,
            "background": background,
            "extras": extra_ids,
        }

    return assets, scopes


def scope_ids(scope):
    return set(
        scope["actors"]
        + scope["props"]
        + scope["extras"]
        + (
            [scope["background"]]
            if scope["background"] is not None
            else []
        )
    )


def placement(node):
    number(node["x"], 0.05, 0.95, "x")
    number(node["y"], 0.25, 0.85, "y")
    number(node["scale"], 0.1, 1.5, "scale")


def validate_batch(candidate, batch, scopes, new_ids):
    fields(candidate, "asset_prompts scenes", "storyboard")

    prompts = candidate["asset_prompts"]

    check(
        isinstance(prompts, dict)
        and set(prompts) == set(new_ids),
        "Daftar prompt aset tidak sesuai new_asset_ids.",
    )

    for value in prompts.values():
        text(value, "Prompt aset")

    planned = candidate["scenes"]

    check(
        isinstance(planned, list)
        and len(planned) == len(batch),
        "Jumlah scene visual tidak sesuai naskah.",
    )

    for source, scene in zip(batch, planned):
        fields(
            scene,
            "id shot camera lighting composition actors props actions",
            "scene visual",
        )

        check(
            type(scene["id"]) is int
            and scene["id"] == source["id"],
            "ID/urutan scene visual tidak sesuai.",
        )

        scope = scopes[source["id"]]
        allowed = scope_ids(scope)

        choice(
            scene["shot"],
            {"wide", "medium", "close_up", "detail"},
            "shot",
        )

        text(scene["composition"], "composition")

        actors = scene["actors"]

        check(isinstance(actors, list), "actors harus daftar.")

        actor_ids = []

        for actor in actors:
            fields(
                actor,
                "asset_id x y scale facing visible expression",
                "aktor visual",
            )

            check(
                isinstance(actor["asset_id"], str)
                and actor["asset_id"] in scope["actors"],
                "Aset tokoh tidak terdaftar dalam scene.",
            )

            actor_ids.append(actor["asset_id"])
            placement(actor)

            choice(
                actor["facing"],
                {"left", "right", "front"},
                "facing",
            )

            check(
                type(actor["visible"]) is bool,
                "visible harus boolean.",
            )

            text(actor["expression"], "expression")

        check(
            len(actor_ids) == len(set(actor_ids))
            and set(actor_ids) == set(scope["actors"]),
            "Tokoh scene visual tidak lengkap atau duplikat.",
        )

        visual_props = scene["props"]

        check(
            isinstance(visual_props, list),
            "props visual harus daftar.",
        )

        prop_ids = []

        for prop in visual_props:
            fields(
                prop,
                "asset_id x y scale owner",
                "properti visual",
            )

            check(
                isinstance(prop["asset_id"], str)
                and prop["asset_id"] in scope["props"],
                "Aset properti tidak terdaftar dalam scene.",
            )

            prop_ids.append(prop["asset_id"])
            placement(prop)

            check(
                prop["owner"] is None
                or (
                    isinstance(prop["owner"], str)
                    and prop["owner"] in scope["actors"]
                ),
                "Pemegang properti tidak tersedia dalam scene.",
            )

        check(
            len(prop_ids) == len(set(prop_ids))
            and set(prop_ids) == set(scope["props"]),
            "Properti scene visual tidak lengkap atau duplikat.",
        )

        fields(scene["camera"], "motion focus", "camera")

        choice(
            scene["camera"]["motion"],
            {"static", "push_in", "pan_left", "pan_right"},
            "Gerakan kamera",
        )

        focus = scene["camera"]["focus"]

        check(
            focus is None
            or (
                isinstance(focus, str)
                and focus in allowed
            ),
            "Fokus kamera tidak tersedia dalam scene.",
        )

        if focus in scope["actors"]:
            focused_actor = next(
                actor
                for actor in actors
                if actor["asset_id"] == focus
            )

            check(
                focused_actor["visible"],
                "Kamera tidak boleh fokus pada tokoh tersembunyi.",
            )

        if scene["shot"] == "close_up":
            check(
                focus in scope["actors"],
                "close_up harus fokus pada tokoh.",
            )

        if scene["shot"] == "detail":
            check(focus is not None, "detail memerlukan fokus.")

        fields(
            scene["lighting"],
            "mode description",
            "lighting",
        )

        choice(
            scene["lighting"]["mode"],
            {"day", "night", "warm", "dark", "dusk"},
            "Mode pencahayaan",
        )

        text(
            scene["lighting"]["description"],
            "Deskripsi pencahayaan",
        )

        actions = scene["actions"]

        check(
            isinstance(actions, list) and len(actions) <= 30,
            "actions harus daftar dengan maksimal 30 aksi.",
        )

        anchors = (
            ["start"]
            + [
                f"line:{index}"
                for index in range(1, len(source["lines"]) + 1)
            ]
            + ["end"]
        )

        rank = {
            anchor: index
            for index, anchor in enumerate(anchors)
        }

        for action in actions:
            fields(
                action,
                "actor kind target cue until to owner_after description",
                "aksi visual",
            )

            check(
                isinstance(action["actor"], str)
                and action["actor"] in allowed,
                "Pelaku aksi tidak tersedia dalam scene.",
            )

            check(
                action["target"] is None
                or (
                    isinstance(action["target"], str)
                    and action["target"] in allowed
                ),
                "Target aksi tidak tersedia dalam scene.",
            )

            choice(
                action["kind"],
                {"move", "gesture", "interact", "react", "ambient"},
                "Jenis aksi",
            )

            for key in ("cue", "until"):
                check(
                    isinstance(action[key], str)
                    and action[key] in rank,
                    "Penanda ucapan pada aksi tidak valid.",
                )

            check(
                rank[action["cue"]] <= rank[action["until"]],
                "Urutan waktu aksi terbalik.",
            )

            if action["kind"] == "move":
                fields(action["to"], "x y", "Tujuan perpindahan")
                number(action["to"]["x"], 0.05, 0.95, "to.x")
                number(action["to"]["y"], 0.25, 0.85, "to.y")

                check(
                    rank[action["cue"]] < rank[action["until"]]
                    or action["cue"].startswith("line:"),
                    "Gerak berpindah membutuhkan rentang waktu.",
                )

            else:
                check(
                    action["to"] is None,
                    "to hanya digunakan oleh aksi move.",
                )

            owner = action["owner_after"]

            check(
                owner is None
                or (
                    isinstance(owner, str)
                    and owner in scope["actors"]
                ),
                "Pemegang akhir tidak tersedia dalam scene.",
            )

            if not (
                action["kind"] == "interact"
                and action["target"] in scope["props"]
            ):
                check(
                    owner is None,
                    "owner_after hanya untuk interaksi properti.",
                )

            text(action["description"], "Deskripsi aksi")


def build_storyboard(context):
    require_real()

    assets, scopes = prepare_assets(context)
    source_scenes = context["script"]["scenes"]
    finished = []

    for start in range(0, len(source_scenes), BATCH_SIZE):
        batch = source_scenes[start:start + BATCH_SIZE]
        needed = set()

        for scene in batch:
            needed.update(scope_ids(scopes[scene["id"]]))

        for asset_id in list(needed):
            reference = assets[asset_id]["reference_asset_id"]

            if reference is not None:
                needed.add(reference)

        new_ids = sorted(
            asset_id
            for asset_id in needed
            if "prompt" not in assets[asset_id]
        )

        request = {
            "brief": context["brief"]["raw_text"],
            "story_bible": context["story_bible"],
            "style": STYLE,
            "source_scenes": batch,
            "scope": {
                scene["id"]: scopes[scene["id"]]
                for scene in batch
            },
            "assets": {
                asset_id: assets[asset_id]
                for asset_id in sorted(needed)
            },
            "new_asset_ids": new_ids,
            "previous_scene": (
                finished[-1] if finished else None
            ),
        }

        for attempt in range(3):
            candidate = llm.ask_json(
                SYSTEM,
                json.dumps(request, ensure_ascii=False),
                mock=lambda: None,
                max_tokens=12000,
            )

            try:
                validate_batch(
                    candidate,
                    batch,
                    scopes,
                    new_ids,
                )
                break

            except (ValueError, TypeError, KeyError) as exc:
                if attempt == 2:
                    raise ValueError(
                        "Storyboard belum valid setelah "
                        f"3 percobaan: {exc}"
                    ) from exc

                request["previous_candidate"] = candidate
                request["validation_error"] = str(exc)

        for asset_id, prompt in candidate["asset_prompts"].items():
            assets[asset_id]["prompt"] = (
                prompt.strip()
                + ", "
                + STYLE["description"]
            )

            assets[asset_id]["negative_prompt"] = (
                STYLE["negative_prompt"]
            )

        for source, visual in zip(batch, candidate["scenes"]):
            finished.append(
                {
                    **source,
                    "asset_refs": copy.deepcopy(
                        scopes[source["id"]]
                    ),
                    "visual": visual,
                }
            )

    return {
        "schema_version": 3,
        "video_id": context["video_id"],
        "title": context["script"]["title"],
        "bible_revision": context["bible_revision"],
        "script_revision": context["script"]["script_revision"],
        "planner_version": VERSION,
        "source_hash": source_hash(context),
        "style": copy.deepcopy(STYLE),
        "assets": assets,
        "scenes": finished,
    }