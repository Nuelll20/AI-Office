"""Terima /tema dari Telegram dan simpan sebagai brief konten."""
import argparse
import sqlite3
import time
from contextlib import closing

from . import db
from .config import DB_PATH, env
from .telegram import _call


SCHEMA = """
CREATE TABLE IF NOT EXISTS content_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    update_id INTEGER NOT NULL,
    chat_id TEXT NOT NULL,
    theme TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    created_at REAL NOT NULL,
    UNIQUE(bot_id, update_id)
);
CREATE TABLE IF NOT EXISTS telegram_cursors (
    bot_id TEXT PRIMARY KEY,
    next_offset INTEGER NOT NULL
);
"""


def initialize():
    db.init()
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def api(method, payload, timeout=30):
    try:
        response = _call(method, payload, timeout=timeout)
    except Exception as exc:
        code = getattr(exc, "code", "-")
        raise RuntimeError(
            f"Telegram {method} gagal: {type(exc).__name__}, HTTP {code}."
        ) from None

    if not response.get("ok"):
        raise RuntimeError(
            f"Telegram {method} ditolak, kode {response.get('error_code', '-')} ."
        )

    return response["result"]


def offset(bot_id):
    row = db.one(
        "SELECT next_offset FROM telegram_cursors WHERE bot_id=?",
        (bot_id,),
    )
    return row["next_offset"] if row else 0


def accept(update, bot_id, username, owner):
    """Simpan brief, log UI, dan cursor dalam satu transaksi."""
    uid = int(update["update_id"])
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = (message.get("text") or "").strip()

    parts = text.split(maxsplit=1)
    command = parts[0].lower() if parts else ""

    allowed = (
        chat.get("type") == "private"
        and str(chat.get("id")) == owner
        and str(sender.get("id")) == owner
        and command in ("/tema", f"/tema@{username.lower()}")
    )

    theme = parts[1].strip() if allowed and len(parts) == 2 else ""
    reply = None

    with closing(sqlite3.connect(DB_PATH, timeout=15)) as conn:
        with conn:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT next_offset FROM telegram_cursors WHERE bot_id=?",
                (bot_id,),
            ).fetchone()

            if row and uid < row[0]:
                return None

            if allowed and not theme:
                reply = "Gunakan: /tema Tema besar konten minggu ini"

            elif allowed:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO content_briefs "
                    "(bot_id,update_id,chat_id,theme,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (bot_id, uid, owner, theme, time.time()),
                )

                if cur.rowcount:
                    brief_id = cur.lastrowid

                    conn.execute(
                        "INSERT INTO events"
                        "(ts,actor,target,action,text,video_id) "
                        "VALUES(?,?,?,?,?,?)",
                        (
                            time.time(),
                            "adit",
                            None,
                            "say",
                            f"Brief #{brief_id} diterima dari Telegram: {theme}",
                            None,
                        ),
                    )

                    reply = (
                        f"Adit: Tema tersimpan sebagai brief #{brief_id}. "
                        "Status: menunggu pengembangan ide."
                    )

            conn.execute(
                "INSERT INTO telegram_cursors(bot_id,next_offset) "
                "VALUES(?,?) "
                "ON CONFLICT(bot_id) DO UPDATE SET "
                "next_offset=excluded.next_offset",
                (bot_id, uid + 1),
            )

    return reply


def listen(once=False):
    owner = env("TELEGRAM_CHAT_ID").strip()

    if not env("TELEGRAM_BOT_TOKEN") or not owner.isdecimal():
        raise RuntimeError(
            "Isi token dan ID chat pribadi di .env terlebih dahulu."
        )

    bot = api("getMe", {})
    bot_id = str(bot["id"])

    if api("getWebhookInfo", {}).get("url"):
        raise RuntimeError(
            "Webhook masih aktif. Listener belum dijalankan."
        )

    print(
        f"Penerima tema aktif: @{bot['username']}. "
        "Ctrl+C untuk berhenti."
    )

    while True:
        updates = api(
            "getUpdates",
            {
                "offset": offset(bot_id),
                "timeout": 0 if once else 20,
                "limit": 100,
                "allowed_updates": ["message"],
            },
            timeout=35,
        )

        for update in sorted(updates, key=lambda item: item["update_id"]):
            reply = accept(update, bot_id, bot["username"], owner)

            if reply:
                print(reply)

                try:
                    api(
                        "sendMessage",
                        {"chat_id": owner, "text": reply},
                    )
                except RuntimeError as exc:
                    print(
                        "Balasan gagal; data yang tersimpan tetap aman. "
                        f"{exc}"
                    )

        if once:
            print("Pemeriksaan satu batch selesai.")
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--once",
        action="store_true",
        help="Baca satu batch pesan",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="Lihat 20 brief terakhir",
    )

    args = parser.parse_args()

    try:
        initialize()

        if args.list:
            rows = db.query(
                "SELECT * FROM content_briefs "
                "ORDER BY id DESC LIMIT 20"
            )

            for row in rows:
                print(
                    f"#{row['id']} | {row['status']} | {row['theme']}"
                )

            if not rows:
                print("Belum ada brief tema.")

        else:
            listen(once=args.once)

    except KeyboardInterrupt:
        print("\nPenerima tema dihentikan.")

    except Exception as exc:
        if isinstance(exc, RuntimeError):
            print(exc)
        else:
            print(
                f"Proses gagal: {type(exc).__name__}. "
                "Data tersimpan tetap tersedia."
            )

        raise SystemExit(1) from None


if __name__ == "__main__":
    main()