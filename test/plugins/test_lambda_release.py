import unittest

# from datetime import datetime
from mock import Mock, patch, MagicMock
from cdflow_commands.plugins.aws_lambda import Release
from cdflow_commands.config import GlobalConfig
from cdflow_commands.state import S3BucketFactory


class TestLambdaRelease(unittest.TestCase):

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.plugins.aws_lambda.S3BucketFactory')
    def test_release_creates_zip_from_directory(self, _, zip_file, mock_os):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        boto_session = Mock()
        boto_s3_client = Mock()
        boto_session.client.return_value = boto_s3_client
        release = Release(
            config, boto_session, 'dummy-component-name', metadata, '1.0.0'
        )
        release.create()
        zip_file.assert_called_once_with('dummy-component-name.zip', 'w')

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch(
        'cdflow_commands.plugins.aws_lambda.S3BucketFactory',
        autospec=S3BucketFactory
    )
    def test_release_gets_bucket_name(
        self, s3_bucket_factory, zip_file, mock_os
    ):
        # Given
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        metadata.aws_region = 'dummy-region'
        boto_session = Mock()
        release = Release(
            config, boto_session, 'dummy-component-name', metadata, '1.0.0'
        )
        s3_bucket_factory_mock = s3_bucket_factory.return_value = Mock()
        # When
        release.create()
        # Then
        s3_bucket_factory_mock.get_bucket_name.assert_called_once_with(
            'cdflow-lambda-releases'
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch(
        'cdflow_commands.plugins.aws_lambda.S3BucketFactory',
        autospec=S3BucketFactory
    )
    def test_release_pushes_to_s3(
        self, mock_lambda_s3_factory, zip_file, mock_os
    ):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        boto_session = Mock()
        boto_s3_client = Mock()
        boto_session.client.return_value = boto_s3_client
        version = '1.0.0'
        release = Release(
            config, boto_session, 'dummy-component-name', metadata, version
        )
        mock_lambda_s3_factory.return_value.get_bucket_name.return_value \
            = 'lambda-bucket'
        release.create()
        boto_s3_client.upload_file.assert_called_once_with(
            zip_file().__enter__().filename,
            'lambda-bucket',
            'dummy-team-name/dummy-component-name/1.0.0.zip'
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.plugins.aws_lambda.S3BucketFactory')
    def test_release_cleans_up_zip_after_push(self, _, zip_file, mock_os):
        config = MagicMock(spec=GlobalConfig)
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        boto_session = Mock()
        boto_s3_client = Mock()
        boto_session.client.return_value = boto_s3_client
        version = '1.0.0'
        release = Release(
            config, boto_session, 'dummy-component-name', metadata, version
        )
        release.create()
        mock_os.remove.assert_called_once_with(zip_file().__enter__().filename)
