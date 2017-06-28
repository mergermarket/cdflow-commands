import unittest

from mock import Mock, patch, MagicMock

from cdflow_commands.account import AccountScheme
from cdflow_commands.plugins.aws_lambda import ReleasePlugin
from cdflow_commands.release import Release
from cdflow_commands.state import S3BucketFactory


class TestLambdaReleasePlugin(unittest.TestCase):

    def setUp(self):
        boto_session = Mock()
        self._ecr_client = Mock()
        boto_session.client.return_value = self._ecr_client
        self._release = MagicMock(spec=Release)

        self._release.boto_session = boto_session

        self._component_name = 'dummy-component'
        self._release.component_name = self._component_name

        self._version = '1.2.3'
        self._release.version = self._version

        self._release.all_environment_config = {
            'lambda_handler': 'handler',
            'lambda_runtime': 'python36',
        }

        self._region = 'dummy-region'
        self._account_id = 'dummy-account-id'
        account_scheme = AccountScheme.create({
            'accounts': {
                'dummy': {
                    'id': self._account_id,
                    'role': 'dummy'
                }
            },
            'release-account': 'dummy',
            'default-region': self._region,
            'release-bucket': 'dummy',
            'environments': {
                'live': 'dummy',
            },
        })

        self._plugin = ReleasePlugin(self._release, account_scheme)

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.plugins.aws_lambda.S3BucketFactory')
    def test_release_returns_release_data(
        self, S3BucketFactory, zip_file, mock_os
    ):
        S3BucketFactory.return_value.get_bucket_name.return_value = 'bucket'

        plugin_data = self._plugin.create()

        assert plugin_data == {
            'handler': 'handler',
            'runtime': 'python36',
            's3_bucket': 'bucket',
            's3_key': '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            ),
        }

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.plugins.aws_lambda.S3BucketFactory')
    def test_release_creates_zip_from_directory(self, _, zip_file, mock_os):
        self._plugin.create()
        zip_file.assert_called_once_with(
            '{}.zip'.format(self._component_name), 'w'
        )

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
        s3_bucket_factory_mock = s3_bucket_factory.return_value = Mock()
        # When
        self._plugin.create()
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
        boto_s3_client = Mock()
        self._release.boto_session.client.return_value = boto_s3_client
        mock_lambda_s3_factory.return_value.get_bucket_name.return_value \
            = 'lambda-bucket'
        self._plugin.create()
        boto_s3_client.upload_file.assert_called_once_with(
            zip_file().__enter__().filename,
            'lambda-bucket',
            '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            )
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    @patch('cdflow_commands.plugins.aws_lambda.S3BucketFactory')
    def test_release_cleans_up_zip_after_push(self, _, zip_file, mock_os):
        self._plugin.create()
        mock_os.remove.assert_called_once_with(zip_file().__enter__().filename)
