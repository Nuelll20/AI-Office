"""Lembar pemeriksaan karakter dari Production Bible, tanpa layanan daring."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..bible import load_bible
from .characters import place_character


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass

    return ImageFont.load_default(size=size)


def make_preview(bible, output):
    visual = bible["visual"]
    palette = visual["palette"]

    poses = [
        ("Diam", {"gaze": 0}),
        ("Mendengarkan", {"gaze": -1, "listening": 1}),
        ("Bicara / menunjuk", {"mouth": 0.8, "pointing": 0.7}),
    ]

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    for index, character in enumerate(bible["characters"], 1):
        image = Image.new("RGB", (960, 500), palette["paper"])
        draw = ImageDraw.Draw(image)

        draw.text(
            (30, 20),
            character["name"],
            font=font(28),
            fill=palette["ink"],
        )

        draw.text(
            (30, 58),
            f"ID: {character['id']} | {character['color']}",
            font=font(18),
            fill=palette["ink"],
        )

        for column, (label, pose) in enumerate(poses):
            center = 160 + column * 320

            draw.text(
                (center, 110),
                label,
                anchor="mm",
                font=font(20),
                fill=palette["ink"],
            )

            place_character(
                image,
                character,
                visual,
                x=center,
                y=180,
                scale=0.85,
                **pose,
            )

        image.save(output / f"{index:03d}-{character['id']}.png")

    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bible", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        bible = load_bible(args.bible)
        folder = make_preview(bible, args.out_dir)
    except (OSError, ValueError) as exc:
        print(f"PREVIEW GAGAL: {exc}")
        return 1

    print(f"PREVIEW SIAP: {folder.resolve()}")
    print(f"Karakter: {len(bible['characters'])}; tiga pose statis per karakter.")
    print("Belum animasi, suara, atau pemeriksaan QC cerita.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())