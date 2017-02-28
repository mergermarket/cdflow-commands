from hashlib import sha1
from textwrap import dedent

from botocore.exceptions import ClientError


TAG_NAME = 'is-cdflow-tfstate-bucket'
TAG_VALUE = 'true'
NAME_PREFIX = 'cdflow-tfstate'
MAX_CREATION_ATTEMPTS = 10


class S3BucketFactory(object):

    def __init__(self, boto_session, account_id):
        self._boto_s3_client = boto_session.client('s3')
        self._aws_region = boto_session.region_name
        self._account_id = account_id

    def get_bucket_name(self):

        buckets = {
            bucket['Name']
            for bucket
            in self._boto_s3_client.list_buckets()['Buckets']
        }

        tagged_buckets = {
            bucket_name for bucket_name in buckets
            if self._bucket_has_tag(bucket_name)
            and self._bucket_in_current_region(bucket_name)
        }

        assert len(tagged_buckets) <= 1, '''
            multiple buckets with {}={} tag found
        '''.format(TAG_NAME, TAG_VALUE).strip()

        if len(tagged_buckets) == 1:
            return list(tagged_buckets)[0]
        else:
            bucket_name = self._create_bucket()
            self._tag_bucket(bucket_name)
            return bucket_name

    def _bucket_has_tag(self, bucket_name):
        tags = self._get_bucket_tags(bucket_name)
        return tags.get(TAG_NAME) == TAG_VALUE

    def _bucket_in_current_region(self, bucket_name):
        region_response = self._boto_s3_client.get_bucket_location(
            Bucket=bucket_name
        )
        region = region_response['LocationConstraint']
        return region == self._aws_region

    def _get_bucket_tags(self, bucket_name):
        try:
            tags = self._boto_s3_client.get_bucket_tagging(
                Bucket=bucket_name
            )['TagSet']
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == 'NoSuchTagSet':
                return {}
            raise
        return {tag['Key']: tag['Value'] for tag in tags}

    def _create_bucket(self):
        for attempt in range(MAX_CREATION_ATTEMPTS):
            bucket_name = self._generate_bucket_name(attempt)
            if self._attempt_to_create_bucket(bucket_name):
                return bucket_name
        raise Exception('could not create bucket after {} attempts'.format(
            MAX_CREATION_ATTEMPTS
        ))

    def _attempt_to_create_bucket(self, bucket_name):
        try:
            self._boto_s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={
                    'LocationConstraint': self._aws_region
                }
            )
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') not in (
                'BucketAlreadyExists', 'BucketAlreadyOwnedByYou'
            ):
                raise
            return False
        return True

    def _tag_bucket(self, bucket_name):
        self._boto_s3_client.put_bucket_tagging(
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

    def _generate_bucket_name(self, attempt):
        parts = map(str, [self._aws_region, self._account_id, attempt])
        concatenated = ''.join(parts)
        return '{}-{}'.format(
            NAME_PREFIX,
            sha1(
                concatenated.encode('utf-8')
            ).hexdigest()[:12]
        )


def write_terragrunt_config(
    aws_region, bucket_name, environment_name, component_name
):
    config_template = dedent('''
        lock = {{
            backend = "dynamodb"
            config {{
                state_file_id = "{state_file_id}"
                aws_region = "{aws_region}"
                table_name = "terragrunt_locks"
                max_lock_retries = 360
            }}
        }}
        remote_state = {{
            backend = "s3"
            config {{
                encrypt = "true"
                bucket = "{bucket}"
                key = "{key_prefix}/terraform.tfstate"
                region = "{aws_region}"
            }}
        }}
    ''').strip() + '\n'
    config = config_template.format(
        state_file_id='-'.join((environment_name, component_name)),
        key_prefix='/'.join((environment_name, component_name)),
        aws_region=aws_region,
        bucket=bucket_name,
    )
    with open('.terragrunt', 'w') as f:
        f.write(config)
