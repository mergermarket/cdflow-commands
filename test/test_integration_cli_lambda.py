import unittest
import json
from io import TextIOWrapper
from datetime import datetime

from mock import Mock, MagicMock, patch, mock_open
import yaml

from cdflow_commands import cli


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.cli.check_output')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.plugins.aws_lambda.os')
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
    def test_release_package_is_created(
        self, check_output, mock_open_config, Session_from_config,
        Session_from_cli, rmtree, mock_os, mock_open_release, make_archive,
        check_call, copytree, mock_os_release, mock_os_lambda,
        ZipFile, check_output_cli, _
    ):
        # Given
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'account-scheme-url': 's3://bucket/key',
            'team': 'your-team',
            'type': 'lambda',
        }
        mock_metadata_file.read.return_value = yaml.dump(metadata)

        mock_open_config.return_value.__enter__.return_value = \
            mock_metadata_file

        check_output_cli.return_value = 'hash\n'.encode('utf-8')

        mock_root_session = Mock()
        mock_root_session.region_name = 'us-east-1'

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
            'lambda-bucket': 'dummy-lambda-bucket',
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

        Session_from_cli.return_value = mock_root_session

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
        Session_from_config.return_value = mock_session

        mock_sts = Mock()
        mock_sts.get_caller_identity.return_value = {
            u'UserId': 'foo',
            'Arn': 'dummy_arn'
        }
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
        version = '6.1.7'

        make_archive.return_value = '/tmp/tmpvyzXQB/{}-{}.zip'.format(
            component_name, version
        )

        mock_os_release.environ = {'CDFLOW_IMAGE_DIGEST': 'hash'}

        # When
        cli.run([
            'release', '--platform-config', 'path/to/config',
            version, '-c', component_name
        ])

        # Then
        mock_s3_client.upload_file.assert_called_once_with(
            ZipFile.return_value.__enter__.return_value.filename,
            'dummy-lambda-bucket',
            'dummy-component/dummy-component-6.1.7.zip'
        )

        mock_session.resource.return_value.Object.assert_called_once_with(
            'releases',
            '{}/{}-{}.zip'.format(component_name, component_name, version)
        )

        mock_session.resource.return_value.Object.return_value\
            .upload_file.assert_called_once_with(
                make_archive.return_value,
                ExtraArgs={'Metadata': {'cdflow_image_digest': 'hash'}},
            )
