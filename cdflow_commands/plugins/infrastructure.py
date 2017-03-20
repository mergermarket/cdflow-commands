import json
import os
from collections import namedtuple
from itertools import chain
from subprocess import check_call
from tempfile import NamedTemporaryFile

from cdflow_commands.plugins import Plugin
from cdflow_commands.secrets import get_secrets


DeployConfig = namedtuple('DeployConfig', [
    'team',
    'platform_config_file',
])


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

    def _terragrunt_parameters(self, secrets_file):
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
        check_call(['terragrunt', 'get', 'infra'])

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
            parameters = self._terragrunt_parameters(f.name)
            check_call(
                ['terragrunt', 'plan'] + parameters + ['infra'], env=env
            )
            check_call(
                ['terragrunt', 'apply'] + parameters + ['infra'], env=env
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
        pass

    def deploy(self):
        deploy = self.deploy_factory()
        deploy.run()

    def destroy(self):
        destroy = self.destroy_factory()
        destroy.run()
