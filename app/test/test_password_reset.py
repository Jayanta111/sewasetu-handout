import importlib
import unittest
from datetime import date
from unittest.mock import patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


class RecordingCursor:
    def __init__(self):
        self.calls = []
        self.read_index = 0

    def execute(self, query, *params):
        if len(params) == 1 and isinstance(params[0], tuple):
            params = params[0]
        self.calls.append((query, params))

    def fetchone(self):
        self.read_index += 1
        if self.read_index == 1:
            query, params = self.calls[-1]
            if params and "' OR '" in params[0]:
                return None
            if "' OR '" in query:
                return ("0000000001",)
            return ("0000000001",)
        if self.read_index == 2:
            return (date(1960, 1, 1),)
        return None

    def close(self):
        pass


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


class PasswordResetTest(unittest.TestCase):
    def test_sql_shaped_mobile_is_passed_as_data(self):
        portal.app.config["TESTING"] = True
        cursor = RecordingCursor()
        payload = "0000000000' OR '1'='1"

        with (
            patch.object(portal, "get_db", return_value=RecordingConnection(cursor)),
            patch.object(portal, "send_sms") as send_sms,
        ):
            response = portal.app.test_client().post(
                "/status/reset", data={"mobile": payload}
            )

        self.assertEqual(response.status_code, 200)
        lookup_query, lookup_params = cursor.calls[0]
        self.assertNotIn(payload, lookup_query)
        self.assertEqual(lookup_params, (payload,))
        self.assertEqual(len(cursor.calls), 1)
        send_sms.assert_not_called()

    def test_reset_lookups_and_update_use_parameters(self):
        portal.app.config["TESTING"] = True
        cursor = RecordingCursor()
        mobile = "0000000001"

        with (
            patch.object(portal, "get_db", return_value=RecordingConnection(cursor)),
            patch.object(portal, "send_sms") as send_sms,
        ):
            response = portal.app.test_client().post(
                "/status/reset", data={"mobile": mobile}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(cursor.calls), 3)
        for query, params in cursor.calls:
            self.assertNotIn(mobile, query)
            self.assertTrue(params)
        self.assertEqual(cursor.calls[0][1], (mobile,))
        self.assertEqual(cursor.calls[1][1], (mobile,))
        send_sms.assert_called_once()


if __name__ == "__main__":
    unittest.main()
