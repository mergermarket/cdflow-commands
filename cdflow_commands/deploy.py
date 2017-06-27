from datetime import datetime
import json
import os
from os import path
from subprocess import check_call
from tempfile import NamedTemporaryFile

from cdflow_commands.secrets import get_secrets


class Deploy:

    CONFIG_BASE_PATH = 'config'
    GLOBAL_CONFIG_FILE = 'all.json'

    def __init__(
        self, component, version, environment, team,
        release_path, account_scheme, boto_session,
    ):
        self._component = component
        self._version = version
        self._environment = environment
        self._team = team
        self._release_path = release_path
        self._account_scheme = account_scheme
        self._boto_session = boto_session

    def run(self, plugin, plan_only=False):
        self._plan(plugin)
        if not plan_only:
            self._apply()

    def _plan(self, plugin):
        with NamedTemporaryFile() as secrets_file_path:
            json.dump(get_secrets(), secrets_file_path)
            plugin_specific_parameters = plugin.parameters()
            check_call(
                self._build_parameters(
                    'plan', secrets_file_path, plugin_specific_parameters
                ),
                cwd=self._release_path,
                env=self._env()
            )

    def _apply(self):
        check_call(
            self._build_parameters('apply'),
            cwd=self._release_path,
            env=self._env()
        )

    @property
    def _plan_path(self):
        if not hasattr(self, '__plan_path'):
            plan_time = datetime.utcnow().strftime('%s')
            self.__plan_path = 'plan-{}'.format(plan_time)
        return self.__plan_path

    @property
    def _platform_config_file_path(self):
        account = self._account_scheme.account_for_environment(
            self._environment
        )
        return 'platform-config/{}/{}.json'.format(
            account, self._boto_session.region_name
        )

    def _build_parameters(
        self, command, secrets_file_path=None, plugin_specific_parameters=None
    ):
        parameters = ['terraform', command]
        if command == 'plan':
            parameters = self._add_plan_parameters(
                parameters, secrets_file_path
            )
            if plugin_specific_parameters:
                parameters += plugin_specific_parameters
        else:
            parameters.append(self._plan_path)
        return parameters

    def _add_plan_parameters(self, parameters, secrets_file_path):
        parameters += [
            'infra',
            '-var', 'component={}'.format(self._component),
            '-var', 'env={}'.format(self._environment),
            '-var', 'aws_region={}'.format(self._boto_session.region_name),
            '-var', 'team={}'.format(self._team),
            '-var', 'version={}'.format(self._version),
            '-var-file', self._platform_config_file_path,
            '-var-file', secrets_file_path,
            '-out', self._plan_path
        ]
        parameters = self._add_environment_config_parameters(parameters)
        return parameters

    def _add_environment_config_parameters(self, parameters):
        environment_config_path = path.join(
            self.CONFIG_BASE_PATH, '{}.json'.format(self._environment)
        )
        global_config_path = path.join(
            self.CONFIG_BASE_PATH, self.GLOBAL_CONFIG_FILE
        )

        if path.exists(environment_config_path):
            parameters += ['-var-file', environment_config_path]

        if path.exists(global_config_path):
            parameters += ['-var-file', global_config_path]

        return parameters

    def _env(self):
        env = os.environ.copy()
        credentials = self._boto_session.get_credentials()
        env.update({
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token,
        })
        return env
