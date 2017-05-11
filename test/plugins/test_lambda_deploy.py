import unittest
from string import ascii_letters, printable

from boto3 import Session
from cdflow_commands.plugins.aws_lambda import (
    Deploy, DeployConfig, LambdaConfig
)
from hypothesis import given
from hypothesis.strategies import dictionaries, fixed_dictionaries, text
from mock import ANY, patch

IGNORED_PARAMS = [ANY] * 18
CALL_KWARGS = 2


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
        self._lambda_config = LambdaConfig(
            'dummy-handler',
            'dummy-runtime'
        )
        self._deploy = Deploy(
            boto_session, 'dummy-component', 'dummy-env', 'dummy-version',
            self._deploy_config, self._lambda_config
        )

    @patch('cdflow_commands.plugins.aws_lambda.check_call')
    @patch('cdflow_commands.plugins.aws_lambda.get_secrets')
    @patch('cdflow_commands.plugins.aws_lambda.NamedTemporaryFile')
    def test_terraform_modules_fetched(
        self, NamedTemporaryFile, get_secrets, check_call
    ):
        # When
        NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
        get_secrets.return_value = {}
        self._deploy.run()
        # Then
        check_call.assert_any_call(['terraform', 'get', 'infra'])

    @patch('cdflow_commands.plugins.aws_lambda.check_call')
    @patch('cdflow_commands.plugins.aws_lambda.get_secrets')
    @patch('cdflow_commands.plugins.aws_lambda.NamedTemporaryFile')
    def test_terraform_plan_called(
        self, NamedTemporaryFile, get_secrets, check_call
    ):
        # When
        NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
        get_secrets.return_value = {}
        self._deploy.run()
        # Then
        check_call.assert_any_call(
            ['terraform', 'plan'] + IGNORED_PARAMS + ['infra'],
            env=ANY
        )

    @patch('cdflow_commands.plugins.aws_lambda.check_call')
    @patch('cdflow_commands.plugins.aws_lambda.get_secrets')
    @patch('cdflow_commands.plugins.aws_lambda.NamedTemporaryFile')
    def test_terrgrunt_apply_called(
        self, NamedTemporaryFile, get_secrets, check_call
    ):
        # When
        NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
        get_secrets.return_value = {}
        self._deploy.run()
        # Then
        check_call.assert_any_call(
            ['terraform', 'apply'] + IGNORED_PARAMS + ['infra'],
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
    def test_terraform_passed_aws_credentials_from_session(
        self, credentials
    ):
        # Given
        boto_session = Session(
            credentials['access_key_id'],
            credentials['secret_access_key'],
            credentials['session_token'],
            'eu-west-10'
        )
        deploy = Deploy(
            boto_session, ANY, ANY, ANY, self._deploy_config,
            self._lambda_config
        )

        with patch(
            'cdflow_commands.plugins.aws_lambda.check_call'
        ) as check_call, patch(
            'cdflow_commands.plugins.aws_lambda.NamedTemporaryFile',
            autospec=True
        ) as NamedTemporaryFile, patch(
            'cdflow_commands.plugins.aws_lambda.get_secrets'
        ) as get_secrets:
            NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
            get_secrets.return_value = {}

            # When
            deploy.run()

            # Then
            check_call.assert_any_call(
                ['terraform', 'plan'] + IGNORED_PARAMS + ['infra'],
                env=ANY
            )
            plan_env = check_call.mock_calls[1][CALL_KWARGS]['env']
            assert plan_env['AWS_ACCESS_KEY_ID'] == \
                credentials['access_key_id']
            assert plan_env['AWS_SECRET_ACCESS_KEY'] == \
                credentials['secret_access_key']
            assert plan_env['AWS_SESSION_TOKEN'] == \
                credentials['session_token']

            check_call.assert_any_call(
                ['terraform', 'apply'] + IGNORED_PARAMS + ['infra'],
                env=ANY
            )
            apply_env = check_call.mock_calls[2][CALL_KWARGS]['env']
            assert apply_env['AWS_ACCESS_KEY_ID'] == \
                credentials['access_key_id']
            assert apply_env['AWS_SECRET_ACCESS_KEY'] == \
                credentials['secret_access_key']
            assert apply_env['AWS_SESSION_TOKEN'] == \
                credentials['session_token']

    @given(dictionaries(
        keys=text(alphabet=printable), values=text(alphabet=printable)
    ))
    def test_terraform_passed_copy_of_local_process_environment(
        self, mock_environment
    ):
        # Given
        boto_session = Session(
            'dummy-access_key_id',
            'dummy-secret_access_key',
            'dummy-session_token',
            'eu-west-10'
        )

        deploy = Deploy(
            boto_session, ANY, ANY, ANY, self._deploy_config,
            self._lambda_config
        )

        with patch(
            'cdflow_commands.plugins.aws_lambda.os'
        ) as mock_os, patch(
            'cdflow_commands.plugins.aws_lambda.check_call'
        ) as check_call, patch(
            'cdflow_commands.plugins.aws_lambda.NamedTemporaryFile',
            autospec=True
        ) as NamedTemporaryFile, patch(
            'cdflow_commands.plugins.aws_lambda.get_secrets'
        ) as get_secrets:
            NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
            get_secrets.return_value = {}
            mock_os.environ = mock_environment.copy()
            aws_env_vars = {
                'AWS_ACCESS_KEY_ID': 'dummy-access_key_id',
                'AWS_SECRET_ACCESS_KEY': 'dummy-secret_access_key',
                'AWS_SESSION_TOKEN': 'dummy-session_token'
            }
            expected_environment = {**mock_environment, **aws_env_vars}

            # When
            deploy.run()
            # Then
            check_call.assert_any_call(
                ['terraform', 'plan'] + IGNORED_PARAMS + ['infra'],
                env=expected_environment
            )
            check_call.assert_any_call(
                ['terraform', 'apply'] + IGNORED_PARAMS + ['infra'],
                env=expected_environment
            )

    @given(dictionaries(
        keys=text(alphabet=printable), values=text(alphabet=printable)
    ))
    def test_terraform_does_not_mutate_local_process_environment(
        self, mock_environment
    ):
        # Given
        boto_session = Session(
            'dummy-access_key_id',
            'dummy-secret_access_key',
            'dummy-session_token',
            'eu-west-10'
        )

        deploy = Deploy(
            boto_session, ANY, ANY, ANY, self._deploy_config,
            self._lambda_config
        )

        with patch(
            'cdflow_commands.plugins.aws_lambda.os'
        ) as mock_os, patch(
            'cdflow_commands.plugins.aws_lambda.check_call'
        ), patch(
            'cdflow_commands.plugins.aws_lambda.NamedTemporaryFile',
            autospec=True
        ) as NamedTemporaryFile, patch(
            'cdflow_commands.plugins.aws_lambda.get_secrets'
        ) as get_secrets:
            NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
            get_secrets.return_value = {}
            mock_os.environ = mock_environment.copy()

            # When
            deploy.run()

            # Then
            assert mock_os.environ == mock_environment

    deploy_data = fixed_dictionaries({
        'team': text(alphabet=printable, min_size=2, max_size=20),
        'dev_account_id': text(alphabet=printable, min_size=12, max_size=12),
        'aws_region': text(alphabet=printable, min_size=5, max_size=12),
        'component_name': text(alphabet=printable, min_size=2, max_size=30),
        'environment_name': text(alphabet=printable, min_size=2, max_size=10),
        'lambda_handler': text(alphabet=printable, min_size=2, max_size=10),
        'lambda_runtime': text(alphabet=printable, min_size=2, max_size=10),
        'version': text(alphabet=printable, min_size=1, max_size=20),
        'platform_config_file': text(
            alphabet=printable, min_size=10, max_size=30
        ),
    })

    @given(deploy_data)
    def test_lambda_terraform_gets_all_parameters(self, data):
        # Given
        boto_session = Session(
            'dummy-access-key-id', 'dummy-secret-access-key', 'dummy-token',
            data['aws_region']
        )
        deploy_config = DeployConfig(
            data['team'],
            data['dev_account_id'],
            data['platform_config_file']
        )
        lambda_config = LambdaConfig(
            data['lambda_handler'],
            data['lambda_runtime']
        )
        deploy = Deploy(
            boto_session,
            data['component_name'],
            data['environment_name'],
            data['version'],
            deploy_config,
            lambda_config
        )

        secret_file_path = '/mock/file/path'

        # When
        with patch(
            'cdflow_commands.plugins.aws_lambda.check_call'
        ) as check_call, patch(
            'cdflow_commands.plugins.aws_lambda.NamedTemporaryFile',
            autospec=True
        ) as NamedTemporaryFile, patch(
            'cdflow_commands.plugins.aws_lambda.get_secrets'
        ) as get_secrets:
            NamedTemporaryFile.return_value.__enter__.return_value.name = \
                secret_file_path
            get_secrets.return_value = {}

            deploy.run()

            # Then
            args = [
                '-var', 'component={}'.format(data['component_name']),
                '-var', 'env={}'.format(data['environment_name']),
                '-var', 'aws_region={}'.format(data['aws_region']),
                '-var', 'team={}'.format(data['team']),
                '-var', 'version={}'.format(data['version']),
                '-var', 'handler={}'.format(data['lambda_handler']),
                '-var', 'runtime={}'.format(data['lambda_runtime']),
                '-var-file', data['platform_config_file'],
                '-var-file', secret_file_path,
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


class TestEnvironmentSpecificConfigAddedToTerraformArgs(unittest.TestCase):

    @given(text(alphabet=ascii_letters, min_size=2, max_size=10))
    def test_environment_specific_config_in_args(self, env_name):

        # Given
        boto_session = Session(
            'dummy-access-key', 'dummy-secreet-access-key',
            'dummy-session-token', 'eu-west-1'
        )
        deploy_config = DeployConfig(
            'dummy-team', 'dummy-account-id', 'dummy-platform-config-file'
        )
        lambda_config = LambdaConfig(
            'dummy-handler',
            'dummy-runtime'
        )
        deploy = Deploy(
            boto_session, 'dummy-component', env_name,
            'dummy-version', deploy_config, lambda_config
        )

        # When
        with patch(
            'cdflow_commands.plugins.aws_lambda.check_call'
        ) as check_call, patch(
            'cdflow_commands.plugins.aws_lambda.path'
        ) as path, patch(
            'cdflow_commands.plugins.aws_lambda.NamedTemporaryFile',
            autospec=True
        ) as NamedTemporaryFile, patch(
            'cdflow_commands.plugins.aws_lambda.get_secrets'
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
                '-var', 'version=dummy-version',
                '-var', 'handler=dummy-handler',
                '-var', 'runtime=dummy-runtime',
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
