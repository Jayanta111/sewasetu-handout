import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch


APP_DIR = pathlib.Path(__file__).resolve().parents[1]
SCHEDULER_PATH = APP_DIR / "scripts" / "deemed_approval.py"


class DeemedApprovalConfigTest(unittest.TestCase):
    def load_scheduler(self):
        spec = importlib.util.spec_from_file_location(
            "sewasetu_deemed_approval_under_test", SCHEDULER_PATH
        )
        scheduler = importlib.util.module_from_spec(spec)
        fake_psycopg2 = types.ModuleType("psycopg2")
        fake_psycopg2.connect = Mock()

        # Import-time config loading is the behavior under test. Keep this
        # isolated from PostgreSQL and the citizen database.
        with patch.dict(sys.modules, {"psycopg2": fake_psycopg2}):
            spec.loader.exec_module(scheduler)
        return scheduler

    def test_scheduler_loads_the_configured_15_day_sla(self):
        scheduler = self.load_scheduler()
        self.assertEqual(scheduler.SLA_DAYS, 15)

    def test_main_approves_only_pending_rows_older_than_sla_and_notifies(self):
        scheduler = self.load_scheduler()
        fixed_now = datetime(2026, 10, 28, 12, 0, 0)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls):
                return fixed_now

        scheduler.datetime = FrozenDateTime
        cursor = Mock()
        cursor.fetchall.return_value = [("SSP-TEST-001", "0000000000")]
        connection = Mock()
        connection.cursor.return_value = cursor
        scheduler.psycopg2.connect.return_value = connection

        with patch.object(scheduler.requests, "post") as send_sms:
            with patch("builtins.print"):
                scheduler.main()

        sql, params = cursor.execute.call_args.args
        self.assertIn("WHERE status = 'PENDING' AND submitted_at < %s", sql)
        self.assertEqual(
            params,
            (fixed_now, fixed_now - timedelta(days=15)),
        )
        connection.commit.assert_called_once()
        send_sms.assert_called_once()
        self.assertEqual(send_sms.call_args.kwargs["json"]["to"], "0000000000")


if __name__ == "__main__":
    unittest.main()
