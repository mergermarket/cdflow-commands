import json
import unittest
from collections import namedtuple
from io import TextIOWrapper

from cdflow_commands import cli
from mock import ANY, MagicMock, Mock, mock_open, patch

BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.config.check_output')
    def test_release_is_a_no_op(
        self, check_output, mock_open, Session_from_cli, _
    ):
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

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'
        Session_from_cli.return_value = mock_root_session

        with self.assertLogs('cdflow_commands.logger', level='INFO') as logs:
            cli.run(['release'])

        message = (
            'INFO:cdflow_commands.logger:'
            'Release takes no action on infrastructure type project'
        )
        assert message in logs.output


class TestDeployCLI(unittest.TestCase):

    def setUp(self):
        self.rmtree_patcher = patch('cdflow_commands.cli.rmtree')
        self.S3BucketFactory_patcher = patch(
            'cdflow_commands.plugins.infrastructure.S3BucketFactory'
        )
        self.LockTableFactory_patcher = patch(
            'cdflow_commands.plugins.infrastructure.LockTableFactory'
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
        self.NamedTemporaryFile_state_patcher = patch(
            'cdflow_commands.state.NamedTemporaryFile'
        )
        self.check_call_state_patcher = patch(
            'cdflow_commands.state.check_call'
        )
        self.rename_patcher = patch(
            'cdflow_commands.state.rename'
        )
        self.rmtree = self.rmtree_patcher.start()
        self.S3BucketFactory = self.S3BucketFactory_patcher.start()
        self.LockTableFactory = self.LockTableFactory_patcher.start()
        self.mock_os_deploy = self.mock_os_deploy_patcher.start()
        self.Session_from_cli = self.Session_from_cli_patcher.start()
        self.Session_from_config = self.Session_from_config_patcher.start()
        self.mock_open = self.mock_open_patcher.start()
        self.check_call = self.check_call_patcher.start()
        self.check_output = self.check_output_patcher.start()
        self.get_secrets = self.get_secrets_patcher.start()
        self.NamedTemporaryFile = self.NamedTemporaryFile_patcher.start()
        self.NamedTemporaryFile_state = \
            self.NamedTemporaryFile_state_patcher.start()
        self.check_call_state = self.check_call_state_patcher.start()
        self.rename = self.rename_patcher.start()

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
        self.S3BucketFactory_patcher.stop()
        self.LockTableFactory_patcher.stop()
        self.mock_os_deploy_patcher.stop()
        self.Session_from_cli_patcher.stop()
        self.Session_from_config_patcher.stop()
        self.mock_open_patcher.stop()
        self.check_call_patcher.stop()
        self.check_output_patcher.stop()
        self.get_secrets_patcher.stop()
        self.NamedTemporaryFile_patcher.stop()
        self.NamedTemporaryFile_state_patcher.stop()
        self.check_call_state_patcher.stop()
        self.rename_patcher.stop()

    def test_deploy_is_configured_and_run(self):
        # Given

        # When
        cli.run([
            'deploy', 'aslive',
            '--var', 'raindrops=roses',
            '--var', 'whiskers=kittens'
        ])

        # Then
        self.check_call_state.assert_any_call(
            ['terraform', 'init', ANY, ANY, ANY, ANY],
            cwd='infra'
        )

        self.check_call.assert_any_call(['terraform', 'get', 'infra'])

        self.check_call.assert_any_call(
            [
                'terraform', 'plan',
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
                'terraform', 'apply',
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


class TestDestroyCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.plugins.infrastructure.S3BucketFactory')
    @patch('cdflow_commands.plugins.infrastructure.LockTableFactory')
    @patch('cdflow_commands.plugins.base.os')
    @patch('cdflow_commands.plugins.infrastructure.os')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.plugins.base.check_call')
    @patch('cdflow_commands.config.check_output')
    @patch('cdflow_commands.state.check_call')
    @patch('cdflow_commands.state.NamedTemporaryFile')
    @patch('cdflow_commands.state.rename')
    def test_destroy_is_configured_and_run(
        self, _1, _2, check_call_state, check_output, check_call, mock_open,
        Session_from_config, Session_from_cli, mock_os_cli, mock_os_deploy,
        _3, _4, rmtree
    ):
        # Given
        mock_os_cli.environ = {
            'JOB_NAME': 'dummy-job-name'
        }
        mock_os_deploy.environ = {}

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
        check_call_state.assert_any_call(
            ['terraform', 'init', ANY, ANY, ANY, ANY],
            cwd='/cdflow/tf-destroy'
        )

        check_call.assert_any_call(
            [
                'terraform', 'plan', '-destroy',
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
                'terraform', 'destroy', '-force',
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
