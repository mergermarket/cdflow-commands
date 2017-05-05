import unittest

from datetime import datetime
from mock import Mock, patch, MagicMock
from cdflow_commands.plugins.aws_lambda import Release
from cdflow_commands.config import GlobalConfig


class TestLambdaRelease(unittest.TestCase):

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_creates_zip_from_directory(self, zip_file, mock_os):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        boto_s3_client = Mock()
        boto_s3_client.list_buckets.return_value = {
            'Buckets': [],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }
        release = Release(
            config, boto_s3_client, 'dummy-component-name', metadata, '1.0.0'
        )
        release.create()
        zip_file.assert_called_once_with('dummy-component-name.zip', 'w')

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_does_not_create_bucket_if_bucket_already_exists(
        self, zip_file, mock_os
    ):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        metadata.aws_region = 'dummy-region'
        boto_s3_client = Mock()
        boto_s3_client.list_buckets.return_value = {
            'Buckets': [
                {
                    'Name': 'lambda-releases',
                    'CreationDate': datetime(2015, 1, 1)
                },
            ],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }
        release = Release(
            config, boto_s3_client, 'dummy-component-name', metadata, '1.0.0'
        )
        release.create()
        assert not boto_s3_client.create_bucket.called

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_creates_bucket_if_needed(self, zip_file, mock_os):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        metadata.aws_region = 'dummy-region'
        boto_s3_client = Mock()
        boto_s3_client.list_buckets.return_value = {
            'Buckets': [],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }
        release = Release(
            config, boto_s3_client, 'dummy-component-name', metadata, '1.0.0'
        )
        release.create()
        boto_s3_client.create_bucket.assert_called_once_with(
            ACL='private',
            Bucket='lambda-releases',
            CreateBucketConfiguration={
                'LocationConstraint': 'dummy-region'
            }
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_pushes_to_s3(self, zip_file, mock_os):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        boto_s3_client = Mock()
        boto_s3_client.list_buckets.return_value = {
            'Buckets': [],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }
        version = '1.0.0'
        release = Release(
            config, boto_s3_client, 'dummy-component-name', metadata, version
        )
        release.create()
        boto_s3_client.upload_file.assert_called_once_with(
            zip_file().__enter__().filename,
            'lambda-releases',
            'dummy-team-name/dummy-component-name/1.0.0.zip'
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_cleans_up_zip_after_push(self, zip_file, mock_os):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        boto_s3_client = Mock()
        boto_s3_client.list_buckets.return_value = {
            'Buckets': [],
            'Owner': {
                'DisplayName': 'string',
                'ID': 'string'
            }
        }
        version = '1.0.0'
        release = Release(
            config, boto_s3_client, 'dummy-component-name', metadata, version
        )
        release.create()
        mock_os.remove.assert_called_once_with(zip_file().__enter__().filename)
