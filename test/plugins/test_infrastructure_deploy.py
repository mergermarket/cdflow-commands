import json
import unittest
from itertools import chain
from string import ascii_letters

from boto3 import Session
from cdflow_commands.plugins.infrastructure import Deploy, DeployConfig
from hypothesis import given
from hypothesis.strategies import text
from mock import ANY, Mock, patch


@patch('cdflow_commands.plugins.infrastructure.os')
@patch('cdflow_commands.plugins.infrastructure.check_call')
@patch('cdflow_commands.plugins.infrastructure.get_secrets')
@patch('cdflow_commands.plugins.infrastructure.NamedTemporaryFile')
class TestDeploy(unittest.TestCase):

    def setUp(self):
        self._aws_access_key = 'dummy-access-key'
        self._aws_secret_access_key = 'dummy-secret-access-key'
        self._aws_session_token = 'dummy-session-token'
        self._boto_session = Session(
            self._aws_access_key, self._aws_secret_access_key,
            self._aws_session_token, 'eu-west-1'
        )
        self._component_name = 'dummy-component'
        self._environment_name = 'dummy-environment'
        self._additional_variables = ['ami_id=ami-123456']
        self._deploy_config = DeployConfig(
            'dummy-team', 'dummy-platform-config-file'
        )
        self._deploy = Deploy(
            self._boto_session, self._component_name, self._environment_name,
            self._additional_variables, self._deploy_config
        )

    def test_terraform_modules_fetched(
        self, NamedTemporaryFile, get_secrets, check_call, mock_os
    ):
        # When
        NamedTemporaryFile.return_value.__enter__.return_value.name =  \
            '/mock/file/path'
        get_secrets.return_value = {}
        self._deploy.run()

        check_call.assert_any_call(['terraform', 'get', 'infra'])

    def test_terraform_plan_called(
        self, NamedTemporaryFile, get_secrets, check_call, mock_os
    ):
        # When
        NamedTemporaryFile.return_value.__enter__.return_value.name =  \
            '/mock/file/path'
        get_secrets.return_value = {}
        self._deploy.run()

        # Then
        base_parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._boto_session.region_name),
            '-var', 'team={}'.format(self._deploy_config.team),
            '-var-file', self._deploy_config.platform_config_file,
            '-var-file', '/mock/file/path'
        ]

        extra_parameters = chain.from_iterable(
            ('-var', ANY) for _ in self._additional_variables
        )

        ignored_parameters = base_parameters + list(extra_parameters)

        check_call.assert_any_call(
            ['terraform', 'plan'] + ignored_parameters + ['infra'],
            env=ANY
        )

    def test_terraform_apply_called(
        self, NamedTemporaryFile, get_secrets, check_call, mock_os
    ):
        # When
        NamedTemporaryFile.return_value.__enter__.return_value.name = \
            '/mock/file/path'
        get_secrets.return_value = {}
        self._deploy.run()

        base_parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._boto_session.region_name),
            '-var', 'team={}'.format(self._deploy_config.team),
            '-var-file', self._deploy_config.platform_config_file,
            '-var-file', '/mock/file/path'
        ]

        extra_parameters = chain.from_iterable(
            ('-var', ANY) for _ in self._additional_variables
        )

        ignored_parameters = base_parameters + list(extra_parameters)

        # Then
        check_call.assert_any_call(
            ['terraform', 'apply'] + ignored_parameters + ['infra'],
            env=ANY
        )

    def test_secrets_written_to_temporary_file(
        self, NamedTemporaryFile, get_secrets, check_call, mock_os
    ):
        # Given
        temporary_file = Mock()

        NamedTemporaryFile.return_value.__enter__.return_value = temporary_file
        get_secrets.return_value = {'a': 1}

        # When
        self._deploy.run()

        # Then
        temporary_file.write.assert_called_once_with(
            json.dumps({'secrets': {'a': 1}}).encode('utf-8')
        )

    def test_aws_credentials_passed_to_terraform(
        self, NamedTemporaryFile, get_secrets, check_call, mock_os
    ):
        # Given
        get_secrets.return_value = {}

        mock_os.environ = {
            'PATH': '/home/me/bin'
        }

        # When
        self._deploy.run()

        # Then
        check_call.assert_any_call(
            ['terraform', 'apply'] + [ANY] * 14 + ['infra'],
            env={
                'AWS_ACCESS_KEY_ID': self._aws_access_key,
                'AWS_SECRET_ACCESS_KEY': self._aws_secret_access_key,
                'AWS_SESSION_TOKEN': self._aws_session_token,
                'PATH': '/home/me/bin'
            }
        )


class TestEnvironmentSpecificConfigAddedToTerraformArgs(unittest.TestCase):

    @given(text(alphabet=ascii_letters, min_size=2, max_size=10))
    def test_environment_specific_config_in_args(self, env_name):

        # Given
        boto_session = Session(
            'dummy-access-key', 'dummy-secreet-access-key',
            'dummy-session-token', 'eu-west-1'
        )
        deploy_config = DeployConfig(
            'dummy-team', 'dummy-platform-config-file'
        )
        deploy = Deploy(
            boto_session, 'dummy-component', env_name,
            [], deploy_config
        )

        # When
        with patch(
            'cdflow_commands.plugins.infrastructure.check_call'
        ) as check_call, patch(
            'cdflow_commands.plugins.infrastructure.path'
        ) as path, patch(
            'cdflow_commands.plugins.infrastructure.NamedTemporaryFile',
            autospec=True
        ) as NamedTemporaryFile, patch(
            'cdflow_commands.plugins.infrastructure.get_secrets'
        ) as get_secrets:
            NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
            get_secrets.return_value = {}
            path.exists.return_value = True
            deploy.run()
            # Then
            config_file = 'config/{}.json'.format(env_name)
            args = [
                '-var', 'component=dummy-component',
                '-var', 'env={}'.format(env_name),
                '-var', 'aws_region=eu-west-1',
                '-var', 'team=dummy-team',
                '-var-file', 'dummy-platform-config-file',
                '-var-file', ANY,
                '-var-file', config_file,
                'infra'
            ]
            check_call.assert_any_call(
                ['terraform', 'plan'] + args,
                env=ANY
            )
            check_call.assert_any_call(
                ['terraform', 'apply'] + args,
                env=ANY
            )
            path.exists.assert_any_call(config_file)
