import json
import os
from os import path
from tempfile import NamedTemporaryFile
from time import time

from cdflow_commands.config import env_with_aws_credetials
from cdflow_commands.constants import (
    CONFIG_BASE_PATH, GLOBAL_CONFIG_FILE, INFRASTRUCTURE_DEFINITIONS_PATH,
    PLATFORM_CONFIG_BASE_PATH, RELEASE_METADATA_FILE, TERRAFORM_BINARY
)
from cdflow_commands.logger import logger
from cdflow_commands.process import check_call


class Deploy:

    def __init__(
        self, environment, release_path, secrets, account_scheme, boto_session,
    ):
        self._environment = environment
        self._release_path = release_path
        self._secrets = secrets
        self._account_scheme = account_scheme
        self._boto_session = boto_session

    def run(self, plan_only=False):
        self._plan()
        if not plan_only:
            self._apply()

    def _plan(self):
        with NamedTemporaryFile(mode='w+', encoding='utf-8') \
                as secrets_file:
            logger.debug(f'Writing secrets to file {secrets_file.name}')
            json.dump(self._secrets, secrets_file)
            secrets_file.flush()
            command = self._build_parameters('plan', secrets_file.name)
            logger.debug(f'Running {command}')
            check_call(
                command, cwd=self._release_path,
                env=env_with_aws_credetials(
                    os.environ, self._boto_session
                ),
            )

    def _apply(self):
        check_call(
            self._build_parameters('apply'),
            cwd=self._release_path,
            env=env_with_aws_credetials(
                os.environ, self._boto_session
            )
        )

    @property
    def plan_path(self):
        if not hasattr(self, '_plan_path'):
            self._plan_path = 'plan-{}'.format(time())
        return self._plan_path

    @property
    def _platform_config_file_path(self):
        account = self._account_scheme.account_for_environment(
            self._environment
        )
        return '{}/{}/{}.json'.format(
            PLATFORM_CONFIG_BASE_PATH, account.alias,
            self._boto_session.region_name
        )

    def _build_parameters(self, command, secrets_file_path=None):
        parameters = [TERRAFORM_BINARY, command, '-input=false']
        if command == 'plan':
            parameters = self._add_plan_parameters(
                parameters, secrets_file_path
            )
        else:
            parameters.append(self.plan_path)
        return parameters

    def _add_plan_parameters(self, parameters, secrets_file_path):
        parameters += [
            '-var', 'env={}'.format(self._environment),
            '-var-file', RELEASE_METADATA_FILE,
            '-var-file', self._platform_config_file_path,
            '-var-file', secrets_file_path,
            '-out', self.plan_path,
        ]
        parameters = self._add_environment_config_parameters(parameters)
        parameters += [INFRASTRUCTURE_DEFINITIONS_PATH]
        return parameters

    def _add_environment_config_parameters(self, parameters):
        environment_config_path = path.join(
            CONFIG_BASE_PATH, '{}.json'.format(self._environment)
        )

        if path.exists(environment_config_path):
            parameters += ['-var-file', environment_config_path]

        if path.exists(GLOBAL_CONFIG_FILE):
            parameters += ['-var-file', GLOBAL_CONFIG_FILE]

        return parameters
