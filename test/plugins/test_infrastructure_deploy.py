import json
import unittest
from itertools import chain

from boto3 import Session

from cdflow_commands.plugins.infrastructure import Deploy, DeployConfig
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

        check_call.assert_any_call(['terragrunt', 'get', 'infra'])

    def test_terragrunt_plan_called(
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
            ['terragrunt', 'plan'] + ignored_parameters + ['infra'],
            env=ANY
        )

    def test_terragrunt_apply_called(
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
            ['terragrunt', 'apply'] + ignored_parameters + ['infra'],
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

    def test_aws_credentials_passed_to_terragrunt(
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
            ['terragrunt', 'apply'] + [ANY] * 14 + ['infra'],
            env={
                'AWS_ACCESS_KEY_ID': self._aws_access_key,
                'AWS_SECRET_ACCESS_KEY': self._aws_secret_access_key,
                'AWS_SESSION_TOKEN': self._aws_session_token,
                'PATH': '/home/me/bin'
            }
        )
