import contextlib
import email
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "upgrade-intake"))

import core  # noqa: E402
from adapters import email_imap, telegram, whatsapp_jsonl  # noqa: E402
import triage_queue  # noqa: E402
import inspect_queue  # noqa: E402
import intake  # noqa: E402

from app import app  # noqa: E402

try:
    import jsonschema  # type: ignore
except ImportError:  # validation test is skipped if the lib is absent
    jsonschema = None

SCHEMA_PATH = ROOT / "tools" / "upgrade-intake" / "schema.json"


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
                "chat": {"id": -100123, "title": "yourgov-feedback"},
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

    def test_quoted_comma_recipient_still_allowlisted(self):
        # RFC 5322 allows a comma inside a quoted display name; a naive
        # split(",") would lose the address and drop a legit message.
        msg = self._msg(
            "Someone <someone@example.com>",
            '"Feedback, YourGov" <feedback@example.com>',
            "Bug",
            "The map crashes on load.",
        )
        cfg = {"email": {"imap_host": "h", "username": "u", "password": "p",
                         "allowed_recipients": ["feedback@example.com"]}}
        rec = email_imap.normalize_email(msg, cfg)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["source"], "email")


class _FakeIMAP:
    """Minimal IMAP4_SSL stand-in: records fetch calls so a test can assert no
    message bodies were downloaded."""
    def __init__(self, uids):
        self._uids = uids
        self.fetched_calls = []

    def login(self, user, password):
        return ("OK", [b""])

    def select(self, folder, readonly=False):
        return ("OK", [b"1"])

    def uid(self, command, *args):
        if command == "search":
            return ("OK", [b" ".join(self._uids)])
        if command == "fetch":
            self.fetched_calls.append(args)
            return ("OK", [None])
        return ("NO", [b""])

    def logout(self):
        return ("BYE", [b""])


class EmailFetchFirstRunTests(unittest.TestCase):
    def test_first_run_fast_forwards_without_downloading_inbox(self):
        # Regression guard: with no cursor, the adapter must NOT do an "ALL"
        # backfill of a real (busy) mailbox — it should fast-forward to the
        # newest UID and ingest nothing, so only post-setup feedback is read.
        from unittest import mock
        fake = _FakeIMAP(uids=[b"1", b"2", b"1426"])
        cfg = {"email": {"imap_host": "h", "imap_port": 993, "username": "u",
                         "password": "p", "allowed_recipients": ["x@y.com"]}}
        with mock.patch.object(email_imap.imaplib, "IMAP4_SSL", return_value=fake), \
             mock.patch.object(email_imap, "read_cursor", return_value=0):
            messages, new_cursor = email_imap.fetch_messages(cfg)
        self.assertEqual(messages, [])            # nothing ingested on first run
        self.assertEqual(new_cursor, 1426)        # fast-forwarded to newest UID
        self.assertEqual(fake.fetched_calls, [])  # never downloaded any bodies


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

    def _seed(self, text="The division list is missing a record."):
        rec = core.make_record(
            source="email", channel_name="c", contributor="p",
            source_message_id="1", text=text,
        )
        core.append_records([rec], queue_file=self.tmp)
        return rec

    def test_triage_junk_decision_sets_reason_and_decided_at(self):
        rec = self._seed()
        rc = triage_queue.main(["junk", rec["id"][:8], "--reason", "spammy", "--by", "t"])
        self.assertEqual(rc, 0)
        latest = core.latest_records(core.load_records(queue_file=self.tmp))[0]
        self.assertEqual(latest["status"], "junk")
        self.assertEqual(latest["junk_reason"], "spammy")
        self.assertEqual(latest["decision_reason"], "spammy")
        self.assertTrue(latest["decided_at"])
        # decided_at must be a parseable ISO-8601 timestamp
        datetime.fromisoformat(latest["decided_at"])

    def test_reviewed_verb_and_all_decision_statuses(self):
        for verb, status in triage_queue.DECISIONS.items():
            built = triage_queue.build_decision_record(
                {"id": "x", "status": "queued"}, status, "r", "by"
            )
            self.assertEqual(built["status"], status)
        # drive the 'reviewed' verb end-to-end
        rec = self._seed("Noted, thanks.")
        triage_queue.main(["reviewed", rec["id"][:8], "--reason", "ack", "--by", "t"])
        latest = core.latest_records(core.load_records(queue_file=self.tmp))[0]
        self.assertEqual(latest["status"], "reviewed")

    def test_triage_drops_stale_junk_reason_when_accepted(self):
        junk = core.make_record(
            source="email", channel_name="c", contributor="p",
            source_message_id="1", text="Free bitcoin crypto giveaway!!!",
        )
        self.assertEqual(junk["status"], "junk")
        core.append_records([junk], queue_file=self.tmp)
        triage_queue.main(["accept", junk["id"][:8], "--reason", "actually a real point", "--by", "t"])
        latest = core.latest_records(core.load_records(queue_file=self.tmp))[0]
        self.assertEqual(latest["status"], "accepted")
        self.assertNotIn("junk_reason", latest)

    def test_triage_rejects_blank_prefix(self):
        self._seed()
        rc = triage_queue.main(["accept", "", "--reason", "oops"])
        self.assertEqual(rc, 1)
        # the lone record must NOT have been triaged
        latest = core.latest_records(core.load_records(queue_file=self.tmp))[0]
        self.assertNotEqual(latest["status"], "accepted")


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
        # With no env var, the page must fall back to the public feedback alias,
        # never a personal address.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MYGOV_FEEDBACK_EMAIL", None)
            body = self.client.get("/feedback").get_data(as_text=True)
        self.assertIn("yourgov@solvx.uk", body)
        self.assertNotIn("captain@solvx.uk", body)

    def test_feedback_renders_configured_links(self):
        with mock.patch.dict(os.environ, {
            "MYGOV_FEEDBACK_WHATSAPP_URL": "https://wa.me/441234",
            "MYGOV_FEEDBACK_TELEGRAM_URL": "https://t.me/yourgov",
        }):
            body = self.client.get("/feedback").get_data(as_text=True)
        self.assertIn('href="https://wa.me/441234"', body)
        self.assertIn('href="https://t.me/yourgov"', body)

    def test_feedback_is_get_only(self):
        # No server-side input path: a POST must not be accepted.
        self.assertEqual(self.client.post("/feedback").status_code, 405)


class GlobalFeedbackLinkTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_link_injected_on_content_pages(self):
        # The subtle global feedback link must appear on normal HTML pages.
        for route in ("/global", "/source-lens"):
            body = self.client.get(route).get_data(as_text=True)
            self.assertIn('id="global-feedback-link"', body, route)
            self.assertIn('href="/feedback"', body, route)

    def test_link_not_injected_on_feedback_page_or_iframe_or_api(self):
        # Don't link the feedback page to itself, don't inject into the embedded
        # map iframe, and never touch JSON API responses.
        self.assertNotIn('id="global-feedback-link"',
                         self.client.get("/feedback").get_data(as_text=True))
        self.assertNotIn('id="global-feedback-link"',
                         self.client.get("/map/relay").get_data(as_text=True))
        api = self.client.get("/api/lens/source-divisions")
        self.assertNotIn("global-feedback-link", api.get_data(as_text=True))

    def test_link_is_accessible_anchor(self):
        body = self.client.get("/global").get_data(as_text=True)
        # A real anchor with an aria-label (not a bare icon/div).
        self.assertIn('aria-label="Send feedback about YourGov"', body)


class ConfigGateTests(unittest.TestCase):
    def test_telegram_required_config(self):
        self.assertFalse(telegram.required_config_ok(
            {"telegram": {"telegram_bot_token": "PUT-YOUR-BOT-TOKEN-HERE", "allowed_chat_ids": [1]}})[0])
        self.assertFalse(telegram.required_config_ok(
            {"telegram": {"telegram_bot_token": "real"}})[0])  # empty allowlist
        self.assertTrue(telegram.required_config_ok(
            {"telegram": {"telegram_bot_token": "real", "allowed_chat_ids": [1]}})[0])

    def test_email_required_config_rejects_placeholder(self):
        self.assertFalse(email_imap.required_config_ok({"email": {}})[0])
        self.assertFalse(email_imap.required_config_ok({"email": {
            "imap_host": "h", "username": "u", "password": "PUT-APP-PASSWORD-HERE",
            "allowed_senders": ["a@b"]}})[0])
        self.assertFalse(email_imap.required_config_ok({"email": {
            "imap_host": "h", "username": "u", "password": "p"}})[0])  # empty allowlist
        self.assertTrue(email_imap.required_config_ok({"email": {
            "imap_host": "h", "username": "u", "password": "p",
            "allowed_recipients": ["f@x"]}})[0])

    def test_whatsapp_required_config(self):
        self.assertFalse(whatsapp_jsonl.required_config_ok({"whatsapp": {}}, None)[0])
        self.assertFalse(whatsapp_jsonl.required_config_ok({"whatsapp": {}}, "p.jsonl")[0])
        self.assertTrue(whatsapp_jsonl.required_config_ok(
            {"whatsapp": {"allowed_chat_jids": ["x@g.us"]}}, "p.jsonl")[0])

    def test_check_channel_config_fails_closed(self):
        with self.assertRaises(SystemExit) as cm:
            intake.check_channel_config("email", {"email": {}}, None)
        self.assertEqual(cm.exception.code, 2)


class RunOnceDedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "q.jsonl"
        self._orig = core.QUEUE_FILE
        core.QUEUE_FILE = self.tmp

    def tearDown(self):
        core.QUEUE_FILE = self._orig

    def _rec(self, mid, text):
        return core.make_record(
            source="telegram", channel_name="c", contributor="p",
            source_message_id=mid, text=text,
        )

    def test_run_once_drops_duplicate_ids_and_commits_after_append(self):
        seed = self._rec("1", "A genuine bug in the map view today.")
        core.append_records([seed], queue_file=self.tmp)
        committed = []

        def fake_channel(channel, cfg, path):
            dupe = dict(seed)
            fresh = self._rec("2", "A different suggestion to add postcode filters.")
            return [dupe, fresh], (lambda: committed.append(channel))

        with mock.patch.object(intake, "run_channel", fake_channel):
            with contextlib.redirect_stdout(io.StringIO()):
                stats = intake.run_once(["telegram"], {}, None)

        self.assertEqual(stats["dropped_dupe"], 1)
        self.assertEqual(stats["written"], 1)
        self.assertEqual(len(core.latest_records(core.load_records(queue_file=self.tmp))), 2)
        self.assertEqual(committed, ["telegram"])  # commit ran only after append

    def test_commit_not_called_when_append_fails(self):
        committed = []

        def fake_channel(channel, cfg, path):
            return [self._rec("1", "A genuine bug in the map view today.")], (lambda: committed.append(channel))

        with mock.patch.object(intake, "run_channel", fake_channel):
            with mock.patch.object(core, "append_records", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    with contextlib.redirect_stdout(io.StringIO()):
                        intake.run_once(["telegram"], {}, None)
        self.assertEqual(committed, [])  # cursor NOT advanced on append failure


class InspectQueueTests(unittest.TestCase):
    def _pair(self):
        base = core.make_record(source="email", channel_name="c", contributor="p",
                                source_message_id="1", text="The map data is wrong on mobile.")
        decided = dict(base)
        decided["status"] = "accepted"
        return base, decided

    def _three(self):
        base, decided = self._pair()
        other = core.make_record(source="telegram", channel_name="d", contributor="q",
                                 source_message_id="2", text="please add a dark mode feature")
        return [base, decided, other]

    def test_apply_filters(self):
        recs = core.latest_records(self._three())
        self.assertEqual(len(inspect_queue._apply_filters(recs, "accepted", None, None, None)), 1)
        self.assertEqual(len(inspect_queue._apply_filters(recs, None, "telegram", None, None)), 1)
        self.assertEqual(len(inspect_queue._apply_filters(recs, None, None, "feature", None)), 1)

    def test_cmd_list_shows_latest_not_original(self):
        base, decided = self._pair()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            inspect_queue.cmd_list([base, decided], None, None, None, None)
        out = buf.getvalue()
        self.assertIn("accepted", out)
        self.assertNotIn("queued", out)  # the superseded original must not show

    def test_cmd_stats_counts_latest_per_id(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            inspect_queue.cmd_stats(self._three())
        self.assertIn("total: 2", buf.getvalue())  # 3 lines collapse to 2 ids


@unittest.skipIf(jsonschema is None, "jsonschema not installed")
class SchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft7Validator(self.schema)

    def _valid(self, rec):
        errors = [e.message for e in self.validator.iter_errors(rec)]
        self.assertEqual(errors, [], msg=f"schema errors: {errors}")

    def test_make_record_shapes_validate(self):
        clean = core.make_record(source="telegram", channel_name="c", contributor="p",
                                 source_message_id="1", text="The map view is broken on mobile.")
        junk = core.make_record(source="email", channel_name="c", contributor="p",
                                source_message_id="2", text="free bitcoin crypto giveaway")
        needs = core.make_record(source="whatsapp", channel_name="c", contributor="p",
                                 source_message_id="3", text="hello team, some general thoughts about the site")
        maximal = core.make_record(source="email", channel_name="c", contributor="p",
                                   source_message_id="4", text="please add dark mode",
                                   thread_ref="t", contact_ref="x@y")
        self.assertEqual(junk["status"], "junk")
        for rec in (clean, junk, needs, maximal):
            self._valid(rec)

    def test_decision_records_validate(self):
        base = core.make_record(source="telegram", channel_name="c", contributor="p",
                                source_message_id="1", text="The map view is broken on mobile.")
        for status in core.DECISION_STATUSES:
            self._valid(triage_queue.build_decision_record(base, status, "reason", "me"))

    def test_make_record_keyset_matches_schema(self):
        rec = core.make_record(source="telegram", channel_name="c", contributor="p",
                               source_message_id="1", text="The map view is broken on mobile.")
        props = set(self.schema["properties"])
        self.assertTrue(set(rec) <= props, msg=f"extra keys: {set(rec) - props}")
        self.assertTrue(set(self.schema["required"]) <= set(rec))


if __name__ == "__main__":
    unittest.main()
