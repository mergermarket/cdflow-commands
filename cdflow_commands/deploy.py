import json
import os
from os import path
from subprocess import check_call
from tempfile import NamedTemporaryFile

from cdflow_commands.secrets import get_secrets


class Deploy:

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

    def run(self, plugin):
        with NamedTemporaryFile() as secrets_file_path:
            json.dump(get_secrets(), secrets_file_path)
            check_call(
                self._build_terraform_parameters('plan', secrets_file_path),
                cwd=self._release_path,
                env=self._env()
            )

    @property
    def _platform_config_file_path(self):
        account = self._account_scheme.account_for_environment(
            self._environment
        )
        return 'platform-config/{}/{}.json'.format(
            account, self._boto_session.region_name
        )

    def _build_terraform_parameters(self, command, secrets_file_path):
        parameters = [
            'terraform', command, 'infra',
            '-var', 'component={}'.format(self._component),
            '-var', 'env={}'.format(self._environment),
            '-var', 'aws_region={}'.format(self._boto_session.region_name),
            '-var', 'team={}'.format(self._team),
            '-var', 'version={}'.format(self._version),
            '-var-file', self._platform_config_file_path,
            '-var-file', secrets_file_path,
        ]
        environment_config_path = 'config/{}.json'.format(self._environment)
        if path.exists(environment_config_path):
            parameters += ['-var-file', environment_config_path]
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
