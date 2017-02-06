import unittest
from mock import patch
from string import printable

from hypothesis import given
from hypothesis.strategies import text, fixed_dictionaries
from boto3 import Session
from mock import ANY

from cdflow_commands.deploy import Deploy, DeployConfig


IGNORED_TERRAGRUNT_PARAMS = [ANY] * 14


class TestDeploy(unittest.TestCase):

    def setUp(self):
        # Given
        boto_session = Session(
            'dummy-access-key', 'dummy-secreet-access-key',
            'dummy-session-token', 'eu-west-1'
        )
        self._deploy_config = DeployConfig(
            'dummy-team', 'dummy-account-id', 'dummy-platform-config-file'
        )
        self._deploy = Deploy(
            boto_session, 'dummy-component', 'dummy-env',
            'dummy-version', self._deploy_config
        )

    @patch('cdflow_commands.deploy.check_call')
    def test_terraform_modules_fetched(self, check_call):
        # When
        self._deploy.run()
        # Then
        check_call.assert_any_call(['terraform', 'get', 'infra'])

    @patch('cdflow_commands.deploy.check_call')
    def test_terragrunt_plan_called(self, check_call):
        # When
        self._deploy.run()
        # Then
        check_call.assert_any_call(
            ['terragrunt', 'plan', 'infra'] + IGNORED_TERRAGRUNT_PARAMS,
            env=ANY
        )

    @patch('cdflow_commands.deploy.check_call')
    def test_terrgrunt_apply_called(self, check_call):
        # When
        self._deploy.run()
        # Then
        check_call.assert_any_call(
            ['terragrunt', 'apply', 'infra'] + IGNORED_TERRAGRUNT_PARAMS,
            env=ANY
        )

    credentials = fixed_dictionaries({
        'access_key_id': text(alphabet=printable, min_size=20, max_size=20),
        'secret_access_key': text(
            alphabet=printable, min_size=40, max_size=40
        ),
        'session_token': text(alphabet=printable, min_size=20, max_size=20)
    })

    @given(credentials)
    def test_terragrunt_passed_aws_credentials_from_session(
        self, credentials
    ):
        # Given
        boto_session = Session(
            credentials['access_key_id'],
            credentials['secret_access_key'],
            credentials['session_token'],
            'eu-west-10'
        )
        deploy = Deploy(boto_session, ANY, ANY, ANY, self._deploy_config)

        with patch('cdflow_commands.deploy.check_call') as check_call:
            # When
            deploy.run()
            # Then
            check_call.assert_any_call(
                ['terragrunt', 'plan', 'infra'] + IGNORED_TERRAGRUNT_PARAMS,
                env={
                    'AWS_ACCESS_KEY_ID': credentials['access_key_id'],
                    'AWS_SECRET_ACCESS_KEY': credentials['secret_access_key'],
                    'AWS_SESSION_TOKEN': credentials['session_token']
                }
            )
            check_call.assert_any_call(
                ['terragrunt', 'apply', 'infra'] + IGNORED_TERRAGRUNT_PARAMS,
                env={
                    'AWS_ACCESS_KEY_ID': credentials['access_key_id'],
                    'AWS_SECRET_ACCESS_KEY': credentials['secret_access_key'],
                    'AWS_SESSION_TOKEN': credentials['session_token']
                }
            )

    deploy_data = fixed_dictionaries({
        'team': text(alphabet=printable, min_size=2, max_size=20),
        'account_id': text(alphabet=printable, min_size=12, max_size=12),
        'aws_region': text(alphabet=printable, min_size=5, max_size=12),
        'component_name': text(alphabet=printable, min_size=2, max_size=30),
        'environment_name': text(alphabet=printable, min_size=2, max_size=10),
        'version': text(alphabet=printable, min_size=1, max_size=20),
        'platform_config_file': text(
            alphabet=printable, min_size=10, max_size=30
        ),
    })

    @given(deploy_data)
    def test_terragrunt_gets_all_parameters(self, data):
        # Given
        deploy_config = DeployConfig(
            data['team'],
            data['account_id'],
            data['platform_config_file']
        )
        boto_session = Session(
            'dummy-access-key-id', 'dummy-secret-access-key', 'dummy-token',
            data['aws_region']
        )
        deploy = Deploy(
            boto_session,
            data['component_name'],
            data['environment_name'],
            data['version'],
            deploy_config
        )
        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            data['account_id'],
            data['aws_region'],
            data['component_name'],
            data['version']
        )

        # When
        with patch('cdflow_commands.deploy.check_call') as check_call:
            deploy.run()
            # Then
            args = [
                '-var', 'component={}'.format(data['component_name']),
                '-var', 'aws_region={}'.format(data['aws_region']),
                '-var', 'env={}'.format(data['environment_name']),
                '-var', 'image={}'.format(image_name),
                '-var', 'team={}'.format(data['team']),
                '-var', 'version={}'.format(data['version']),
                '-var-file', data['platform_config_file']
            ]
            check_call.assert_any_call(
                ['terragrunt', 'plan', 'infra'] + args,
                env=ANY
            )
            check_call.assert_any_call(
                ['terragrunt', 'apply', 'infra'] + args,
                env=ANY
            )
