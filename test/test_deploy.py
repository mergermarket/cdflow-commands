import unittest
from collections import namedtuple

from mock import patch, Mock, MagicMock

from cdflow_commands.account import AccountScheme
from cdflow_commands.deploy import Deploy


BotoCredentials = namedtuple(
    'BotoCredentials', ['access_key', 'secret_key', 'token']
)


class TestDeploy(unittest.TestCase):

    @patch('cdflow_commands.deploy.check_call')
    @patch('cdflow_commands.deploy.path')
    @patch('cdflow_commands.deploy.NamedTemporaryFile')
    @patch('cdflow_commands.deploy.os')
    @patch('cdflow_commands.deploy.get_secrets')
    def test_deploy_runs_terraform_plan(
        self, get_secrets, mock_os, NamedTemporaryFile, path, check_call
    ):
        component = 'dummy-component'
        version = 'dummy-version'
        environment = 'test'
        team = 'dummy-team'
        release_path = '/path/to/release'

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.account_for_environment.return_value = 'dummy-account'

        boto_session = Mock()
        boto_session.region_name = 'us-north-4'
        credentials = BotoCredentials(
            'dummy-access-key', 'dummy-secret-key', 'dummy-token'
        )
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            component, version, environment, team,
            release_path, account_scheme, boto_session,
        )

        get_secrets.return_value = {}

        secret_file_path = NamedTemporaryFile.return_value.__enter__\
            .return_value

        mock_os.environ = {}

        dummy_plugin = Mock()
        dummy_plugin.parameters.return_value = []

        deploy.run(dummy_plugin)

        check_call.assert_called_with(
            [
                'terraform', 'plan', 'infra',
                '-var', 'component={}'.format(component),
                '-var', 'env={}'.format(environment),
                '-var', 'aws_region={}'.format(boto_session.region_name),
                '-var', 'team={}'.format(team),
                '-var', 'version={}'.format(version),
                '-var-file', 'platform-config/{}/{}.json'.format(
                    'dummy-account', boto_session.region_name
                ),
                '-var-file', secret_file_path,
                '-var-file', 'config/{}.json'.format(environment),
            ],
            cwd=release_path,
            env={
                'AWS_ACCESS_KEY_ID': credentials.access_key,
                'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                'AWS_SESSION_TOKEN': credentials.token,
            }
        )
