"""Buat gambar per adegan dan gunakan kembali hasil yang masih cocok."""
import argparse
import hashlib
import json

from . import db, events
from .comfyui import ComfyUI, workflow
from .config import OUTPUT_DIR, ROOT, env


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def image_hash(path):
    data = path.read_bytes()

    if len(data) < 45 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"PNG tidak valid: {path.name}")

    if not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
        raise ValueError(f"PNG belum lengkap: {path.name}")

    return hashlib.sha256(data).hexdigest()


def cached(path, fingerprint):
    try:
        meta = json.loads(
            path.with_suffix(".image.json").read_text(
                encoding="utf-8"
            )
        )
        return (
            meta["fingerprint"] == fingerprint
            and meta["sha256"] == image_hash(path)
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def generate_images(video_id, limit=None, check_only=False):
    if limit is not None and limit < 1:
        raise ValueError("Limit minimal 1.")

    if not db.get_video(video_id):
        raise ValueError(f"Video {video_id} tidak ditemukan.")

    out = OUTPUT_DIR / video_id
    scene_file = out / "scenes.json"

    if not scene_file.exists():
        raise ValueError(
            "scenes.json belum ada. "
            "Selesaikan tahap naskah dan scene dahulu."
        )

    data = json.loads(scene_file.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Daftar scene kosong atau tidak valid.")

    if data.get("video_id") != video_id:
        raise ValueError("video_id dalam scenes.json tidak cocok.")

    checkpoint = env("COMFYUI_CHECKPOINT")
    if not checkpoint:
        raise ValueError("Isi COMFYUI_CHECKPOINT di .env dahulu.")

    records, seen = [], set()

    for scene in scenes:
        sid = scene.get("id")
        prompt = scene.get("final_prompt")

        if type(sid) is not int or sid < 1 or sid in seen:
            raise ValueError(
                "ID scene harus bilangan positif "
                "dan tidak boleh sama."
            )

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(
                f"final_prompt scene {sid} kosong atau tidak valid."
            )

        seen.add(sid)

        # Seed tetap untuk pasangan video dan nomor adegan.
        seed = int(
            hashlib.sha256(
                f"{video_id}:{sid}".encode()
            ).hexdigest()[:8],
            16,
        )

        graph = workflow(checkpoint, prompt, seed)
        fingerprint = hashlib.sha256(
            json.dumps(
                graph,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        path = out / "images" / f"scene-{sid:03d}.png"
        records.append(
            (
                scene,
                path,
                seed,
                fingerprint,
                cached(path, fingerprint),
            )
        )

    ready = sum(item[4] for item in records)
    print(f"Gambar cocok dan tersedia: {ready}/{len(scenes)}")

    if check_only:
        for scene, _, _, _, valid in records:
            label = "SIAP" if valid else "PERLU DIBUAT"
            print(f"Scene {scene['id']:03d}: {label}")
        return ready

    (out / "images").mkdir(exist_ok=True)

    for scene, path, _, _, valid in records:
        scene["image_status"] = "ready" if valid else "pending"
        scene.pop("image_error", None)

        if valid:
            scene["image_path"] = path.relative_to(ROOT).as_posix()
        else:
            scene.pop("image_path", None)

    def save(status):
        write_json(scene_file, data)
        db.update_video(video_id, scenes=data, status=status)

    save(
        "images_processing"
        if ready < len(scenes)
        else "images_ready"
    )

    client, made = ComfyUI(), 0

    for scene, path, seed, fingerprint, valid in records:
        sid = scene["id"]

        if valid:
            print(f"LEWATI scene {sid:03d}: hasil masih cocok.")
            continue

        if limit is not None and made >= limit:
            break

        try:
            events.emit(
                "bayu",
                "work",
                f"Membuat gambar scene {sid}...",
                video_id=video_id,
            )

            client.generate(
                scene["final_prompt"],
                path,
                seed=seed,
            )

            write_json(
                path.with_suffix(".image.json"),
                {
                    "fingerprint": fingerprint,
                    "sha256": image_hash(path),
                    "seed": seed,
                },
            )

            scene["image_status"] = "ready"
            scene["image_path"] = path.relative_to(ROOT).as_posix()

            made += 1
            ready += 1

            save("images_processing")
            print(f"SELESAI scene {sid:03d}: {path}")

        except (Exception, KeyboardInterrupt) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)

            scene["image_status"] = (
                "pending" if interrupted else "failed"
            )
            scene["image_error"] = (
                str(exc) or "Dihentikan pengguna."
            )

            save(
                "images_partial"
                if interrupted
                else "images_failed"
            )

            events.emit(
                "bayu",
                "say",
                f"Proses berhenti pada scene {sid}.",
                video_id=video_id,
            )
            raise

    status = (
        "images_ready"
        if ready == len(scenes)
        else "images_partial"
    )
    save(status)

    events.emit(
        "bayu",
        "say",
        f"Gambar siap {ready}/{len(scenes)}.",
        video_id=video_id,
    )

    print(
        f"Status: {status}. "
        f"Gambar baru: {made}. "
        f"Total siap: {ready}/{len(scenes)}."
    )
    return ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    db.init()

    try:
        generate_images(args.id, args.limit, args.check)
    except KeyboardInterrupt:
        parser.exit(
            130,
            "Dihentikan. Periksa antrean ComfyUI "
            "sebelum menjalankan ulang.\n",
        )
    except (
        RuntimeError,
        ValueError,
        OSError,
        KeyError,
        TypeError,
    ) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()