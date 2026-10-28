import importlib
import unittest
from unittest.mock import patch

try:
    # Host runs import app/app.py as app.app; inside the Docker image the
    # same file is at /app/app.py and is imported as the top-level app module.
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


class ApplyCaptchaTest(unittest.TestCase):
    def test_correct_captcha_requests_otp(self):
        portal.app.config["TESTING"] = True

        with (
            patch.object(portal, "deadline_remaining", return_value=1),
            patch.object(portal, "get_db") as get_db,
            patch.object(portal, "send_sms") as send_sms,
        ):
            client = portal.app.test_client()

            with client.session_transaction() as session:
                session["captcha_answer"] = 8

            response = client.post(
                "/apply",
                data={"mobile": "1234567890", "captcha": "8"},
            )

            self.assertEqual(response.status_code, 302)
            self.assertIn("/verify", response.headers["Location"])
            get_db.assert_called_once()
            send_sms.assert_called_once()

    def test_wrong_captcha_does_not_request_otp(self):
        portal.app.config["TESTING"] = True

        with (
            patch.object(portal, "deadline_remaining", return_value=1),
            patch.object(portal, "get_db") as get_db,
            patch.object(portal, "send_sms") as send_sms,
        ):
            client = portal.app.test_client()

            with client.session_transaction() as session:
                session["captcha_answer"] = 8

            response = client.post(
                "/apply",
                data={"mobile": "1234567890", "captcha": "9"},
            )

            self.assertEqual(response.status_code, 200)
            get_db.assert_not_called()
            send_sms.assert_not_called()


if __name__ == "__main__":
    unittest.main()
