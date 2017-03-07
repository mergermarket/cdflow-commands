import os
from os import path
import json
from subprocess import check_call
from collections import namedtuple
from tempfile import NamedTemporaryFile
from cdflow_commands.secrets import get_secrets


DeployConfig = namedtuple('DeployConfig', [
    'team',
    'dev_account_id',
    'platform_config_file',
])


class Deploy(object):

    def __init__(
        self, boto_session, component_name, environment_name,
        version, ecs_cluster, config
    ):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._version = version
        self._ecs_cluster = ecs_cluster
        self._team = config.team
        self._dev_account_id = config.dev_account_id
        self._platform_config_file = config.platform_config_file

    @property
    def _image_name(self):
        return '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._dev_account_id,
            self._aws_region,
            self._component_name,
            self._version
        )

    def _terragrunt_parameters(self, secrets_file):
        parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._aws_region),
            '-var', 'team={}'.format(self._team),
            '-var', 'image={}'.format(self._image_name),
            '-var', 'version={}'.format(self._version),
            '-var', 'ecs_cluster={}'.format(self._ecs_cluster),
            '-var-file', self._platform_config_file,
            '-var-file', secrets_file
        ]
        config_file = 'config/{}.json'.format(self._environment_name)
        if path.exists(config_file):
            parameters += ['-var-file', config_file]
        return parameters + ['infra']

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
                self._team,
                self._component_name,
                self._boto_session
            )
            f.write(json.dumps({'secrets': secrets}).encode('utf-8'))
            f.flush()
            parameters = self._terragrunt_parameters(f.name)
            check_call(
                ['terragrunt', 'plan'] + parameters,
                env=env
            )
            check_call(
                ['terragrunt', 'apply'] + parameters,
                env=env
            )
