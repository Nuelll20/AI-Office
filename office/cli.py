import argparse
import re
import time

from . import db, pipeline, scout, server, telegram


def cmd_scout(a):
    scout.run(a.n)


def cmd_pick(a):
    batch = scout.latest_batch()
    if not batch:
        print("Belum ada ide. Jalankan dulu:  python -m office.cli scout")
        return
    nums = list(a.numbers)
    if not nums:
        if not telegram.configured():
            print("Telegram belum diset. Pilih manual, contoh:  python -m office.cli pick 1 3 5")
            return
        print("Menunggu balasan di Telegram (contoh: 1 3 5)...")
        end = time.time() + a.wait
        while time.time() < end and not nums:
            txt = telegram.wait_reply(int(max(1, min(60, end - time.time()))))
            if txt:
                nums = [int(x) for x in re.findall(r"\d+", txt)]
    if not nums:
        print("Tidak ada pilihan.")
        return
    picked = []
    for i, idea in enumerate(batch, 1):
        if i in nums:
            db.run("UPDATE ideas SET status='picked' WHERE id=?", (idea["id"],))
            picked.append(idea)
        elif idea["status"] == "proposed":
            db.run("UPDATE ideas SET status='rejected' WHERE id=?", (idea["id"],))
    for idea in picked:
        vid = db.add_video(idea["text"])
        print(f"Masuk antrean: {vid}  {idea['text'][:70]}")
    telegram.send(f"✅ {len(picked)} ide masuk antrean produksi")


def cmd_idea(a):
    vid = db.add_video(a.text)
    print(f"Masuk antrean: {vid}")


def cmd_produce(a):
    if a.id:
        pipeline.produce(a.id)
    elif a.all:
        while pipeline.produce_next():
            pass
    else:
        pipeline.produce_next()


def cmd_status(a):
    rows = db.query("SELECT id,status,idea FROM videos ORDER BY created_at, id")
    if not rows:
        print("Belum ada video.")
    for r in rows:
        print(f"{r['id']:<14} {r['status']:<13} {r['idea'][:60]}")


def cmd_demo(a):
    vid = db.add_video("Penjaga mercusuar menerima surat tiap malam dari orang yang sudah meninggal 50 tahun lalu")
    pipeline.produce(vid)


def main():
    p = argparse.ArgumentParser(prog="office")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(f=lambda a: print("DB siap."))
    s = sub.add_parser("scout"); s.add_argument("-n", type=int, default=6); s.set_defaults(f=cmd_scout)
    k = sub.add_parser("pick"); k.add_argument("numbers", nargs="*", type=int)
    k.add_argument("--wait", type=int, default=600); k.set_defaults(f=cmd_pick)
    i = sub.add_parser("idea"); i.add_argument("text"); i.set_defaults(f=cmd_idea)
    r = sub.add_parser("produce"); r.add_argument("--all", action="store_true")
    r.add_argument("--id"); r.set_defaults(f=cmd_produce)
    sub.add_parser("status").set_defaults(f=cmd_status)
    sub.add_parser("demo").set_defaults(f=cmd_demo)
    u = sub.add_parser("ui"); u.add_argument("--port", type=int, default=8000)
    u.set_defaults(f=lambda a: server.serve(a.port))

    a = p.parse_args()
    db.init()
    a.f(a)


if __name__ == "__main__":
    main()
