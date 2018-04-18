import os
from time import time

from cdflow_commands.config import env_with_aws_credetials
from cdflow_commands.constants import (
    TERRAFORM_BINARY, INFRASTRUCTURE_DEFINITIONS_PATH,
)
from cdflow_commands.process import check_call


class Destroy:

    def __init__(self, boto_session, release_path):
        self._boto_session = boto_session
        self._release_path = release_path
        self._infra_path = os.path.join(
            self._release_path, INFRASTRUCTURE_DEFINITIONS_PATH,
        )

    def run(self, plan_only=False):
        self._plan()
        if not plan_only:
            self._destroy()

    def _plan(self):
        check_call(
            [
                TERRAFORM_BINARY, 'plan', '-destroy',
                '-out', self.plan_path,
                self._infra_path,
            ],
            env=env_with_aws_credetials(
                os.environ, self._boto_session
            ),
            cwd=self._release_path,
        )

    def _destroy(self):
        check_call(
            [TERRAFORM_BINARY, 'apply', self.plan_path],
            env=env_with_aws_credetials(
                os.environ, self._boto_session
            ),
            cwd=self._release_path,
        )

    @property
    def plan_path(self):
        if not hasattr(self, '_plan_path'):
            self._plan_path = 'plan-{}'.format(time())
        return self._plan_path
