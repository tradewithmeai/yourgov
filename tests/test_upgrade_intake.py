import email
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "upgrade-intake"))

import core  # noqa: E402
from adapters import email_imap, telegram, whatsapp_jsonl  # noqa: E402
import triage_queue  # noqa: E402
import inspect_queue  # noqa: E402

from app import app  # noqa: E402


TG_CFG = {
    "telegram": {
        "telegram_bot_token": "test-token",
        "allowed_chat_ids": [-100123],
        "allowed_usernames": ["neil"],
    }
}
EMAIL_CFG = {
    "email": {
        "imap_host": "imap.example.com",
        "username": "feedback@example.com",
        "password": "x",
        "allowed_senders": ["someone@example.com"],
        "allowed_recipients": ["feedback@example.com"],
    }
}
WA_CFG = {
    "whatsapp": {
        "allowed_chat_jids": ["123-456@g.us"],
        "allowed_sender_jids": ["447700900000@s.whatsapp.net"],
    }
}


class TelegramNormaliseTests(unittest.TestCase):
    def test_allowlisted_text_message_normalises(self):
        update = {
            "update_id": 5,
            "message": {
                "message_id": 42,
                "text": "The vote count is wrong on the Brexit division page.",
                "chat": {"id": -100123, "title": "mygov-feedback"},
                "from": {"first_name": "Neil", "username": "neil"},
            },
        }
        rec = telegram.normalize_update(update, TG_CFG)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["source"], "telegram")
        self.assertEqual(rec["contributor"], "Neil")
        self.assertEqual(rec["source_message_id"], "42")
        self.assertIn("vote count", rec["raw_message"])

    def test_non_allowlisted_chat_dropped(self):
        update = {
            "update_id": 6,
            "message": {
                "message_id": 1,
                "text": "hello there friend",
                "chat": {"id": -999, "title": "random"},
                "from": {"first_name": "Mallory"},
            },
        }
        self.assertIsNone(telegram.normalize_update(update, TG_CFG))


class EmailNormaliseTests(unittest.TestCase):
    def _msg(self, frm, to, subject, body):
        raw = (
            f"From: {frm}\r\n"
            f"To: {to}\r\n"
            f"Subject: {subject}\r\n"
            f"Message-ID: <abc@example.com>\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{body}\r\n"
        ).encode("utf-8")
        return email.message_from_bytes(raw)

    def test_allowlisted_sender_normalises(self):
        msg = self._msg(
            "Someone <someone@example.com>",
            "feedback@example.com",
            "Suggestion",
            "It would be nice if you could add a dark mode to the map.",
        )
        rec = email_imap.normalize_email(msg, EMAIL_CFG)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["source"], "email")
        self.assertEqual(rec["contributor"], "Someone")
        self.assertEqual(rec["contact_ref"], "someone@example.com")
        self.assertIn("dark mode", rec["raw_message"])
        self.assertEqual(rec["kind"], "feature")

    def test_non_allowlisted_dropped(self):
        msg = self._msg("spam@evil.com", "other@example.com", "hi", "buy now")
        self.assertIsNone(email_imap.normalize_email(msg, EMAIL_CFG))


class WhatsAppNormaliseTests(unittest.TestCase):
    def test_bridge_record_normalises(self):
        obj = {
            "messageId": "WA123",
            "chatJid": "123-456@g.us",
            "senderJid": "447700900000@s.whatsapp.net",
            "senderName": "Pat",
            "kind": "text",
            "text": "The search is broken when I type a postcode with a space.",
            "fromMe": False,
        }
        rec = whatsapp_jsonl.normalize_record(obj, WA_CFG)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["source"], "whatsapp")
        self.assertEqual(rec["contributor"], "Pat")
        self.assertEqual(rec["source_message_id"], "WA123")
        self.assertEqual(rec["kind"], "bug")

    def test_from_me_dropped(self):
        obj = {
            "messageId": "WA999",
            "chatJid": "123-456@g.us",
            "senderJid": "447700900000@s.whatsapp.net",
            "text": "our own outgoing message",
            "fromMe": True,
        }
        self.assertIsNone(whatsapp_jsonl.normalize_record(obj, WA_CFG))

    def test_document_with_caption_keeps_filename_evidence(self):
        obj = {
            "messageId": "WA200",
            "chatJid": "123-456@g.us",
            "senderJid": "x@s.whatsapp.net",
            "kind": "document",
            "text": "Here is a screenshot of the broken layout on mobile.",
            "fileName": "screenshot.png",
            "fromMe": False,
        }
        rec = whatsapp_jsonl.normalize_record(obj, WA_CFG)
        self.assertIn("screenshot.png", rec["evidence"])


class SchemaAndClassificationTests(unittest.TestCase):
    def test_source_enum_supports_all_three(self):
        self.assertEqual(set(core.SOURCES), {"telegram", "whatsapp", "email"})

    def test_complaint_vs_suggestion_kind(self):
        self.assertEqual(core.classify_kind("This is terrible, I am really disappointed"), "complaint")
        self.assertEqual(core.classify_kind("You should consider adding filters"), "suggestion")
        self.assertEqual(core.classify_kind("Thanks, this is great work!"), "praise")
        self.assertEqual(core.classify_kind("The page crashes with a 500 error"), "bug")

    def test_category_still_classifies(self):
        self.assertEqual(core.classify_category("the colour and spacing is confusing"), "ux")
        self.assertEqual(core.classify_category("please add a feature"), "feature")


class JunkFilterTests(unittest.TestCase):
    def test_empty_is_junk(self):
        is_junk, reason = core.detect_junk("   ")
        self.assertTrue(is_junk)
        self.assertEqual(reason, "empty_after_strip")

    def test_link_only_is_junk(self):
        is_junk, reason = core.detect_junk("https://spam.example.com/win")
        self.assertTrue(is_junk)
        self.assertEqual(reason, "link_only")

    def test_too_many_urls_is_junk(self):
        text = "a http://x.com b http://y.com c http://z.com d http://w.com"
        is_junk, reason = core.detect_junk(text)
        self.assertTrue(is_junk)
        self.assertEqual(reason, "too_many_urls")

    def test_spam_phrase_is_junk(self):
        is_junk, reason = core.detect_junk("Free bitcoin crypto giveaway, double your money!")
        self.assertTrue(is_junk)
        self.assertTrue(reason.startswith("spam_phrase:"))

    def test_repeated_chars_is_junk(self):
        is_junk, reason = core.detect_junk("aaaaaaaaaaaaaaaa")
        self.assertTrue(is_junk)
        self.assertEqual(reason, "repeated_chars")

    def test_too_short_is_junk_unless_bug(self):
        self.assertTrue(core.detect_junk("ok")[0])
        self.assertFalse(core.detect_junk("login bug")[0])

    def test_real_feedback_is_not_junk(self):
        is_junk, _ = core.detect_junk("The MP profile page does not show recent votes.")
        self.assertFalse(is_junk)

    def test_make_record_marks_junk_and_preserves_raw(self):
        rec = core.make_record(
            source="email",
            channel_name="x",
            contributor="y",
            source_message_id="1",
            text="Free bitcoin crypto giveaway!!!",
        )
        self.assertEqual(rec["status"], "junk")
        self.assertIn("junk_reason", rec)
        self.assertEqual(rec["raw_message"], "Free bitcoin crypto giveaway!!!")


class DedupeTests(unittest.TestCase):
    def test_stable_id_is_deterministic(self):
        a = core.stable_id("chan", "neil", "the same summary")
        b = core.stable_id("CHAN", "Neil", "The Same Summary")
        self.assertEqual(a, b)

    def test_different_summary_different_id(self):
        a = core.stable_id("chan", "neil", "one thing")
        b = core.stable_id("chan", "neil", "another thing")
        self.assertNotEqual(a, b)


class QueueIOTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp()) / "q.jsonl"

    def test_append_preserves_raw_message(self):
        rec = core.make_record(
            source="telegram", channel_name="c", contributor="p",
            source_message_id="9", text="A genuine bug report about the map.",
        )
        core.append_records([rec], queue_file=self.tmp)
        loaded = core.load_records(queue_file=self.tmp)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["raw_message"], "A genuine bug report about the map.")

    def test_latest_records_resolves_repeated_ids(self):
        rec = core.make_record(
            source="telegram", channel_name="c", contributor="p",
            source_message_id="9", text="A genuine bug report about the map.",
        )
        core.append_records([rec], queue_file=self.tmp)
        decided = dict(rec)
        decided["status"] = "accepted"
        core.append_records([decided], queue_file=self.tmp)

        all_lines = core.load_records(queue_file=self.tmp)
        self.assertEqual(len(all_lines), 2)  # append-only: original line still present
        latest = core.latest_records(all_lines)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["status"], "accepted")


class TriageTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp()) / "q.jsonl"
        self._orig = core.QUEUE_FILE
        core.QUEUE_FILE = self.tmp

    def tearDown(self):
        core.QUEUE_FILE = self._orig

    def test_triage_appends_decision_without_editing(self):
        rec = core.make_record(
            source="email", channel_name="c", contributor="p",
            source_message_id="1", text="The division list is missing a record.",
        )
        core.append_records([rec], queue_file=self.tmp)
        before = self.tmp.read_text(encoding="utf-8")

        rc = triage_queue.main(["accept", rec["id"][:8], "--reason", "valid", "--by", "tester"])
        self.assertEqual(rc, 0)

        after_lines = core.load_records(queue_file=self.tmp)
        self.assertEqual(len(after_lines), 2)
        # original first line is byte-for-byte unchanged (append-only)
        self.assertTrue(self.tmp.read_text(encoding="utf-8").startswith(before))

        latest = core.latest_records(after_lines)[0]
        self.assertEqual(latest["status"], "accepted")
        self.assertEqual(latest["decision_reason"], "valid")
        self.assertEqual(latest["decided_by"], "tester")
        self.assertEqual(latest["id"], rec["id"])  # id preserved across decision

    def test_triage_unknown_id_fails(self):
        rc = triage_queue.main(["reject", "deadbeef", "--reason", "n/a"])
        self.assertEqual(rc, 1)


class FeedbackRouteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_feedback_returns_200_and_three_channels(self):
        r = self.client.get("/feedback")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("WhatsApp", body)
        self.assertIn("Telegram", body)
        self.assertIn("Email", body)

    def test_feedback_uses_fallback_email(self):
        r = self.client.get("/feedback")
        self.assertIn("captain@solvx.uk", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
