import pathlib
import re
import unittest


APP_DIR = pathlib.Path(__file__).resolve().parents[1]


class PerformanceIndexTest(unittest.TestCase):
    def test_schema_and_migration_index_hot_application_queries(self):
        schema = (APP_DIR / "schema.sql").read_text(encoding="utf-8")
        migration = APP_DIR / "migrations" / "001_application_indexes.sql"
        schema_normalized = re.sub(r"\s+", " ", schema).lower()

        self.assertIn(
            "create index if not exists applications_mobile_idx on applications (mobile)",
            schema_normalized,
        )
        self.assertIn(
            "create index if not exists applications_pending_submitted_idx "
            "on applications (submitted_at) where status = 'pending'",
            schema_normalized,
        )
        self.assertTrue(migration.exists(), "existing databases need an index migration")
        migration_normalized = re.sub(
            r"\s+", " ", migration.read_text(encoding="utf-8")
        ).lower()
        self.assertIn("create index concurrently if not exists applications_mobile_idx", migration_normalized)
        self.assertIn("create index concurrently if not exists applications_pending_submitted_idx", migration_normalized)


if __name__ == "__main__":
    unittest.main()
