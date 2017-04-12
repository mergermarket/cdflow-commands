from hashlib import sha1
from os.path import abspath
from shutil import move
from subprocess import check_call
from tempfile import NamedTemporaryFile
from textwrap import dedent

from botocore.exceptions import ClientError
from cdflow_commands.exceptions import CDFlowError
from cdflow_commands.logger import logger

TAG_NAME = 'is-cdflow-tfstate-bucket'
TAG_VALUE = 'true'
NAME_PREFIX = 'cdflow-tfstate'
MAX_CREATION_ATTEMPTS = 10


class MissingTagError(CDFlowError):
    pass


class IncorrectSchemaError(CDFlowError):
    pass


def initialise_terraform_backend(
    directory, aws_region, bucket_name, lock_table_name,
    environment_name, component_name
):
    with NamedTemporaryFile(
        prefix='cdflow_backend_', suffix='.tf',
        dir=directory, delete=False, mode='w+'
    ) as backend_file:
        logger.debug(f'Writing backend config to {backend_file.name}')
        backend_file.write(dedent('''
            terraform {
                backend "s3" {
                }
            }
        ''').strip())

    state_file_key = f'{environment_name}/{component_name}/terraform.tfstate'
    logger.debug(
        f'Initialising backend in {directory} with {bucket_name}, '
        '{aws_region}, {state_file_key}, {lock_table_name}'
    )
    check_call(
        [
            'terraform', 'init',
            f'-backend-config=bucket={bucket_name}',
            f'-backend-config=region={aws_region}',
            f'-backend-config=key={state_file_key}',
            f'-backend-config=lock_table={lock_table_name}',
        ],
        cwd=directory
    )

    from_path = abspath(f'{directory}/.terraform')
    to_path = abspath('./.terraform')

    logger.debug(f'Moving {from_path} to {to_path}')
    move(from_path, to_path)


class LockTableFactory:

    TABLE_NAME = 'terraform_locks'
    TAG_NAME = 'cdflow_terraform_locks'
    TAG_VALUE = 'true'
    ID_COLUMN = 'LockID'

    def __init__(self, boto_session):
        self._boto_session = boto_session

    @property
    def _client(self):
        client = getattr(self, '_dbclient', None)
        if not client:
            client = self._dbclient = self._boto_session.client('dynamodb')
        return client

    def _try_to_get_table(self):
        response = self._client.describe_table(
            TableName=self.TABLE_NAME
        )
        self._check_tag(response['Table']['TableArn'])
        self._check_schema(response['Table'])
        return response['Table']['TableName']

    def _check_schema(self, table_definition):
        for attribute in table_definition['AttributeDefinitions']:
            if attribute['AttributeName'] == self.ID_COLUMN:
                return True
        raise IncorrectSchemaError(f'No attribute {self.ID_COLUMN} in table')

    def _check_tag(self, table_arn):
        tags_response = self._client.list_tags_of_resource(
            ResourceArn=table_arn
        )
        for tag in tags_response['Tags']:
            if tag['Key'] == self.TAG_NAME and tag['Value'] == self.TAG_VALUE:
                return True
        raise MissingTagError(f'No tag {self.TAG_NAME} found for {table_arn}')

    def _get_fallback_table(self):
        tables = self._client.list_tables()
        for table_name in tables['TableNames']:
            try:
                return self._try_to_get_table(table_name)
            except MissingTagError as e:
                logger.debug(e)

    def _create_table(self):
        response = self._client.create_table(
            TableName=self.TABLE_NAME,
            AttributeDefinitions=[
                {'AttributeName': self.ID_COLUMN, 'AttributeType': 'S'}
            ],
            KeySchema=[{'AttributeName': self.ID_COLUMN, 'KeyType': 'HASH'}],
            ProvisionedThroughput={
                'ReadCapacityUnits': 1,
                'WriteCapacityUnits': 1
            }
        )
        self._client.tag_resource(
            ResourceArn=response['TableDescription']['TableArn'],
            Tags=[
                {'Key': self.TAG_NAME, 'Value': self.TAG_VALUE}
            ]
        )
        self._client.get_waiter('table_exists').wait(TableName=self.TABLE_NAME)
        return self.TABLE_NAME

    @staticmethod
    def _resource_not_found(exception):
        return (
            exception.response.get('Error', {}).get('Code')
            ==
            'ResourceNotFoundException'
        )

    def get_table_name(self):
        try:
            return self._try_to_get_table()
        except ClientError as e:
            if self._resource_not_found(e):
                return self._create_table()
            else:
                raise e


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
