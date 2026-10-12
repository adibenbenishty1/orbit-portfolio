"""Check migration error propagation and lock cleanup without PostgreSQL.

Run with the project environment:
    .venv/bin/python -m unittest discover -s deploy/helm/tests -p test_migration_failure.py -v
"""

from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch


ENV = Path(__file__).resolve().parents[3] / 'apps/catalog/alembic/env.py'


class MigrationFailureTests(unittest.TestCase):
    def test_failure_releases_lock_and_propagates_to_container(self):
        from alembic import context

        configuration = MagicMock()
        configuration.config_file_name = None
        connection = MagicMock()
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        with (
            patch.object(context, 'config', configuration, create=True),
            patch.object(context, 'is_offline_mode', return_value=False),
            patch.object(context, 'configure'),
            patch.object(context, 'begin_transaction', return_value=MagicMock()),
            patch.object(context, 'run_migrations', side_effect=RuntimeError('migration failed')),
            patch('sqlalchemy.engine_from_config', return_value=engine),
        ):
            with self.assertRaisesRegex(RuntimeError, 'migration failed'):
                runpy.run_path(str(ENV))
        self.assertEqual([str(call.args[0]) for call in connection.execute.call_args_list], [
            'SELECT pg_advisory_lock(672418017)',
            'SELECT pg_advisory_unlock(672418017)',
        ])
        connection.rollback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
