import json
import unittest
from datetime import datetime
from io import TextIOWrapper

from cdflow_commands import cli
from mock import MagicMock, Mock, mock_open, patch
import yaml


@patch('cdflow_commands.release._copy_platform_config')
@patch('cdflow_commands.cli.check_output')
@patch('cdflow_commands.release.os')
@patch('cdflow_commands.release.copytree')
@patch('cdflow_commands.release.check_call')
@patch('cdflow_commands.release.make_archive')
@patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
@patch('cdflow_commands.cli.os')
@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.Session')
@patch('cdflow_commands.config.Session')
@patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
@patch('cdflow_commands.config.check_output')
@patch('cdflow_commands.plugins.ecs.check_call')
class TestReleaseCLI(unittest.TestCase):

    def test_release_is_configured_and_created(
        self, check_call, check_output, mock_open, Session_from_config,
        Session_from_cli, rmtree, mock_os, mock_open_release, make_archive,
        check_call_release, copytree, mock_os_release, check_output_cli, _
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
            'classic-metadata-handling': True,
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
        user_id = 'foo'
        mock_sts.get_caller_identity.return_value = {u'UserId': user_id}
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

        mock_release_file = MagicMock(spec=TextIOWrapper)
        mock_open_release.return_value.__enter__.return_value = \
            mock_release_file

        component_name = 'dummy-component'
        version = '1.2.3'

        make_archive.return_value = '/tmp/tmpvyzXQB/{}-{}.zip'.format(
            component_name, version
        )

        mock_os_release.environ = {'CDFLOW_IMAGE_DIGEST': 'hash'}

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

        mock_sts.assume_role.assert_called_once_with(
            DurationSeconds=14400,
            RoleArn='arn:aws:iam::123456789:role/admin',
            RoleSessionName=user_id,
        )

        check_call.assert_any_call([
            'docker', 'build',
            '-t', image_name, '.'
        ])
        check_call.assert_any_call(['docker', 'push', image_name])

        mock_session.resource.return_value.Object.assert_called_once_with(
            'releases',
            '{}/{}-{}.zip'.format(component_name, component_name, version)
        )

        mock_session.resource.return_value.Object.return_value\
            .upload_file.assert_called_once_with(
                make_archive.return_value,
                ExtraArgs={'Metadata': {'cdflow_image_digest': 'hash'}},
            )

    def test_release_uses_component_name_from_origin(
        self, check_call, check_output, mock_open, Session_from_config,
        Session_from_cli, rmtree, mock_os, mock_open_release, make_archive,
        check_call_release, copytree, mock_os_release, check_output_cli, _
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
            'classic-metadata-handling': True,
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
        mock_sts.get_caller_identity.return_value = {'UserId': 'foo'}
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

        mock_os_release.environ = {'CDFLOW_IMAGE_DIGEST': 'hash'}

        cli.run([
            'release', '--platform-config', 'path/to/config', version,
        ])

        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            123456789,
            'us-north-4',
            component_name,
            version
        )

        check_call.assert_any_call([
            'docker', 'build',
            '-t', image_name, '.'
        ])
        check_call.assert_any_call(['docker', 'push', image_name])

        mock_session.resource.return_value.Object.assert_called_once_with(
            'releases',
            '{}/{}-{}.zip'.format(component_name, component_name, version)
        )

        mock_session.resource.return_value.Object.return_value\
            .upload_file.assert_called_once_with(
                make_archive.return_value,
                ExtraArgs={'Metadata': {'cdflow_image_digest': 'hash'}},
            )
