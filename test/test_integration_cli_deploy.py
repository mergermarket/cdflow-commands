import json
import unittest
from collections import namedtuple
from io import TextIOWrapper
from os.path import join
from subprocess import PIPE

import yaml

from cdflow_commands import cli
from cdflow_commands.constants import (
    INFRASTRUCTURE_DEFINITIONS_PATH, ACCOUNT_SCHEME_FILE
)
from mock import ANY, MagicMock, Mock, patch


BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


@patch('cdflow_commands.secrets.credstash')
@patch('cdflow_commands.release.os')
@patch('cdflow_commands.release.ZipFile')
@patch('cdflow_commands.release.TemporaryDirectory')
@patch('cdflow_commands.deploy.os')
@patch('cdflow_commands.deploy.Popen')
@patch('cdflow_commands.deploy.check_call')
@patch('cdflow_commands.deploy.time')
@patch('cdflow_commands.deploy.NamedTemporaryFile')
@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.Session')
@patch('cdflow_commands.config.Session')
@patch('cdflow_commands.config.open')
@patch('cdflow_commands.config.check_output')
@patch('cdflow_commands.state.NamedTemporaryFile')
@patch('cdflow_commands.state.check_output')
@patch('cdflow_commands.state.check_call')
@patch('cdflow_commands.state.atexit')
class TestDeployCLI(unittest.TestCase):

    def setup_mocks(
        self, atexit, check_call_state, check_output_state,
        NamedTemporaryFile_state, check_output, _open, Session_from_config,
        Session_from_cli, rmtree, NamedTemporaryFile_deploy, time,
        check_call_deploy, popen_call, mock_os_deploy, TemporaryDirectory,
        ZipFile, mock_os_release, credstash,
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)
        mock_metadata_file_open = MagicMock()
        mock_metadata_file_open.__enter__.return_value = mock_metadata_file

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

        _open.side_effect = lambda filename: \
            mock_account_scheme_open \
            if filename.endswith(ACCOUNT_SCHEME_FILE) \
            else mock_metadata_file_open

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

        aws_access_key_id = 'dummy-access-key-id'
        aws_secret_access_key = 'dummy-secret-access-key'
        aws_session_token = 'dummy-session-token'

        mock_assumed_session = Mock()
        mock_assumed_session.region_name = 'us-north-4'
        mock_assumed_session.get_credentials.return_value = BotoCreds(
            aws_access_key_id,
            aws_secret_access_key,
            aws_session_token
        )

        mock_db_client = Mock()
        mock_db_client.describe_table.return_value = {
            'Table': {
                'TableName': 'terraform_locks',
                'AttributeDefinitions': [{'AttributeName': 'LockID'}]
            }
        }

        mock_s3_client = Mock()
        mock_s3_client.list_buckets.return_value = {
            'Buckets': [{'Name': 'tfstate'}]
        }
        mock_s3_client.get_bucket_tagging.return_value = {
            'TagSet': [{'Key': 'is-cdflow-tfstate-bucket', 'Value': 'true'}],
        }
        mock_s3_client.get_bucket_location.return_value = {
            'LocationConstraint': mock_assumed_session.region_name,
        }

        mock_assumed_session.client.side_effect = (
            mock_s3_client, mock_db_client,
        )

        Session_from_config.return_value = mock_assumed_session

        TemporaryDirectory.return_value.__enter__.return_value = '/tmp/foo'

        mock_os_deploy.environ = {'foo': 'bar'}

        mock_os_release.environ = {'CDFLOW_IMAGE_DIGEST': 'hash'}

        component_name = 'dummy-component'

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        credstash.listSecrets.return_value = []

        process_mock = Mock()
        process_mock.poll.return_value = 0
        attrs = {
            'communicate.return_value': (
                ''.encode('utf-8'),
                ''.encode('utf-8')
            )
        }
        process_mock.configure_mock(**attrs)
        popen_call.return_value = process_mock

        check_output_state.return_value = '* default'.encode('utf-8')

        return (
            check_call_state, check_call_deploy, popen_call,
            TemporaryDirectory, mock_assumed_session,
            NamedTemporaryFile_deploy, time, aws_access_key_id,
            aws_secret_access_key, aws_session_token, rmtree, component_name,
        )

    def test_deploy_is_configured_and_run(self, *args):
        check_call_state, check_call_deploy, popen_call, TemporaryDirectory, \
            mock_assumed_session, NamedTemporaryFile_deploy, time, \
            aws_access_key_id, aws_secret_access_key, aws_session_token, \
            rmtree, component_name = self.setup_mocks(*args)

        # Given
        version = '1.2.3'

        workdir = '{}/{}-{}'.format(
            TemporaryDirectory.return_value.__enter__.return_value,
            component_name, version,
        )

        # When
        cli.run(['deploy', 'live', version])

        # Then
        check_call_state.assert_any_call(
            [
                'terraform', 'init',
                ANY, ANY, ANY, ANY, ANY, ANY, ANY, ANY, ANY, ANY,
                join(workdir, INFRASTRUCTURE_DEFINITIONS_PATH),
            ],
            cwd=workdir,
        )

        popen_call.assert_any_call(
            [
                'terraform', 'plan', '-input=false',
                '-var', 'env=live',
                '-var-file', 'release.json',
                '-var-file', ANY,
                '-var-file',
                NamedTemporaryFile_deploy.return_value.__enter__.return_value
                .name,
                '-out', 'plan-{}'.format(time.return_value),
                'infra',
            ],
            cwd=workdir,
            env={
                'foo': 'bar',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token,
                'AWS_DEFAULT_REGION': mock_assumed_session.region_name
            },
            stdout=PIPE, stderr=PIPE
        )

        check_call_deploy.assert_any_call(
            [
                'terraform', 'apply', '-input=false',
                'plan-{}'.format(time.return_value),
            ],
            env={
                'foo': 'bar',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token,
                'AWS_DEFAULT_REGION': mock_assumed_session.region_name,
            },
            cwd=workdir,
        )

        rmtree.assert_called_once_with('.terraform/')

    def test_deploy_is_planned_with_flag(self, *args):
        check_call_state, check_call_deploy, popen_call, TemporaryDirectory, \
            mock_assumed_session, NamedTemporaryFile_deploy, time, \
            aws_access_key_id, aws_secret_access_key, aws_session_token, \
            rmtree, component_name = self.setup_mocks(*args)

        # Given
        version = '1.2.3'

        workdir = '{}/{}-{}'.format(
            TemporaryDirectory.return_value.__enter__.return_value,
            component_name, version,
        )
        # When
        cli.run(['deploy', 'live', version, '--plan-only'])

        # Then
        popen_call.assert_called_once_with(
            [
                'terraform', 'plan', '-input=false',
                '-var', 'env=live',
                '-var-file', 'release.json',
                '-var-file', ANY,
                '-var-file',
                NamedTemporaryFile_deploy.return_value.__enter__.return_value
                .name,
                '-out', 'plan-{}'.format(time.return_value),
                'infra',
            ],
            cwd=workdir,
            env={
                'foo': 'bar',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token,
                'AWS_DEFAULT_REGION': mock_assumed_session.region_name,
            },
            stdout=PIPE, stderr=PIPE
        )
