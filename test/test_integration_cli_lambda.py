import unittest
import json

from collections import namedtuple
from io import TextIOWrapper
from datetime import datetime
from cdflow_commands import cli
from mock import Mock, MagicMock, patch, mock_open, ANY


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_release_package_is_created(
        self, mock_open, mock_os,
        session_from_cli, session_from_config, zip_file
    ):
        # Given
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'lambda',
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
        session_from_cli.return_value = mock_root_session

        mock_s3_client = Mock()
        mock_s3_client.list_buckets.return_value = {
            'Buckets': [],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }

        mock_session = Mock()
        mock_session.client.return_value = mock_s3_client
        session_from_config.return_value = mock_session

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
        version = '6.1.7'
        # When
        cli.run(['release', version, '-c', component_name])
        # Then
        mock_s3_client.upload_file.assert_called_once_with(
            zip_file().__enter__().filename,
            'lambda-releases',
            'dummy-team/dummy-component/6.1.7.zip'
        )


BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


class TestDeployCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.plugins.aws_lambda.check_call')
    @patch('cdflow_commands.plugins.aws_lambda.get_secrets')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.S3BucketFactory')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.state.check_call')
    @patch('cdflow_commands.plugins.aws_lambda.LockTableFactory')
    @patch('cdflow_commands.state.NamedTemporaryFile')
    @patch('cdflow_commands.state.move')
    @patch('cdflow_commands.state.atexit')
    def test_deploy_is_configured_and_run(
        self, _1, _2, _3, _4, check_call_state, mock_open,
        mock_lambda_s3_factory, mock_lambda_os, session_from_cli,
        session_from_config, get_secrets, check_call, rmtree
    ):
        # Given
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'lambda',
            'REGION': 'eu-west-12',
            'ACCOUNT_PREFIX': 'mmg',
            'HANDLER': 'dummy-handler',
            'RUNTIME': 'dummy-runtime'
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
        session_from_cli.return_value = mock_root_session

        mock_s3_client = Mock()
        mock_s3_client.list_buckets.return_value = {
            'Buckets': [],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }

        mock_assumed_session = Mock()
        mock_assumed_session.region_name = 'eu-west-12'
        mock_assumed_session.get_credentials.return_value = BotoCreds(
            'dummy-access-key-id',
            'dummy-secret-access-key',
            'dummy-session-token'
        )

        session_from_config.return_value = mock_assumed_session

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
        mock_lambda_os.environ = {
            'JOB_NAME': 'dummy-job-name'
        }
        get_secrets.return_value = {}

        component_name = 'dummy-component'

        # When
        cli.run(['deploy', 'aslive', '1.2.3', '-c', component_name])

        # Then
        check_call_state.assert_any_call(
            ['terraform', 'init', ANY, ANY, ANY, ANY],
            cwd='infra'
        )

        check_call.assert_any_call(['terraform', 'get', 'infra'])

        check_call.assert_any_call(
            [
                'terraform', 'plan',
                '-var', 'component=dummy-component',
                '-var', 'env=aslive',
                '-var', 'aws_region=eu-west-12',
                '-var', 'team=dummy-team',
                '-var', 'version=1.2.3',
                '-var', 'handler=dummy-handler',
                '-var', 'runtime=dummy-runtime',
                '-var-file', 'infra/platform-config/mmg/dev/eu-west-12.json',
                '-var-file', ANY,
                'infra'
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': 'dummy-access-key-id',
                'AWS_SECRET_ACCESS_KEY': 'dummy-secret-access-key',
                'AWS_SESSION_TOKEN': 'dummy-session-token'
            }
        )

        check_call.assert_any_call(
            [
                'terraform', 'apply',
                '-var', 'component=dummy-component',
                '-var', 'env=aslive',
                '-var', 'aws_region=eu-west-12',
                '-var', 'team=dummy-team',
                '-var', 'version=1.2.3',
                '-var', 'handler=dummy-handler',
                '-var', 'runtime=dummy-runtime',
                '-var-file', 'infra/platform-config/mmg/dev/eu-west-12.json',
                '-var-file', ANY,
                'infra'
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': 'dummy-access-key-id',
                'AWS_SECRET_ACCESS_KEY': 'dummy-secret-access-key',
                'AWS_SESSION_TOKEN': 'dummy-session-token'
            }
        )
