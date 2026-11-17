import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from office import db, intake
from office.story_context import get_context


def message(
    uid=10,
    mid=1,
    text="Seekor ikan mencari jalan pulang.",
    owner=123,
):
    return {
        "update_id": uid,
        "message": {
            "message_id": mid,
            "chat": {
                "id": owner,
                "type": "private",
            },
            "from": {
                "id": owner,
            },
            "text": text,
        },
    }


class IntakeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)

        db_patch = patch.object(
            db,
            "DB_PATH",
            Path(folder.name) / "office.db",
        )

        db_patch.start()
        self.addCleanup(db_patch.stop)

        intake.initialize()

    def accept(self, update):
        return intake.accept(
            update,
            "99",
            "kantor_bot",
            "123",
        )

    def test_free_text_creates_context_and_office_events(self):
        result = self.accept(message())
        context = get_context(result["video_id"])

        self.assertEqual(
            context["brief"]["source"],
            "telegram",
        )

        self.assertEqual(
            context["brief"]["telegram"]["message_id"],
            1,
        )

        self.assertEqual(
            context["brief"]["raw_text"],
            message()["message"]["text"],
        )

        self.assertEqual(intake.offset("99"), 11)

        events = db.query(
            "SELECT * FROM events ORDER BY id"
        )

        self.assertEqual(
            [event["action"] for event in events],
            ["walk_to", "say", "back"],
        )

        self.assertTrue(
            all(
                event["video_id"] == result["video_id"]
                for event in events
            )
        )

    def test_replayed_update_does_not_create_another_job(self):
        self.accept(message())

        self.assertIsNone(self.accept(message()))

        self.assertEqual(
            len(db.query("SELECT id FROM videos")),
            1,
        )

        self.assertEqual(
            len(
                db.query(
                    "SELECT * FROM telegram_intake_receipts"
                )
            ),
            1,
        )

    def test_same_message_with_different_update_is_still_deduplicated(self):
        first = self.accept(message())
        second = self.accept(message(uid=11))

        self.assertEqual(second["kind"], "duplicate")
        self.assertEqual(first["video_id"], second["video_id"])

        self.assertEqual(
            len(db.query("SELECT id FROM videos")),
            1,
        )

        self.assertEqual(
            len(db.query("SELECT * FROM events")),
            3,
        )

    def test_same_text_in_new_messages_creates_separate_jobs(self):
        first = self.accept(message())

        second = self.accept(
            message(uid=11, mid=2)
        )

        self.assertNotEqual(
            first["video_id"],
            second["video_id"],
        )

    def test_other_sender_and_groups_do_not_create_jobs(self):
        self.accept(message(owner=456))

        group = message(uid=11)
        group["message"]["chat"]["type"] = "group"

        self.accept(group)

        self.assertEqual(
            db.query("SELECT id FROM videos"),
            [],
        )

        self.assertEqual(
            db.query(
                "SELECT reply FROM telegram_intake_receipts "
                "WHERE reply IS NOT NULL"
            ),
            [],
        )

    def test_commands_and_other_bot_mentions_are_not_stories(self):
        texts = (
            "/start",
            "/cerita",
            "/revisi",
            "/cerita@other_bot Isi cerita",
        )

        for i, text in enumerate(texts, 10):
            self.accept(
                message(
                    uid=i,
                    mid=i,
                    text=text,
                )
            )

        self.assertEqual(
            db.query("SELECT id FROM videos"),
            [],
        )

    def test_story_command_preserves_multiline_content(self):
        text = (
            "Baris pertama.\n"
            "Baris kedua dengan kejadian berbeda."
        )

        result = self.accept(
            message(
                text="/cerita@kantor_bot " + text
            )
        )

        self.assertEqual(
            get_context(result["video_id"])["brief"]["raw_text"],
            text,
        )

    def test_status_returns_real_job_status(self):
        job = self.accept(message())["video_id"]

        self.accept(
            message(
                uid=11,
                mid=2,
                text="/status " + job,
            )
        )

        row = db.one(
            "SELECT reply FROM telegram_intake_receipts "
            "WHERE update_id=11"
        )

        self.assertIn(job + ": queued", row["reply"])

        self.assertEqual(
            len(db.query("SELECT id FROM videos")),
            1,
        )

    def test_unsupported_media_do_not_create_partial_stories(self):
        update = message()

        del update["message"]["text"]

        update["message"]["photo"] = [
            {"file_id": "test"}
        ]

        update["message"]["caption"] = (
            "Caption bukan cerita lengkap"
        )

        self.accept(update)

        self.assertEqual(
            db.query("SELECT id FROM videos"),
            [],
        )

        self.assertIsNotNone(
            db.one(
                "SELECT reply FROM telegram_intake_receipts"
            )["reply"]
        )

    def test_database_failure_rolls_back_job_event_and_cursor(self):
        db.run(
            "CREATE TRIGGER fail_event "
            "BEFORE INSERT ON events "
            "BEGIN SELECT RAISE(ABORT, 'test'); END"
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.accept(message())

        self.assertEqual(
            db.query("SELECT id FROM videos"),
            [],
        )

        self.assertEqual(
            db.query(
                "SELECT * FROM telegram_intake_receipts"
            ),
            [],
        )

        self.assertEqual(
            db.query(
                "SELECT * FROM telegram_story_messages"
            ),
            [],
        )

        self.assertEqual(intake.offset("99"), 0)

        db.run("DROP TRIGGER fail_event")

        self.assertEqual(
            self.accept(message())["kind"],
            "story",
        )

    def test_unsent_reply_survives_retry(self):
        self.accept(message())

        with patch.object(
            intake,
            "api",
            side_effect=intake.TelegramError(
                "sendMessage",
                503,
            ),
        ):
            intake.flush_replies("99")

        self.assertIsNone(
            db.one(
                "SELECT sent_at FROM telegram_intake_receipts"
            )["sent_at"]
        )

        with patch.object(
            intake,
            "api",
            return_value={},
        ) as api:
            intake.flush_replies("99")
            intake.flush_replies("99")

        self.assertEqual(api.call_count, 1)

        self.assertIsNotNone(
            db.one(
                "SELECT sent_at FROM telegram_intake_receipts"
            )["sent_at"]
        )

    def test_existing_cursor_is_preserved(self):
        db.run(
            "INSERT INTO telegram_cursors VALUES(?,?)",
            ("99", 200),
        )

        intake.initialize()

        self.assertEqual(intake.offset("99"), 200)

        self.assertIsNone(
            self.accept(message(uid=199))
        )

    def test_api_error_does_not_print_credentials(self):
        with patch.object(
            intake,
            "_call",
            side_effect=RuntimeError(
                "https://botSECRET_TOKEN"
            ),
        ):
            with self.assertRaises(
                intake.TelegramError
            ) as raised:
                intake.api("getMe", {})

        self.assertNotIn(
            "SECRET_TOKEN",
            str(raised.exception),
        )


if __name__ == "__main__":
    unittest.main()