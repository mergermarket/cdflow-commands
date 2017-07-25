import os
from subprocess import check_call
from time import time

from cdflow_commands.constants import (
    TERRAFORM_BINARY, TERRAFORM_DESTROY_DEFINITION
)


class Destroy:

    def __init__(self, boto_session):
        self._boto_session = boto_session

    def run(self, plan_only=False):
        self._plan()
        if not plan_only:
            self._destroy()

    def _plan(self):
        check_call(
            [
                TERRAFORM_BINARY, 'plan', '-destroy',
                '-var', 'aws_region={}'.format(self._boto_session.region_name),
                '-out', self.plan_path,
                TERRAFORM_DESTROY_DEFINITION,
            ],
            env=self._env(),
            cwd='/cdflow',
        )

    def _destroy(self):
        check_call(
            [
                TERRAFORM_BINARY, 'destroy', '-force',
                '-var', 'aws_region={}'.format(self._boto_session.region_name),
                TERRAFORM_DESTROY_DEFINITION,
            ],
            env=self._env(),
            cwd='/cdflow',
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
