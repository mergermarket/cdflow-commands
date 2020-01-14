import unittest
from unittest.mock import Mock, patch, MagicMock, ANY
from io import TextIOWrapper
import json
from dataclasses import dataclass

import yaml

from cdflow_commands import cli


@dataclass
class creds:
    access_key: str
    secret_key: str
    token: str


class TestCliShell(unittest.TestCase):

    @patch('cdflow_commands.cli.copy')
    @patch('cdflow_commands.cli.copytree')
    @patch('cdflow_commands.state.check_call')
    @patch('cdflow_commands.config.open')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.check_output')
    @patch('cdflow_commands.cli.os.getcwd')
    @patch('cdflow_commands.cli.os.chdir')
    @patch('cdflow_commands.state.NamedTemporaryFile')
    @patch('cdflow_commands.state.check_output')
    @patch('cdflow_commands.state.atexit')
    @patch('cdflow_commands.cli.pty')
    def test_enters_shell(
        self, pty, atexit, check_output_state, NamedTemporaryFile_state, chdir,
        cli_getcwd, config_check_output, Session_from_config, Session_from_cli,
        _open, check_call_state, copytree, copy
    ):
        cli_getcwd.return_value = '/tmp/'

        config_check_output.return_value = (
            'git@github.com:org/my-component.git'
        ).encode('utf-8')

        Session_from_config.return_value.get_credentials.return_value = creds(
            'access-key', 'secret-key', 'token',
        )
        Session_from_config.return_value.region_name = 'eu-central-2'

        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)
        mock_metadata_file_open = MagicMock()
        mock_metadata_file_open.__enter__.return_value = mock_metadata_file
        _open.return_value = mock_metadata_file_open

        account_scheme = {
            'accounts': {
                'foodev': {
                    'id': '123456789',
                    'role': 'admin',
                }
            },
            'release-account': 'foodev',
            'release-bucket': 'releases',
            'default-region': 'us-north-4',
            'environments': {
                'live': 'foodev',
            },
            'terraform-backend-s3-bucket': 'tfstate-bucket',
            'terraform-backend-s3-dynamodb-table': 'tflocks-table',
        }

        mock_account_scheme = MagicMock(spec=TextIOWrapper)
        mock_account_scheme.read.return_value = json.dumps(account_scheme)
        mock_account_scheme_open = MagicMock()
        mock_account_scheme_open.__enter__.return_value = mock_account_scheme

        mock_sts_client = Mock()
        mock_sts_client.get_caller_identity.return_value = {
            u'UserId': 'foo',
            'Arn': 'dummy_arn'
        }
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

        mock_s3_body = Mock()
        mock_s3_body.read.return_value = json.dumps(account_scheme)

        mock_s3_resource = Mock()
        mock_s3_resource.Object.return_value.get.return_value = {
            'Body': mock_s3_body,
        }
        mock_root_session.resource.return_value = mock_s3_resource
        Session_from_cli.return_value = mock_root_session

        check_output_state.return_value = '* default\n  live'.encode('utf-8')

        cli.run(['shell', 'live', '-v'])

        check_call_state.assert_any_call(
            [
                'terraform', 'init',
                '-get=true', '-get-plugins=true',
                ANY, ANY, ANY, ANY, ANY, ANY, ANY, ANY,
                ANY,
            ],
            cwd=ANY,
        )

        check_call_state.assert_any_call(
            [
                'terraform', 'workspace', 'select', 'live',
                ANY,
            ],
            cwd=ANY,
        )

        pty.spawn.assert_called_once()

        mock_sts_client.assume_role.assert_called_with(
            DurationSeconds=14400,
            RoleArn='arn:aws:iam::123456789:role/admin',
            RoleSessionName=ANY,
        )

    @patch('cdflow_commands.cli.move')
    @patch('cdflow_commands.cli.copy')
    @patch('cdflow_commands.cli.copytree')
    @patch('cdflow_commands.state.check_call')
    @patch('cdflow_commands.config.open')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.check_output')
    @patch('cdflow_commands.cli.os.getcwd')
    @patch('cdflow_commands.cli.os.chdir')
    @patch('cdflow_commands.state.NamedTemporaryFile')
    @patch('cdflow_commands.state.check_output')
    @patch('cdflow_commands.cli.pty')
    @patch('cdflow_commands.release.time')
    @patch('cdflow_commands.release.ZipFile')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.state.atexit')
    def test_finds_release_and_enters_shell(
        self, atexit, TemporaryDirectory, ZipFile, time, pty,
        check_output_state, NamedTemporaryFile_state, cli_chdir, cli_getcwd,
        config_check_output, Session_from_config, Session_from_cli, _open,
        check_call_state, copytree, copy, move,
    ):

        cli_getcwd.return_value = '/tmp/my-component-1.2.3'

        TemporaryDirectory.return_value.__enter__.return_value = '/foo/'

        config_check_output.return_value = (
            'git@github.com:org/my-component.git'
        ).encode('utf-8')

        Session_from_config.return_value.get_credentials.return_value = creds(
            'access-key', 'secret-key', 'token',
        )
        Session_from_config.return_value.region_name = 'eu-central-2'

        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)
        mock_metadata_file_open = MagicMock()
        mock_metadata_file_open.__enter__.return_value = mock_metadata_file
        _open.return_value = mock_metadata_file_open

        account_scheme = {
            'accounts': {
                'foodev': {
                    'id': '123456789',
                    'role': 'admin',
                }
            },
            'release-account': 'foodev',
            'release-bucket': 'releases',
            'default-region': 'us-north-4',
            'environments': {
                'live': 'foodev',
            },
            'terraform-backend-s3-bucket': 'tfstate-bucket',
            'terraform-backend-s3-dynamodb-table': 'tflocks-table',
        }

        mock_account_scheme = MagicMock(spec=TextIOWrapper)
        mock_account_scheme.read.return_value = json.dumps(account_scheme)
        mock_account_scheme_open = MagicMock()
        mock_account_scheme_open.__enter__.return_value = mock_account_scheme

        mock_sts_client = Mock()
        mock_sts_client.get_caller_identity.return_value = {
            u'UserId': 'foo',
            'Arn': 'dummy_arn'
        }
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

        mock_s3_body = Mock()
        mock_s3_body.read.return_value = json.dumps(account_scheme)

        mock_s3_resource = Mock()
        mock_s3_resource.Object.return_value.get.return_value = {
            'Body': mock_s3_body,
        }
        mock_root_session.resource.return_value = mock_s3_resource
        Session_from_cli.return_value = mock_root_session

        check_output_state.return_value = '* default\n  live'.encode('utf-8')

        cli.run(['shell', 'live', '1.2.3'])

        check_call_state.assert_any_call(
            [
                'terraform', 'init',
                '-get=false', '-get-plugins=false',
                ANY, ANY, ANY, ANY, ANY, ANY, ANY, ANY,
                ANY,
            ],
            cwd=ANY,
        )

        check_call_state.assert_any_call(
            [
                'terraform', 'workspace', 'select', 'live',
                ANY,
            ],
            cwd=ANY,
        )

        pty.spawn.assert_called_once()

        mock_sts_client.assume_role.assert_called_with(
            DurationSeconds=14400,
            RoleArn='arn:aws:iam::123456789:role/admin',
            RoleSessionName=ANY,
        )

        ZipFile.assert_called_once()

        move.assert_any_call(
            '/foo/my-component-1.2.3/release.json',
            ANY,
        )

        move.assert_any_call(
            '/foo/my-component-1.2.3/platform-config',
            ANY,
        )

        move.assert_any_call(
            '/foo/my-component-1.2.3/.terraform',
            ANY,
        )
