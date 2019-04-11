import json
import os
import sys
from os import path
from tempfile import NamedTemporaryFile
from time import time

from cdflow_commands.config import env_with_aws_credetials
from cdflow_commands.constants import (
    CONFIG_BASE_PATH, GLOBAL_CONFIG_FILE_NAME, INFRASTRUCTURE_DEFINITIONS_PATH,
    PLATFORM_CONFIG_BASE_PATH, RELEASE_METADATA_FILE, TERRAFORM_BINARY
)
from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.process import check_call
from subprocess import Popen, PIPE
import re


class TerraformApplyError(UserFacingError):
    pass


class Deploy:

    def __init__(
        self, environment, release_path, secrets, account_scheme, boto_session,
        infra_path=INFRASTRUCTURE_DEFINITIONS_PATH,
        config_base_path=CONFIG_BASE_PATH,
        interactive=False,
    ):
        self._environment = environment
        self._release_path = release_path
        self._secrets = secrets
        self._account_scheme = account_scheme
        self._boto_session = boto_session
        self._infra_path = infra_path
        self._config_base_path = config_base_path
        self._interactive = interactive

    def run(self, plan_only=False):
        plan_exit_code = self._plan()
        if plan_exit_code != 0:
            raise TerraformApplyError(
                f'terraform plan exited with {plan_exit_code}'
            )
        if not plan_only:
            self._apply()

    def _print_obfuscated_output(self, out):
        secrets_values = self._secrets.get('secrets', {}).values()
        if out:
            if secrets_values:
                pattern = '|'.join(
                    re.escape(secret)
                    for secret in secrets_values
                )
                out = re.sub(
                    pattern,
                    '*******',
                    out.decode('utf-8')
                )
                out = out.encode('utf-8')

            sys.stdout.write(out.decode('utf-8'))
            sys.stdout.flush()

    def _print_err(self, err):
        if err:
            sys.stderr.write(err.decode('utf-8'))
            sys.stderr.flush()

    def _plan(self):
        with NamedTemporaryFile(mode='w+', encoding='utf-8') \
                as secrets_file:
            logger.debug(f'Writing secrets to file {secrets_file.name}')
            json.dump(self._secrets, secrets_file)
            secrets_file.flush()
            command = self._build_parameters('plan', secrets_file.name)
            logger.debug(f'Running {command}')

            process = Popen(
                command, cwd=self._release_path,
                env=env_with_aws_credetials(
                    os.environ, self._boto_session
                ),
                stdout=PIPE, stderr=PIPE
            )

            while True:
                (out, err) = process.communicate()
                self._print_obfuscated_output(out)
                self._print_err(err)

                exit_code = process.poll()
                if exit_code is not None:
                    return exit_code

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
        if self._interactive:
            return 'plan-$(date +%s)'
        if not hasattr(self, '_plan_path'):
            self._plan_path = 'plan-{}'.format(time())
        return self._plan_path

    def _platform_config_file_paths(self):
        accounts = [self._account_scheme.account_for_environment(
            self._environment
        )]

        return [
            '{}/{}/{}.json'.format(
                PLATFORM_CONFIG_BASE_PATH, account.alias,
                self._boto_session.region_name
            )
            for account in accounts
        ]

    def _build_parameters(self, command, secrets_file_path=None):
        parameters = [TERRAFORM_BINARY, command]
        if not self._interactive:
            parameters += ['-input=false']
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
        ]

        for platform_config_path in self._platform_config_file_paths():
            parameters += ['-var-file', platform_config_path]

        if secrets_file_path:
            parameters += ['-var-file', secrets_file_path]

        parameters += ['-out', self.plan_path]

        parameters = self._add_environment_config_parameters(parameters)
        parameters += [self._infra_path]
        return parameters

    def _add_environment_config_parameters(self, parameters):
        environment_config_path = path.join(
            self._config_base_path, f'{self._environment}.json',
        )
        global_config_file_path = path.join(
            self._config_base_path, GLOBAL_CONFIG_FILE_NAME,
        )

        if path.exists(environment_config_path):
            parameters += ['-var-file', environment_config_path]

        if path.exists(global_config_file_path):
            parameters += ['-var-file', global_config_file_path]

        return parameters
