"""Render environment overlays and check their database secret wiring.

Run with Helm and PyYAML installed:
    python3 -m unittest discover -s deploy/helm/tests -p test_environment_values.py -v
"""

from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1] / 'orbit'


class EnvironmentValuesTests(unittest.TestCase):
    def test_each_environment_renders_its_own_database_configuration(self):
        configurations = {}
        for environment in ('dev', 'prod'):
            with self.subTest(environment=environment):
                overlay = CHART / f'values-{environment}.yaml'
                values = yaml.safe_load(overlay.read_text())
                result = subprocess.run(
                    ['helm', 'template', 'orbit', str(CHART), '-f', str(overlay)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                docs = list(yaml.safe_load_all(result.stdout))
                pod = next(d for d in docs if d['kind'] == 'Deployment'
                           and d['metadata']['name'] == 'orbit-catalog')['spec']['template']['spec']
                env = {entry['name']: entry for entry in pod['containers'][0]['env']}
                migration = pod['initContainers'][0]
                self.assertEqual(migration['command'], ['alembic', 'upgrade', 'head'])
                self.assertEqual(migration['image'], pod['containers'][0]['image'])
                self.assertEqual(migration['env'], pod['containers'][0]['env'])
                self.assertEqual(migration['volumeMounts'], pod['containers'][0]['volumeMounts'])
                self.assertEqual(env['ENV']['value'], environment)
                self.assertEqual(env['DB_HOST']['value'], values['catalog']['env']['DB_HOST'])
                provider_name = pod['volumes'][0]['csi']['volumeAttributes']['secretProviderClass']
                provider = next(d for d in docs if d['kind'] == 'SecretProviderClass'
                                and d['metadata']['name'] == provider_name)
                objects = yaml.safe_load(provider['spec']['parameters']['objects'])
                secret = values['catalog']['secrets']['databaseSecretObject']
                self.assertEqual(objects[0]['objectName'], secret)
                synced = provider['spec']['secretObjects'][0]
                for field in ('DB_USER', 'DB_PASSWORD'):
                    self.assertEqual(env[field]['valueFrom']['secretKeyRef'],
                                     {'name': synced['secretName'], 'key': field})
                configurations[environment] = (env['DB_HOST']['value'], secret)
        self.assertNotEqual(configurations['dev'][0], configurations['prod'][0])
        self.assertNotEqual(configurations['dev'][1], configurations['prod'][1])

    def test_development_database_can_be_supplied_at_deploy_time(self):
        host = 'development-db.example.invalid'
        secret = 'arn:aws:secretsmanager:eu-north-1:123456789012:secret:rds!db-dev'
        result = subprocess.run(
            ['helm', 'template', 'orbit', str(CHART), '-f', str(CHART / 'values-dev.yaml'),
             '--set-string', f'catalog.env.DB_HOST={host}',
             '--set-string', f'catalog.secrets.databaseSecretObject={secret}'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = list(yaml.safe_load_all(result.stdout))
        pod = next(d for d in docs if d['kind'] == 'Deployment'
                   and d['metadata']['name'] == 'orbit-catalog')['spec']['template']['spec']
        self.assertIn({'name': 'DB_HOST', 'value': host}, pod['containers'][0]['env'])
        provider = next(d for d in docs if d['kind'] == 'SecretProviderClass'
                        and d['metadata']['name'] == 'orbit-catalog-secrets')
        self.assertEqual(yaml.safe_load(provider['spec']['parameters']['objects'])[0]['objectName'], secret)

    def test_compose_waits_for_database_and_migration_success(self):
        services = yaml.safe_load((CHART.parents[2] / 'docker-compose.yml').read_text())['services']
        migration = services['catalog-migrate']
        self.assertEqual(migration['command'], ['alembic', 'upgrade', 'head'])
        self.assertEqual(migration['build'], services['catalog']['build'])
        self.assertEqual(migration['environment'], services['catalog']['environment'])
        self.assertEqual(migration['depends_on']['postgres']['condition'], 'service_healthy')
        self.assertEqual(services['catalog']['depends_on']['catalog-migrate']['condition'],
                         'service_completed_successfully')
        self.assertEqual(migration['restart'], 'no')


if __name__ == '__main__':
    unittest.main()
