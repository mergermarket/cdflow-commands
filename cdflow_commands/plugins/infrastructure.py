import json
import os
from collections import namedtuple
from itertools import chain
from subprocess import check_call
from tempfile import NamedTemporaryFile

from cdflow_commands.config import (
    assume_role, get_platform_config_path, get_role_session_name
)
from cdflow_commands.logger import logger
from cdflow_commands.plugins import Plugin
from cdflow_commands.plugins.base import Destroy
from cdflow_commands.secrets import get_secrets
from cdflow_commands.state import (
    LockTableFactory, S3BucketFactory, initialise_terraform_backend
)

DeployConfig = namedtuple('DeployConfig', [
    'team',
    'platform_config_file',
])


def build_infrastructure_plugin(
    environment_name, component_name, additional_variables,
    metadata, global_config, root_session
):

    release_factory = None

    deploy_factory = build_deploy_factory(
        environment_name, component_name, additional_variables,
        metadata, global_config, root_session
    )

    destroy_factory = build_destroy_factory(
        environment_name, component_name, metadata, global_config, root_session
    )

    return InfrastructurePlugin(
        release_factory, deploy_factory, destroy_factory
    )


def build_deploy_factory(
    environment_name, component_name, additional_variables,
    metadata, global_config, root_session,
):
    def _deploy_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

        platform_config_file = get_platform_config_path(
            metadata.account_prefix, metadata.aws_region, is_prod
        )
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
            platform_config_file=platform_config_file,
        )
        return Deploy(
            boto_session, component_name, environment_name,
            additional_variables, deploy_config
        )
    return _deploy_factory


def build_destroy_factory(
    environment_name, component_name, metadata, global_config, root_session
):
    def _destroy_factory():
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
            '/cdflow/tf-destroy', metadata.aws_region, s3_bucket, lock_table_name,
            environment_name, component_name
        )

        return Destroy(
            boto_session, component_name, environment_name, s3_bucket
        )
    return _destroy_factory


class Deploy:

    def __init__(
        self, boto_session, component_name, environment_name,
        additional_variables, config
    ):
        self._boto_session = boto_session
        self._component_name = component_name
        self._environment_name = environment_name
        self._additional_variables = additional_variables
        self._config = config

    def _terraform_parameters(self, secrets_file):
        parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._boto_session.region_name),
            '-var', 'team={}'.format(self._config.team),
            '-var-file', self._config.platform_config_file,
            '-var-file', secrets_file
        ]

        additional_variables = chain.from_iterable(
            ('-var', variable) for variable in self._additional_variables
        )

        return parameters + list(additional_variables)

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
                self._config.team,
                self._component_name,
                self._boto_session
            )
            f.write(json.dumps({'secrets': secrets}).encode('utf-8'))
            f.flush()
            parameters = self._terraform_parameters(f.name)
            check_call(
                ['terraform', 'plan'] + parameters + ['infra'], env=env
            )
            check_call(
                ['terraform', 'apply'] + parameters + ['infra'], env=env
            )


class InfrastructurePlugin(Plugin):
    def __init__(
        self, release_factory, deploy_factory,
        destroy_factory
    ):
        self.release_factory = release_factory
        self.deploy_factory = deploy_factory
        self.destroy_factory = destroy_factory

    def release(self):
        logger.info('Release takes no action on infrastructure type project')

    def deploy(self):
        deploy = self.deploy_factory()
        deploy.run()

    def destroy(self):
        destroy = self.destroy_factory()
        destroy.run()
