import unittest

from mock import Mock, patch
from cdflow_commands.plugins.aws_lambda import Release


class TestLambdaRelease(unittest.TestCase):

    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_create_zips_directory(self, zip_file):
        config = Mock()
        metadata = Mock()
        self._boto_s3_client = Mock()
        release = Release(
            config, self._boto_s3_client, 'dummy-component-name', metadata
        )
        release.create()
        zip_file.assert_called_once_with('dummy-component-name.zip', 'x')

    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_creates_bucket_with_teamname(self, zip_file):
        config = Mock()
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        metadata.aws_region = 'dummy-region'
        boto_s3_client = Mock()
        release = Release(
            config, boto_s3_client, 'dummy-component-name', metadata
        )
        release.create()
        assert boto_s3_client.create_bucket.called_once_with(
            ACL='private',
            Bucket='dummy-team-name',
            CreateBucketConfiguration={
                'LocationConstraint': 'dummy-region'
            }
        )

    @patch('cdflow_commands.plugins.aws_lambda.ZipFile')
    def test_release_pushes_to_s3(self, zip_file):
        config = Mock()
        metadata = Mock()
        metadata.team = 'dummy-team-name'
        self._boto_s3_client = Mock()
        release = Release(
            config, self._boto_s3_client, 'dummy-component-name', metadata
        )
        release.create()
        self._boto_s3_client.put_object.assert_called_once_with(
            Body=zip_file(),
            Bucket='dummy-team-name',
            Key='dummy-component-name'
        )
