import os
from subprocess import check_call
from time import time

from cdflow_commands.constants import (
    TERRAFORM_BINARY, TERRAFORM_DESTROY_DEFINITION
)


class Destroy:

    def __init__(self, boto_session, component_name, environment, bucket_name):
        self._boto_session = boto_session

    def run(self):
        check_call([
            TERRAFORM_BINARY, 'plan', '-destroy',
            '-var', 'aws_region={}'.format(self._boto_session.region_name),
            '-out', self.plan_path,
            TERRAFORM_DESTROY_DEFINITION,
        ], env=self._env(),
        )

    @property
    def plan_path(self):
        if not hasattr(self, '_plan_path'):
            self._plan_path = 'plan-{}'.format(time())
        return self._plan_path

    def _env(self):
        env = os.environ.copy()
        credentials = self._boto_session.get_credentials()
        env.update({
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token,
        })
        return env
