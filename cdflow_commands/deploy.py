import os
import json
from subprocess import check_call
from collections import namedtuple
from tempfile import NamedTemporaryFile

from cdflow_commands.secrets import get_secrets
from cdflow_commands.terragrunt import build_command_parameters


DeployConfig = namedtuple('DeployConfig', [
    'team',
    'dev_account_id',
    'platform_config_file',
])


class Deploy(object):

    def __init__(
        self, boto_session, component_name, environment_name,
        version, config
    ):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._version = version
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
        return build_command_parameters(
            self._component_name,
            self._environment_name,
            self._aws_region,
            self._team,
            self._image_name,
            self._version,
            self._platform_config_file,
            secrets_file
        )

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
            json.dump({'secrets': secrets}, f)
            parameters = self._terragrunt_parameters(f.name)
            check_call(
                ['terragrunt', 'plan'] + parameters,
                env=env
            )
            check_call(
                ['terragrunt', 'apply'] + parameters,
                env=env
            )
