import atexit
from hashlib import sha1
from os import unlink
from os.path import join
from tempfile import NamedTemporaryFile
from textwrap import dedent

from botocore.exceptions import ClientError

from cdflow_commands.constants import TERRAFORM_BINARY
from cdflow_commands.exceptions import CDFlowError
from cdflow_commands.logger import logger
from cdflow_commands.process import check_call, check_output

TFSTATE_NAME_PREFIX = 'cdflow-tfstate'
TFSTATE_TAG_NAME = 'is-cdflow-tfstate-bucket'
TAG_VALUE = 'true'
MAX_CREATION_ATTEMPTS = 10


class IncorrectSchemaError(CDFlowError):
    pass


def remove_file(filepath):
    try:
        logger.debug(f'Removing {filepath}')
        unlink(filepath)
    except OSError as e:
        logger.debug(f'Error removing {filepath}: {e}')


class TerraformStateClassic:

    def __init__(
        self,
        boto_session,
        base_directory,
        sub_directory,
        tfstate_filename,
        environment_name,
        component_name,
    ):
        self.boto_session = boto_session
        self.base_directory = base_directory
        self.sub_directory = sub_directory
        self.tfstate_filename = tfstate_filename
        self.environment_name = environment_name
        self.component_name = component_name

    @property
    def bucket(self):
        if not hasattr(self, '_bucket'):
            s3_bucket_factory = S3BucketFactory(self.boto_session)
            self._bucket = s3_bucket_factory.get_bucket_name()
        return self._bucket

    @property
    def dynamodb_table(self):
        if not hasattr(self, '_dynamodb_table'):
            lock_table_factory = LockTableFactory(self.boto_session)
            self._dynamodb_table = lock_table_factory.get_table_name()
        return self._dynamodb_table

    @property
    def working_directory(self):
        return join(self.base_directory, self.sub_directory)

    @property
    def state_file_key(self):
        return join(
            self.environment_name, self.component_name, self.tfstate_filename,
        )

    def init(self):
        with NamedTemporaryFile(
            prefix='cdflow_backend_', suffix='.tf',
            dir=self.working_directory, delete=False, mode='w+'
        ) as backend_file:
            logger.debug(f'Writing backend config to {backend_file.name}')
            backend_file.write(dedent('''
                terraform {
                    backend "s3" {
                    }
                }
            ''').strip())
            logger.debug(
                f'Registering {backend_file.name} to be removed at exit'
            )
            atexit.register(remove_file, backend_file.name)

        logger.debug(
            f'Initialising backend in {self.working_directory} '
            f'with {self.bucket}, {self.boto_session.region_name}, '
            f'{self.state_file_key}, {self.dynamodb_table}'
        )

        credentials = self.boto_session.get_credentials()
        check_call(
            [
                TERRAFORM_BINARY, 'init',
                '-get=false',
                '-get-plugins=false',
                f'-backend-config=bucket={self.bucket}',
                f'-backend-config=region={self.boto_session.region_name}',
                f'-backend-config=key={self.state_file_key}',
                f'-backend-config=dynamodb_table={self.dynamodb_table}',
                f'-backend-config=access_key={credentials.access_key}',
                f'-backend-config=secret_key={credentials.secret_key}',
                f'-backend-config=token={credentials.token}',
                self.working_directory,
            ],
            cwd=self.base_directory,
        )


class TerraformState:

    def __init__(
        self,
        boto_session,
        base_directory,
        sub_directory,
        tfstate_filename,
        environment_name,
        component_name,
        account_scheme,
        team_name,
    ):
        self.boto_session = boto_session
        self.base_directory = base_directory
        self.sub_directory = sub_directory
        self.tfstate_filename = tfstate_filename
        self.environment_name = environment_name
        self.component_name = component_name
        self.account_scheme = account_scheme
        self.team_name = team_name

    @property
    def bucket(self):
        return self.account_scheme.backend_s3_bucket

    @property
    def dynamodb_table(self):
        return self.account_scheme.backend_s3_dynamodb_table

    @property
    def working_directory(self):
        return join(self.base_directory, self.sub_directory)

    @property
    def state_file_key(self):
        return join(
            self.component_name, self.environment_name, self.tfstate_filename,
        )

    @property
    def workspace_key_prefix(self):
        return join(self.team_name, self.component_name)

    def write_backend_config(self, backend_file):
        logger.debug(f'Writing backend config to {backend_file.name}')
        backend_file.write(dedent('''
            terraform {
                backend "s3" {
                }
            }
        ''').strip())
        logger.debug(
            f'Registering {backend_file.name} to be removed at exit'
        )
        atexit.register(remove_file, backend_file.name)

    def terraform_init(self):
        credentials = self.boto_session.get_credentials()
        logger.debug(
            f'Initialising in {self.boto_session.region_name} '
            f'with bucket: {self.bucket}, '
            f'key prefix: {self.workspace_key_prefix}, '
            f'tfstate file: {self.tfstate_filename}, '
            f'dynamodb table: {self.dynamodb_table}'
        )
        check_call(
            [
                TERRAFORM_BINARY, 'init',
                '-get=false',
                '-get-plugins=false',
                f'-backend-config=bucket={self.bucket}',
                f'-backend-config=region={self.boto_session.region_name}',
                f'-backend-config=key={self.tfstate_filename}',
                (
                    '-backend-config=workspace_key_prefix='
                    f'{self.workspace_key_prefix}'
                ),
                f'-backend-config=dynamodb_table={self.dynamodb_table}',
                f'-backend-config=access_key={credentials.access_key}',
                f'-backend-config=secret_key={credentials.secret_key}',
                f'-backend-config=token={credentials.token}',
                self.working_directory,
            ],
            cwd=self.base_directory,
        )

    def workspace_exists(self):
        workspace_data = check_output(
            [
                TERRAFORM_BINARY, 'workspace', 'list', self.working_directory,
            ],
            cwd=self.base_directory,
        )
        existing_workspaces = {
            w.strip() for w in workspace_data.decode('utf-8').split('\n')
        }

        return self.environment_name in existing_workspaces

    def terraform_new_workspace(self):
        check_call(
            [
                TERRAFORM_BINARY, 'workspace',
                'new', self.environment_name,
                self.working_directory,
            ],
            cwd=self.base_directory,
        )

    def terraform_select_workspace(self):
        check_call(
            [
                TERRAFORM_BINARY, 'workspace',
                'select', self.environment_name,
                self.working_directory,
            ],
            cwd=self.base_directory,
        )

    def init(self):
        with NamedTemporaryFile(
            prefix='cdflow_backend_', suffix='.tf',
            dir=self.working_directory, delete=False, mode='w+'
        ) as backend_file:
            self.write_backend_config(backend_file)

        self.terraform_init()

        if self.workspace_exists():
            logger.debug(
                f'Workspace exists, selecting {self.environment_name}'
            )
            self.terraform_select_workspace()
        else:
            logger.debug(
                f'Creating new workspace {self.environment_name}'
            )
            self.terraform_new_workspace()


def terraform_state(
    base_directory, sub_directory, boto_session, environment_name,
    component_name, tfstate_filename, account_scheme, team_name,
):
    if account_scheme.classic_metadata_handling:
        terraform_state = TerraformStateClassic(
            boto_session, base_directory, sub_directory, tfstate_filename,
            environment_name, component_name,
        )
    else:
        terraform_state = TerraformState(
            boto_session, base_directory, sub_directory, tfstate_filename,
            environment_name, component_name, account_scheme, team_name,
        )
    return terraform_state


class LockTableFactory:

    TABLE_NAME = 'terraform_locks'
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
        self._check_schema(response['Table'])
        return response['Table']['TableName']

    def _check_schema(self, table_definition):
        for attribute in table_definition['AttributeDefinitions']:
            if attribute['AttributeName'] == self.ID_COLUMN:
                return True
        raise IncorrectSchemaError(f'No attribute {self.ID_COLUMN} in table')

    def _create_table(self):
        self._client.create_table(
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


class S3BucketFactory:

    def __init__(self, boto_session):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name

    @property
    def _boto_s3_client(self):
        client = getattr(self, '_s3client', None)
        if not client:
            client = self._s3client = self._boto_session.client('s3')
        return client

    def get_bucket_name(self, bucket_name_prefix=TFSTATE_NAME_PREFIX):

        bucket_tag = TFSTATE_TAG_NAME

        buckets = {
            bucket['Name']
            for bucket
            in self._boto_s3_client.list_buckets()['Buckets']
        }

        tagged_buckets = {
            bucket_name for bucket_name in buckets
            if self._bucket_has_tag(bucket_name, bucket_tag)
            and self._bucket_in_current_region(bucket_name)
        }

        assert len(tagged_buckets) <= 1, '''
            multiple buckets with {}={} tag found
        '''.format(bucket_tag, TAG_VALUE).strip()

        if len(tagged_buckets) == 1:
            logger.debug(
                'Single bucket ({}) with tag: {}={} found'.format(
                    list(tagged_buckets)[0], bucket_tag, TAG_VALUE
                )
            )
            return list(tagged_buckets)[0]
        else:
            bucket_name = self._create_bucket(bucket_name_prefix)
            self._tag_bucket(bucket_name, bucket_tag)
            return bucket_name

    def _bucket_has_tag(self, bucket_name, bucket_tag):
        logger.debug(f'Checking for tag {bucket_tag} on bucket {bucket_name}')
        tags = self._get_bucket_tags(bucket_name)
        return tags.get(bucket_tag) == TAG_VALUE

    def _bucket_in_current_region(self, bucket_name):
        region_response = self._boto_s3_client.get_bucket_location(
            Bucket=bucket_name
        )
        region = region_response['LocationConstraint']

        logger.debug(f'Checking bucket {bucket_name} region {region}')

        if self._aws_region == 'us-east-1' and region is None:
            return True

        return region == self._aws_region

    def _get_bucket_tags(self, bucket_name):
        try:
            tags = self._boto_s3_client.get_bucket_tagging(
                Bucket=bucket_name
            )['TagSet']
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code')
            if code in ('NoSuchTagSet', 'NoSuchBucket'):
                return {}
            raise
        return {tag['Key']: tag['Value'] for tag in tags}

    def _create_bucket(self, bucket_name_prefix):
        logger.debug('Creating bucket with name {}'.format(bucket_name_prefix))
        for attempt in range(MAX_CREATION_ATTEMPTS):
            if bucket_name_prefix == TFSTATE_NAME_PREFIX:
                bucket_name = self._generate_bucket_name(
                    attempt, bucket_name_prefix
                )
            else:
                bucket_name = bucket_name_prefix
            if self._attempt_to_create_bucket(bucket_name):
                logger.debug(
                    's3 bucket with name: {} created'.format(bucket_name)
                )
                return bucket_name
        raise Exception('could not create bucket after {} attempts'.format(
            MAX_CREATION_ATTEMPTS
        ))

    def _generate_create_bucket_params(self, bucket_name):
        create_bucket_params = {
            'Bucket': bucket_name,
        }
        if self._aws_region != 'us-east-1':
            create_bucket_params['CreateBucketConfiguration'] = {
                'LocationConstraint': self._aws_region
            }

        return create_bucket_params

    def _attempt_to_create_bucket(self, bucket_name):
        try:
            self._boto_s3_client.create_bucket(
                **self._generate_create_bucket_params(bucket_name)
            )
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') not in (
                'BucketAlreadyExists', 'BucketAlreadyOwnedByYou'
            ):
                raise
            return False
        return True

    def _tag_bucket(self, bucket_name, bucket_tag):
        logger.debug('Tagging bucket: {} with tag: {}={}'.format(
            bucket_name, bucket_tag, TAG_VALUE
        ))
        self._boto_s3_client.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={
                'TagSet': [
                    {
                        'Key': bucket_tag,
                        'Value': TAG_VALUE,
                    }
                ]
            }
        )

    def _generate_bucket_name(self, attempt, bucket_name_prefix):
        parts = map(str, [self._aws_region, attempt])
        concatenated = ''.join(parts)
        return '{}-{}'.format(
            bucket_name_prefix,
            sha1(
                concatenated.encode('utf-8')
            ).hexdigest()[:12]
        )
