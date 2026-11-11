"""Aksi benda berdasarkan jadwal dialog, tanpa aturan khusus tokoh."""

import math

from ..bible import entries, object_fields, require, text


ACTIONS = {
    "raise_prop": (25, 140),
    "show_prop": (50, 120),
}


def validate_actions(data):
    props = {
        item["id"]: item
        for item in data["props"]
    }

    lines = {
        line["id"]: index
        for index, line in enumerate(data["lines"])
    }

    for line in data["lines"]:
        if "gesture_target" in line:
            text(
                line["gesture_target"],
                "gesture_target",
            )

            require(
                line.get("gesture") == "point",
                "gesture_target",
                "sasaran hanya untuk gestur point",
            )

            require(
                line["gesture_target"] in props,
                "gesture_target",
                "benda sasaran tidak hadir",
            )

    for index, action in entries(
        data.get("actions", []),
        "actions",
    ):
        path = f"actions[{index}]"

        object_fields(
            action,
            path,
            "kind actor prop from_line to_line",
        )

        for key in action:
            text(
                action[key],
                path + "." + key,
            )

        require(
            action["kind"] in ACTIONS,
            path,
            "jenis aksi tidak dikenal",
        )

        require(
            action["actor"] in data["actors"],
            path,
            "pelaku tidak hadir",
        )

        require(
            action["prop"] in props,
            path,
            "benda tidak hadir",
        )

        require(
            props[action["prop"]]["owner"] == action["actor"],
            path,
            "pelaku harus memegang benda",
        )

        require(
            sum(
                item["owner"] == action["actor"]
                for item in props.values()
            ) == 1,
            path,
            "aksi ini memerlukan satu benda di tangan",
        )

        require(
            action["from_line"] in lines
            and action["to_line"] in lines,
            path,
            "acuan dialog tidak dikenal",
        )

        require(
            lines[action["from_line"]]
            <= lines[action["to_line"]],
            path,
            "urutan dialog terbalik",
        )


def compile_actions(data, lines, fps):
    schedule = {
        line["id"]: line
        for line in lines
    }

    tracks = []

    for action in data.get("actions", []):
        start = schedule[
            action["from_line"]
        ]["start_frame"]

        release = max(
            1,
            round(0.35 * fps),
        )

        end = (
            schedule[action["to_line"]]["end_frame"]
            + release
        )

        track = dict(
            action,
            start_frame=start,
            end_frame=end,
            release_frames=release,
        )

        for other in tracks:
            require(
                other["actor"] != track["actor"]
                or track["end_frame"] <= other["start_frame"]
                or track["start_frame"] >= other["end_frame"],
                "actions",
                "aksi tangan pelaku saling bertumpuk",
            )

        tracks.append(track)

    return tracks


def sample_action(tracks, actor, index, fps):
    for track in tracks:
        if (
            track["actor"] != actor
            or not track["start_frame"] <= index < track["end_frame"]
        ):
            continue

        attack = min(
            max(1, round(0.4 * fps)),
            (track["end_frame"] - track["start_frame"]) / 2,
        )

        value = min(
            1,
            (index - track["start_frame"]) / attack,
            (track["end_frame"] - index)
            / track["release_frames"],
        )

        weight = value * value * (3 - 2 * value)

        return track["kind"], weight

    return None, 0.0


def pointing_angles(target, head, direction, scale, co, si):
    # Ubah sasaran dunia menjadi koordinat lokal lengan.
    dx = direction * (target[0] - head[0]) / scale
    dy = (target[1] - head[1]) / scale

    x = dx * co + dy * si
    y = -dx * si + dy * co - 66.3

    distance = math.hypot(x, y)

    if distance < 1e-6:
        return 60, 95

    upper = 66.3
    lower = 73.1

    # Sisakan jarak antara tangan dan permukaan benda.
    clearance = (
        target[2] / scale
        if len(target) == 3
        else 25
    ) + 18

    reach = min(
        max(
            distance - clearance,
            lower - upper + 1,
        ),
        (upper + lower) * 0.95,
    )

    x *= reach / distance
    y *= reach / distance

    base = math.atan2(x, y)

    cosine = (
        upper * upper
        + reach * reach
        - lower * lower
    ) / (2 * upper * reach)

    angle = base - math.acos(
        max(-1, min(1, cosine))
    )

    elbow = (
        upper * math.sin(angle),
        upper * math.cos(angle),
    )

    return (
        math.degrees(angle),
        math.degrees(
            math.atan2(
                x - elbow[0],
                y - elbow[1],
            )
        ),
    )