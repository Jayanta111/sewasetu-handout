import importlib
import os
import pathlib
import re
import unittest
from unittest.mock import patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


APP_DIR = pathlib.Path(__file__).resolve().parents[1]


class RuntimeSecretTest(unittest.TestCase):
    def test_flask_session_secret_comes_from_environment(self):
        self.assertTrue(portal.app.secret_key)
        self.assertTrue(os.environ.get("SEWASETU_FLASK_SECRET_KEY"))
        self.assertTrue(
            portal.app.secret_key == os.environ["SEWASETU_FLASK_SECRET_KEY"],
            "Flask must use the configured runtime secret",
        )

    def test_database_connect_uses_runtime_password(self):
        with patch.object(portal.psycopg2, "connect") as connect:
            portal.get_db()

        self.assertTrue(connect.called)
        self.assertTrue(
            connect.call_args.kwargs.get("password") == os.environ.get("SEWASETU_DB_PASSWORD"),
            "database password must come from the runtime environment",
        )

    def test_source_config_and_compose_do_not_contain_secret_defaults(self):
        app_config = (APP_DIR / "config" / "app.ini").read_text(encoding="utf-8")
        source = (APP_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"(?im)^\s*(secret_key|password)\s*=", app_config))
        self.assertIn('os.environ.get("SEWASETU_FLASK_SECRET_KEY")', source)
        self.assertIn('os.environ["SEWASETU_DB_PASSWORD"]', source)


if __name__ == "__main__":
    unittest.main()
