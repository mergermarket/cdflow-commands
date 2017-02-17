from subprocess import check_call
from collections import namedtuple
import os

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

    @property
    def _terragrunt_parameters(self):
        return build_command_parameters(
            self._component_name,
            self._environment_name,
            self._aws_region,
            self._team,
            self._image_name,
            self._version,
            self._platform_config_file,
        )

    def run(self):
        check_call(['terraform', 'get', 'infra'])

        credentials = self._boto_session.get_credentials()
        env = os.environ.copy()
        env.update({
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token
        })

        check_call(
            ['terragrunt', 'plan'] + self._terragrunt_parameters,
            env=env
        )
        check_call(
            ['terragrunt', 'apply'] + self._terragrunt_parameters,
            env=env
        )
