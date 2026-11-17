"""Pratinjau HTML posisi aset; tanpa JavaScript atau layanan eksternal."""

from html import escape


def e(value):
    return escape(str(value), quote=True)


def render_html(board):
    assets = board["assets"]
    cards = []

    for scene in board["scenes"]:
        visual = scene["visual"]
        nodes = []

        actor_positions = {
            actor["asset_id"]: (
                actor["x"] * 540,
                actor["y"] * 400,
            )
            for actor in visual["actors"]
        }

        for actor in visual["actors"]:
            x, y = actor_positions[actor["asset_id"]]
            name = assets[actor["asset_id"]]["name"]
            opacity = "1" if actor["visible"] else "0.35"

            nodes.append(
                f'<g opacity="{opacity}">'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="29" '
                'fill="#28A99C" stroke="#40332D" stroke-width="2"/>'
                f'<text x="{x:.1f}" y="{y + 48:.1f}" '
                'text-anchor="middle" font-size="16">'
                f'{e(name)}</text></g>'
            )

        for prop in visual["props"]:
            x = prop["x"] * 540
            y = prop["y"] * 400
            name = assets[prop["asset_id"]]["name"]

            if prop["owner"] is not None:
                ox, oy = actor_positions[prop["owner"]]

                nodes.append(
                    f'<line x1="{ox:.1f}" y1="{oy:.1f}" '
                    f'x2="{x:.1f}" y2="{y:.1f}" '
                    'stroke="#BA6040" stroke-dasharray="5 4"/>'
                )

            nodes.append(
                f'<rect x="{x - 23:.1f}" y="{y - 18:.1f}" '
                'width="46" height="36" rx="8" fill="#E7B94C"/>'
                f'<text x="{x:.1f}" y="{y + 39:.1f}" '
                'text-anchor="middle" font-size="14">'
                f'{e(name)}</text>'
            )

        lines = "".join(
            "<li>"
            + e(
                (
                    assets[
                        next(
                            actor["asset_id"]
                            for actor in visual["actors"]
                            if assets[actor["asset_id"]].get(
                                "character_id"
                            ) == line["speaker"]
                        )
                    ]["name"]
                    if line["speaker"] is not None
                    else "Narator"
                )
            )
            + ": "
            + e(line["text"])
            + "</li>"
            for line in scene["lines"]
        )

        actions = "".join(
            "<li>"
            + e(action["cue"])
            + " → "
            + e(action["until"])
            + ": "
            + e(action["description"])
            + "</li>"
            for action in visual["actions"]
        )

        cards.append(
            '<article>'
            f'<h2>Adegan {scene["id"]} · {e(visual["shot"])}</h2>'
            f'<p>{e(scene["time_label"])} · '
            f'{e(visual["lighting"]["mode"])}</p>'
            '<svg viewBox="0 0 540 400" role="img" '
            'aria-label="Posisi aset adegan">'
            '<rect width="540" height="400" rx="18" fill="#EEE0C8"/>'
            + "".join(nodes)
            + '</svg>'
            f'<p><b>Aksi:</b> {e(scene["action"])}</p>'
            f'<p><b>Komposisi:</b> {e(visual["composition"])}</p>'
            f'<p><b>Kamera:</b> {e(visual["camera"]["motion"])}</p>'
            f'<p><b>Cahaya:</b> '
            f'{e(visual["lighting"]["description"])}</p>'
            f'<ul>{lines}</ul>'
            f'<details><summary>Rencana gerakan</summary>'
            f'<ul>{actions}</ul></details>'
            '</article>'
        )

    inventory = "".join(
        f"<li><b>{e(item['name'])}</b> · "
        f"{e(item['kind'])}<br><small>{e(asset_id)}</small></li>"
        for asset_id, item in board["assets"].items()
    )

    return (
        '<!doctype html><html lang="id"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(board["title"])} — Storyboard</title>'
        '<style>'
        '*{box-sizing:border-box}'
        'body{margin:0;background:#F7EDDC;color:#40332D;'
        'font-family:system-ui,sans-serif;padding:24px}'
        'main{max-width:1400px;margin:auto}'
        '.grid{display:grid;grid-template-columns:'
        'repeat(auto-fit,minmax(310px,1fr));gap:20px}'
        'article{background:#FFFBF3;border:1px solid #DAC8AC;'
        'padding:18px;border-radius:18px}'
        'h1{margin-top:0}h2{font-size:19px}'
        'p,li{line-height:1.5}svg{width:100%;height:auto}'
        'small{overflow-wrap:anywhere}details{margin-top:16px}'
        '</style></head><body><main>'
        f'<h1>{e(board["title"])}</h1>'
        '<p>Blocking adegan: posisi aset dan rencana shot. '
        'Ilustrasi final dibuat pada tahap berikutnya.</p>'
        '<p>Garis putus-putus menghubungkan properti '
        'dengan pemegangnya.</p>'
        f'<div class="grid">{"".join(cards)}</div>'
        '<details><summary>Manifest aset</summary>'
        f'<ul>{inventory}</ul></details>'
        '</main></body></html>'
    )