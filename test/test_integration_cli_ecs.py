import json
import unittest
from collections import namedtuple
from datetime import datetime
from io import TextIOWrapper

from cdflow_commands import cli
from mock import ANY, MagicMock, Mock, mock_open, patch
import yaml


@patch('cdflow_commands.cli.check_output')
@patch('cdflow_commands.release.copytree')
@patch('cdflow_commands.release.check_call')
@patch('cdflow_commands.release.make_archive')
@patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.plugins.ecs.os')
@patch('cdflow_commands.cli.Session')
@patch('cdflow_commands.config.Session')
@patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
@patch('cdflow_commands.config.check_output')
@patch('cdflow_commands.plugins.ecs.check_call')
class TestReleaseCLI(unittest.TestCase):

    def test_release_is_configured_and_created(
        self, check_call, check_output, mock_open, Session_from_config,
        Session_from_cli, mock_os, rmtree, mock_open_release, make_archive,
        check_call_release, copytree, check_output_cli
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)

        mock_open.return_value.__enter__.return_value = mock_metadata_file

        mock_root_session = Mock()
        mock_root_session.region_name = 'us-east-1'
        Session_from_cli.return_value = mock_root_session

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

        mock_release_file = MagicMock(spec=TextIOWrapper)
        mock_open_release.return_value.__enter__.return_value = \
            mock_release_file

        component_name = 'dummy-component'
        version = '1.2.3'

        make_archive.return_value = '/tmp/tmpvyzXQB/{}-{}.zip'.format(
            component_name, version
        )

        check_output_cli.return_value = 'hash\n'.encode('utf-8')

        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            123456789,
            'us-north-4',
            component_name,
            version
        )

        cli.run([
            'release', '--platform-config', 'path/to/config',
            version, '-c', component_name
        ])

        check_output_cli.assert_called_once_with(['git', 'rev-parse', 'HEAD'])

        check_call.assert_any_call(['docker', 'build', '-t', image_name, '.'])
        check_call.assert_any_call(['docker', 'push', image_name])

        mock_session.resource.return_value.Object.assert_called_once_with(
            'releases',
            '{}/{}-{}.zip'.format(component_name, component_name, version)
        )

        mock_session.resource.return_value.Object.return_value\
            .upload_file.assert_called_once_with(make_archive.return_value)

    def test_release_uses_component_name_from_origin(
        self, check_call, check_output, mock_open, Session_from_config,
        Session_from_cli, mock_os, rmtree, mock_open_release, make_archive,
        check_call_release, copytree, check_output_cli
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'docker',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)

        mock_open.return_value.__enter__.return_value = mock_metadata_file

        mock_root_session = Mock()
        mock_root_session.region_name = 'us-east-1'
        Session_from_cli.return_value = mock_root_session

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

        mock_release_file = MagicMock(spec=TextIOWrapper)
        mock_open_release.return_value.__enter__.return_value = \
            mock_release_file

        component_name = 'dummy-component'
        version = '1.2.3'

        make_archive.return_value = '/tmp/tmpvyzXQB/{}-{}.zip'.format(
            component_name, version
        )

        check_output_cli.return_value = 'hash\n'.encode('utf-8')

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        cli.run([
            'release', '--platform-config', 'path/to/config', version,
        ])

        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            123456789,
            'us-north-4',
            component_name,
            version
        )

        check_call.assert_any_call(['docker', 'build', '-t', image_name, '.'])
        check_call.assert_any_call(['docker', 'push', image_name])

        mock_session.resource.return_value.Object.assert_called_once_with(
            'releases',
            '{}/{}-{}.zip'.format(component_name, component_name, version)
        )

        mock_session.resource.return_value.Object.return_value\
            .upload_file.assert_called_once_with(make_archive.return_value)


BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])


@patch('cdflow_commands.release.ZipFile')
@patch('cdflow_commands.release.TemporaryDirectory')
@patch('cdflow_commands.deploy.os')
@patch('cdflow_commands.deploy.check_call')
@patch('cdflow_commands.deploy.time')
@patch('cdflow_commands.deploy.NamedTemporaryFile')
@patch('cdflow_commands.deploy.get_secrets')
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
        get_secrets, NamedTemporaryFile_deploy, time, check_call_deploy,
        mock_os, TemporaryDirectory, ZipFile,
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
            mock_db_client, mock_s3_client,
        )

        Session_from_config.return_value = mock_assumed_session

        mock_os.environ = {'JOB_NAME': 'dummy-job-name'}

        component_name = 'dummy-component'

        check_output.return_value = 'git@github.com:org/{}.git'.format(
            component_name
        ).encode('utf-8')

        get_secrets.return_value = {}

        return (
            check_call_state, check_call_deploy, TemporaryDirectory,
            mock_assumed_session, NamedTemporaryFile_deploy, time,
            aws_access_key_id, aws_secret_access_key, aws_session_token,
            rmtree,
        )

    def test_deploy_is_configured_and_run(self, *args):
        check_call_state, check_call_deploy, TemporaryDirectory, \
            mock_assumed_session, NamedTemporaryFile_deploy, time, \
            aws_access_key_id, aws_secret_access_key, aws_session_token, \
            rmtree = self.setup_mocks(*args)

        # When
        cli.run(['deploy', 'live', '1.2.3'])

        # Then
        check_call_state.assert_any_call(
            ['terraform', 'init', ANY, ANY, ANY, ANY],
            cwd='{}/infra'.format(
                TemporaryDirectory.return_value.__enter__.return_value
            )
        )

        check_call_deploy.assert_any_call(
            [
                'terraform', 'plan', 'infra',
                '-var', 'env=live',
                '-var', 'aws_region={}'.format(
                    mock_assumed_session.region_name
                ),
                '-var-file', 'release.json',
                '-var-file', ANY,
                '-var-file',
                NamedTemporaryFile_deploy.return_value.__enter__.return_value,
                '-out', 'plan-{}'.format(time.return_value),
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            },
            cwd=TemporaryDirectory.return_value.__enter__.return_value,
        )

        check_call_deploy.assert_any_call(
            [
                'terraform', 'apply', 'plan-{}'.format(time.return_value),
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            },
            cwd=TemporaryDirectory.return_value.__enter__.return_value,
        )

        rmtree.assert_called_once_with('.terraform/')

    def test_deploy_is_planned_with_flag(self, *args):
        check_call_state, check_call_deploy, TemporaryDirectory, \
            mock_assumed_session, NamedTemporaryFile_deploy, time, \
            aws_access_key_id, aws_secret_access_key, aws_session_token, \
            rmtree = self.setup_mocks(*args)
        # When
        cli.run(['deploy', 'live', '1.2.3', '--plan-only'])

        # Then
        check_call_deploy.assert_called_once_with(
            [
                'terraform', 'plan', 'infra',
                '-var', 'env=live',
                '-var', 'aws_region={}'.format(
                    mock_assumed_session.region_name
                ),
                '-var-file', 'release.json',
                '-var-file', ANY,
                '-var-file',
                NamedTemporaryFile_deploy.return_value.__enter__.return_value,
                '-out', 'plan-{}'.format(time.return_value),
            ],
            env={
                'JOB_NAME': 'dummy-job-name',
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token
            },
            cwd=TemporaryDirectory.return_value.__enter__.return_value,
        )


class TestDestroyCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.plugins.ecs.S3BucketFactory')
    @patch('cdflow_commands.plugins.ecs.LockTableFactory')
    @patch('cdflow_commands.plugins.base.os')
    @patch('cdflow_commands.plugins.ecs.os')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.plugins.base.check_call')
    @patch('cdflow_commands.config.check_output')
    @patch('cdflow_commands.state.check_call')
    @patch('cdflow_commands.state.NamedTemporaryFile')
    @patch('cdflow_commands.state.move')
    @patch('cdflow_commands.state.atexit')
    def test_destroy_is_configured_and_run(
        self, _1, _2, _3, check_call_state, check_output, check_call,
        mock_open, Session_from_config, Session_from_cli, mock_os_cli,
        mock_os_deploy, _4, _5, rmtree
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
