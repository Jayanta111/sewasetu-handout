import importlib
import unittest
from datetime import date as RealDate, datetime as RealDateTime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


IST = ZoneInfo("Asia/Kolkata")
FIXED_UTC_NOW = RealDateTime(2026, 10, 31, 19, 0, tzinfo=timezone.utc)


class FixedDateTime:
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_UTC_NOW.replace(tzinfo=None)
        return FIXED_UTC_NOW.astimezone(tz)

    @classmethod
    def strptime(cls, *args):
        return RealDateTime.strptime(*args)


class FixedDate:
    @staticmethod
    def today():
        return RealDate(2026, 10, 31)


class DatabaseReached(Exception):
    pass


class ISTBoundaryTest(unittest.TestCase):
    def make_client(self, dob):
        portal.app.config["TESTING"] = True
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["verified_mobile"] = "0000000000"
            session["form_data"] = {
                "applicant_name": "Fictional Applicant",
                "village": "Test Village",
                "block": "Sonari",
                "gender": "Other",
                "marital_status": "Married",
                "bank_account": "000000000000",
                "ifsc": "ABCD0123456",
                "dob": dob,
            }
        return client

    def test_60th_birthday_is_based_on_ist_application_date(self):
        client = self.make_client("01/11/1966")
        with (
            patch.object(portal, "datetime", FixedDateTime),
            patch.object(portal, "date", FixedDate),
            patch.object(portal, "SCHEME_DEADLINE",
                         RealDateTime(2026, 11, 2, 0, 0, tzinfo=IST)),
            patch.object(portal, "get_db", side_effect=DatabaseReached),
        ):
            with self.assertRaises(DatabaseReached):
                client.post("/declaration")

    def test_day_month_input_does_not_make_next_day_birthday_eligible_early(self):
        client = self.make_client("02/11/1966")
        with (
            patch.object(portal, "datetime", FixedDateTime),
            patch.object(portal, "get_db", side_effect=DatabaseReached),
        ):
            response = client.post("/declaration", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("at least 60 years old", response.get_data(as_text=True))

    def test_application_window_is_closed_at_midnight_ist(self):
        client = self.make_client("10/01/1966")
        with (
            patch.object(portal, "datetime", FixedDateTime),
            patch.object(portal, "date", FixedDate),
            patch.object(portal, "get_db", side_effect=DatabaseReached),
        ):
            response = client.post("/declaration", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))


if __name__ == "__main__":
    unittest.main()
