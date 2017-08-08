import json
import unittest
from collections import namedtuple
from io import TextIOWrapper

from cdflow_commands import cli
from cdflow_commands.constants import (
    CDFLOW_BASE_PATH, TERRAFORM_BINARY, TERRAFORM_DESTROY_DEFINITION,
)
from mock import ANY, MagicMock, Mock, patch
import yaml


BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


@patch.dict('cdflow_commands.cli.os.environ', {'JOB_NAME': 'dummy-job-name'})
@patch('cdflow_commands.secrets.credstash')
@patch('cdflow_commands.release.os')
@patch('cdflow_commands.release.ZipFile')
@patch('cdflow_commands.release.TemporaryDirectory')
@patch('cdflow_commands.deploy.os')
@patch('cdflow_commands.deploy.check_call')
@patch('cdflow_commands.deploy.time')
@patch('cdflow_commands.deploy.NamedTemporaryFile')
@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.Session')
@patch('cdflow_commands.config.Session')
@patch('cdflow_commands.config.open')
@patch('cdflow_commands.config.check_output')
@patch('cdflow_commands.state.NamedTemporaryFile')
@patch('cdflow_commands.state.check_call')
@patch('cdflow_commands.state.move')
@patch('cdflow_commands.state.atexit')
class TestDeployCLI(unittest.TestCase):

    def setup_mocks(
        self, atexit, move, check_call_state, NamedTemporaryFile_state,
        check_output, _open, Session_from_config, Session_from_cli, rmtree,
        NamedTemporaryFile_deploy, time,
        check_call_deploy, mock_os_deploy, TemporaryDirectory, ZipFile,
        mock_os_release, credstash,
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)

        _open.return_value.__enter__.return_value = mock_metadata_file

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

        mock_s3_body = Mock()
        mock_s3_body.read.return_value = json.dumps({
            'accounts': {
                'foodev': {
                    'id': '123456789',
                    'role': 'admon',
                }
            },
            'release-account': 'foodev',
            'release-bucket': 'releases',
            'default-region': 'us-north-4',
            'environments': {
                'live': 'foodev',
            }
        })

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

        return (
            check_call_state, check_call_deploy, TemporaryDirectory,
            mock_assumed_session, NamedTemporaryFile_deploy, time,
            aws_access_key_id, aws_secret_access_key, aws_session_token,
            rmtree, component_name,
        )

    def test_deploy_is_configured_and_run(self, *args):
        check_call_state, check_call_deploy, TemporaryDirectory, \
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
            ['terraform', 'init', ANY, ANY, ANY, ANY, ANY],
            cwd=workdir+'/infra'
        )

        check_call_deploy.assert_any_call(
            [
                'terraform', 'plan', '-input=false',
                '-var', 'env=live',
                '-var', 'aws_region={}'.format(
                    mock_assumed_session.region_name
                ),
                '-var-file', 'release.json',
                '-var-file', ANY,
                '-var-file',
                NamedTemporaryFile_deploy.return_value.__enter__.return_value
                .name,
                '-out', 'plan-{}'.format(time.return_value),
                'infra',
            ],
            env={
                'foo': 'bar',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            },
            cwd=workdir,
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
                'AWS_SESSION_TOKEN': aws_session_token
            },
            cwd=workdir,
        )

        rmtree.assert_called_once_with('.terraform/')

    def test_deploy_is_planned_with_flag(self, *args):
        check_call_state, check_call_deploy, TemporaryDirectory, \
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
        check_call_deploy.assert_called_once_with(
            [
                'terraform', 'plan', '-input=false',
                '-var', 'env=live',
                '-var', 'aws_region={}'.format(
                    mock_assumed_session.region_name
                ),
                '-var-file', 'release.json',
                '-var-file', ANY,
                '-var-file',
                NamedTemporaryFile_deploy.return_value.__enter__.return_value
                .name,
                '-out', 'plan-{}'.format(time.return_value),
                'infra',
            ],
            env={
                'foo': 'bar',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            },
            cwd=workdir,
        )


@patch.dict('cdflow_commands.cli.os.environ', {'JOB_NAME': 'dummy-job-name'})
@patch('cdflow_commands.destroy.check_call')
@patch('cdflow_commands.destroy.time')
@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.Session')
@patch('cdflow_commands.config.Session')
@patch('cdflow_commands.config.open')
@patch('cdflow_commands.config.check_output')
@patch('cdflow_commands.state.NamedTemporaryFile')
@patch('cdflow_commands.state.check_call')
@patch('cdflow_commands.state.move')
@patch('cdflow_commands.state.atexit')
class TestDestroyCLI(unittest.TestCase):

    def setup_mocks(
        self, atexit, move, check_call_state, NamedTemporaryFile_state,
        check_output, _open, Session_from_config, Session_from_cli, rmtree,
        time, check_call_destroy,
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)

        _open.return_value.__enter__.return_value = mock_metadata_file

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

        mock_s3_body = Mock()
        mock_s3_body.read.return_value = json.dumps({
            'accounts': {
                'foodev': {
                    'id': '123456789',
                    'role': 'admon',
                }
            },
            'release-account': 'foodev',
            'release-bucket': 'releases',
            'default-region': 'us-north-4',
            'environments': {
                'live': 'foodev',
            }
        })

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

        remove_state_mock_s3 = Mock()

        mock_assumed_session.client.side_effect = (
            mock_s3_client, mock_db_client, mock_s3_client,
            remove_state_mock_s3,
        )

        Session_from_config.return_value = mock_assumed_session

        component_name = 'dummy-component'

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        return (
            check_call_state, mock_assumed_session, time, aws_access_key_id,
            aws_secret_access_key, aws_session_token, component_name,
            check_call_destroy, remove_state_mock_s3,
        )

    def test_uses_terraform_to_destroy(self, *args):
        check_call_state, mock_assumed_session, time, aws_access_key_id, \
            aws_secret_access_key, aws_session_token, component_name, \
            check_call_destroy, remove_state_mock_s3 = self.setup_mocks(*args)

        environment = 'live'
        state_file_key = '{}/{}/terraform.tfstate'.format(
            environment, component_name
        )

        cli.run(['destroy', environment])

        check_call_state.assert_called_once_with(
            [
                TERRAFORM_BINARY, 'init',
                '-get-plugins=false',
                '-backend-config=bucket=tfstate',
                '-backend-config=region=us-north-4',
                '-backend-config=key={}'.format(state_file_key),
                '-backend-config=lock_table=terraform_locks',
            ],
            cwd=ANY,
        )

        check_call_destroy.assert_any_call(
            [
                TERRAFORM_BINARY, 'plan', '-destroy',
                '-var', 'aws_region=us-north-4',
                '-out', ANY, TERRAFORM_DESTROY_DEFINITION,
            ],
            env=ANY,
            cwd=CDFLOW_BASE_PATH,
        )

        check_call_destroy.assert_any_call(
            [TERRAFORM_BINARY, 'apply', ANY],
            env=ANY,
            cwd=CDFLOW_BASE_PATH,
        )

        remove_state_mock_s3.delete_object.assert_called_once_with(
            Bucket='tfstate', Key=state_file_key
        )

    def test_plan_only_does_not_destroy_or_remove_state(self, *args):
        check_call_state, mock_assumed_session, time, aws_access_key_id, \
            aws_secret_access_key, aws_session_token, component_name, \
            check_call_destroy, remove_state_mock_s3 = self.setup_mocks(*args)

        environment = 'live'
        state_file_key = '{}/{}/terraform.tfstate'.format(
            environment, component_name
        )

        cli.run(['destroy', environment, '--plan-only'])

        check_call_state.assert_called_once_with(
            [
                TERRAFORM_BINARY, 'init',
                '-get-plugins=false',
                '-backend-config=bucket=tfstate',
                '-backend-config=region=us-north-4',
                '-backend-config=key={}'.format(state_file_key),
                '-backend-config=lock_table=terraform_locks',
            ],
            cwd=ANY,
        )

        check_call_destroy.assert_called_once_with(
            [
                TERRAFORM_BINARY, 'plan', '-destroy',
                '-var', 'aws_region=us-north-4',
                '-out', ANY, TERRAFORM_DESTROY_DEFINITION,
            ],
            env=ANY,
            cwd=CDFLOW_BASE_PATH,
        )

        remove_state_mock_s3.delete_object.assert_not_called()
