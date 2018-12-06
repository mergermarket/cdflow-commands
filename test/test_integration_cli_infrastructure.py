import json
import unittest
from datetime import datetime
from io import TextIOWrapper

from mock import MagicMock, Mock, mock_open, patch
import yaml

from cdflow_commands import cli


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.os')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.cli.check_output')
    @patch('cdflow_commands.cli.os')
    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.config.check_output')
    def test_release_is_a_no_op(
        self, check_output, mock_open, Session_from_config, Session_from_cli,
        rmtree, mock_os, check_output_cli, mock_open_release, make_archive,
        check_call_release, copytree, mock_os_release, _
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'infrastructure',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)

        mock_open.return_value.__enter__.return_value = mock_metadata_file

        check_output_cli.return_value = 'hash\n'.encode('utf-8')

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

        component_name = 'dummy-component'
        version = '1.2.3'

        mock_os_release.environ = {'CDFLOW_IMAGE_DIGEST': 'hash'}

        make_archive.return_value = '/tmp/tmpvyzXQB/{}-{}.zip'.format(
            component_name, version
        )

        cli.run([
            'release', '--platform-config', 'path/to/config',
            version, '-c', component_name
        ])

        Session_from_config.return_value.resource.return_value.Object\
            .assert_called_once_with(
                'releases',
                '{}/{}-{}.zip'.format(component_name, component_name, version)
            )

        Session_from_config.return_value.resource.return_value.Object.\
            return_value.upload_file.assert_called_once_with(
                make_archive.return_value,
                ExtraArgs={'Metadata': {'cdflow_image_digest': 'hash'}},
            )
