"""Penerima cerita Telegram dengan penyimpanan pekerjaan secara atomik."""

import argparse
import time
from contextlib import closing

from . import db
from .config import env
from .story_context import make_brief
from .telegram import _call


SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_cursors(
    bot_id TEXT PRIMARY KEY,
    next_offset INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_story_messages(
    bot_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    PRIMARY KEY(bot_id, chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS telegram_intake_receipts(
    bot_id TEXT NOT NULL,
    update_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    video_id TEXT,
    chat_id TEXT,
    reply TEXT,
    sent_at REAL,
    PRIMARY KEY(bot_id, update_id)
);
"""

HELP = (
    "Adit siap menerima cerita.\n\n"
    "Kirim cerita sebagai pesan teks biasa, atau:\n"
    "/cerita Isi cerita Anda\n"
    "/tema Arahan cerita Anda\n"
    "/status untuk lima pekerjaan terbaru\n"
    "/status ID_PEKERJAAN untuk satu pekerjaan\n\n"
    "Saat ini cerita disimpan untuk tahap pengembangan berikutnya."
)


class TelegramError(RuntimeError):
    def __init__(self, method, code=None):
        self.code = code
        super().__init__(
            f"Telegram {method} gagal (HTTP {code or '-'})."
        )


def api(method, payload, timeout=35):
    try:
        response = _call(
            method,
            payload,
            timeout=timeout,
        )

    except Exception as exc:
        raise TelegramError(
            method,
            getattr(exc, "code", None),
        ) from None

    if not isinstance(response, dict) or not response.get("ok"):
        code = (
            response.get("error_code")
            if isinstance(response, dict)
            else None
        )

        raise TelegramError(method, code)

    return response["result"]


def initialize():
    db.init()

    with closing(db._conn()) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def offset(bot_id):
    row = db.one(
        "SELECT next_offset FROM telegram_cursors WHERE bot_id=?",
        (bot_id,),
    )

    return row["next_offset"] if row else 0


def parse_message(message, username):
    text = message.get("text")

    if not isinstance(text, str) or not text.strip():
        return (
            "help",
            "Kirim cerita sebagai pesan teks. "
            "Foto, video, dan audio belum diproses pada tahap ini.",
        )

    text = text.strip()

    if not text.startswith("/"):
        return "story", text

    parts = text.split(maxsplit=1)
    command, _, mention = parts[0].partition("@")

    if mention and mention.lower() != username.lower():
        return "ignored", None

    body = parts[1].strip() if len(parts) == 2 else ""
    command = command.lower()

    if command in ("/start", "/help"):
        return "help", HELP

    if command in ("/cerita", "/tema"):
        if body:
            return "story", body

        return "help", "Gunakan: /cerita Isi cerita Anda"

    if command == "/status":
        return "status", body

    return (
        "help",
        "Perintah belum tersedia. "
        "Gunakan /help untuk melihat perintah aktif.",
    )


def status_text(connection, video_id):
    if video_id:
        rows = connection.execute(
            "SELECT id,status FROM videos WHERE id=?",
            (video_id,),
        ).fetchall()

    else:
        rows = connection.execute(
            "SELECT id,status FROM videos "
            "ORDER BY created_at DESC,id DESC LIMIT 5"
        ).fetchall()

    return (
        "\n".join(
            f"{row['id']}: {row['status']}"
            for row in rows
        )
        or "Pekerjaan tidak ditemukan."
    )


def accept(update, bot_id, username, owner):
    uid = update.get("update_id")

    if type(uid) is not int or uid < 0:
        raise ValueError("update_id Telegram tidak valid.")

    bot_id = str(bot_id)
    owner = str(owner)

    with closing(db._conn()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                "SELECT 1 FROM telegram_intake_receipts "
                "WHERE bot_id=? AND update_id=?",
                (bot_id, uid),
            ).fetchone()

            if existing:
                return None

            previous = connection.execute(
                "SELECT next_offset FROM telegram_cursors "
                "WHERE bot_id=?",
                (bot_id,),
            ).fetchone()

            if previous and uid < previous[0]:
                return None

            message = update.get("message") or {}
            chat = message.get("chat") or {}
            sender = message.get("from") or {}

            allowed = (
                chat.get("type") == "private"
                and str(chat.get("id")) == owner
                and str(sender.get("id")) == owner
            )

            kind = "ignored"
            reply = None
            video_id = None

            if allowed:
                kind, body = parse_message(message, username)

                if kind == "story":
                    message_id = message.get("message_id")

                    if type(message_id) is not int or message_id < 1:
                        raise ValueError(
                            "message_id Telegram tidak valid."
                        )

                    old = connection.execute(
                        "SELECT video_id FROM telegram_story_messages "
                        "WHERE bot_id=? AND chat_id=? AND message_id=?",
                        (bot_id, owner, message_id),
                    ).fetchone()

                    if old:
                        kind = "duplicate"
                        video_id = old["video_id"]

                    else:
                        brief = make_brief(
                            body,
                            source="telegram",
                        )

                        brief["telegram"] = {
                            "bot_id": bot_id,
                            "chat_id": owner,
                            "message_id": message_id,
                            "update_id": uid,
                        }

                        brief["original_message"] = message["text"]

                        video_id = db.add_video(
                            body,
                            brief=brief,
                            connection=connection,
                        )

                        connection.execute(
                            "INSERT INTO telegram_story_messages "
                            "VALUES(?,?,?,?)",
                            (
                                bot_id,
                                owner,
                                message_id,
                                video_id,
                            ),
                        )

                        now = time.time()

                        connection.executemany(
                            "INSERT INTO events"
                            "(ts,actor,target,action,text,video_id) "
                            "VALUES(?,?,?,?,?,?)",
                            [
                                (
                                    now,
                                    "adit",
                                    "telegram",
                                    "walk_to",
                                    "Mengambil cerita dari Telegram.",
                                    video_id,
                                ),
                                (
                                    now,
                                    "adit",
                                    None,
                                    "say",
                                    f"Brief {video_id} diterima: "
                                    f"{body[:100]}",
                                    video_id,
                                ),
                                (
                                    now,
                                    "adit",
                                    None,
                                    "back",
                                    "Brief tersimpan; menunggu "
                                    "pengembangan cerita.",
                                    video_id,
                                ),
                            ],
                        )

                        reply = (
                            "Adit: Cerita tersimpan.\n"
                            f"ID: {video_id}\n"
                            "Status: menunggu pengembangan cerita."
                        )

                elif kind == "status":
                    reply = status_text(connection, body)

                elif kind == "help":
                    reply = body

            connection.execute(
                "INSERT INTO telegram_intake_receipts"
                "(bot_id,update_id,kind,video_id,chat_id,reply) "
                "VALUES(?,?,?,?,?,?)",
                (
                    bot_id,
                    uid,
                    kind,
                    video_id,
                    owner if allowed else None,
                    reply,
                ),
            )

            connection.execute(
                "INSERT INTO telegram_cursors(bot_id,next_offset) "
                "VALUES(?,?) "
                "ON CONFLICT(bot_id) DO UPDATE SET "
                "next_offset=MAX(next_offset,excluded.next_offset)",
                (bot_id, uid + 1),
            )

    return {
        "kind": kind,
        "video_id": video_id,
    }


def flush_replies(bot_id):
    rows = db.query(
        "SELECT * FROM telegram_intake_receipts "
        "WHERE bot_id=? "
        "AND reply IS NOT NULL "
        "AND sent_at IS NULL "
        "ORDER BY update_id LIMIT 20",
        (str(bot_id),),
    )

    for row in rows:
        try:
            api(
                "sendMessage",
                {
                    "chat_id": row["chat_id"],
                    "text": row["reply"],
                },
            )

        except TelegramError as exc:
            print(
                f"{exc} Balasan tetap tersimpan "
                "untuk dicoba kembali.",
                flush=True,
            )

            return

        db.run(
            "UPDATE telegram_intake_receipts SET sent_at=? "
            "WHERE bot_id=? AND update_id=?",
            (
                time.time(),
                str(bot_id),
                row["update_id"],
            ),
        )


def listen(once=False):
    owner = env("TELEGRAM_CHAT_ID").strip()

    if (
        not env("TELEGRAM_BOT_TOKEN").strip()
        or not owner.isdecimal()
    ):
        raise ValueError(
            "Isi TELEGRAM_BOT_TOKEN dan ID chat pribadi "
            "TELEGRAM_CHAT_ID di .env."
        )

    bot = api("getMe", {})
    bot_id = str(bot["id"])

    if api("getWebhookInfo", {}).get("url"):
        raise ValueError(
            "Webhook bot masih aktif. "
            "Listener polling belum dijalankan."
        )

    print(
        f"Penerima cerita aktif: @{bot['username']}. "
        "Ctrl+C untuk berhenti.",
        flush=True,
    )

    while True:
        flush_replies(bot_id)

        try:
            updates = api(
                "getUpdates",
                {
                    "offset": offset(bot_id),
                    "timeout": 0 if once else 20,
                    "limit": 100,
                    "allowed_updates": ["message"],
                },
            )

        except TelegramError as exc:
            if once or exc.code in (400, 401, 403, 404, 409):
                raise

            print(
                f"{exc} Mencoba kembali dalam 3 detik.",
                flush=True,
            )

            time.sleep(3)
            continue

        for update in sorted(
            updates,
            key=lambda item: item["update_id"],
        ):
            result = accept(
                update,
                bot_id,
                bot["username"],
                owner,
            )

            if result and result["kind"] == "story":
                print(
                    f"Cerita masuk: {result['video_id']}",
                    flush=True,
                )

        flush_replies(bot_id)

        if once:
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--once",
        action="store_true",
        help="Baca satu batch pesan",
    )

    args = parser.parse_args()

    try:
        initialize()
        listen(args.once)

    except KeyboardInterrupt:
        print("\nPenerima cerita dihentikan.")

    except (ValueError, TelegramError) as exc:
        message = str(exc)

        if isinstance(exc, TelegramError) and exc.code == 409:
            message += (
                " Hentikan listener bot lain "
                "yang memakai token yang sama."
            )

        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()