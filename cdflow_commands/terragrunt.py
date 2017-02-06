
from botocore.exceptions import ClientError
from hashlib import sha1

TAG_NAME = 'is-cdflow-tfstate-bucket'
TAG_VALUE = 'true'
NAME_PREFIX = 'cdflow-tfstate'
MAX_CREATION_ATTEMPTS = 10


def get_bucket_name(session, region, account_id):

    boto_s3_client = session.client('s3')

    buckets = {
        bucket['Name'] for bucket in boto_s3_client.list_buckets()['Buckets']
    }

    tagged_buckets = {
        bucket for bucket in buckets if _bucket_has_tag(boto_s3_client, bucket)
    }

    assert len(tagged_buckets) <= 1, '''
        multiple buckets with {}={} tag found
    '''.format(TAG_NAME, TAG_VALUE).strip()

    if len(tagged_buckets) == 1:
        return list(tagged_buckets)[0]
    else:
        bucket_name = _create_bucket(boto_s3_client, region, account_id)
        _tag_bucket(boto_s3_client, bucket_name)
        return bucket_name


def _bucket_has_tag(boto_s3_client, bucket_name):
    tags = _get_bucket_tags(boto_s3_client, bucket_name)
    return tags.get(TAG_NAME) == TAG_VALUE


def _get_bucket_tags(boto_s3_client, bucket_name):
    try:
        tags = boto_s3_client.get_bucket_tagging(Bucket=bucket_name)['TagSet']
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'NoSuchTagSet':
            return {}
        raise
    return {tag['Key']: tag['Value'] for tag in tags}


def _create_bucket(boto_s3_client, region, account_id):
    for attempt in range(MAX_CREATION_ATTEMPTS):
        bucket_name = _generate_bucket_name(region, account_id, attempt)
        if _attempt_to_create_bucket(boto_s3_client, bucket_name):
            return bucket_name
    raise Exception('could not create bucket after {} attempts'.format(
        MAX_CREATION_ATTEMPTS
    ))


def _attempt_to_create_bucket(boto_s3_client, bucket_name):
    try:
        boto_s3_client.create_bucket(Bucket=bucket_name)
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') != 'BucketAlreadyExists':
            raise
        return False
    return True


def _tag_bucket(boto_s3_client, bucket_name):
    boto_s3_client.put_bucket_tagging(
        Bucket=bucket_name,
        Tagging={
            'TagSet': [
                {
                    'Key': TAG_NAME,
                    'Value': TAG_VALUE,
                }
            ]
        }
    )


def _generate_bucket_name(region, account_id, attempt):
    return '{}-{}'.format(
        NAME_PREFIX, sha1(region + account_id + str(attempt)).hexdigest()[:12]
    )
