import deploy
import unittest

from unittest.mock import patch
from testfixtures import LogCapture


class MockServiceJsonLoader:
    def __init__(self, metadata):
        self.metadata = metadata

    def load(self):
        return self.metadata

mock_service_json_loader = MockServiceJsonLoader({'TEAM': 'some-team'})


def test_positional_args():
    deployment = deploy.Deployment(
        'ci 0'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert deployment.environment == 'ci', 'environment passed'
    assert deployment.version == '0', 'version passed'


def test_component_name_arg():
    deployment = deploy.Deployment(
        'ci 1 -c mycomp1'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp1', 'short component name argument'

    deployment = deploy.Deployment(
        'ci 2 --component-name=mycomp2'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp2', 'long component name argument '

    deployment = deploy.Deployment(
        'ci 3 --component-name mycomp3'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp3', 'long component name argument with equals'


def test_component_name_env():
    deployment = deploy.Deployment(
        'ci 4 -c mycomp4'.split(' '),
        {'COMPONENT_NAME': 'notmycomp4'},
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp4', 'argument overrides environment variable'

    deployment = deploy.Deployment(
        'ci 5'.split(' '),
        {'COMPONENT_NAME': 'mycomp5'},
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp5', 'component name from environment variable'


def test_component_name_from_git():

    class MockShellRunner:
        def run(self, command, capture=False):
            if command == 'git config remote.origin.url':
                assert capture, 'output is captured for git command'
                return 0, 'https://github.com/mergermarket/mycomp6.git\n', ''
            else:
                raise Exception('unexpected command ' + command)

    deployment = deploy.Deployment(
        'ci 6'.split(' '),
        {},
        shell_runner=MockShellRunner(),
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp6', 'name extracted from git remote'

    deployment = deploy.Deployment(
        'ci 6a -c mycomp6a'.split(' '),
        {},
        shell_runner=MockShellRunner(),
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp6a', 'arg overrides git remote'

    deployment = deploy.Deployment(
        'ci 6b'.split(' '),
        {'COMPONENT_NAME': 'mycomp6b'},
        shell_runner=MockShellRunner(),
        service_json_loader=mock_service_json_loader
    )
    assert deployment.component_name == 'mycomp6b', 'environment variable overrides git remote'


class DeploymentTests(unittest.TestCase):
    @patch('subprocess.call')
    def test__terragrunt_plan__exception(self, m):
        d = deploy.Deployment(
            'ci 0'.split(' '),
            {},
            service_json_loader=mock_service_json_loader
        )

        m.side_effect = Exception('Boom!')

        with LogCapture() as l:
            d.terragrunt_plan('')
            l.check(
                ('deploy', 'ERROR', 'Exception caught while executing terragrunt plan!')
            )

    @patch('subprocess.call')
    def test__terragrunt_apply__exception(self, m):
        d = deploy.Deployment(
            'ci 0'.split(' '),
            {},
            service_json_loader=mock_service_json_loader
        )

        m.side_effect = Exception('Boom!')

        with LogCapture() as l:
            d.terragrunt_apply('')
            l.check(
                ('deploy', 'ERROR', 'Exception caught while executing terragrunt apply!')
            )

    def test__terragrunt_s3_bucket_name__return_value(self):
        d = deploy.Deployment(
            'ci 0'.split(' '),
            {},
            service_json_loader=mock_service_json_loader
        )
        self.assertEqual(d.terragrunt_s3_bucket_name('7278378123'), 'terraform-tfstate-38a14c')
