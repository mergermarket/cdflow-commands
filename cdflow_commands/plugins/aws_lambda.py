import json
import os
from os import path
from subprocess import check_call
from tempfile import NamedTemporaryFile
from collections import namedtuple
from zipfile import ZipFile
from contextlib import contextmanager
from cdflow_commands.config import (
    assume_role, get_role_session_name, get_platform_config_path
)
from cdflow_commands.logger import logger
from cdflow_commands.plugins import Plugin
from cdflow_commands.secrets import get_secrets
from cdflow_commands.state import (
    LockTableFactory, S3BucketFactory, initialise_terraform_backend
)


def build_lambda_plugin(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    release_factory = build_release_factory(
        global_config,
        root_session,
        component_name,
        metadata,
        version
    )
    deploy_factory = build_deploy_factory(
        environment_name,
        component_name,
        version,
        metadata,
        global_config,
        root_session
    )
    return LambdaPlugin(
        release_factory,
        deploy_factory,
        None
    )


def build_release_factory(
    global_config, root_session, component_name, metadata, version
):
    def _release_factory():
        boto_session = assume_role(
            root_session,
            global_config.dev_account_id,
            get_role_session_name(os.environ)
        )
        return Release(
            global_config,
            boto_session,
            component_name,
            metadata,
            version
        )
    return _release_factory


def build_deploy_factory(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    def _deploy_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

        boto_session = assume_role(
            root_session,
            account_id,
            get_role_session_name(os.environ)
        )
        s3_bucket_factory = S3BucketFactory(boto_session, account_id)
        s3_bucket = s3_bucket_factory.get_bucket_name()

        lock_table_factory = LockTableFactory(boto_session)
        lock_table_name = lock_table_factory.get_table_name()

        initialise_terraform_backend(
            'infra', metadata.aws_region, s3_bucket, lock_table_name,
            environment_name, component_name
        )
        deploy_config = DeployConfig(
            team=metadata.team,
            dev_account_id=global_config.dev_account_id,
            platform_config_file=get_platform_config_path(
                metadata.account_prefix,
                metadata.aws_region,
                is_prod
            )
        )
        lambda_config = LambdaConfig(
            handler=metadata.handler,
            runtime=metadata.runtime
        )
        return Deploy(
            boto_session,
            component_name,
            environment_name,
            version,
            deploy_config,
            lambda_config
        )
    return _deploy_factory


class LambdaPlugin(Plugin):
    def __init__(
        self,
        release_factory,
        deploy_factory,
        destroy_factory
    ):
        self.release_factory = release_factory
        self.deploy_factory = deploy_factory

    def release(self):
        release = self.release_factory()
        release.create()

    def deploy(self):
        deploy = self.deploy_factory()
        deploy.run()

    def destroy(self):
        pass


class Release():
    def __init__(
        self,
        global_config,
        boto_session,
        component_name,
        metadata,
        version
    ):
        self._global_config = global_config
        self._boto_session = boto_session
        self._component_name = component_name
        self._metadata = metadata
        self._version = version

    @property
    def _bucket_name(self):
        return 'cdflow-lambda-releases'

    @property
    def _lambda_s3_key(self):
        return '{}/{}/{}.zip'.format(
            self._metadata.team, self._component_name, self._version
        )

    def create(self):
        zipped_folder = self._zip_up_component()
        s3_bucket_factory = S3BucketFactory(
            self._boto_session, self._global_config.dev_account_id
        )
        created_bucket_name = s3_bucket_factory.get_bucket_name(
            self._bucket_name
        )
        boto_s3_client = self._boto_session.client('s3')
        self._upload_zip_to_bucket(
            boto_s3_client, created_bucket_name, zipped_folder.filename
        )
        self._remove_zipped_folder(zipped_folder.filename)

    @contextmanager
    def _change_dir(self, path):
        top_level = os.getcwd()
        os.chdir(path)
        yield
        os.chdir(top_level)

    def _zip_up_component(self):
        logger.info('Zipping up ./{} folder'.format(self._component_name))
        with ZipFile(self._component_name + '.zip', 'w') as zipped_folder:
            with self._change_dir(self._component_name):
                for dirname, subdirs, files in os.walk('.'):
                    for filename in files:
                        zipped_folder.write(os.path.join(dirname, filename))
        return zipped_folder

    def _upload_zip_to_bucket(self, boto_s3_client, bucket_name, filename):
        logger.info('Uploading {} to s3 bucket ({}) with key: {}'.format(
            filename, bucket_name, self._lambda_s3_key
        ))
        boto_s3_client.upload_file(
            filename,
            bucket_name,
            self._lambda_s3_key
        )

    def _remove_zipped_folder(self, filename):
        logger.info('Removing local zipped package: {}'.format(filename))
        os.remove(filename)


DeployConfig = namedtuple('DeployConfig', [
    'team',
    'dev_account_id',
    'platform_config_file',
])

LambdaConfig = namedtuple('LambdaConfig', [
    'handler',
    'runtime'
])


class Deploy(object):

    def __init__(
        self, boto_session, component_name, environment_name,
        version, deploy_config, lambda_config
    ):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._version = version
        self._team = deploy_config.team
        self._dev_account_id = deploy_config.dev_account_id
        self._platform_config_file = deploy_config.platform_config_file
        self._lambda_config = lambda_config

    @property
    def _handler(self):
        return self._lambda_config.handler

    @property
    def _runtime(self):
        return self._lambda_config.runtime

    def _terraform_parameters(self, secrets_file):
        parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._aws_region),
            '-var', 'team={}'.format(self._team),
            '-var', 'version={}'.format(self._version),
            '-var', 'handler={}'.format(self._handler),
            '-var', 'runtime={}'.format(self._runtime),
            '-var-file', self._platform_config_file,
            '-var-file', secrets_file
        ]
        config_file = 'config/{}.json'.format(self._environment_name)
        if path.exists(config_file):
            parameters += ['-var-file', config_file]
        return parameters + ['infra']

    def run(self):
        check_call(['terraform', 'get', 'infra'])

        credentials = self._boto_session.get_credentials()
        env = os.environ.copy()
        env.update({
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token
        })
        with NamedTemporaryFile() as f:
            secrets = get_secrets(
                self._environment_name,
                self._team,
                self._component_name,
                self._boto_session
            )
            f.write(json.dumps({'secrets': secrets}).encode('utf-8'))
            f.flush()
            parameters = self._terraform_parameters(f.name)
            check_call(
                ['terraform', 'plan'] + parameters,
                env=env
            )
            check_call(
                ['terraform', 'apply'] + parameters,
                env=env
            )
