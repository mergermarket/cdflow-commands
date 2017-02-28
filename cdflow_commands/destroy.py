import os
from subprocess import check_call
from collections import namedtuple

from cdflow_commands.terragrunt import build_command_parameters


DestroyConfig = namedtuple('DestroyConfig', [
    'team', 'platform_config_file'
])


class Destroy(object):

    def __init__(self, boto_session, component_name, environment_name, config):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._team = config.team
        self._platform_config_file = config.platform_config_file

    @property
    def _terragrunt_parameters(self):
        return build_command_parameters(
            self._component_name,
            self._environment_name,
            self._aws_region,
            self._team,
            'any',
            'all',
            self._platform_config_file,
            ''
        )

    def run(self):
        check_call(['terragrunt', 'get', 'infra'])
        credentials = self._boto_session.get_credentials()
        aws_credentials = {
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token
        }
        env = os.environ.copy()
        env.update(aws_credentials)
        check_call(
            ['terragrunt', 'plan'] + self._terragrunt_parameters,
            env=env
        )
        check_call(
            ['terragrunt', 'destroy', '-force'] + self._terragrunt_parameters,
            env=env
        )
