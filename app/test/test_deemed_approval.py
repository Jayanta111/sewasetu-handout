import importlib.util
import os
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

    def test_dry_run_is_read_only_reports_count_and_sends_no_sms(self):
        scheduler = self.load_scheduler()
        fixed_now = datetime(2026, 10, 28, 12, 0, 0)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls):
                return fixed_now

        scheduler.datetime = FrozenDateTime
        cursor = Mock()
        cursor.fetchone.return_value = (4874,)
        connection = Mock()
        connection.cursor.return_value = cursor
        scheduler.psycopg2.connect.return_value = connection

        with patch.object(scheduler.requests, "post") as send_sms:
            with patch("builtins.print") as output:
                count = scheduler.main(dry_run=True)

        connection.set_session.assert_called_once_with(readonly=True)
        sql, params = cursor.execute.call_args.args
        self.assertIn("SELECT COUNT(*)", sql.upper())
        self.assertIn("WHERE status = 'PENDING' AND submitted_at < %s", sql)
        self.assertEqual(params, (fixed_now - timedelta(days=15),))
        self.assertEqual(count, 4874)
        output.assert_called_once()
        self.assertIn("4874", output.call_args.args[0])
        cursor.fetchall.assert_not_called()
        connection.commit.assert_not_called()
        send_sms.assert_not_called()

    def test_dry_run_connection_is_closed_after_reporting(self):
        scheduler = self.load_scheduler()
        scheduler.psycopg2.connect.return_value.cursor.return_value.fetchone.return_value = (0,)

        scheduler.main(dry_run=True)

        connection = scheduler.psycopg2.connect.return_value
        connection.cursor.return_value.close.assert_called_once()
        connection.close.assert_called_once()

    def test_database_name_override_targets_isolated_rehearsal_database(self):
        scheduler = self.load_scheduler()
        scheduler.psycopg2.connect.return_value.cursor.return_value.fetchone.return_value = (0,)

        with patch.dict(os.environ, {"SEWASETU_DB_NAME": "sewasetu_rehearsal"}):
            with patch("builtins.print"):
                scheduler.main(dry_run=True)

        self.assertEqual(
            scheduler.psycopg2.connect.call_args.kwargs["dbname"],
            "sewasetu_rehearsal",
        )


if __name__ == "__main__":
    unittest.main()
