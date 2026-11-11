"""Properti dari bentuk dasar; tampilan instance berasal dari Bible."""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from ..bible import (
    entries, invalid_constant, number, object_fields,
    require, text, unique_object,
)
from .preview import font
from .prop_attachment import load_asset_layout, paste_attached

def load_catalog():
    path = (
        Path(__file__).resolve().parents[2]
        / "config/animation/props.json"
    )

    data = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )

    object_fields(data, "props_catalog", "schema_version assets")
    number(
        data["schema_version"],
        "props_catalog.schema_version",
        1, 1, integer=True,
    )

    require(
        isinstance(data["assets"], dict) and bool(data["assets"]),
        "assets",
        "harus berupa objek berisi aset",
    )

    for identity, shapes in data["assets"].items():
        text(identity, "asset_id", r"[a-z0-9][a-z0-9_-]*")

        for index, shape in entries(shapes, identity, 1):
            path = f"assets.{identity}[{index}]"
            object_fields(shape, path, "kind coords paint width")

            require(
                shape["kind"] in ("rect", "ellipse", "line", "polygon"),
                path,
                "jenis bentuk tidak didukung",
            )

            coords = shape["coords"]

            require(
                isinstance(coords, list)
                and 4 <= len(coords) <= 32
                and len(coords) % 2 == 0,
                path,
                "koordinat harus berpasangan",
            )

            for value in coords:
                number(value, path + ".coords", 0, 100)

            if shape["kind"] in ("rect", "ellipse"):
                require(
                    len(coords) == 4
                    and coords[0] < coords[2]
                    and coords[1] < coords[3],
                    path,
                    "batas bentuk tidak valid",
                )

            if shape["kind"] == "polygon":
                require(
                    len(coords) >= 6,
                    path,
                    "polygon membutuhkan tiga titik",
                )

            number(shape["width"], path + ".width", 0.1, 12)
            text(shape["paint"], path + ".paint")

            require(
                shape["paint"] in ("ink", "paper", "head_fill", "accent")
                or re.fullmatch(
                    r"#[0-9A-Fa-f]{6}", shape["paint"]
                ) is not None,
                path,
                "warna tidak dikenal",
            )

    return data["assets"]

def resolve_appearance(item, definition):
    base = definition["appearance"]
    views = base.get("views", {})

    if "view" in item:
        text(item["view"], "prop.view")
        require(
            item["view"] in views,
            "prop.view",
            "tampilan tidak terdaftar di Bible",
        )
        return views[item["view"]]

    if item["owner"] is not None and "held" in views:
        return views["held"]

    return base

def validate_props(items, bible, actors):
    catalog = load_catalog()

    definitions = {
        item["id"]: item
        for item in bible["props"]
    }
    seen = set()

    for index, item in entries(items, "props"):
        path = f"props[{index}]"
        require(isinstance(item, dict), path, "harus objek")

        owner = item.get("owner")

        fields = (
            "id owner x y"
            if owner is None
            else "id owner offset_x offset_y"
        )

        if "view" in item:
            fields += " view"

        object_fields(item, path, fields)
        text(item["id"], path + ".id")

        require(
            item["id"] in definitions,
            path,
            "properti tidak terdaftar di Bible",
        )

        require(
            item["id"] not in seen,
            path,
            "instance properti duplikat",
        )
        seen.add(item["id"])

        # Ambil definisinya sebelum memilih tampilan.
        definition = definitions[item["id"]]

        require(
            "appearance" in definition,
            path,
            "properti memerlukan definisi appearance",
        )

        selected = resolve_appearance(item, definition)

        require(
            selected["asset"] in catalog,
            path,
            "aset belum tersedia",
        )

        if owner is None:
            number(
                item["x"],
                path + ".x",
                0,
                bible["target"]["width"],
            )
            number(
                item["y"],
                path + ".y",
                0,
                bible["target"]["height"],
            )
        else:
            text(owner, path + ".owner")

            require(
                owner in actors,
                path,
                "pemegang tidak hadir dalam adegan",
            )

            for key in ("offset_x", "offset_y"):
                number(
                    item[key],
                    path + "." + key,
                    -100,
                    100,
                )

    return items

def draw_prop_label(layer, appearance, palette):
    if not appearance.get("label"):
        return

    size = layer.width
    draw = ImageDraw.Draw(layer)
    words = appearance["label"].split()

    lines = (
        words
        if len(words) <= 2
        else [" ".join(words[:2]), " ".join(words[2:])]
    )

    maximum = size * 0.5

    for height in range(max(6, round(size * 0.11)), 3, -1):
        label_font = font(height)

        if all(
            draw.textlength(line, font=label_font) <= maximum
            for line in lines
        ):
            break

    require(
        all(
            draw.textlength(line, font=label_font) <= maximum
            for line in lines
        ),
        "prop.label",
        "judul terlalu panjang untuk ukuran properti ini",
    )

    draw.multiline_text(
        (size * 0.52, size * 0.32),
        "\n".join(lines),
        font=label_font,
        fill=palette["paper"],
        anchor="ma",
        align="center",
        spacing=1,
    )

def draw_prop(
    image, appearance, palette, x, y,
    scale=1, direction=1, catalog=None, angle=None,
):
    catalog = load_catalog() if catalog is None else catalog
    size = max(4, round(appearance["size"] * scale))

    layer = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(layer)
    paints = dict(palette, accent=appearance["accent"])

    for shape in catalog[appearance["asset"]]:
        coords = [
            value * (size-1) / 100
            for value in shape["coords"]
        ]
        points = list(zip(coords[::2], coords[1::2]))
        paint = paints.get(shape["paint"], shape["paint"])

        if shape["kind"] == "rect":
            draw.rectangle(coords, fill=paint)
        elif shape["kind"] == "ellipse":
            draw.ellipse(coords, fill=paint)
        elif shape["kind"] == "polygon":
            draw.polygon(points, fill=paint)
        else:
            draw.line(
                points,
                fill=paint,
                width=max(1, round(shape["width"] * size / 100)),
            )

    if direction < 0:
        layer = layer.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    draw_prop_label(layer, appearance, palette)
    if angle is not None:
        layout = load_asset_layout().get(appearance["asset"])

        require(
            layout is not None,
            "prop",
            "titik genggam aset belum terdaftar",
        )

        paste_attached(
            image,
            layer,
            x,
            y,
            direction,
            layout,
            angle,
        )
        return
    position = (round(x-size/2), round(y-size/2))

    require(
        position[0] >= 0
        and position[1] >= 0
        and position[0]+size <= image.width
        and position[1]+size <= image.height,
        "prop",
        "properti keluar dari kanvas",
    )

    if image.mode == "RGBA":
        image.alpha_composite(layer, dest=position)
    else:
        image.paste(layer, position, layer)


def draw_scene_props(image, items, bible, anchors):
    catalog = load_catalog()
    definitions = {item["id"]: item for item in bible["props"]}
    characters = {
        item["id"]: item
        for item in bible["characters"]
    }

    for item in items:
        owner = item["owner"]
        scale, direction = 1, 1

        if owner is None:
            x, y = item["x"], item["y"]
        else:
            anchor = anchors[owner]
            scale = anchor["scale"]
            direction = anchor["direction"]

            x = (
                anchor["hand"][0]
                + item["offset_x"] * scale * direction
            )
            y = (
                anchor["hand"][1]
                + item["offset_y"] * scale
            )

        draw_prop(
            image,
            resolve_appearance(item, definitions[item["id"]]),
            bible["visual"]["palette"],
            x,
            y,
            scale,
            direction,
            catalog,
            angle=(
                None
                if owner is None
                else anchors[owner]["hand_angle"]
            ),
        )

        if owner is not None:
            hx, hy = anchors[owner]["hand"]
            radius = 6 * scale

            ImageDraw.Draw(image).ellipse(
                (
                    hx-radius, hy-radius,
                    hx+radius, hy+radius,
                ),
                fill=characters[owner]["color"],
            )