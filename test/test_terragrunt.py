import unittest

from mock import Mock
from re import match

from hypothesis import given
from hypothesis.strategies import text
from botocore.exceptions import ClientError


from cdflow_commands import terragrunt


NEW_BUCKET_PATTERN = r'^cdflow-tfstate-[a-z0-9]+$'


class TestTerragrunt(unittest.TestCase):

    @given(text())
    def test_get_existing_bucket(self, bucket_name):

        # Given
        session = Mock()
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

        # When
        retrieved_bucket_name = terragrunt.get_bucket_name(
            session, 'dummy-region', 'dummy-account-id'
        )

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

        # Then
        with self.assertRaises(AssertionError):
            # When
            terragrunt.get_bucket_name(
                session, 'dummy-region', 'dummy-account-id'
            )

    def test_handle_untagged_buckets(self):

        # Given
        session = Mock()
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

        # When
        bucket = terragrunt.get_bucket_name(
            session, 'dummy-region', 'dummy-account-id'
        )

        # Then
        assert bucket == 'terragrunt-bucket'

    def test_bucket_created_and_tagged(self):

        # Given
        session = Mock()
        s3_client = Mock()
        session.client.return_value = s3_client

        s3_client.list_buckets.return_value = {
            'Buckets': []
        }

        # When
        bucket_name = terragrunt.get_bucket_name(
            session, 'dummy-region', 'dummy-account-id'
        )

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
        bucket = terragrunt.get_bucket_name(
            session, 'region-1', 'account-id-1'
        )
        duplicate_bucket = terragrunt.get_bucket_name(
            session, 'region-1', 'account-id-1'
        )
        bucket_different_region = terragrunt.get_bucket_name(
            session, 'region-2', 'account-id-1'
        )
        bucket_different_account = terragrunt.get_bucket_name(
            session, 'region-1', 'account-id-2'
        )

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

        # When
        bucket_name = terragrunt.get_bucket_name(
            session, 'dummy-region', 'dummy-account-id'
        )

        # Then
        first_call, second_call = s3_client.create_bucket.mock_calls
        first_bucket_param = first_call[2]['Bucket']
        second_bucket_param = second_call[2]['Bucket']
        assert match(NEW_BUCKET_PATTERN, first_bucket_param)
        assert match(NEW_BUCKET_PATTERN, second_bucket_param)
        assert first_bucket_param != bucket_name
        assert second_bucket_param == bucket_name
