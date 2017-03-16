import unittest

import json
from io import TextIOWrapper
from datetime import datetime
from collections import namedtuple
from string import printable

from mock import patch, Mock, mock_open, MagicMock, ANY

from hypothesis import given, assume
from hypothesis.strategies import text

from cdflow_commands.ecs_monitor import ECSMonitor
from cdflow_commands import cli
from cdflow_commands.ecs_monitor import (
    InProgressEvent, DoneEvent
)
from cdflow_commands.exceptions import UserFacingError


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.unlink')
@patch('cdflow_commands.cli.os')
@patch('cdflow_commands.cli.Session')
@patch('cdflow_commands.config.Session')
@patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
@patch('cdflow_commands.config.check_output')
@patch('cdflow_commands.release.check_call')
class TestReleaseCLI(unittest.TestCase):

    def test_release_is_configured_and_created(
        self, check_call, _1, mock_open,
        Session_from_config, Session_from_cli, mock_os, _2, _3
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-12',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_metadata_file.read.return_value = json.dumps(metadata)

        mock_dev_file = MagicMock(spec=TextIOWrapper)
        dev_config = {
            'platform_config': {
                'account_id': 123456789,
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=TextIOWrapper)
        prod_config = {
            'platform_config': {
                'account_id': 987654321,
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'
        Session_from_cli.return_value = mock_root_session

        mock_ecr_client = Mock()
        mock_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': 'dXNlcm5hbWU6cGFzc3dvcmQ=',
                    'proxyEndpoint': 'dummy-endpoint'
                }
            ]
        }

        mock_session = Mock()
        mock_session.client.return_value = mock_ecr_client
        Session_from_config.return_value = mock_session

        mock_sts = Mock()
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'dummy-access-key-id',
                'SecretAccessKey': 'dummy-secret-access-key',
                'SessionToken': 'dummy-session-token',
                'Expiration': datetime(2015, 1, 1)
            },
            'AssumedRoleUser': {
                'AssumedRoleId': 'dummy-assumed-role-id',
                'Arn': 'dummy-arn'
            },
            'PackedPolicySize': 123
        }
        mock_root_session.client.return_value = mock_sts

        mock_os.environ = {
            'JOB_NAME': 'dummy-job-name'
        }

        component_name = 'dummy-component'
        version = '1.2.3'
        cli.run(['release', version, '-c', component_name])

        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            123456789,
            'eu-west-12',
            component_name,
            version
        )

        check_call.assert_any_call(['docker', 'build', '-t', image_name, '.'])
        check_call.assert_any_call(['docker', 'push', image_name])

    def test_release_uses_component_name_from_origin(
        self, check_call, check_output, mock_open,
        Session_from_config, Session_from_cli, mock_os, _1, _2
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-12',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_metadata_file.read.return_value = json.dumps(metadata)

        mock_dev_file = MagicMock(spec=TextIOWrapper)
        dev_config = {
            'platform_config': {
                'account_id': 123456789,
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=TextIOWrapper)
        prod_config = {
            'platform_config': {
                'account_id': 987654321,
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'
        Session_from_cli.return_value = mock_root_session

        mock_ecr_client = Mock()
        mock_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': 'dXNlcm5hbWU6cGFzc3dvcmQ=',
                    'proxyEndpoint': 'dummy-endpoint'
                }
            ]
        }

        mock_session = Mock()
        mock_session.client.return_value = mock_ecr_client
        Session_from_config.return_value = mock_session

        mock_sts = Mock()
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'dummy-access-key-id',
                'SecretAccessKey': 'dummy-secret-access-key',
                'SessionToken': 'dummy-session-token',
                'Expiration': datetime(2015, 1, 1)
            },
            'AssumedRoleUser': {
                'AssumedRoleId': 'dummy-assumed-role-id',
                'Arn': 'dummy-arn'
            },
            'PackedPolicySize': 123
        }
        mock_root_session.client.return_value = mock_sts

        mock_os.environ = {
            'JOB_NAME': 'dummy-job-name'
        }

        component_name = 'dummy-component'
        version = '1.2.3'

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        cli.run(['release', version])

        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            123456789,
            'eu-west-12',
            component_name,
            version
        )

        check_call.assert_any_call(['docker', 'build', '-t', image_name, '.'])
        check_call.assert_any_call(['docker', 'push', image_name])


BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


class TestDeployCLI(unittest.TestCase):

    def setUp(self):
        self._original_interval = ECSMonitor._INTERVAL
        ECSMonitor._INTERVAL = 0.1

    def tearDown(self):
        ECSMonitor._INTERVAL = self._original_interval

    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.cli.unlink')
    @patch('cdflow_commands.cli.ECSEventIterator')
    @patch('cdflow_commands.cli.S3BucketFactory')
    @patch('cdflow_commands.deploy.os')
    @patch('cdflow_commands.cli.os')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.deploy.check_call')
    @patch('cdflow_commands.config.check_output')
    @patch('cdflow_commands.deploy.get_secrets')
    @patch('cdflow_commands.deploy.NamedTemporaryFile')
    def test_deploy_is_configured_and_run(
        self, NamedTemporaryFile, get_secrets, check_output, check_call,
        mock_open, Session_from_config, Session_from_cli, mock_os_cli,
        mock_os_deploy, _, ECSEventIterator, unlink, rmtree
    ):
        mock_os_cli.environ = {
            'JOB_NAME': 'dummy-job-name'
        }
        mock_os_deploy.environ = {}

        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-12',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_metadata_file.read.return_value = json.dumps(metadata)

        mock_dev_file = MagicMock(spec=TextIOWrapper)
        dev_config = {
            'platform_config': {
                'account_id': 123456789,
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=TextIOWrapper)
        prod_config = {
            'platform_config': {
                'account_id': 987654321,
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        mock_sts_client = Mock()
        mock_sts_client.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'dummy-access-key',
                'SecretAccessKey': 'dummy-secret-key',
                'SessionToken': 'dummy-session-token',
            }
        }

        mock_root_session = Mock()
        mock_root_session.client.return_value = mock_sts_client
        mock_root_session.region_name = 'eu-west-12'
        Session_from_cli.return_value = mock_root_session

        aws_access_key_id = 'dummy-access-key-id'
        aws_secret_access_key = 'dummy-secret-access-key'
        aws_session_token = 'dummy-session-token'
        mock_assumed_session = Mock()
        mock_assumed_session.region_name = 'eu-west-12'
        mock_assumed_session.get_credentials.return_value = BotoCreds(
            aws_access_key_id,
            aws_secret_access_key,
            aws_session_token
        )

        Session_from_config.return_value = mock_assumed_session

        component_name = 'dummy-component'

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
        get_secrets.return_value = {}

        ECSEventIterator.return_value = [
            InProgressEvent(0, 0, 2, 0, []),
            InProgressEvent(1, 0, 2, 0, []),
            DoneEvent(2, 0, 2, 0, [])
        ]

        # When
        with self.assertLogs('cdflow_commands.logger', level='INFO') as logs:
            cli.run(['deploy', 'aslive', '1.2.3'])

        # Then
        check_call.assert_any_call(['terragrunt', 'get', 'infra'])

        image_name = (
            '123456789.dkr.ecr.eu-west-12.amazonaws.com/'
            'dummy-component:1.2.3'
        )

        check_call.assert_any_call(
            [
                'terragrunt', 'plan',
                '-var', 'component=dummy-component',
                '-var', 'env=aslive',
                '-var', 'aws_region=eu-west-12',
                '-var', 'team=dummy-team',
                '-var', 'image={}'.format(image_name),
                '-var', 'version=1.2.3',
                '-var', 'ecs_cluster=default',
                '-var-file', 'infra/platform-config/mmg/dev/eu-west-12.json',
                '-var-file', ANY,
                'infra'
            ],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            }
        )

        check_call.assert_any_call(
            [
                'terragrunt', 'apply',
                '-var', 'component=dummy-component',
                '-var', 'env=aslive',
                '-var', 'aws_region=eu-west-12',
                '-var', 'team=dummy-team',
                '-var', 'image={}'.format(image_name),
                '-var', 'version=1.2.3',
                '-var', 'ecs_cluster=default',
                '-var-file', 'infra/platform-config/mmg/dev/eu-west-12.json',
                '-var-file', ANY,
                'infra'
            ],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            }
        )

        assert logs.output == [
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 0 previous: 0'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 1 previous: 0'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 2 previous: 0'),
            'INFO:cdflow_commands.logger:Deployment complete'
        ]

        rmtree.assert_called_once_with('.terraform/')
        unlink.assert_called_once_with('.terragrunt')


class TestSetupForInfrastructure(unittest.TestCase):

    @given(text(alphabet=printable))
    def test_dev_session_passed_to_non_live_deployments(
        self, environment_name
    ):
        # Given
        assume(environment_name != 'live')
        metadata = Mock()
        global_config = Mock()
        global_config.dev_account_id = 123456789
        global_config.prod_account_id = 987654321
        root_session = Mock()
        sts_client = Mock()
        sts_client.assume_role.return_value = {'Credentials': {
            'AccessKeyId': 'dummy-access-key-id',
            'SecretAccessKey': 'dummy-secret-access-key',
            'SessionToken': 'dummy-session-token',
        }}
        root_session.client.return_value = sts_client

        with patch(
            'cdflow_commands.cli.os'
        ) as mock_os, patch(
            'cdflow_commands.cli.S3BucketFactory'
        ):
            mock_os.environ = {'JOB_NAME': 'dummy-job'}

            # When
            cli._setup_for_infrastructure(
                environment_name, 'dummy-component-name',
                metadata, global_config, root_session
            )

            # Then
            sts_client.assume_role.assert_called_once_with(
                RoleArn='arn:aws:iam::123456789:role/admin',
                RoleSessionName='dummy-job',
            )

    @patch('cdflow_commands.cli.os')
    @patch('cdflow_commands.cli.S3BucketFactory')
    def test_prod_session_passed_to_live_deployments(
        self, S3BucketFactory, mock_os
    ):
        # Given
        metadata = Mock()
        global_config = Mock()
        global_config.dev_account_id = 123456789
        global_config.prod_account_id = 987654321
        root_session = Mock()
        sts_client = Mock()
        sts_client.assume_role.return_value = {'Credentials': {
            'AccessKeyId': 'dummy-access-key-id',
            'SecretAccessKey': 'dummy-secret-access-key',
            'SessionToken': 'dummy-session-token',
        }}
        root_session.client.return_value = sts_client

        mock_os.environ = {'JOB_NAME': 'dummy-job'}

        # When
        cli._setup_for_infrastructure(
            'live', 'dummy-component-name',
            metadata, global_config, root_session
        )

        # Then
        sts_client.assume_role.assert_called_once_with(
            RoleArn='arn:aws:iam::987654321:role/admin',
            RoleSessionName='dummy-job',
        )

    @patch('cdflow_commands.cli.os')
    @patch('cdflow_commands.cli.Deploy')
    @patch(
        'cdflow_commands.terragrunt.open', new_callable=mock_open, create=True
    )
    @patch('cdflow_commands.config.Session')
    def test_tfstate_bucket_set_up_in_dev_account_for_aslive_deployment(
        self, Session, mock_open, _, mock_os
    ):
        # Given
        metadata = Mock()
        global_config = Mock()
        global_config.dev_account_id = 123456789
        global_config.prod_account_id = 987654321
        root_session = Mock()
        sts_client = Mock()
        sts_client.assume_role.return_value = {'Credentials': {
            'AccessKeyId': 'dummy-access-key-id',
            'SecretAccessKey': 'dummy-secret-access-key',
            'SessionToken': 'dummy-session-token',
        }}
        root_session.client.return_value = sts_client

        mock_s3_client = Mock()
        mock_s3_client.list_buckets = MagicMock(spec=dict)

        mock_assumed_session = Mock()
        mock_assumed_session.region_name = 'eu-west-4'
        mock_assumed_session.client.return_value = mock_s3_client
        Session.return_value = mock_assumed_session

        mock_os.environ = {'JOB_NAME': 'dummy-job'}

        # When
        cli._setup_for_infrastructure(
            'aslive', 'dummy-component-name',
            metadata, global_config, root_session
        )

        # Then
        mock_open.assert_called_once_with('.terragrunt', 'w')


class TestDestroyCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.cli.unlink')
    @patch('cdflow_commands.cli.S3BucketFactory')
    @patch('cdflow_commands.destroy.os')
    @patch('cdflow_commands.cli.os')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.destroy.check_call')
    @patch('cdflow_commands.config.check_output')
    def test_destroy_is_configured_and_run(
        self, check_output, check_call, mock_open,
        Session_from_config, Session_from_cli, mock_os_cli, mock_os_deploy, _,
        unlink, rmtree
    ):
        # Given
        mock_os_cli.environ = {
            'JOB_NAME': 'dummy-job-name'
        }
        mock_os_deploy.environ = {}

        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-12',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_metadata_file.read.return_value = json.dumps(metadata)

        mock_dev_file = MagicMock(spec=TextIOWrapper)
        dev_config = {
            'platform_config': {
                'account_id': 123456789,
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=TextIOWrapper)
        prod_config = {
            'platform_config': {
                'account_id': 987654321,
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        mock_sts_client = Mock()
        mock_sts_client.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'dummy-access-key',
                'SecretAccessKey': 'dummy-secret-key',
                'SessionToken': 'dummy-session-token',
            }
        }

        mock_root_session = Mock()
        mock_root_session.client.return_value = mock_sts_client
        mock_root_session.region_name = 'eu-west-12'
        Session_from_cli.return_value = mock_root_session

        aws_access_key_id = 'dummy-access-key-id'
        aws_secret_access_key = 'dummy-secret-access-key'
        aws_session_token = 'dummy-session-token'
        mock_assumed_session = Mock()
        mock_assumed_session.region_name = 'eu-west-12'
        mock_assumed_session.get_credentials.return_value = BotoCreds(
            aws_access_key_id,
            aws_secret_access_key,
            aws_session_token
        )

        Session_from_config.return_value = mock_assumed_session

        component_name = 'dummy-component'

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        # When
        cli.run(['destroy', 'aslive'])

        # Then
        check_call.assert_any_call(
            [
                'terragrunt', 'plan', '-destroy',
                '-var', 'aws_region=eu-west-12',
                '/cdflow/tf-destroy'
            ],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            }
        )

        check_call.assert_any_call(
            [
                'terragrunt', 'destroy', '-force',
                '-var', 'aws_region=eu-west-12',
                '/cdflow/tf-destroy'
            ],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            }
        )

        rmtree.assert_called_once_with('.terraform/')
        unlink.assert_called_once_with('.terragrunt')


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.unlink')
@patch('cdflow_commands.cli.sys')
@patch('cdflow_commands.cli.load_service_metadata')
class TestVerboseLogging(unittest.TestCase):

    def test_verbose_flag_in_arguments(
        self, load_service_metadata, _1, _2, _3
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run(['release', 'version', '--verbose'])

        # Then
        assert 'DEBUG:cdflow_commands.logger:Debug logging on' in logs.output

    def test_short_verbose_flag_in_arguments(
        self, load_service_metadata, _1, _2, _3
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run(['release', 'version', '-v'])

        # Then
        assert 'DEBUG:cdflow_commands.logger:Debug logging on' in logs.output


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.unlink')
@patch('cdflow_commands.cli.sys')
@patch('cdflow_commands.cli.load_service_metadata')
class TestUserFacingErrorThrown(unittest.TestCase):

    def test_non_zero_exit(
        self, load_service_metadata, mock_sys, _1, _2
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError('Error')

        # When
        with self.assertLogs('cdflow_commands.logger', level='ERROR') as logs:
            cli.run(['release', 'version'])

        # Then
        mock_sys.exit.assert_called_once_with(1)
        expected_message = 'ERROR:cdflow_commands.logger:Error'
        assert expected_message in logs.output

    def test_files_are_always_attempted_to_be_removed(
        self, load_service_metadata, mock_sys, unlink, rmtree
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError

        # When
        cli.run(['release', 'version'])

        # Then
        rmtree.assert_called_once_with('.terraform/')
        unlink.assert_called_once_with('.terragrunt')

    def test_missing_files_are_ignored(
        self, load_service_metadata, mock_sys, unlink, rmtree
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError
        unlink.side_effect = OSError
        rmtree.side_effect = OSError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run(['release', 'version'])

        # Then
        rmtree.assert_called_once_with('.terraform/')
        unlink.assert_called_once_with('.terragrunt')

        message_template = 'DEBUG:cdflow_commands.logger:No path {} to remove'
        assert message_template.format('.terraform/') in logs.output
        assert message_template.format('.terragrunt') in logs.output
