import unittest

from mock import Mock, patch, MagicMock

from cdflow_commands.account import AccountScheme
from cdflow_commands.plugins.aws_lambda import ReleasePlugin
from cdflow_commands.release import Release


class TestLambdaReleasePlugin(unittest.TestCase):

    def setUp(self):
        boto_session = Mock()
        self._ecr_client = Mock()
        boto_session.client.return_value = self._ecr_client
        self._release = MagicMock(spec=Release)
        self._release.multi_region = False

        self._release.boto_session = boto_session

        self._component_name = 'dummy-component'
        self._release.component_name = self._component_name

        self._version = '1.2.3'
        self._release.version = self._version

        self._region = 'dummy-region'
        self._account_id = 'dummy-account-id'
        self._account_scheme = AccountScheme.create({
            'accounts': {
                'dummy': {
                    'id': self._account_id,
                    'role': 'dummy'
                }
            },
            'release-account': 'dummy',
            'default-region': self._region,
            'release-bucket': 'dummy',
            'lambda-bucket': 'dummy-lambda-bucket',
            'lambda-buckets': {
                'test-region1': 'dummy-lambda-bucket',
                'test-region2': 'dummy-lambda-bucket2',
            },
            'environments': {
                'live': 'dummy',
            },
            'terraform-backend-s3-bucket': 'tfstate-bucket',
            'terraform-backend-s3-dynamodb-table': 'tflocks-table'
        }, 'a-team')

        self._plugin = ReleasePlugin(self._release, self._account_scheme)

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_returns_release_data(
        self, zip_file, mock_os
    ):

        plugin_data = self._plugin.create()

        assert plugin_data == {
            's3_bucket': 'dummy-lambda-bucket',
            's3_key': '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            ),
        }

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_creates_zip_from_directory(self, zip_file, mock_os):
        self._plugin.create()
        zip_file.assert_called_once_with(
            '{}.zip'.format(self._component_name), 'w'
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_pushes_to_s3(
        self, zip_file, mock_os
    ):
        boto_s3_client = Mock()
        self._release.boto_session.client.return_value = boto_s3_client
        self._plugin.create()
        boto_s3_client.upload_file.assert_called_once_with(
            zip_file().__enter__().filename,
            'dummy-lambda-bucket',
            '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            )
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_pushes_to_multiple_s3_regions(
        self, zip_file, mock_os
    ):
        # Given
        boto_s3_client_region1 = Mock()
        boto_s3_client_region2 = Mock()
        self._release.boto_session.client.side_effect = \
            lambda service, region_name: boto_s3_client_region1 \
            if region_name == 'test-region1' else boto_s3_client_region2
        self._release.multi_region = True

        # When
        plugin_data = ReleasePlugin(
            self._release, self._account_scheme
        ).create()

        # Then
        self.assertEqual(plugin_data, {
            's3_bucket.test-region1': 'dummy-lambda-bucket',
            's3_bucket.test-region2': 'dummy-lambda-bucket2',
            's3_bucket_regions_csv': 'test-region1,test-region2',
            's3_key': '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            ),
        })
        self._release.boto_session.client.assert_any_call(
            's3', region_name='test-region1'
        )
        self._release.boto_session.client.assert_any_call(
            's3', region_name='test-region2'
        )
        boto_s3_client_region1.upload_file.assert_any_call(
            zip_file().__enter__().filename,
            'dummy-lambda-bucket',
            '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            )
        )
        boto_s3_client_region2.upload_file.assert_any_call(
            zip_file().__enter__().filename,
            'dummy-lambda-bucket2',
            '{}/{}-{}.zip'.format(
                self._component_name, self._component_name, self._version
            )
        )

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_cleans_up_zip_after_push(self, zip_file, mock_os):
        self._plugin.create()
        mock_os.remove.assert_called_once_with(zip_file().__enter__().filename)
