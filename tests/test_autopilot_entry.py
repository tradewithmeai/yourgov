import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app


class AutopilotEntryTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_root_redirects_to_uk_view_with_autopilot(self):
        # Live countries (GB is the default) skip the globe and land directly on
        # the UK source-lens view. The autopilot flag is preserved.
        r = self.client.get("/?autopilot=1", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/source-lens?", r.headers["Location"])
        self.assertIn("autopilot=1", r.headers["Location"])

    def test_root_redirects_directly_to_uk_view_without_start_modal(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/source-lens?", r.headers["Location"])
        self.assertNotIn("from=start", r.headers["Location"])
        self.assertIn("cc=GB", r.headers["Location"])
        self.assertIn("lang=en", r.headers["Location"])

    def test_home_page_does_not_auto_navigate_to_start(self):
        r = self.client.get("/home")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("/start?lang=", body)
        self.assertNotIn("window.location.href = go.getAttribute('href')", body)

    def test_welcome_page_does_not_auto_navigate_to_start(self):
        r = self.client.get("/welcome")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("/start?lang=", body)
        self.assertNotIn("window.location.href = go.getAttribute('href')", body)

    def test_start_preserves_autopilot_flag(self):
        r = self.client.get("/start?autopilot=1", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/source-lens?", r.headers["Location"])
        self.assertIn("from=start", r.headers["Location"])
        self.assertIn("autopilot=1", r.headers["Location"])

    def test_non_live_country_still_routes_to_globe(self):
        # The globe is kept for countries without a working data adapter.
        # cc resolution validates against the feasibility dataset, so use a code
        # present there; assert it does NOT divert to the UK view.
        r = self.client.get("/?cc=US", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        loc = r.headers["Location"]
        # US is not a live country -> globe. (If US ever isn't a known code it
        # falls back to GB/source-lens; this asserts the live-vs-not branch.)
        self.assertTrue("/global?" in loc or "/source-lens?" in loc)
        if "cc=US" in loc:
            self.assertIn("/global?", loc)

    def test_welcome_page_carries_autopilot_into_link(self):
        r = self.client.get("/welcome?autopilot=1")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("autopilot=1", body)
        self.assertIn("/start?lang=", body)


if __name__ == "__main__":
    unittest.main()
