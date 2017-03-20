import json
import unittest
from collections import namedtuple
from io import TextIOWrapper

from cdflow_commands import cli
from mock import ANY, MagicMock, Mock, patch


BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


class TestDeployCLI(unittest.TestCase):

    def setUp(self):
        self.rmtree_patcher = patch('cdflow_commands.cli.rmtree')
        self.unlink_patcher = patch('cdflow_commands.cli.unlink')
        self.S3BucketFactory_patcher = patch(
            'cdflow_commands.plugins.infrastructure.S3BucketFactory'
        )
        self.mock_os_deploy_patcher = patch(
            'cdflow_commands.plugins.infrastructure.os'
        )
        self.Session_from_cli_patcher = patch('cdflow_commands.cli.Session')
        self.Session_from_config_patcher = patch(
            'cdflow_commands.config.Session'
        )
        self.mock_open_patcher = patch('cdflow_commands.config.open')
        self.check_call_patcher = patch(
            'cdflow_commands.plugins.infrastructure.check_call'
        )
        self.check_output_patcher = patch(
            'cdflow_commands.config.check_output'
        )
        self.get_secrets_patcher = patch(
            'cdflow_commands.plugins.infrastructure.get_secrets'
        )
        self.NamedTemporaryFile_patcher = patch(
            'cdflow_commands.plugins.infrastructure.NamedTemporaryFile'
        )
        self.rmtree = self.rmtree_patcher.start()
        self.unlink = self.unlink_patcher.start()
        self.S3BucketFactory = self.S3BucketFactory_patcher.start()
        self.mock_os_deploy = self.mock_os_deploy_patcher.start()
        self.Session_from_cli = self.Session_from_cli_patcher.start()
        self.Session_from_config = self.Session_from_config_patcher.start()
        self.mock_open = self.mock_open_patcher.start()
        self.check_call = self.check_call_patcher.start()
        self.check_output = self.check_output_patcher.start()
        self.get_secrets = self.get_secrets_patcher.start()
        self.NamedTemporaryFile = self.NamedTemporaryFile_patcher.start()

        self.mock_os_deploy.environ = {
            'JOB_NAME': 'dummy-job-name'
        }

        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'infrastructure',
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

        self.mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        self.mock_sts_client = Mock()
        self.mock_sts_client.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'dummy-access-key',
                'SecretAccessKey': 'dummy-secret-key',
                'SessionToken': 'dummy-session-token',
            }
        }

        mock_root_session = Mock()
        mock_root_session.client.return_value = self.mock_sts_client
        mock_root_session.region_name = 'eu-west-12'
        self.Session_from_cli.return_value = mock_root_session

        self.aws_access_key_id = 'dummy-access-key-id'
        self.aws_secret_access_key = 'dummy-secret-access-key'
        self.aws_session_token = 'dummy-session-token'

        mock_assumed_session = Mock()
        mock_assumed_session.region_name = 'eu-west-12'
        mock_assumed_session.get_credentials.return_value = BotoCreds(
            self.aws_access_key_id,
            self.aws_secret_access_key,
            self.aws_session_token
        )

        self.Session_from_config.return_value = mock_assumed_session

        component_name = 'dummy-component'

        self.check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        self.NamedTemporaryFile.return_value.__enter__.return_value.name = ANY
        self.get_secrets.return_value = {}

    def tearDown(self):
        self.rmtree_patcher.stop()
        self.unlink_patcher.stop()
        self.S3BucketFactory_patcher.stop()
        self.mock_os_deploy_patcher.stop()
        self.Session_from_cli_patcher.stop()
        self.Session_from_config_patcher.stop()
        self.mock_open_patcher.stop()
        self.check_call_patcher.stop()
        self.check_output_patcher.stop()
        self.get_secrets_patcher.stop()
        self.NamedTemporaryFile_patcher.stop()

    def test_deploy_is_configured_and_run(self):
        # Given

        # When
        cli.run([
            'deploy', 'aslive',
            '--var', 'raindrops=roses',
            '--var', 'whiskers=kittens'
        ])

        # Then
        self.check_call.assert_any_call(['terragrunt', 'get', 'infra'])

        self.check_call.assert_any_call(
            [
                'terragrunt', 'plan',
                '-var', 'component=dummy-component',
                '-var', 'env=aslive',
                '-var', 'aws_region=eu-west-12',
                '-var', 'team=dummy-team',
                '-var-file', 'infra/platform-config/mmg/dev/eu-west-12.json',
                '-var-file', ANY,
                '-var', 'raindrops=roses',
                '-var', 'whiskers=kittens',
                'infra'
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': self.aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': self.aws_secret_access_key,
                'AWS_SESSION_TOKEN': self.aws_session_token
            }
        )

        self.check_call.assert_any_call(
            [
                'terragrunt', 'apply',
                '-var', 'component=dummy-component',
                '-var', 'env=aslive',
                '-var', 'aws_region=eu-west-12',
                '-var', 'team=dummy-team',
                '-var-file', 'infra/platform-config/mmg/dev/eu-west-12.json',
                '-var-file', ANY,
                '-var', 'raindrops=roses',
                '-var', 'whiskers=kittens',
                'infra'
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': self.aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': self.aws_secret_access_key,
                'AWS_SESSION_TOKEN': self.aws_session_token
            }
        )
