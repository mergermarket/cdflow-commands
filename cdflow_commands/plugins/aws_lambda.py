import json
import os
from os import path
from subprocess import check_call
from tempfile import NamedTemporaryFile
from collections import namedtuple
from zipfile import ZipFile
from cdflow_commands.config import (
    assume_role, get_role_session_name, get_platform_config_path
)
from cdflow_commands.plugins import Plugin
from cdflow_commands.secrets import get_secrets


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
        boto_s3_client = assume_role(
            root_session,
            global_config.dev_account_id,
            get_role_session_name(os.environ)
        ).client('s3')
        return Release(
            global_config,
            boto_s3_client,
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
        deploy_config = DeployConfig(
            team=metadata.team,
            dev_account_id=global_config.dev_account_id,
            platform_config_file=get_platform_config_path(
                metadata.account_prefix,
                metadata.aws_region,
                is_prod
            )
        )
        return Deploy(
            boto_session,
            component_name,
            environment_name,
            version,
            deploy_config
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
        boto_s3_client,
        component_name,
        metadata,
        version
    ):
        self._global_config = global_config
        self._boto_s3_client = boto_s3_client
        self._component_name = component_name
        self._metadata = metadata
        self._version = version

    @property
    def _bucket_name(self):
        return 'mmg-lambdas-{}'.format(self._metadata.team)

    @property
    def _lambda_s3_key(self):
        return '{}/{}.zip'.format(self._component_name, self._version)

    def create(self):
        zipped_folder = self._zip_up_component()
        if not self._bucket_exists():
            self._create_bucket()
        self._upload_zip_to_bucket(zipped_folder.filename)
        self._remove_zipped_folder(zipped_folder.filename)

    def _zip_up_component(self):
        with ZipFile(self._component_name + '.zip', 'w') as zipped_folder:
            for dirname, subdirs, files in os.walk(self._component_name):
                zipped_folder.write(dirname)
                for filename in files:
                    zipped_folder.write(os.path.join(dirname, filename))
        return zipped_folder

    def _bucket_exists(self):
        bucket_list = self._boto_s3_client.list_buckets()
        bucket_names = [
            bucket['Name']
            for bucket in bucket_list['Buckets']
            if bucket['Name'] == self._bucket_name
        ]
        return bucket_names

    def _create_bucket(self):
        self._boto_s3_client.create_bucket(
            ACL='private',
            Bucket=self._bucket_name,
            CreateBucketConfiguration={
                'LocationConstraint': self._metadata.aws_region
            }
        )

    def _upload_zip_to_bucket(self, filename):
        self._boto_s3_client.upload_file(
            filename,
            self._bucket_name,
            self._lambda_s3_key
        )

    def _remove_zipped_folder(self, filename):
        os.remove(filename)


DeployConfig = namedtuple('DeployConfig', [
    'team',
    'dev_account_id',
    'platform_config_file',
])


class Deploy(object):

    def __init__(
        self, boto_session, component_name, environment_name,
        version, deploy_config
    ):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._version = version
        self._team = deploy_config.team
        self._dev_account_id = deploy_config.dev_account_id
        self._platform_config_file = deploy_config.platform_config_file

    def _terraform_parameters(self, secrets_file):
        parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._aws_region),
            '-var', 'team={}'.format(self._team),
            '-var', 'version={}'.format(self._version),
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
