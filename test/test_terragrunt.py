import unittest

from mock import Mock
from re import match

from hypothesis import given
from hypothesis.strategies import text

from botocore.exceptions import ClientError

from cdflow_commands import terragrunt
from cdflow_commands.terragrunt import S3BucketFactory


NEW_BUCKET_PATTERN = r'^cdflow-tfstate-[a-z0-9]+$'


class TestS3BucketFactory(unittest.TestCase):

    @given(text())
    def test_get_existing_bucket(self, bucket_name):
        # Given
        session = Mock()
        session.region_name = 'dummy-region'
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': [
                {'Name': bucket_name}
            ]
        }
        s3_client.get_bucket_tagging.return_value = {
            'TagSet': [
                {
                    'Key': terragrunt.TAG_NAME,
                    'Value': terragrunt.TAG_VALUE,
                }
            ]
        }

        s3_bucket_factory = S3BucketFactory(session, 'dummy-account-id')

        # When
        retrieved_bucket_name = s3_bucket_factory.get_bucket_name()

        # Then
        session.client.called_once_with('s3')
        s3_client.list_buckets.assert_called_once_with()
        s3_client.get_bucket_tagging.assert_called_once_with(
            Bucket=bucket_name
        )
        assert retrieved_bucket_name == bucket_name

    def test_assertion_error_on_multiple_buckets(self):

        # Given
        session = Mock()
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': [
                {'Name': 'terragrunt-bucket'},
                {'Name': 'another-terragrunt-bucket'}
            ]
        }

        s3_client.get_bucket_tagging.return_value = {
            'TagSet': [
                {
                    'Key': terragrunt.TAG_NAME,
                    'Value': terragrunt.TAG_VALUE,
                }
            ]
        }

        s3_bucket_factory = S3BucketFactory(session, 'dummy-account-id')

        # When & Then
        self.assertRaises(AssertionError, s3_bucket_factory.get_bucket_name)

    def test_handle_untagged_buckets(self):

        # Given
        session = Mock()
        session.region_nane = 'dummy-region-name'
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': [
                {'Name': 'another-bucket'},
                {'Name': 'terragrunt-bucket'}
            ]
        }

        def get_bucket_tagging(Bucket):
            if Bucket == 'terragrunt-bucket':
                return {
                    'TagSet': [
                        {
                            'Key': terragrunt.TAG_NAME,
                            'Value': terragrunt.TAG_VALUE,
                        }
                    ]
                }
            else:
                raise ClientError({
                    'Error': {
                        'Code': 'NoSuchTagSet',
                        'Message': 'The TagSet does not exist'
                    }
                }, 'GetBucketTagging')
        s3_client.get_bucket_tagging = get_bucket_tagging

        s3_bucket_factory = S3BucketFactory(session, 'dummy-account-id')

        # When
        bucket = s3_bucket_factory.get_bucket_name()

        # Then
        assert bucket == 'terragrunt-bucket'

    def test_bucket_created_and_tagged(self):

        # Given
        session = Mock()
        session.region_name = 'dummy-region-name'
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': []
        }

        s3_bucket_factory = S3BucketFactory(session, 'dummy-account-id')
        # When
        bucket_name = s3_bucket_factory.get_bucket_name()

        # Then
        s3_client.create_bucket.assert_called_once_with(Bucket=bucket_name)

        s3_client.put_bucket_tagging.assert_called_once_with(
            Bucket=bucket_name,
            Tagging={
                'TagSet': [
                    {
                        'Key': terragrunt.TAG_NAME,
                        'Value': terragrunt.TAG_VALUE,
                    }
                ]
            }
        )

    def test_bucket_name_generally_unique_based_on_account_and_region(self):

        # Given
        session = Mock()
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': []
        }

        # When
        session.region_name = 'region-1'
        bucket = S3BucketFactory(
            session, 'account-id-1'
        ).get_bucket_name()
        duplicate_bucket = S3BucketFactory(
            session, 'account-id-1'
        ).get_bucket_name()
        bucket_different_account = S3BucketFactory(
            session, 'account-id-2'
        ).get_bucket_name()
        session.region_name = 'region-2'
        bucket_different_region = S3BucketFactory(
            session, 'account-id-1'
        ).get_bucket_name()

        # Then
        assert match(NEW_BUCKET_PATTERN, bucket)
        assert match(NEW_BUCKET_PATTERN, duplicate_bucket)
        assert match(NEW_BUCKET_PATTERN, bucket_different_region)
        assert match(NEW_BUCKET_PATTERN, bucket_different_account)
        assert bucket == duplicate_bucket
        assert bucket != bucket_different_region
        assert bucket != bucket_different_account
        assert bucket_different_region != bucket_different_account

    def test_bucket_name_when_bucket_not_available(self):
        # Given
        session = Mock()
        session.region_name = 'dummy-region'
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': []
        }
        s3_client.create_bucket.side_effect = [
            ClientError({
                'Error': {
                    'Code': 'BucketAlreadyExists',
                    'Message': 'The requested bucket name is not available'
                }
            }, 'CreateBucket'),
            {}
        ]

        s3_bucket_factory = S3BucketFactory(session, 'dummy-account-id')

        # When
        bucket_name = s3_bucket_factory.get_bucket_name()

        # Then
        first_call, second_call = s3_client.create_bucket.mock_calls
        first_bucket_param = first_call[2]['Bucket']
        second_bucket_param = second_call[2]['Bucket']
        assert match(NEW_BUCKET_PATTERN, first_bucket_param)
        assert match(NEW_BUCKET_PATTERN, second_bucket_param)
        assert first_bucket_param != bucket_name
        assert second_bucket_param == bucket_name
