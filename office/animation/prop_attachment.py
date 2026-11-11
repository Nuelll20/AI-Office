"""Letakkan properti dengan rotasi berpusat pada titik genggam."""
import json
import math
from pathlib import Path

from PIL import Image

from ..bible import (
    invalid_constant, number, object_fields,
    require, unique_object,
)


def load_asset_layout():
    path = (
        Path(__file__).resolve().parents[2]
        / "config/animation/asset_layout.json"
    )

    data = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )

    object_fields(data, "asset_layout", "schema_version assets")
    number(
        data["schema_version"],
        "asset_layout.schema_version",
        1, 1, integer=True,
    )
    require(
        isinstance(data["assets"], dict),
        "asset_layout.assets",
        "harus objek",
    )

    for name, item in data["assets"].items():
        object_fields(item, name, "grip rotation_follow")

        require(
            isinstance(item["grip"], list)
            and len(item["grip"]) == 2,
            name,
            "grip harus berisi x dan y",
        )

        for value in item["grip"]:
            number(value, name + ".grip", 0, 100)

        number(
            item["rotation_follow"],
            name + ".rotation_follow",
            0, 1,
        )

    return data["assets"]


def paste_attached(image, layer, x, y, direction, layout, angle):
    gx, gy = [
        value * (layer.width-1) / 100
        for value in layout["grip"]
    ]

    if direction < 0:
        gx = layer.width - 1 - gx

    radius = math.ceil(math.hypot(layer.width, layer.height)) + 2
    canvas = Image.new("RGBA", (radius*2+1, radius*2+1))

    canvas.alpha_composite(
        layer,
        dest=(round(radius-gx), round(radius-gy)),
    )

    rotation = -direction * angle * layout["rotation_follow"]

    canvas = canvas.rotate(
        rotation,
        resample=Image.Resampling.BICUBIC,
        center=(radius, radius),
    )

    position = (round(x-radius), round(y-radius))
    bounds = canvas.getbbox()

    require(bounds is not None, "prop", "aset kosong")
    require(
        position[0]+bounds[0] >= 0
        and position[1]+bounds[1] >= 0
        and position[0]+bounds[2] <= image.width
        and position[1]+bounds[3] <= image.height,
        "prop",
        "properti keluar dari kanvas",
    )

    if image.mode == "RGBA":
        image.alpha_composite(canvas, dest=position)
    else:
        image.paste(canvas, position, canvas)